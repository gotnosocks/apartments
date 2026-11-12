"""Review: queues of cards for Ben to judge one at a time, on a phone or a laptop.

Ben asked on 2026-11-12 for a way to go through the data and flag what looks wrong (labels,
extraction, features, units that should be merged) that is easy enough to use while watching
TV. A producer on thelio writes each queue as `<site root>/review/queues/<queue>/meta.json` and
`cards.jsonl`; this module shows the cards one at a time with their evidence, and appends each
answer to `<site root>/review/decisions.jsonl` under a file lock, as the Tags ledger does. The
newest line for a queue and card is the answer in force, and `undo` clears it.

`export` turns the answers in force into ledger lines for a reviewed PR: a card's proposal for
an applying answer, a set for a value Ben typed, an exclude for an ad he marked as not an
apartment. Each line carries his reading as an `owner` item beside the card's own backing
evidence. Every other answer goes to a findings file for the thread that built the queue.
docs/review-app.md describes the card format and the flow.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from . import tags

FOLDER = "review"
QUEUES = "queues"
DECISIONS = "decisions.jsonl"
EXPORTED = "exported.jsonl"
MEDIA = "media"
# Image hosts the review pages may load from, besides the site itself: StreetEasy's photo and
# floor plan host. The content policy blocks every other host.
IMAGE_HOSTS: tuple[str, ...] = ("photos.zillowstatic.com",)
QUEUE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
CARD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:~+-]{0,199}")
DIGITS = re.compile(r"[0-9]{1,32}")
MAX_NOTE = 1000
# Answers the site adds to every queue, beside the queue's own.
SKIP = "skip"
UNDO = "undo"
PROBLEM = "problem"
OPTION = "option"
BUILT_IN = (SKIP, UNDO, PROBLEM, OPTION)
# The data errors of the Tags vocabulary, offered under "Something else is wrong".
PROBLEMS: tuple[dict[str, str], ...] = tuple(
    item for item in tags.VOCABULARY if item["group"] == "data_error"
)
PROBLEM_CODES = frozenset(item["code"] for item in PROBLEMS)
# The fields Ben can type a value for, with the ledger field each belongs to. Baths are set
# together, as the corrections ledger sets them.
FIX_FIELDS: dict[str, str] = {
    "bedrooms": "Bedrooms",
    "full_baths": "Full baths",
    "half_baths": "Half baths",
    "square_feet": "Size (sq ft)",
    "latest_ask": "Latest ask ($)",
}
WHOLE = ("bedrooms", "full_baths", "half_baths")
POSITIVE = ("square_feet", "latest_ask")
DEFAULT_ANSWERS = (
    {"code": "yes", "label": "Yes", "key": "y", "applies": True},
    {"code": "no", "label": "No", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
)
BLOCK_TYPES = ("facts", "grid", "ads", "text", "links")
# Path segments the review routes use themselves, so no queue or card may take them.
RESERVED = frozenset({"media", "undo", "answers.jsonl"})
# StreetEasy's image sizes: the cards give a medium one, and a tap opens the largest.
SIZE = re.compile(r"-(?:se_medium_500_250|se_large_800_400|p_e|p_f)\.webp$")
FULL = "-se_extra_large_1500_800.webp"

_write_lock = threading.Lock()
_cache_lock = threading.Lock()
_queue_cache: dict[str, tuple[tuple, Queue]] = {}
_decision_cache: dict[str, tuple[tuple, Decisions]] = {}


class BadInput(ValueError):
    """An answer the site refuses, with the reason to show."""


def folder(root: Path) -> Path:
    return Path(root) / FOLDER


def decisions_path(root: Path) -> Path:
    return folder(root) / DECISIONS


def exported_path(root: Path) -> Path:
    return folder(root) / EXPORTED


def utc_now(now: dt.datetime | None = None) -> str:
    stamp = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _version(path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError:
        return (None,)
    return (stat.st_mtime_ns, stat.st_size)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- queues


@dataclasses.dataclass(frozen=True)
class Card:
    id: str
    sha: str
    data: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.data.get("title") or self.id)

    def ads(self) -> list[dict[str, Any]]:
        """Every ad of the card's ads blocks, the first time each appears."""
        seen: dict[str, dict[str, Any]] = {}
        for block in self.data.get("blocks") or []:
            if block.get("type") != "ads":
                continue
            for ad in block.get("ads") or []:
                lid = str(ad.get("listing_id") or "")
                if DIGITS.fullmatch(lid) and lid not in seen:
                    seen[lid] = ad
        return list(seen.values())

    def fixable(self) -> list[dict[str, Any]]:
        """The card's ads with a `record`, which a typed value can be exported for."""
        return [ad for ad in self.ads() if isinstance(ad.get("record"), dict)]

    def option(self, code: str) -> dict[str, Any] | None:
        for item in self.data.get("options") or []:
            if isinstance(item, dict) and item.get("code") == code:
                return item
        return None


