"""The Review section (`review.py`): queues, answers, undo, the pages and the ledger export."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from apartments.site import review
from apartments.site.web import create_app

PHOTO = "https://photos.zillowstatic.com/fp/" + "a" * 32 + "-se_medium_500_250.webp"

JOIN = {
    "id": "16-monitor-street-brooklyn:3e",
    "title": "16 Monitor St: 3E, 3G",
    "subtitle": "Nooklyn · 1 bed",
    "claim": "The repost screen links these labels.",
    "proposal": {
        "ledger": "units",
        "line": {
            "change": "join_units",
            "building": "16-monitor-street-brooklyn",
            "units": ["3e", "3g"],
        },
        "evidence": [
            {
                "kind": "city_record",
                "detail": "Condo lots 1E to 4E and 1F to 4F; none for 3G.",
            }
        ],
        "summary": "Join 3G into 3E.",
    },
    "blocks": [
        {
            "type": "facts",
            "title": "City records",
            "rows": [{"label": "PLUTO residential units", "value": "8", "mark": "bad"}],
        },
        {
            "type": "grid",
            "title": "Labels",
            "floors": [
                {
                    "floor": "3",
                    "cells": [
                        {"label": "3E", "ads": 6, "mark": "city"},
                        {"label": "3G", "ads": 1, "mark": "candidate"},
                    ],
                }
            ],
        },
        {
            "type": "ads",
            "title": "The chain",
            "nominating": True,
            "ads": [
                {
                    "listing_id": "2501619",
                    "unit": "3G",
                    "photos": [PHOTO, "https://evil.example/x.webp"],
                    "text": "Sunny one bedroom",
                    "url": "https://streeteasy.com/rental/2501619",
                }
            ],
        },
    ],
}

OUTLIER = {
    "id": "ad:4760220",
    "listing_id": "4760220",
    "title": "123 Main St #4",
    "blocks": [
        {
            "type": "ads",
            "title": "The ad",
            "ads": [
                {
                    "listing_id": "4760220",
                    "unit": "4",
                    "bedrooms": 2,
                    "full_baths": 2,
                    "half_baths": 0,
                    "record": {
                        "period": "2025-06",
                        "bedrooms": 2.0,
                        "full_baths": 2,
                        "half_baths": 0,
                        "square_feet": None,
                        "latest_ask": 4100.0,
                    },
                },
                {"listing_id": "4700001", "unit": "4"},
            ],
        }
    ],
}

STUDIO = {
    "id": "beds:5000001",
    "listing_id": "5000001",
    "title": "9 Elm St #2",
    "proposal": {
        "ledger": "corrections",
        "line": {
            "change": "set",
            "listing_id": "5000001",
            "set": {"bedrooms": 2.0},
            "when": {"period": "2024-03", "bedrooms": 0.0},
        },
        "evidence": [
            {
                "kind": "other_ad",
                "listing_id": "4000001",
                "detail": "The 2023 ad codes 2 bedrooms.",
            }
        ],
        "summary": "Set bedrooms to 2.",
    },
    "options": [
        {
            "code": "b3",
            "label": "3 bedrooms",
            "proposal": {
                "ledger": "corrections",
                "line": {
                    "change": "set",
                    "listing_id": "5000001",
                    "set": {"bedrooms": 3.0},
                    "when": {"period": "2024-03", "bedrooms": 0.0},
                },
                "evidence": [],
                "summary": "Set bedrooms to 3.",
            },
        }
    ],
    "blocks": [],
}


def _write_queue(root: Path, name: str, cards: list[dict], answers=None) -> None:
    base = root / "review" / "queues" / name
    base.mkdir(parents=True, exist_ok=True)
    meta = {"queue": name, "title": name.title(), "question": "Is it right?"}
    if answers is not None:
        meta["answers"] = answers
    (base / "meta.json").write_text(json.dumps(meta))
    (base / "cards.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cards))


JOIN_ANSWERS = [
    {"code": "yes", "label": "One apartment", "key": "y", "applies": True},
    {"code": "no", "label": "Different apartments", "key": "n"},
    {"code": "unsure", "label": "Can't tell", "key": "u"},
]


@pytest.fixture()
def root(tmp_path):
    _write_queue(tmp_path, "joins", [JOIN], JOIN_ANSWERS)
    _write_queue(
        tmp_path,
        "outliers",
        [OUTLIER, STUDIO, {"id": "ad:3", "title": "Third"}],
        [
            {"code": "fine", "label": "Data looks right", "key": "n"},
            {"code": "unsure", "label": "Can't tell", "key": "u"},
        ],
    )
    return tmp_path


@pytest.fixture()
def client(root):
    app = create_app(root)
    app.config["TESTING"] = True
    return app.test_client()


def _answers(root: Path) -> list[dict]:
    path = root / "review" / "decisions.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_home_lists_queues_with_progress(client):
    page = client.get("/review").get_data(as_text=True)
    assert "Joins" in page and "Outliers" in page
    assert "1 to go" in page and "3 to go" in page


def test_queue_redirects_to_its_first_card(client):
    response = client.get("/review/outliers")
    assert response.status_code == 303
    assert response.headers["Location"].endswith("/review/outliers/ad:4760220")


def test_card_page_shows_evidence_and_answers(client):
    response = client.get("/review/joins/16-monitor-street-brooklyn:3e")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "If yes: Join 3G into 3E." in page
    assert "Only nominates" in page
    assert "One apartment" in page and 'data-key="y"' in page
    assert PHOTO in page and "evil.example" not in page
    assert "se_extra_large_1500_800" in page
    csp = response.headers["Content-Security-Policy"]
    assert "img-src 'self' data: https://photos.zillowstatic.com;" in csp


def test_other_pages_keep_the_strict_image_policy(client):
    csp = client.get("/review").headers["Content-Security-Policy"]
    assert "img-src 'self' data:;" in csp


def test_unknown_queue_and_card_are_404(client):
    assert client.get("/review/nope").status_code == 404
    assert client.get("/review/joins/nope").status_code == 404


def test_answer_moves_to_next_card_and_offers_undo(client, root):
    response = client.post("/review/outliers/ad:4760220", data={"answer": "fine"})
    assert response.status_code == 303
    assert (
        "/review/outliers/beds:5000001?saved=ad:4760220" in response.headers["Location"]
    )
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Saved <strong>Data looks right</strong> for 123 Main St #4" in page
    [line] = _answers(root)
    assert line["answer"] == "fine" and line["card"] == "ad:4760220"
    assert len(line["card_sha"]) == 64


def test_skipped_card_comes_back_last(client):
    client.post("/review/outliers/ad:4760220", data={"answer": "skip"})
    response = client.post("/review/outliers/beds:5000001", data={"answer": "fine"})
    assert response.headers["Location"].split("?")[0].endswith("/ad:3")
    response = client.post("/review/outliers/ad:3", data={"answer": "unsure"})
    assert response.headers["Location"].split("?")[0].endswith("/ad:4760220")
    response = client.post("/review/outliers/ad:4760220", data={"answer": "fine"})
    assert response.headers["Location"].endswith("/review/outliers?saved=ad:4760220")
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "All done" in page and "Saved <strong>Data looks right</strong>" in page


def test_undo_reopens_the_last_card(client, root):
    client.post("/review/outliers/ad:4760220", data={"answer": "fine"})
    client.post("/review/outliers/beds:5000001", data={"answer": "unsure"})
    response = client.post("/review/outliers/undo")
    assert response.headers["Location"].endswith("/review/outliers/beds:5000001")
    current = review.load_decisions(root).for_queue("outliers")
    assert set(current) == {"ad:4760220"}


def test_undo_from_a_toast_clears_only_its_card(client, root):
    client.post("/review/outliers/ad:4760220", data={"answer": "fine"})
    client.post("/review/outliers/beds:5000001", data={"answer": "unsure"})
    response = client.post("/review/outliers/undo", data={"card": "ad:4760220"})
    assert response.headers["Location"].endswith("/review/outliers/ad:4760220")
    current = review.load_decisions(root).for_queue("outliers")
    assert set(current) == {"beds:5000001"}


def test_skipping_the_last_card_shows_the_toast(client):
    for card in ("ad:4760220", "beds:5000001"):
        client.post(f"/review/outliers/{card}", data={"answer": "fine"})
    response = client.post("/review/outliers/ad:3", data={"answer": "skip"})
    page = client.get(response.headers["Location"], follow_redirects=True)
    assert "Saved <strong>Skipped</strong>" in page.get_data(as_text=True)


def test_shortcut_keys_s_and_z_stay_reserved():
    answers = review._answers(
        [
            {"code": "a", "label": "A", "key": "s"},
            {"code": "b", "label": "B", "key": "z"},
        ]
    )
    assert [a["key"] for a in answers] == ["", ""]


def test_export_skips_lines_for_a_changed_card(client, root, tmp_path):
    _answer(client, "joins", "16-monitor-street-brooklyn:3e", answer="yes")
    changed = {**JOIN, "subtitle": "rebuilt"}
    _write_queue(root, "joins", [changed], JOIN_ANSWERS)
    out = review.export(root, tmp_path / "ledger", day="2026-11-12")
    assert out["units"] == 0 and out["findings"] == 1
    [finding] = [
        json.loads(x) for x in (root / "review" / "findings-2026-11-12-01.jsonl").open()
    ]
    assert finding["card_changed"] is True


def test_a_second_export_sorts_after_the_first(client, root, tmp_path):
    ledger = tmp_path / "ledger"
    _answer(client, "outliers", "beds:5000001", answer="option:b3")
    review.export(root, ledger, day="2026-11-12")
    client.post("/review/outliers/beds:5000001", data={"answer": "fine"})
    _answer(
        client,
        "outliers",
        "ad:4760220",
        answer="problem",
        fix_listing="4760220",
        fix_field="latest_ask",
        fix_value="1250000",
    )
    review.export(root, ledger, day="2026-11-12")
    names = sorted(p.name for p in ledger.glob("*.ndjson"))
    assert names == [
        "2026-11-12-review-app-01.ndjson",
        "2026-11-12-review-app-02.ndjson",
    ]
    [line] = [json.loads(x) for x in (ledger / names[1]).open()]
    assert "Latest ask ($) is 1,250,000" in line["evidence"][0]["detail"]


def test_refuses_bad_answers(client, root):
    assert (
        client.post("/review/outliers/ad:3", data={"answer": "yes"}).status_code == 400
    )
    assert (
        client.post("/review/outliers/ad:3", data={"answer": "option:zz"}).status_code
        == 400
    )
    assert (
        client.post("/review/outliers/ad:3", data={"answer": "problem"}).status_code
        == 400
    )
    bad_value = {
        "answer": "problem",
        "fix_listing": "4760220",
        "fix_field": "bedrooms",
        "fix_value": "1.5",
    }
    assert client.post("/review/outliers/ad:4760220", data=bad_value).status_code == 400
    response = client.post(
        "/review/outliers/ad:3",
        data={"answer": "fine"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert not (root / "review" / "decisions.jsonl").exists()


def test_problem_with_a_typed_value(client, root):
    data = {
        "answer": "problem",
        "problem": ["wrong_beds", "made_up"],
        "fix_listing": "4760220",
        "fix_field": "full_baths",
        "fix_value": "1",
        "note": "text says 1.5 baths",
    }
    assert client.post("/review/outliers/ad:4760220", data=data).status_code == 303
    [line] = _answers(root)
    assert line["problems"] == ["wrong_beds"]
    assert line["fix"] == {"listing_id": "4760220", "field": "full_baths", "value": 1}
    page = client.get("/review/outliers/ad:4760220").get_data(as_text=True)
    assert "Problem: Wrong bedrooms, Full baths 1" in page


def test_changed_card_is_marked(client, root):
    client.post("/review/outliers/ad:3", data={"answer": "fine"})
    _write_queue(
        root,
        "outliers",
        [OUTLIER, STUDIO, {"id": "ad:3", "title": "Third, rebuilt"}],
        [
            {"code": "fine", "label": "Data looks right", "key": "n"},
            {"code": "unsure", "label": "Can't tell", "key": "u"},
        ],
    )
    page = client.get("/review/outliers/ad:3").get_data(as_text=True)
    assert "the card has changed since" in page


def test_bad_card_lines_are_counted_not_fatal(root, client):
    base = root / "review" / "queues" / "joins"
    with (base / "cards.jsonl").open("a") as f:
        f.write(
            "not json\n" + json.dumps({"id": "undo"}) + "\n" + json.dumps(JOIN) + "\n"
        )
    queue = review.load_queue(root, "joins")
    assert len(queue.cards) == 1 and len(queue.errors) == 3
    assert "could not be read" in client.get("/review").get_data(as_text=True)


def test_media_files_are_served_safely(client, root):
    media = root / "review" / "media"
    media.mkdir(parents=True)
    (media / "plan.png").write_bytes(b"\x89PNG")
    assert client.get("/review/media/plan.png").status_code == 200
    assert client.get("/review/media/../decisions.jsonl").status_code == 404
    assert review.image_url("/review/media/plan.png") == "/review/media/plan.png"
    assert review.image_url("/review/media/../x") is None
    assert review.image_url("http://photos.zillowstatic.com/x.webp") is None


def _answer(client, queue, card, **data):
    response = client.post(f"/review/{queue}/{card}", data=data)
    assert response.status_code == 303, response.get_data(as_text=True)


def _answer_all(client):
    _answer(
        client, "joins", "16-monitor-street-brooklyn:3e", answer="yes", note="no 3G lot"
    )
    _answer(client, "outliers", "beds:5000001", answer="option:b3")
    _answer(
        client,
        "outliers",
        "ad:4760220",
        answer="problem",
        problem="not_apartment",
        fix_listing="4760220",
        fix_field="full_baths",
        fix_value="1",
    )
    _answer(client, "outliers", "ad:3", answer="unsure")


def test_export_writes_ledger_lines_once(client, root, tmp_path):
    _answer_all(client)
    ledger = tmp_path / "ledger"
    out = review.export(root, ledger, day="2026-11-12")
    assert out["corrections"] == 3 and out["units"] == 1 and out["answers"] == 4
    units = [
        json.loads(x)
        for x in (ledger / "units" / "2026-11-12-review-app-01.ndjson").open()
    ]
    [join] = units
    assert join["change"] == "join_units" and join["units"] == ["3e", "3g"]
    assert [e["kind"] for e in join["evidence"]] == ["city_record", "owner"]
    assert (
        "Ben's reading in the review app on 2026-11-12: One apartment"
        in (join["evidence"][1]["detail"])
    )
    assert "Note: no 3G lot" in join["evidence"][1]["detail"]
    assert join["decided"] == "2026-11-12" and join["source"].startswith(
        "review app joins/16-monitor-street-brooklyn:3e "
    )
    fixes = [json.loads(x) for x in (ledger / "2026-11-12-review-app-01.ndjson").open()]
    beds, baths, exclude = fixes
    assert beds["set"] == {"bedrooms": 3.0}
    assert baths["set"] == {"full_baths": 1, "half_baths": 0}
    assert baths["when"] == {"period": "2025-06", "full_baths": 2, "half_baths": 0}
    assert exclude == {
        **exclude,
        "change": "exclude",
        "listing_id": "4760220",
        "reason": "not_apartment",
        "when": {"period": "2025-06"},
    }
    findings = [
        json.loads(x) for x in (root / "review" / "findings-2026-11-12-01.jsonl").open()
    ]
    assert {f["card"] for f in findings} == {"ad:4760220", "ad:3"}
    again = review.export(root, ledger, day="2026-11-12")
    assert again["answers"] == 0 and again["files"] == []


def test_exported_lines_pass_the_ledger_rules(client, root, tmp_path):
    _answer_all(client)
    ledger = tmp_path / "ledger"
    review.export(root, ledger, day="2026-11-12")
    _check_with_ledger_rules(ledger)


def test_export_dry_run_writes_nothing(client, root, tmp_path):
    _answer(client, "joins", "16-monitor-street-brooklyn:3e", answer="yes")
    out = review.export(root, tmp_path / "ledger", day="2026-11-12", dry_run=True)
    assert out["units"] == 1 and out["files"] == []
    assert not (tmp_path / "ledger").exists()
    assert not review.exported_path(root).exists()


def _check_with_ledger_rules(ledger: Path) -> None:
    """Read the written files with the pipeline's own parser, where its packages are installed."""
    pytest.importorskip("sqlmesh")
    path = (
        Path(__file__).resolve().parents[2]
        / "pipeline"
        / "models"
        / "ledger"
        / "entries.py"
    )
    spec = importlib.util.spec_from_file_location("ledger_entries_for_review", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.read(sorted(ledger.glob("*.ndjson")))
    module.read_units(sorted((ledger / "units").glob("*.ndjson")))


def test_card_ids_may_hold_slug_characters(root, client):
    card = {**JOIN, "id": "226-east-59-street-new_york:5fw+5u"}
    _write_queue(root, "joins", [card], JOIN_ANSWERS)
    assert review.load_queue(root, "joins").errors == ()
    response = client.get("/review/joins/226-east-59-street-new_york:5fw+5u")
    assert response.status_code == 200


def test_export_never_joins_a_page_twice(client, root, tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "units").mkdir(parents=True)
    earlier = {
        "change": "join_units",
        "building": "16-monitor-street-brooklyn",
        "units": ["3g", "3h"],
        "evidence": [{"kind": "owner", "detail": "Ben, 2026-11-11"}],
        "decided": "2026-11-11",
    }
    (ledger / "units" / "2026-11-11-x.ndjson").write_text(json.dumps(earlier) + "\n")
    _answer(client, "joins", "16-monitor-street-brooklyn:3e", answer="yes")
    out = review.export(root, ledger, day="2026-11-12")
    assert out["units"] == 0 and out["findings"] == 1
    [finding] = [
        json.loads(x) for x in (root / "review" / "findings-2026-11-12-01.jsonl").open()
    ]
    assert finding["page_already_joined"] is True


def test_joined_pages_leave_out_retracted_joins(tmp_path):
    line = json.dumps({"change": "join_units", "building": "b", "units": ["1", "2"]})
    entry = review.hashlib.sha256(line.encode()).hexdigest()[:16]
    (tmp_path / "units").mkdir()
    (tmp_path / "units" / "a.ndjson").write_text(line + "\n")
    assert review.joined_pages(tmp_path) == {("b", "1"), ("b", "2")}
    retract = json.dumps({"change": "retract", "entry": entry})
    (tmp_path / "units" / "b.ndjson").write_text(retract + "\n")
    assert review.joined_pages(tmp_path) == set()
