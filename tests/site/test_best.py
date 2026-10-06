"""Best for you: current listings ranked by a preference sheet (Ben, 2026-10-06)."""

import json
import math

import pytest

from apartments.site import best

SHEET = {
    "profile": "test-v1",
    "description": "A test renter.",
    "weights": {
        "bedrooms=2": 1,
        "label:penthouse": -1,
        "quiet_street": 1,
        "text:gym": 0,
    },
    "latent": {"building level (buildings.level_pct)": 0.5, "unit effect": "later"},
    "neutral_on_purpose": ["furnished"],
}


@pytest.fixture(autouse=True)
def sheets(tmp_path, monkeypatch):
    """Preference sheets in the test's own folder, never the machine's."""
    folder = tmp_path / "preferences"
    folder.mkdir()
    (folder / "test-v1.json").write_text(json.dumps(SHEET))
    monkeypatch.setattr(best, "DIR", folder)
    monkeypatch.setattr(best, "DEFAULT_PROFILE", "test-v1")
    return folder


def test_profile_drops_zeros_and_reads_latent(sheets):
    p = best.load_profile(sheets / "test-v1.json")
    assert p["weights"] == {
        "bedrooms=2": 1.0,
        "label:penthouse": -1.0,
        "quiet_street": 1.0,
    }
    assert p["latent"] == {"level": 0.5}
    assert p["unmodelled"] == ["unit effect: later"]


def test_score_uses_the_model_size_and_the_sheet_sign():
    profile = {
        "weights": {
            "laundry=in_unit": 1.0,
            "elevator=no": -1.0,
            "log_sqft_vs_bedroom_median": 1.0,
            "log_floor": 1.0,
            "log_floor_above_6": 1.0,
        },
        "latent": {"level": 0.5},
    }
    betas = {
        "laundry=in_unit": 0.02,
        "elevator=no": 0.01,  # positive in the model, still a minus for this renter
        "log_sqft_vs_bedroom_median": 0.25,
        "log_floor": 0.01,
        "log_floor_above_6": 0.05,
    }
    inputs = {
        "laundry=in_unit": 1.0,
        "elevator=no": 1.0,
        "log_sqft_vs_bedroom_median": -0.2,
        "log_floor": 2.0,
        "log_floor_above_6": 0.5,
    }
    s = best.score(
        {"floor": 8}, inputs, {"level_pct": 10.0, "trend_pct": None}, profile, betas
    )
    expected = 0.02 - 0.01 - 0.05 + (0.02 + 0.025) + 0.5 * math.log1p(0.10)
    assert s["score"] == pytest.approx(expected)
    assert [t["label"] for t in s["pros"]] == [
        "a building that rents above similar ones",
        "the 8th floor",
        "in-unit laundry",
    ]
    assert [t["label"] for t in s["cons"]] == [
        "less space than usual for its bedrooms",
        "no elevator",
    ]
    assert s["unknown"] == []


def test_unstated_details_are_named_not_counted():
    profile = {"weights": {"laundry=in_unit": 1.0, "elevator=no": -1.0}, "latent": {}}
    s = best.score(
        {"floor": None},
        {"laundry=unknown": 1.0, "elevator=unknown": 1.0},
        None,
        profile,
        {"laundry=in_unit": 0.02, "elevator=no": 0.01},
    )
    assert s["score"] == 0
    assert s["unknown"] == ["elevator", "laundry"]


def test_choose_filters_and_sorts():
    rows = [
        {"audit_id": "a", "bedrooms": 1, "ask": 4000, "income_restricted": False, "score": 0.1, "value": -8.2, "deal": 0.2},
        {"audit_id": "b", "bedrooms": 1, "ask": 6000, "income_restricted": False, "score": 0.3, "value": -8.4, "deal": 0.1},
        {"audit_id": "c", "bedrooms": 4, "ask": 3000, "income_restricted": True, "score": 0.5, "value": -7.5, "deal": 0.3},
    ]  # fmt: skip
    assert [r["audit_id"] for r in best.choose(rows)] == ["a", "b"]
    assert [r["audit_id"] for r in best.choose(rows, income=True)] == ["c", "a", "b"]
    assert [r["audit_id"] for r in best.choose(rows, sort="fit")] == ["b", "a"]
    assert [r["audit_id"] for r in best.choose(rows, max_rent=5000)] == ["a"]
    assert [r["audit_id"] for r in best.choose(rows, beds=3, income=True)] == ["c"]
    assert best.choose(rows, beds=0) == []


def test_page_ranks_current_listings(client):
    page = client.get("/best").get_data(as_text=True)
    assert "<h1>Best for you</h1>" in page
    assert "test-v1" in page
    assert 'href="/research/glossary#fit-score"' in page
    assert 'quiet street <span class="muted">(not modelled)</span>' in page
    assert "unit effect: later" in page
    assert 'aria-current="page">Best for you</a>' in page


def test_csv_and_sorts(client):
    response = client.get("/best.csv?sort=fit")
    assert response.status_code == 200
    header = response.get_data(as_text=True).splitlines()[0]
    assert header.startswith("rank,audit_id,building")
    page = client.get("/best?sort=deal&beds=1&max=9000").get_data(as_text=True)
    assert "Fits you, at a good price</strong>" in page
    assert 'value="9000"' in page
    # Not "best for the money": across all sizes it ranks cheapest first.
    assert "Fits you, at a good price</strong>" in client.get("/best").get_data(
        as_text=True
    )


def test_unknown_profile_is_404(client):
    assert client.get("/best?profile=nobody").status_code == 404
    assert client.get("/best?profile=../etc").status_code == 404


def test_glossary_entry(client):
    page = client.get("/research/glossary").get_data(as_text=True)
    assert 'id="fit-score"' in page