@dataclasses.dataclass(frozen=True)
class Queue:
    name: str
    meta: dict[str, Any]
    cards: tuple[Card, ...]
    by_id: dict[str, Card]
    errors: tuple[str, ...]

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.name)

    @property
    def answers(self) -> list[dict[str, Any]]:
        return _answers(self.meta.get("answers"))

    def answer(self, code: str) -> dict[str, Any] | None:
        return next((a for a in self.answers if a["code"] == code), None)


def _answers(raw) -> list[dict[str, Any]]:
    """The queue's own answer buttons: two to four, each with a code and a label."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        code, label = item.get("code"), item.get("label")
        if (
            not isinstance(code, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", code)
            or code in BUILT_IN
            or not isinstance(label, str)
            or any(a["code"] == code for a in out)
        ):
            continue
        key = item.get("key")
        out.append(
            {
                "code": code,
                "label": label,
                # s skips and z undoes on every queue.
                "key": key
                if isinstance(key, str) and len(key) == 1 and key not in "sz"
                else "",
                "applies": item.get("applies") is True,
            }
        )
    return out[:4] if len(out) >= 2 else [dict(a) for a in DEFAULT_ANSWERS]


def _parse_cards(text: str) -> tuple[list[Card], list[str]]:
    cards: list[Card] = []
    errors: list[str] = []
    seen: set[str] = set()
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {number}: not JSON")
            continue
        card_id = data.get("id") if isinstance(data, dict) else None
        if (
            not isinstance(card_id, str)
            or not CARD_ID.fullmatch(card_id)
            or card_id in RESERVED
        ):
            errors.append(f"line {number}: no valid id")
            continue
        if card_id in seen:
            errors.append(f"line {number}: repeats id {card_id}")
            continue
        seen.add(card_id)
        blocks = data.get("blocks")
        data["blocks"] = [
            b
            for b in (blocks if isinstance(blocks, list) else [])
            if isinstance(b, dict) and b.get("type") in BLOCK_TYPES
        ]
        cards.append(Card(card_id, _sha(line), data))
    return cards, errors


def load_queue(root: Path, name: str) -> Queue | None:
    """The queue `name`, cached by its two files' versions; None when it has no files."""
    if not QUEUE_NAME.fullmatch(name or "") or name in RESERVED:
        return None
    base = folder(root) / QUEUES / name
    meta_path, cards_path = base / "meta.json", base / "cards.jsonl"
    key = str(base)
    version = (_version(meta_path), _version(cards_path))
    if (None,) in version:
        return None
    with _cache_lock:
        hit = _queue_cache.get(key)
        if hit and hit[0] == version:
            return hit[1]
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        text = cards_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    cards, errors = _parse_cards(text)
    queue = Queue(name, meta, tuple(cards), {c.id: c for c in cards}, tuple(errors))
    with _cache_lock:
        _queue_cache[key] = (version, queue)
    return queue


