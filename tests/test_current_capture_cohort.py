import pytest

from models import current_capture_cohort as m


def candidate(n, building="b1", **changes):
    return {
        "unit_id": f"u{n}",
        "building_id": building,
        "source": "streeteasy",
        "source_listing_id": str(100 + n),
        "capture_id": f"cap{n}",
        "canonical_unit_url": f"https://streeteasy.com/building/{building}/{n}c",
        "collected_at": "2026-10-05T01:00:00Z",
        "known_at": "2026-10-05T01:01:00Z",
        "listing_status": "ACTIVE",
        "price_basis": "gross_advertised_rent",
        "rent": 4000,
        "bedrooms": 1,
        "bathrooms": 1,
        "advertised_floor": None,
        **changes,
    }


def history(unit, building, neighbourhood, period="2026-09-01", **changes):
    return {
        "audit_id": f"h:{unit}",
        "unit_id": unit,
        "building": building,
        "period": period,
        "analysis_price_basis": m.HISTORICAL,
        "neighbourhood": neighbourhood,
        "known_at": "2026-09-30T00:00:00Z",
        **changes,
    }


def evidence(row, root):
    count = {"value": 1, "present": True}
    return {
        "capture_id": row["capture_id"],
        "bathroom_fields": {
            "fullBathroomCount": count,
            "halfBathroomCount": {"value": 0, "present": True},
        },
    }


def queue(listing, *seeds):
    return {"source_listing_id": listing, "observations": [{"seed": s} for s in seeds]}


def test_seeds_name_the_neighbourhood_and_both_is_ambiguous():
    got = m.seed_neighbourhoods(
        [
            queue("1", "/for-rent/west-village"),
            queue("2", "/for-rent/chelsea", "/for-rent/west-chelsea"),
            queue("3", "/for-rent/chelsea", "/for-rent/west-village"),
            queue("4", "/for-rent/soho"),
            queue("5", "/for-rent/chelsea"),
            queue("5", "/for-rent/west-village"),  # another queue disagrees
        ]
    )
    assert got == {"1": "West Village", "2": "Chelsea", "3": None, "4": None, "5": None}


def test_new_month_replaces_old_captures_and_keeps_history():
    parent = [
        history("u1", "b1", "Chelsea"),
        history("u9", "b2", "West Village"),
        {
            **history("u8", "b1", "Chelsea"),
            "audit_id": "capture:old",
            "analysis_price_basis": m.CURRENT,
        },
    ]
    candidates = [
        candidate(1),  # Chelsea, label floor 1
        candidate(2, "b2"),  # West Village by seed
        candidate(3, "b2"),  # seeded Chelsea in a WV building
        candidate(4, "new"),  # no registry entry
        candidate(5, rent=500),  # outside the rent support
        candidate(6, canonical_unit_url="https://streeteasy.com/building/b1/12c"),
    ]
    seeds = {
        "101": "Chelsea",
        "102": "West Village",
        "103": "Chelsea",
        "104": "Chelsea",
        "105": "Chelsea",
        "106": "Chelsea",
    }
    rows, ev, excluded, summary, dropped = m.assemble(
        parent,
        candidates,
        [],
        {f"cap{n}": None for n in range(1, 7)},
        seeds,
        {"b1", "b2"},
        {"b1": 6},
        as_of="2026-10-05T02:00:00Z",
        max_age_days=1,
        evidence_of=evidence,
    )
    assert dropped == ["capture:old"]
    current = {r["unit_id"]: r for r in rows if r["analysis_price_basis"] == m.CURRENT}
    assert set(current) == {"u1", "u2", "u6"}
    assert current["u1"]["period"] == "2026-10-01"
    assert current["u1"]["neighbourhood"] == "Chelsea"
    assert current["u2"]["neighbourhood"] == "West Village"
    assert current["u1"]["listed_floor"] == 1 == current["u1"]["label_derived_floor"]
    # 12C reads floor 12, above the building's 6 floors: refused.
    assert current["u6"]["listed_floor"] is None
    assert (
        current["u6"]["floor_label_provenance"]["status"]
        == "above_captured_building_floor_count"
    )
    assert current["u1"]["reported_full_bathrooms"] == 1
    reasons = {e["record"]["unit_id"]: e["reason"] for e in excluded}
    assert reasons["u3"] == "seed_disagrees_with_building_neighbourhood"
    assert reasons["u4"] == "building_not_in_registry"
    assert reasons["u5"] == "outside_analysis_rent_or_layout_support"
    assert [r for r in rows if r["analysis_price_basis"] == m.HISTORICAL] == parent[:2]
    assert summary["current_new_units"] == 2


def test_parent_rows_in_the_new_month_are_refused():
    with pytest.raises(ValueError, match="in or after"):
        m.assemble(
            [history("u1", "b1", "Chelsea", period="2026-10-01")],
            [candidate(1)],
            [],
            {},
            {"101": "Chelsea"},
            {"b1"},
            {},
            as_of="2026-10-05T02:00:00Z",
            max_age_days=1,
            evidence_of=evidence,
        )


def old_current(listing, unit, **changes):
    return {
        **history(unit, "b1", "Chelsea"),
        "audit_id": f"capture:old{listing}",
        "analysis_price_basis": m.CURRENT,
        "source_listing_id": listing,
        "bathrooms": 1,
        "reported_full_bathrooms": 1,
        "reported_half_bathrooms": 0,
        "bathroom_count_evidence": {
            "flags": ["reviewed_bathroom_composition_conflict"],
            "composition_status": "reviewed_composition_conflict_unknown",
        },
        "research_review_history": [
            {"action": "mask_bathroom_composition", "decision_id": "d1"}
        ],
        **changes,
    }


def run_one(parent, cand, floors=None):
    return m.assemble(
        parent,
        [cand],
        [],
        {cand["capture_id"]: None},
        {cand["source_listing_id"]: "Chelsea"},
        {"b1"},
        floors or {},
        as_of="2026-10-05T02:00:00Z",
        max_age_days=1,
        evidence_of=evidence,
    )


def test_reviews_carry_to_the_same_ad_or_stop_the_build():
    parent = [history("u0", "b1", "Chelsea"), old_current("101", "u1")]
    rows, *_ = run_one(parent, candidate(1))
    new = next(r for r in rows if r["analysis_price_basis"] == m.CURRENT)
    assert (
        new["research_review_history"][0]["carried_from_audit_id"] == "capture:old101"
    )
    assert (
        new["bathroom_count_evidence"]["composition_status"]
        == "reviewed_composition_conflict_unknown"
    )
    assert (
        "reviewed_bathroom_composition_conflict"
        in new["bathroom_count_evidence"]["flags"]
    )
    with pytest.raises(ValueError, match="explicit reapplication"):
        run_one(parent, candidate(1, bathrooms=2))


def test_buildings_excluded_from_label_numbering_get_no_label_floor():
    parent = [
        history(
            "u0",
            "b1",
            "Chelsea",
            floor_label_provenance={"status": m.NUMBERING_EXCLUDED},
        )
    ]
    rows, *_ = run_one(parent, candidate(1))
    new = next(r for r in rows if r["analysis_price_basis"] == m.CURRENT)
    assert new["listed_floor"] is None and new["label_derived_floor"] is None
    assert new["floor_label_provenance"]["status"] == m.NUMBERING_EXCLUDED
    rows, *_ = run_one(parent, candidate(1, advertised_floor=3))
    assert (
        next(r for r in rows if r["analysis_price_basis"] == m.CURRENT)["listed_floor"]
        == 3
    )
