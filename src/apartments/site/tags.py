"""Append-only tag ledger for marking deals, data errors and unmodeled factors.

Readers tag an ad as a confirmed deal, a specific data error, or a low or high ask
explained by something the model lacks. `append` writes one JSON line per update to
`<site root>/tags/tags.jsonl` under a file lock with `fsync`, capturing a snapshot
of the ad from `diagnostics/` when available. The newest line for a `listing_id`
sets its active tag, and `"clear"` removes it. The parsed ledger is cached by the
file's `(mtime_ns, size)` so `/deals`, `/listings/<id>` and `/tags` read tags in
memory until a new line is appended.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import fcntl
import io
import json
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import facts

FOLDER = "tags"
FILENAME = "tags.jsonl"
CLEAR = "clear"
MAX_NOTE = 500
MAX_IDS = 300
DIGIT_ID = re.compile(r"[0-9]{1,32}")

GROUPS: tuple[tuple[str, str], ...] = (
    ("deal", "Deal"),
    ("data_error", "Data error"),
    ("unmodeled", "Unmodeled"),
)
GROUP_LABELS: dict[str, str] = dict(GROUPS)
GROUP_ALIASES: dict[str, str] = {
    "deal": "deal",
    "data_error": "data_error",
    "data error": "data_error",
    "unmodeled": "unmodeled",
}
RULED_OUT_GROUPS: frozenset[str] = frozenset({"data_error", "unmodeled"})

VOCABULARY: tuple[dict[str, str], ...] = (
    {
        "code": "deal",
        "label": "Real deal",
        "group": "deal",
        "meaning": "Looks like a real deal after reading the ad.",
    },
    {
        "code": "wrong_beds",
        "label": "Wrong bedrooms",
        "group": "data_error",
        "meaning": "Recorded bedrooms do not match the ad or floor plan.",
    },
    {
        "code": "wrong_price",
        "label": "Wrong price",
        "group": "data_error",
        "meaning": "Recorded ask misreads the rent, free months or lease term.",
    },
    {
        "code": "wrong_unit",
        "label": "Wrong unit or building",
        "group": "data_error",
        "meaning": "Ad is matched to the wrong unit or building.",
    },
    {
        "code": "not_apartment",
        "label": "Not an apartment",
        "group": "data_error",
        "meaning": "Room, commercial unit, parking or storage rather than an apartment.",
    },
    {
        "code": "restricted",
        "label": "Eligibility restricted",
        "group": "data_error",
        "meaning": "Income-restricted or other eligibility rule applies.",
    },
    {
        "code": "duplicate",
        "label": "Duplicate",
        "group": "data_error",
        "meaning": "Duplicate listing for the same apartment and offer.",
    },
    {
        "code": "data_other",
        "label": "Other data error",
        "group": "data_error",
        "meaning": "Another error in the recorded facts for this ad.",
    },
    {
        "code": "condition",
        "label": "Condition",
        "group": "unmodeled",
        "meaning": "Wear, dated finishes or a fresh renovation explains the ask.",
    },
    {
        "code": "size_layout",
        "label": "Size or layout",
        "group": "unmodeled",
        "meaning": "Room size, layout, basement level or ceiling height explains the ask.",
    },
    {
        "code": "light_view_noise",
        "label": "Light, view or noise",
        "group": "unmodeled",
        "meaning": "Airshaft light, street or train noise, or an open view explains the ask.",
    },
    {
        "code": "short_term",
        "label": "Short lease or furnished",
        "group": "unmodeled",
        "meaning": "Short lease, sublet or furnished offer.",
    },
    {
        "code": "fees_concession",
        "label": "Fees or concession",
        "group": "unmodeled",
        "meaning": "Broker fee or concession terms are not captured in the net ask.",
    },
    {
        "code": "unmodeled_other",
        "label": "Other unmodeled",
        "group": "unmodeled",
        "meaning": "Another property of the apartment or lease that the model lacks.",
    },
)

BY_CODE: dict[str, dict[str, str]] = {item["code"]: item for item in VOCABULARY}
GROUPED_VOCABULARY: tuple[tuple[str, str, tuple[dict[str, str], ...]], ...] = tuple(
    (
        group_code,
        group_label,
        tuple(item for item in VOCABULARY if item["group"] == group_code),
    )
    for group_code, group_label in GROUPS
)

SNAPSHOT_KEYS = (
    "address",
    "unit",
    "building",
    "bedrooms",
    "ask",
    "model_median",
    "miss",
    "flags",
    "source",
    "day",
)

CSV_COLUMNS = (
    "listing_id",
    "tag",
    "group",
    "label",
    "note",
    "at",
    "source",
    "day",
    "building",
    "address",
    "unit",
    "bedrooms",
    "ask",
    "model_median",
    "miss",
    "flags",
)


class BadInput(ValueError):
    """Form or query input that violates the tag ledger contract."""


@dataclasses.dataclass(frozen=True)
class Ledger:
    """Parsed view of `tags.jsonl`."""

    lines: tuple[dict[str, Any], ...]
    raw_lines: tuple[dict[str, Any], ...]
    current: dict[str, dict[str, Any]]
    raw_current: dict[str, dict[str, Any]]
    by_listing: dict[str, tuple[dict[str, Any], ...]]


EMPTY_LEDGER = Ledger(
    lines=(),
    raw_lines=(),
    current={},
    raw_current={},
    by_listing={},
)

_write_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: dict[tuple[str, int, int], Ledger] = {}


def ledger_path(root: Path) -> Path:
    """Path to `<root>/tags/tags.jsonl`."""
    return Path(root) / FOLDER / FILENAME


def _clean_note(note: str | None) -> str:
    if not note:
        return ""
    collapsed = re.sub(r"[\x00-\x1f\x7f]+", " ", str(note)).strip()
    return collapsed[:MAX_NOTE]


def _validate(listing_id: str | None, tag: str | None) -> tuple[str, str]:
    lid = "" if listing_id is None else str(listing_id).strip()
    if not DIGIT_ID.fullmatch(lid):
        raise BadInput("Listing id must be digits.")
    code = "" if tag is None else str(tag).strip()
    if code != CLEAR and code not in BY_CODE:
        raise BadInput(f"Unknown tag: {code!r}.")
    return lid, code


def _enrich_line(raw: dict[str, Any]) -> dict[str, Any] | None:
    lid = str(raw.get("listing_id") or "").strip()
    code = str(raw.get("tag") or "").strip()
    if not DIGIT_ID.fullmatch(lid):
        return None
    if code == CLEAR:
        label: str | None = "Cleared"
        group: str | None = None
        meaning = ""
    elif code in BY_CODE:
        spec = BY_CODE[code]
        label = spec["label"]
        group = spec["group"]
        meaning = spec["meaning"]
    else:
        return None
    raw_flags = raw.get("flags")
    flag_codes = (
        [str(f) for f in raw_flags if isinstance(f, str)]
        if isinstance(raw_flags, list)
        else []
    )
    return {
        "listing_id": lid,
        "tag": code,
        "label": label,
        "group": group,
        "group_label": GROUP_LABELS.get(group or "", ""),
        "meaning": meaning,
        "note": _clean_note(raw.get("note")),
        "at": str(raw.get("at") or ""),
        "address": raw.get("address"),
        "unit": raw.get("unit"),
        "building": raw.get("building"),
        "bedrooms": raw.get("bedrooms"),
        "ask": raw.get("ask"),
        "model_median": raw.get("model_median"),
        "miss": raw.get("miss"),
        "flags": flag_codes,
        "flag_items": facts.flag_items(flag_codes),
        "source": raw.get("source"),
        "day": raw.get("day"),
    }


def _parse_ledger(content: str) -> Ledger:
    lines: list[dict[str, Any]] = []
    raw_lines: list[dict[str, Any]] = []
    active: dict[str, dict[str, Any]] = {}
    raw_active: dict[str, dict[str, Any]] = {}
    per_listing: dict[str, list[dict[str, Any]]] = {}

    for text in content.splitlines():
        stripped = text.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        enriched = _enrich_line(obj)
        if enriched is None:
            continue
        lid = enriched["listing_id"]
        lines.append(enriched)
        raw_lines.append(obj)
        per_listing.setdefault(lid, []).append(enriched)
        # Re-insert after pop so dict order tracks the latest update per listing.
        active.pop(lid, None)
        raw_active.pop(lid, None)
        if enriched["tag"] != CLEAR:
            active[lid] = enriched
            raw_active[lid] = obj

    newest_first = dict(reversed(list(active.items())))
    raw_newest_first = dict(reversed(list(raw_active.items())))
    frozen_by_listing = {k: tuple(v) for k, v in per_listing.items()}
    return Ledger(
        lines=tuple(lines),
        raw_lines=tuple(raw_lines),
        current=newest_first,
        raw_current=raw_newest_first,
        by_listing=frozen_by_listing,
    )


def load_ledger(root: Path) -> Ledger:
    """Read and cache `<root>/tags/tags.jsonl` keyed by `(mtime_ns, size)`."""
    path = ledger_path(root)
    try:
        stat = path.stat()
    except OSError:
        return EMPTY_LEDGER
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return EMPTY_LEDGER
    parsed = _parse_ledger(content)
    with _cache_lock:
        if len(_cache) >= 8:
            _cache.clear()
        _cache[key] = parsed
    return parsed


def current_tags(root: Path) -> dict[str, dict[str, Any]]:
    """Map of `listing_id` to its current active tag dict (newest first)."""
    return load_ledger(root).current


def for_listing(
    root: Path, listing_id: str | None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Current tag (or `None`) and earlier ledger lines (newest first) for one ad."""
    lid = "" if listing_id is None else str(listing_id).strip()
    if not lid:
        return None, []
    ledger = load_ledger(root)
    history = list(ledger.by_listing.get(lid, ()))
    if not history:
        return None, []
    active = ledger.current.get(lid)
    earlier = history[:-1] if active is not None else history
    earlier.reverse()
    return active, earlier


