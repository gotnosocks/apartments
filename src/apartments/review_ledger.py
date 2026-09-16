"""Append-only human review and observed-capture correction ledger."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import jsonpatch
from jsonpointer import JsonPointer

from .corrections import CorrectionError, canonical, validate_edit

GENESIS = "0" * 64
STAGES = {"identity", "prices", "layout", "size", "amenities"}
DECISIONS = {"confirmed", "needs_attention", "parser_issue"}
MAX_BATCH = 5000
MAX_PARSER_BATCH = 100000


class ReviewLedgerError(ValueError):
    pass


class ReviewConflict(ReviewLedgerError):
    pass


def _now():
    return datetime.now(UTC).isoformat()


def _ids(value):
    if not isinstance(value, list) or not value or len(value) > MAX_BATCH:
        raise ReviewLedgerError(f"snapshot_ids must contain 1 to {MAX_BATCH} IDs")
    if any(type(x) is not int or x < 0 for x in value) or len(set(value)) != len(value):
        raise ReviewLedgerError("snapshot_ids must be unique nonnegative integers")
    return sorted(value)


def _parser_ids(value):
    if not isinstance(value, list) or not value or len(value) > MAX_PARSER_BATCH:
        raise ReviewLedgerError(
            f"snapshot_ids must contain 1 to {MAX_PARSER_BATCH} IDs"
        )
    if any(type(x) is not int or x < 0 for x in value) or len(set(value)) != len(value):
        raise ReviewLedgerError("snapshot_ids must be unique nonnegative integers")
    return sorted(value)


def _read(stream, dataset):
    events, prev, ids = [], GENESIS, set()
    for line in stream:
        if not line.endswith("\n"):
            raise ReviewLedgerError("Incomplete ledger tail")
        try:
            event = json.loads(line)
            sig = event["hash"]
            payload = {k: v for k, v in event.items() if k != "hash"}
            if (
                event["previous_hash"] != prev
                or hashlib.sha256(canonical(payload).encode()).hexdigest() != sig
            ):
                raise ReviewLedgerError("Review ledger hash chain mismatch")
            if (
                event["id"] in ids
                or event["schema_version"] != 1
                or event["dataset"] != dataset
            ):
                raise ReviewLedgerError("Invalid review ledger event identity")
            if event["action"] not in {"review", "parser_issue", "correct", "retract"}:
                raise ReviewLedgerError("Invalid review ledger action")
            datetime.fromisoformat(event["recorded_at"])
            if event["action"] == "review":
                if (
                    type(event["snapshot_id"]) is not int
                    or event["stage"] not in STAGES
                    or event["decision"] not in DECISIONS
                ):
                    raise ReviewLedgerError("Invalid review event")
                if not isinstance(event["note"], str) or not event["author"].strip():
                    raise ReviewLedgerError("Invalid review text")
            elif event["action"] == "parser_issue":
                if (
                    not isinstance(event["selection"], dict)
                    or not isinstance(event["field"], str)
                    or not event["field"].strip()
                ):
                    raise ReviewLedgerError("Invalid parser issue")
                _parser_ids(event["snapshot_ids"])
            elif event["action"] == "correct":
                _ids(event["snapshot_ids"])
                if not event["author"].strip() or not event["reason"].strip():
                    raise ReviewLedgerError("Correction author and reason required")
                spec = {
                    "target": {"source": "streeteasy", "capture_id": "review"},
                    "patch": event["patch"],
                    "validity": {"all_time": True},
                }
                validate_edit(spec)
            elif (
                not event["correction_id"]
                or not event["author"].strip()
                or not event["reason"].strip()
            ):
                raise ReviewLedgerError("Invalid retraction")
            events.append(event)
            ids.add(event["id"])
            prev = sig
        except ReviewLedgerError:
            raise
        except Exception as e:
            raise ReviewLedgerError(
                f"Invalid ledger event {len(events) + 1}: {e}"
            ) from e
    corrections = {e["id"] for e in events if e["action"] == "correct"}
    for e in events:
        if e["action"] == "retract" and e["correction_id"] not in corrections:
            raise ReviewLedgerError("Retraction references unknown correction")
    return events


class ReviewLedger:
    def __init__(self, path, dataset):
        if not isinstance(dataset, str) or not dataset.strip():
            raise ReviewLedgerError("dataset is required")
        self.path, self.dataset = Path(path), dataset

    def _read(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            return _read(f, self.dataset)

    def events(self):
        return self._read()

    def revision(self):
        events = self.events()
        return events[-1]["hash"] if events else GENESIS

    def _append(self, action, **data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            events = _read(f, self.dataset)
            event = {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "recorded_at": _now(),
                "dataset": self.dataset,
                "action": action,
                "previous_hash": events[-1]["hash"] if events else GENESIS,
                **deepcopy(data),
            }
            event["hash"] = hashlib.sha256(canonical(event).encode()).hexdigest()
            f.seek(0, os.SEEK_END)
            f.write(canonical(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return event

    def record_review(
        self, snapshot_id: int, stage: str, decision: str, note: str, author: str
    ):
        if (
            type(snapshot_id) is not int
            or snapshot_id < 0
            or stage not in STAGES
            or decision not in DECISIONS
            or not isinstance(note, str)
            or not isinstance(author, str)
            or not author.strip()
        ):
            raise ReviewLedgerError("Invalid review")
        return self._append(
            "review",
            snapshot_id=snapshot_id,
            stage=stage,
            decision=decision,
            note=note,
            author=author,
        )

    def record_parser_issue(
        self,
        selection: dict,
        field: str,
        note: str,
        author: str,
        snapshot_ids: list[int],
    ):
        if (
            not isinstance(selection, dict)
            or not isinstance(field, str)
            or not field.strip()
            or not isinstance(note, str)
            or not isinstance(author, str)
            or not author.strip()
        ):
            raise ReviewLedgerError("Invalid parser issue")
        canonical(selection)
        return self._append(
            "parser_issue",
            selection=selection,
            field=field,
            note=note,
            author=author,
            snapshot_ids=_parser_ids(snapshot_ids),
        )

    def correct(
        self,
        snapshot_ids: list[int],
        patch: list,
        author: str,
        reason: str,
        expected_revision: str,
        request_id=None,
    ):
        ids = _ids(snapshot_ids)
        if (
            not isinstance(author, str)
            or not author.strip()
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ReviewLedgerError("Author and reason are required")
        # Restrict patches to normalized document attributes, never its archive envelope.
        spec = {
            "target": {"source": "streeteasy", "capture_id": "review"},
            "patch": patch,
            "validity": {"all_time": True},
        }
        try:
            validate_edit(spec)
        except CorrectionError as e:
            raise ReviewLedgerError(str(e)) from e
        for op in patch:
            parts = JsonPointer(op["path"]).parts
            if parts[0] == "archive_listing" and parts[1:2] == ["id"]:
                raise ReviewLedgerError("Cannot edit archive listing identity metadata")
        if request_id is not None and (
            not isinstance(request_id, str) or not request_id.strip()
        ):
            raise ReviewLedgerError("request_id must be a nonempty string")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            events = _read(f, self.dataset)
            if request_id is not None:
                prior = next(
                    (e for e in events if e.get("request_id") == request_id), None
                )
                if prior is not None:
                    if (
                        prior.get("snapshot_ids"),
                        prior.get("patch"),
                        prior.get("author"),
                        prior.get("reason"),
                    ) != (ids, patch, author, reason):
                        raise ReviewConflict(
                            "request_id was already used for a different correction"
                        )
                    return prior
            rev = events[-1]["hash"] if events else GENESIS
            if rev != expected_revision:
                raise ReviewConflict(
                    "Ledger revision changed; refresh before correcting"
                )
            event = {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "recorded_at": _now(),
                "dataset": self.dataset,
                "action": "correct",
                "snapshot_ids": ids,
                "patch": deepcopy(patch),
                "author": author,
                "reason": reason,
                "previous_hash": rev,
            }
            if request_id is not None:
                event["request_id"] = request_id
            event["hash"] = hashlib.sha256(canonical(event).encode()).hexdigest()
            f.seek(0, os.SEEK_END)
            f.write(canonical(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return event

    def retract(self, correction_id, author, reason, expected_revision=None):
        if not all(
            isinstance(x, str) and x.strip() for x in (correction_id, author, reason)
        ):
            raise ReviewLedgerError("Retraction needs correction ID, author and reason")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            events = _read(f, self.dataset)
            rev = events[-1]["hash"] if events else GENESIS
            if expected_revision is not None and rev != expected_revision:
                raise ReviewConflict("Ledger revision changed")
            correction = next(
                (
                    e
                    for e in events
                    if e["id"] == correction_id and e["action"] == "correct"
                ),
                None,
            )
            retracted = {e["correction_id"] for e in events if e["action"] == "retract"}
            if correction is None or correction_id in retracted:
                raise ReviewLedgerError("Correction is unknown or already retracted")
            event = {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "recorded_at": _now(),
                "dataset": self.dataset,
                "action": "retract",
                "correction_id": correction_id,
                "author": author,
                "reason": reason,
                "previous_hash": rev,
            }
            event["hash"] = hashlib.sha256(canonical(event).encode()).hexdigest()
            f.seek(0, os.SEEK_END)
            f.write(canonical(event) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return event

    def apply(self, raw: dict, snapshot_id: int, *, events=None):
        result = deepcopy(raw)
        evidence = []
        ledger_events = self.events() if events is None else events
        retracted = {
            e["correction_id"] for e in ledger_events if e["action"] == "retract"
        }
        for e in ledger_events:
            if (
                e["action"] != "correct"
                or e["id"] in retracted
                or snapshot_id not in e["snapshot_ids"]
            ):
                continue
            try:
                result = jsonpatch.apply_patch(result, e["patch"], in_place=False)
            except Exception as ex:
                raise ReviewLedgerError(
                    f"Correction {e['id']} cannot apply: {ex}"
                ) from ex
            evidence.append(
                {
                    "id": e["id"],
                    "author": e["author"],
                    "reason": e["reason"],
                    "patch": deepcopy(e["patch"]),
                }
            )
        return result, evidence

    def active_corrections(self):
        events = self.events()
        retracted = {e["correction_id"] for e in events if e["action"] == "retract"}
        return [
            e for e in events if e["action"] == "correct" and e["id"] not in retracted
        ]

    def activity(self):
        events = self.events()
        retracted = {e["correction_id"] for e in events if e["action"] == "retract"}
        return {
            "reviews": [e for e in events if e["action"] == "review"][-100:],
            "parser_issues": [e for e in events if e["action"] == "parser_issue"][
                -100:
            ],
            "corrections": [
                {**e, "active": e["id"] not in retracted}
                for e in events
                if e["action"] == "correct"
            ][-100:],
        }