def queue_names(root: Path) -> list[str]:
    base = folder(root) / QUEUES
    try:
        names = sorted(p.name for p in base.iterdir() if p.is_dir())
    except OSError:
        return []
    return [n for n in names if QUEUE_NAME.fullmatch(n) and n not in RESERVED]


def load_queues(root: Path) -> list[Queue]:
    queues = [load_queue(root, n) for n in queue_names(root)]
    return [q for q in queues if q is not None]


# ---------------------------------------------------------------- answers


@dataclasses.dataclass(frozen=True)
class Decisions:
    """The answer lines in order, and the answer in force for each queue and card."""

    lines: tuple[dict[str, Any], ...]
    current: dict[tuple[str, str], dict[str, Any]]

    def for_queue(self, queue: str) -> dict[str, dict[str, Any]]:
        return {c: d for (q, c), d in self.current.items() if q == queue}


def _parse_decisions(text: str) -> Decisions:
    lines: list[dict[str, Any]] = []
    current: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(line, dict):
            continue
        queue, card, answer = line.get("queue"), line.get("card"), line.get("answer")
        if not all(isinstance(v, str) for v in (queue, card, answer, line.get("at"))):
            continue
        line["seq"] = len(lines)
        lines.append(line)
        if answer == UNDO:
            current.pop((queue, card), None)
        else:
            current[(queue, card)] = line
    return Decisions(tuple(lines), current)


def load_decisions(root: Path) -> Decisions:
    path = decisions_path(root)
    version = _version(path)
    key = str(path)
    with _cache_lock:
        hit = _decision_cache.get(key)
        if hit and hit[0] == version:
            return hit[1]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    decisions = _parse_decisions(text)
    with _cache_lock:
        _decision_cache[key] = (version, decisions)
    return decisions