def _snapshot(root: Path, listing_id: str) -> dict[str, Any]:
    """Diagnostic fields recorded alongside a tag when `diagnostics/` has the ad."""
    try:
        diag = facts.load(Path(root))
    except facts.Refused:
        diag = None
    if diag is None:
        return {}
    ad = diag.ad(listing_id)
    if ad is None:
        return {}
    flags = [
        item["code"]
        for item in (ad.get("flags") or [])
        if isinstance(item, dict) and item.get("code")
    ]
    return {
        "address": ad.get("address"),
        "unit": ad.get("unit"),
        "building": ad.get("building"),
        "bedrooms": ad.get("bedrooms"),
        "ask": ad.get("ask"),
        "model_median": ad.get("model_median"),
        "miss": ad.get("miss"),
        "flags": flags,
        "source": ad.get("source"),
        "day": ad.get("day"),
    }


def append(
    root: Path,
    listing_id: str,
    tag: str,
    note: str | None = "",
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Validate and append one tag line to `<root>/tags/tags.jsonl` with lock and fsync."""
    lid, code = _validate(listing_id, tag)
    cleaned_note = _clean_note(note)
    stamp_dt = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    at = stamp_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    snap = _snapshot(Path(root), lid)

    record: dict[str, Any] = {
        "listing_id": lid,
        "tag": code,
        "note": cleaned_note,
        "at": at,
    }
    if snap:
        record.update(snap)

    encoded = (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    path = ledger_path(root)
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                view = memoryview(encoded)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    spec = BY_CODE.get(code)
    return {
        "listing_id": lid,
        "tag": code,
        "label": spec["label"] if spec else None,
        "group": spec["group"] if spec else None,
        "note": cleaned_note,
        "at": at,
    }


def _norm_host(netloc: str, scheme: str) -> str:
    host = netloc.strip().lower()
    if scheme == "http" and host.endswith(":80"):
        return host[:-3]
    if scheme == "https" and host.endswith(":443"):
        return host[:-4]
    return host


def _same_origin() -> bool:
    """False when `Origin` or `Referer` is present and names a different host."""
    req_host = _norm_host(request.host, request.scheme)
    for header in ("Origin", "Referer"):
        raw = request.headers.get(header)
        if raw is None:
            continue
        parsed = urlsplit(raw.strip())
        if (
            not parsed.scheme
            or not parsed.netloc
            or _norm_host(parsed.netloc, parsed.scheme) != req_host
        ):
            return False
    return True


def _safe_next(target: str | None, fallback: str) -> str:
    """Return `target` when it is a local path on this host, else `fallback`."""
    if not target:
        return fallback
    text = target.strip()
    if (
        not text.startswith("/")
        or text.startswith("//")
        or "\\" in text
        or "\r" in text
        or "\n" in text
    ):
        return fallback
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc:
        return fallback
    return text


def _wants_json() -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept


def _error_response(code: int, message: str):
    if _wants_json():
        return jsonify({"error": message}), code
    return render_template("error.html", code=code, message=message, meta=None), code


def _public_tag(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "listing_id": entry["listing_id"],
        "tag": entry["tag"],
        "label": entry["label"],
        "group": entry["group"],
        "note": entry["note"],
        "at": entry["at"],
    }


def register(app: Flask, root_fn: Callable[[], Path]) -> None:
    """Register `/tags`, `/tags/for`, `/tags.csv`, `/tags.jsonl` and `tag_form`."""
    app.jinja_env.globals["TAG_GROUPS"] = GROUPED_VOCABULARY

    def tag_form(
        listing_id: str,
        current: dict[str, Any] | None = None,
        next_url: str = "",
        compact: bool = False,
    ):
        macro = app.jinja_env.get_template("_tags.html").module.tag_form
        return macro(listing_id, current, next_url, compact=compact)

    app.jinja_env.globals["tag_form"] = tag_form

    @app.post("/tags")
    def tags_post():
        if not _same_origin():
            return _error_response(
                403, "Cross-origin tag submissions are not accepted."
            )
        listing_id = request.form.get("listing_id")
        tag = request.form.get("tag")
        note = request.form.get("note", "")
        try:
            saved = append(root_fn(), listing_id or "", tag or "", note)
        except BadInput as err:
            return _error_response(400, str(err))
        if _wants_json():
            return jsonify(saved)
        fallback = url_for("listing", key=saved["listing_id"])
        return redirect(_safe_next(request.form.get("next"), fallback), code=303)

    @app.get("/tags/for")
    def tags_for():
        raw_parts: list[str] = []
        for chunk in request.args.getlist("ids"):
            raw_parts.extend(part.strip() for part in chunk.split(","))
        tokens = [t for t in raw_parts if t]
        if len(tokens) > MAX_IDS:
            return jsonify({"error": f"At most {MAX_IDS} ids per request."}), 400
        ids: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if not DIGIT_ID.fullmatch(token):
                return jsonify({"error": "Listing ids must be digits."}), 400
            if token not in seen:
                seen.add(token)
                ids.append(token)
        active = current_tags(root_fn())
        matched = {lid: _public_tag(active[lid]) for lid in ids if lid in active}
        return jsonify(
            {
                "tags": matched,
                "vocabulary": list(VOCABULARY),
                "groups": [{"code": k, "label": v} for k, v in GROUPS],
            }
        )

    @app.get("/tags")
    def tags_ledger():
        ledger = load_ledger(root_fn())
        all_current = list(ledger.current.values())

        group_counts = {k: 0 for k, _ in GROUPS}
        tag_counts = {item["code"]: 0 for item in VOCABULARY}
        for entry in all_current:
            grp = entry.get("group")
            code = entry.get("tag")
            if grp in group_counts:
                group_counts[grp] += 1
            if code in tag_counts:
                tag_counts[code] += 1

        raw_group = (request.args.get("group") or "").strip().lower()
        chosen_group = GROUP_ALIASES.get(raw_group)
        raw_tag = (request.args.get("tag") or "").strip()
        chosen_tag = raw_tag if raw_tag in BY_CODE else None

        rows = [
            entry
            for entry in all_current
            if (chosen_group is None or entry.get("group") == chosen_group)
            and (chosen_tag is None or entry.get("tag") == chosen_tag)
        ]

        def filter_url(group: str | None = None, tag: str | None = None) -> str:
            params: dict[str, str] = {}
            if group:
                params["group"] = group
            if tag:
                params["tag"] = tag
            base = url_for("tags_ledger")
            return f"{base}?{urlencode(params)}" if params else base

        return render_template(
            "tags.html",
            meta=None,
            section="estimates",
            rows=rows,
            total_current=len(all_current),
            total_lines=len(ledger.lines),
            groups=[
                {
                    "code": code,
                    "label": label,
                    "count": group_counts[code],
                }
                for code, label in GROUPS
            ],
            vocab_counts=[
                item | {"count": tag_counts[item["code"]]} for item in VOCABULARY
            ],
            chosen_group=chosen_group,
            chosen_tag=chosen_tag,
            filter_url=filter_url,
        )

    @app.get("/tags.jsonl")
    def tags_jsonl():
        ledger = load_ledger(root_fn())
        include_all = request.args.get("all") == "1"
        records = (
            ledger.raw_lines if include_all else tuple(ledger.raw_current.values())
        )
        body = "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in records
        )
        return Response(
            body,
            mimetype="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=tags.jsonl"},
        )

    @app.get("/tags.csv")
    def tags_csv():
        ledger = load_ledger(root_fn())
        include_all = request.args.get("all") == "1"
        records = ledger.lines if include_all else tuple(ledger.current.values())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_COLUMNS)
        for item in records:
            writer.writerow(
                [
                    item["listing_id"],
                    item["tag"],
                    item["group"] or "",
                    item["label"] if item["tag"] != CLEAR else "",
                    item["note"],
                    item["at"],
                    item.get("source") or "",
                    item.get("day") or "",
                    item.get("building") or "",
                    item.get("address") or "",
                    item.get("unit") or "",
                    "" if item.get("bedrooms") is None else item.get("bedrooms"),
                    "" if item.get("ask") is None else item.get("ask"),
                    (
                        ""
                        if item.get("model_median") is None
                        else item.get("model_median")
                    ),
                    "" if item.get("miss") is None else item.get("miss"),
                    ";".join(item.get("flags") or []),
                ]
            )
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=tags.csv"},
        )
