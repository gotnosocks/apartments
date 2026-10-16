import json

import pytest

from rentfrontier import cohort


def write(directory, rows):
    directory.mkdir()
    with open(directory / "observations.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def row(audit, listing, unit, period, area="Chelsea", **extra):
    return {
        "audit_id": audit,
        "source_listing_id": listing,
        "unit_id": unit,
        "period": period,
        "neighbourhood": area,
        **extra,
    }


def test_extend_adds_only_new_ads_of_the_base_areas(tmp_path):
    base = [
        row("a1", "1", "u1", "2020-01-01", corrections=None, exclusion_reason=""),
        row("a2", "2", "u2", "2020-02-01", corrections=None, exclusion_reason=""),
    ]
    extra = [
        row("b1", "1", "u1", "2020-01-01"),  # listing in base
        row("b3", "3", "u3", "2020-01-01", area="Noho"),  # area not in base
        row("b4", "4", "u2", "2020-02-01"),  # unit-month in base
        row("b5", "5", "u2", "2020-03-01"),  # added
    ]
    write(tmp_path / "base", base)
    write(tmp_path / "extra", extra)
    report = cohort.extend(tmp_path / "out", tmp_path / "base", tmp_path / "extra")
    assert report["rows"] == {
        "base": 2,
        "added": 1,
        "skipped": {
            "listing in base": 1,
            "area not in base": 1,
            "unit-month in base": 1,
        },
    }
    with open(tmp_path / "out/observations.jsonl") as f:
        out = [json.loads(line) for line in f]
    assert out[:2] == base
    assert out[2] == {**extra[3], "corrections": None, "exclusion_reason": ""}


def test_extend_refuses_a_shared_audit_id(tmp_path):
    write(tmp_path / "base", [row("a1", "1", "u1", "2020-01-01")])
    write(tmp_path / "extra", [row("a1", "2", "u2", "2020-01-01")])
    with pytest.raises(SystemExit, match="audit id"):
        cohort.extend(tmp_path / "out", tmp_path / "base", tmp_path / "extra")