def append_line(path: Path, record: dict[str, Any]) -> None:
    """Append `record` as one JSON line under a lock with fsync, after a newline when the file
    ends partway through a line."""
    encoded = (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                size = os.fstat(fd).st_size
                payload = (
                    b"\n" + encoded
                    if size > 0 and os.pread(fd, 1, size - 1) != b"\n"
                    else encoded
                )
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _clean_note(note: str | None) -> str:
    text = " ".join((note or "").split())
    return text[:MAX_NOTE]


def _fix(card: Card, listing_id: str, field: str, value: str) -> dict[str, Any] | None:
    """The typed value as `{"listing_id", "field", "value"}`, or None when nothing was typed."""
    if not (value or "").strip():
        return None
    if field not in FIX_FIELDS:
        raise BadInput("Choose which value to fix.")
    ads = {str(ad["listing_id"]) for ad in card.ads()}
    if listing_id not in ads:
        raise BadInput("Choose which ad the value is for.")
    try:
        number = float(value.replace(",", "").replace("$", "").strip())
    except ValueError:
        raise BadInput("The value must be a number.") from None
    if not (0 <= number < 1e7):
        raise BadInput("The value is out of range.")
    if field in WHOLE and number != int(number):
        raise BadInput(f"{FIX_FIELDS[field]} takes a whole number.")
    if field in POSITIVE and number <= 0:
        raise BadInput(f"{FIX_FIELDS[field]} takes a value above 0.")
    return {
        "listing_id": listing_id,
        "field": field,
        "value": int(number) if field in WHOLE else number,
    }


def record_answer(
    root: Path,
    queue: Queue,
    card: Card,
    answer: str,
    *,
    note: str | None = "",
    problems: Iterable[str] = (),
    fix_listing: str = "",
    fix_field: str = "",
    fix_value: str = "",
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Check one answer against the queue and card, and append it."""
    option = None
    if answer.startswith(f"{OPTION}:"):
        option = answer.split(":", 1)[1]
        if card.option(option) is None:
            raise BadInput("That choice is not on this card.")
        answer = OPTION
    elif answer not in (SKIP, PROBLEM) and queue.answer(answer) is None:
        raise BadInput("That answer is not offered here.")
    chosen: list[str] = []
    fix = None
    if answer == PROBLEM:
        chosen = sorted({p for p in problems if p in PROBLEM_CODES})
        fix = _fix(card, fix_listing, fix_field, fix_value)
        if not chosen and fix is None and not _clean_note(note):
            raise BadInput("Pick what is wrong, type the right value, or add a note.")
    record = {
        "queue": queue.name,
        "card": card.id,
        "answer": answer,
        "option": option,
        "problems": chosen,
        "fix": fix,
        "note": _clean_note(note),
        "at": utc_now(now),
        "card_sha": card.sha,
    }
    append_line(decisions_path(root), record)
    return record


def undo_last(
    root: Path,
    queue: Queue,
    card: str | None = None,
    now: dt.datetime | None = None,
) -> str | None:
    """Clear the answer in force for `card`, or without one the newest answer in force in the
    queue; the card it was for, or None when there was none to clear. The toast names its
    card, so a stale toast never clears another card's answer."""
    decisions = load_decisions(root)
    in_force = [
        d
        for (q, c), d in decisions.current.items()
        if q == queue.name and (card is None or c == card)
    ]
    if not in_force:
        return None
    last = max(in_force, key=lambda d: d["seq"])
    append_line(
        decisions_path(root),
        {"queue": queue.name, "card": last["card"], "answer": UNDO, "at": utc_now(now)},
    )
    return last["card"]


def progress(queue: Queue, answered: dict[str, dict[str, Any]]) -> dict[str, int]:
    done = sum(
        1 for c in queue.cards if c.id in answered and answered[c.id]["answer"] != SKIP
    )
    skipped = sum(
        1 for c in queue.cards if c.id in answered and answered[c.id]["answer"] == SKIP
    )
    total = len(queue.cards)
    return {
        "total": total,
        "done": done,
        "skipped": skipped,
        "left": total - done - skipped,
    }


def next_card(
    queue: Queue, answered: dict[str, dict[str, Any]], after: str | None = None
) -> Card | None:
    """The first card with no answer, in queue order; then the skipped cards, oldest skip
    first. `after` leaves out that card, so a skip moves on."""
    for card in queue.cards:
        if card.id not in answered and card.id != after:
            return card
    skipped = sorted(
        (d["seq"], c)
        for c, d in answered.items()
        if d["answer"] == SKIP and c in queue.by_id and c != after
    )
    return queue.by_id[skipped[0][1]] if skipped else None


# ---------------------------------------------------------------- export


def number_text(value: float) -> str:
    """A typed value as text: whole numbers with thousands separators, others as given."""
    value = float(value)
    return f"{value:,.0f}" if value == int(value) else f"{value:,}"


def owner_item(reader: str, day: str, label: str, note: str, where: str) -> dict:
    detail = f"{reader}'s reading in the review app on {day}: {label}."
    if note:
        detail += f" Note: {note}"
    return {"kind": "owner", "detail": f"{detail} Card {where}."}


def _set_line(card: Card, fix: dict[str, Any]) -> dict[str, Any] | None:
    """A corrections ledger set for the typed value, or None when the ad has no record."""
    ad = next(
        (a for a in card.fixable() if str(a["listing_id"]) == fix["listing_id"]), None
    )
    if ad is None:
        return None
    record = ad["record"]
    field, value = fix["field"], fix["value"]
    if field in ("full_baths", "half_baths"):
        other = "half_baths" if field == "full_baths" else "full_baths"
        if other not in record:
            return None
        values = {field: value, other: record[other]}
        values = {k: values[k] for k in ("full_baths", "half_baths")}
        if values["full_baths"] is None or values["half_baths"] is None:
            return None
    else:
        values = {field: value}
    if any(k not in record for k in values):
        return None
    when = {k: record[k] for k in values}
    if isinstance(record.get("period"), str):
        when = {"period": record["period"], **when}
    return {
        "change": "set",
        "listing_id": fix["listing_id"],
        "set": values,
        "when": when,
    }


def _exclude_line(card: Card, problems: list[str]) -> dict[str, Any] | None:
    """An exclude of the card's own ad, for an ad Ben marked as not an apartment."""
    lid = str(card.data.get("listing_id") or "")
    if "not_apartment" not in problems or not DIGITS.fullmatch(lid):
        return None
    line: dict[str, Any] = {
        "change": "exclude",
        "listing_id": lid,
        "reason": "not_apartment",
    }
    ad = next((a for a in card.ads() if str(a["listing_id"]) == lid), None)
    if ad and isinstance(ad.get("record"), dict):
        period = ad["record"].get("period")
        if isinstance(period, str):
            line["when"] = {"period": period}
    return line


def joined_pages(ledger: Path) -> set[tuple[str, str]]:
    """The (building, unit) pages of the joins in force in the unit ledger's files: joins no
    later retract undoes. The unit ledger lets a page take part in one join at most."""
    joins: dict[str, list[tuple[str, str]]] = {}
    retracted: set[str] = set()
    for path in sorted((ledger / "units").glob("*.ndjson"), key=lambda p: p.name):
        for text in path.read_text(encoding="utf-8").split("\n"):
            if not text.strip():
                continue
            try:
                line = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(line, dict):
                continue
            if line.get("change") == "retract":
                retracted.add(str(line.get("entry")))
            elif line.get("change") == "join_units":
                entry = hashlib.sha256(text.encode()).hexdigest()[:16]
                building = str(line.get("building"))
                joins[entry] = [(building, str(u)) for u in line.get("units") or []]
    return {
        page
        for entry, pages in joins.items()
        if entry not in retracted
        for page in pages
    }


def plan_export(
    root: Path, reader: str, day: str, taken: set[tuple[str, str]] | None = None
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """The answers in force not yet exported, as (corrections lines, unit lines, findings,
    exported records). `taken` holds the pages already in a join in force; a join that would
    put one of them in a second join is not written, and goes to the findings."""
    taken = set(taken or ())
    decisions = load_decisions(root)
    done = _exported_keys(root)
    corrections: list[dict] = []
    units: list[dict] = []
    findings: list[dict] = []
    marks: list[dict] = []
    queues = {q.name: q for q in load_queues(root)}
    for (queue_name, card_id), decision in sorted(
        decisions.current.items(), key=lambda kv: kv[1]["seq"]
    ):
        key = (queue_name, card_id, decision["at"])
        if decision["answer"] == SKIP or key in done:
            continue
        queue = queues.get(queue_name)
        card = queue.by_id.get(card_id) if queue else None
        where = f"{queue_name}/{card_id}"
        source = f"review app {where} {decision['at']}"
        note = decision.get("note") or ""
        written: list[tuple[str, dict]] = []
        if card is None:
            findings.append({**_finding(decision), "missing_card": True})
            marks.append(_mark(decision, []))
            continue
        answer = queue.answer(decision["answer"])
        proposal = None
        label = answer["label"] if answer else decision["answer"]
        if decision["answer"] == OPTION:
            option = card.option(decision.get("option") or "")
            proposal = option.get("proposal") if option else None
            label = option.get("label", decision.get("option")) if option else label
        elif answer and answer["applies"]:
            proposal = card.data.get("proposal")
        if isinstance(proposal, dict) and isinstance(proposal.get("line"), dict):
            evidence = [
                e for e in proposal.get("evidence") or [] if isinstance(e, dict)
            ]
            summary = proposal.get("summary") or label
            item = owner_item(reader, day, f"{label} ({summary})", note, where)
            line = {
                **proposal["line"],
                "evidence": [*evidence, item],
                "decided": day,
                "source": source,
            }
            kind = "units" if proposal.get("ledger") == "units" else "corrections"
            written.append((kind, line))
        if decision["answer"] == PROBLEM:
            problems = decision.get("problems") or []
            fix = decision.get("fix")
            names = ", ".join(tags.BY_CODE[p]["label"] for p in problems) or "a problem"
            if fix:
                line = _set_line(card, fix)
                if line:
                    text = f"{FIX_FIELDS[fix['field']]} is {number_text(fix['value'])}"
                    item = owner_item(reader, day, text, note, where)
                    written.append(
                        (
                            "corrections",
                            {
                                **line,
                                "evidence": [item],
                                "decided": day,
                                "source": source,
                            },
                        )
                    )
            line = _exclude_line(card, problems)
            if line:
                item = owner_item(reader, day, names, note, where)
                written.append(
                    (
                        "corrections",
                        {**line, "evidence": [item], "decided": day, "source": source},
                    )
                )
        if written and card.sha != decision.get("card_sha"):
            # The card changed after the answer, so its proposal or records may not be what
            # Ben saw: no line is written, and the finding asks for a new answer.
            written = []
        clash = False
        for _, line in written:
            if line.get("change") == "join_units":
                pages = {(line.get("building"), u) for u in line.get("units") or []}
                clash = clash or bool(pages & taken)
        if clash:
            written = []
        for _, line in written:
            if line.get("change") == "join_units":
                taken.update((line.get("building"), u) for u in line.get("units") or [])
        for kind, line in written:
            (units if kind == "units" else corrections).append(line)
        if not written or decision["answer"] == PROBLEM:
            finding = _finding(decision, card)
            if clash:
                finding["page_already_joined"] = True
            findings.append(finding)
        marks.append(_mark(decision, [line for _, line in written]))
    return corrections, units, findings, marks


def _finding(decision: dict, card: Card | None = None) -> dict:
    out = {k: v for k, v in decision.items() if k != "seq"}
    if card is not None:
        out["title"] = card.title
        if card.data.get("listing_id"):
            out["listing_id"] = card.data["listing_id"]
        if card.sha != decision.get("card_sha"):
            out["card_changed"] = True
    return out


def _mark(decision: dict, lines: list[dict]) -> dict:
    return {
        "queue": decision["queue"],
        "card": decision["card"],
        "at": decision["at"],
        "lines": len(lines),
    }


def _exported_keys(root: Path) -> set[tuple[str, str, str]]:
    try:
        text = exported_path(root).read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()
    keys = set()
    for raw in text.split("\n"):
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(line, dict):
            keys.add((line.get("queue"), line.get("card"), line.get("at")))
    return keys


def _free_name(folder_: Path, stem: str, suffix: str) -> Path:
    """`<stem>-01<suffix>`, or the next free number, so a later export of a day sorts after
    an earlier one, as the ledger reads its files in order of name."""
    n = 1
    while (path := folder_ / f"{stem}-{n:02d}{suffix}").exists():
        n += 1
    return path


def _dump(line: dict) -> str:
    return json.dumps(line, ensure_ascii=False, sort_keys=True)


def export(
    root: Path,
    ledger: Path,
    *,
    reader: str = "Ben",
    day: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write the ledger lines and findings of the answers not yet exported."""
    day = day or dt.date.today().isoformat()
    corrections, units, findings, marks = plan_export(
        root, reader, day, joined_pages(ledger)
    )
    stem = f"{day}-review-app"
    out: dict[str, Any] = {
        "corrections": len(corrections),
        "units": len(units),
        "findings": len(findings),
        "answers": len(marks),
        "files": [],
    }
    if dry_run or not marks:
        return out
    for lines, base in ((corrections, ledger), (units, ledger / "units")):
        if not lines:
            continue
        base.mkdir(parents=True, exist_ok=True)
        path = _free_name(base, stem, ".ndjson")
        path.write_text("".join(_dump(line) + "\n" for line in lines), encoding="utf-8")
        out["files"].append(str(path))
    if findings:
        path = _free_name(folder(root), f"findings-{day}", ".jsonl")
        path.write_text(
            "".join(_dump(line) + "\n" for line in findings), encoding="utf-8"
        )
        out["files"].append(str(path))
    for mark in marks:
        append_line(exported_path(root), {**mark, "exported": utc_now()})
    return out


# ---------------------------------------------------------------- pages


def _same_origin() -> bool:
    return tags._same_origin()


def _safe_media(name: str) -> bool:
    parts = Path(name).parts
    return bool(parts) and not any(p in ("..", "") or p.startswith(".") for p in parts)


def image_url(url: Any) -> str | None:
    """`url` when the page may load it: a review media path or an allowed host over https."""
    if not isinstance(url, str):
        return None
    if url.startswith(f"/{FOLDER}/{MEDIA}/") and _safe_media(
        url[len(f"/{FOLDER}/{MEDIA}/") :]
    ):
        return url
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname in IMAGE_HOSTS:
        return url
    return None


def full_image(url: str) -> str:
    """The largest size of a StreetEasy image, for a tap on its thumbnail."""
    return SIZE.sub(FULL, url) if url.startswith("https://") else url


def link_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    return url if parts.scheme in ("http", "https") and parts.netloc else None


def _wants_json() -> bool:
    return "application/json" in (request.headers.get("Accept") or "").lower()


def _error(code: int, message: str):
    if _wants_json():
        return jsonify({"error": message}), code
    return render_template("error.html", code=code, message=message), code


def register(app: Flask, root_fn: Callable[[], Path]) -> None:
    """Register the `/review` pages."""

    app.jinja_env.globals["review_image"] = image_url
    app.jinja_env.globals["review_link"] = link_url
    app.jinja_env.globals["review_full"] = full_image

    def allow_images():
        g.img_hosts = IMAGE_HOSTS

    def queue_or_404(name: str) -> Queue:
        queue = load_queue(root_fn(), name)
        if queue is None:
            abort(404)
        return queue

    @app.get("/review")
    def review_home():
        root = root_fn()
        decisions = load_decisions(root)
        rows = []
        for queue in load_queues(root):
            answered = decisions.for_queue(queue.name)
            rows.append({"queue": queue, "progress": progress(queue, answered)})
        recent = [d for d in reversed(decisions.lines) if d["answer"] != UNDO][:10]
        return render_template("review_home.html", rows=rows, recent=recent)

    @app.get("/review/<name>")
    def review_queue(name: str):
        queue = queue_or_404(name)
        answered = load_decisions(root_fn()).for_queue(name)
        card = next_card(queue, answered)
        if card is None:
            last = request.args.get("saved")
            saved = None
            if last in answered and last in queue.by_id:
                saved = {"card": queue.by_id[last], "decision": answered[last]}
            return render_template(
                "review_card.html",
                queue=queue,
                card=None,
                progress=progress(queue, answered),
                saved=saved,
                answer_label=lambda d: _answer_label(queue, saved["card"], d),
                current=None,
                next_url=None,
            )
        return redirect(
            url_for(
                "review_card",
                name=name,
                card_id=card.id,
                saved=request.args.get("saved") or None,
            ),
            code=303,
        )

    @app.get("/review/<name>/<card_id>")
    def review_card(name: str, card_id: str):
        queue = queue_or_404(name)
        card = queue.by_id.get(card_id)
        if card is None:
            abort(404)
        root = root_fn()
        decisions = load_decisions(root)
        answered = decisions.for_queue(name)
        saved = None
        last = request.args.get("saved")
        if (
            last
            and last in answered
            and (last != card.id or answered[last]["answer"] == SKIP)
        ):
            saved = {"card": queue.by_id.get(last), "decision": answered[last]}
        upcoming = next_card(queue, {**answered, card.id: {"answer": "x"}})
        allow_images()
        return render_template(
            "review_card.html",
            queue=queue,
            card=card,
            progress=progress(queue, answered),
            saved=saved,
            current=answered.get(card.id),
            next_url=url_for("review_card", name=name, card_id=upcoming.id)
            if upcoming
            else None,
            problems=PROBLEMS,
            fix_fields=FIX_FIELDS,
            answer_label=lambda d: _answer_label(queue, card, d),
        )

    @app.post("/review/<name>/<card_id>")
    def review_answer(name: str, card_id: str):
        if not _same_origin():
            return _error(403, "Cross-origin answers are not accepted.")
        queue = queue_or_404(name)
        card = queue.by_id.get(card_id)
        if card is None:
            abort(404)
        root = root_fn()
        form = request.form
        try:
            saved = record_answer(
                root,
                queue,
                card,
                form.get("answer", ""),
                note=form.get("note", ""),
                problems=form.getlist("problem"),
                fix_listing=form.get("fix_listing", ""),
                fix_field=form.get("fix_field", ""),
                fix_value=form.get("fix_value", ""),
            )
        except BadInput as err:
            return _error(400, str(err))
        answered = load_decisions(root).for_queue(name)
        after = card.id if saved["answer"] == SKIP else None
        upcoming = next_card(queue, answered, after=after)
        if _wants_json():
            return jsonify(
                {
                    "saved": saved,
                    "next": url_for("review_card", name=name, card_id=upcoming.id)
                    if upcoming
                    else None,
                }
            )
        if upcoming is None:
            return redirect(url_for("review_queue", name=name, saved=card.id), code=303)
        return redirect(
            url_for("review_card", name=name, card_id=upcoming.id, saved=card.id),
            code=303,
        )

    @app.post("/review/<name>/undo")
    def review_undo(name: str):
        if not _same_origin():
            return _error(403, "Cross-origin answers are not accepted.")
        queue = queue_or_404(name)
        target = request.form.get("card") or None
        card_id = undo_last(root_fn(), queue, target)
        if target and card_id is None:
            card_id = target
        if card_id and card_id in queue.by_id:
            return redirect(
                url_for("review_card", name=name, card_id=card_id), code=303
            )
        return redirect(url_for("review_queue", name=name), code=303)

    @app.get("/review/answers.jsonl")
    def review_answers_jsonl():
        decisions = load_decisions(root_fn())
        body = "".join(
            json.dumps({k: v for k, v in d.items() if k != "seq"}, ensure_ascii=False)
            + "\n"
            for d in decisions.lines
        )
        return Response(body, mimetype="application/x-ndjson")

    @app.get("/review/media/<path:name>")
    def review_media(name: str):
        if not _safe_media(name):
            abort(404)
        return send_from_directory(folder(root_fn()) / MEDIA, name, max_age=86400)


def _answer_label(queue: Queue, card: Card, decision: dict | None) -> str:
    if not decision:
        return ""
    code = decision["answer"]
    if code == SKIP:
        return "Skipped"
    if code == OPTION:
        option = card.option(decision.get("option") or "") if card else None
        return option.get("label", "") if option else str(decision.get("option"))
    if code == PROBLEM:
        names = [tags.BY_CODE[p]["label"] for p in decision.get("problems") or []]
        fix = decision.get("fix")
        if fix:
            names.append(
                f"{FIX_FIELDS.get(fix['field'], fix['field'])} {number_text(fix['value'])}"
            )
        return "Problem: " + (", ".join(names) or "see note")
    answer = queue.answer(code)
    return answer["label"] if answer else code


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m apartments.site.review")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write ledger lines for the answers in force")
    exp.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ.get("SITE_ROOT", "/data1/apartments/site")),
    )
    exp.add_argument("--ledger", type=Path, default=Path("pipeline/ledger"))
    exp.add_argument("--reader", default="Ben")
    exp.add_argument("--day", default=None, help="the day of the decision, YYYY-MM-DD")
    exp.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.day):
        parser.error("--day takes YYYY-MM-DD")
    result = export(
        args.root, args.ledger, reader=args.reader, day=args.day, dry_run=args.dry_run
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
