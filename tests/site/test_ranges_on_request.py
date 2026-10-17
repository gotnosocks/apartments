"""Likely ask ranges worked out when a listing's page opens, from the range
atoms of a bundle summarized with `--range-atoms` (detail.py, ranges.py)."""

import json
import math
import sqlite3
from statistics import NormalDist

import pytest

from apartments.site import build, detail, ranges

from .conftest import _parquet, _sha, summary_rows

# The predictive distribution of each row's log ask: the estimate's total log
# rent N(log median, ATOM_SD), plus noise N(0, NOISE_SD[group]).
ATOM_SD = 0.04
NOISE_SD = {0: 0.08, 1: 0.15}
GRID = 4097


def noise_table(sd: float) -> dict:
    lower = -60 * sd
    step = 120 * sd / (GRID - 1)
    cdf = NormalDist(0, sd).cdf
    return {
        "lower": lower,
        "step": step,
        "cdf": [cdf(lower + i * step) for i in range(GRID)],
    }


def exact(median: float, sd: float, p: float) -> float:
    total = math.hypot(ATOM_SD, sd)
    return median * math.exp(NormalDist(0, total).inv_cdf(p))


@pytest.fixture
def atoms_bundle(make_bundle, tmp_path):
    """The test bundle with atoms for every row but a1, whose chunk fell back
    to the exact ranges, and the noise tables beside it."""
    bundle = make_bundle(tmp_path / "atoms-inputs")
    rows = summary_rows()
    for i, row in enumerate(rows):
        group = i % 2
        median = row["estimate_median"]
        if row["audit_id"] == "a1":
            row.update(noise_group=None, estimate_atoms=None)
            for name, lower, upper in ranges.RANGES:
                row[f"estimate_pred_lower_{name}"] = exact(
                    median, NOISE_SD[group], lower
                )
                row[f"estimate_pred_upper_{name}"] = exact(
                    median, NOISE_SD[group], upper
                )
            continue
        atom = NormalDist(math.log(median), ATOM_SD).inv_cdf
        row["noise_group"] = group
        row["estimate_atoms"] = [
            atom((j + 0.5) / ranges.ATOMS) for j in range(ranges.ATOMS)
        ]
        for name in ("95", "80"):
            row[f"estimate_pred_lower_{name}"] = None
            row[f"estimate_pred_upper_{name}"] = None
    _parquet(bundle / "rows.parquet", rows)
    (bundle / ranges.NOISE_FILE).write_text(
        json.dumps({"groups": {str(g): noise_table(sd) for g, sd in NOISE_SD.items()}})
    )
    record = json.loads((bundle / "complete.json").read_text())
    record["files"] = {
        p.name: _sha(p) for p in sorted(bundle.iterdir()) if p.name != "complete.json"
    }
    (bundle / "complete.json").write_text(json.dumps(record))
    return bundle


@pytest.fixture
def atoms_root(atoms_bundle, tmp_path):
    root = tmp_path / "site-atoms"
    build.build(atoms_bundle, root, scope="Chelsea")
    return root


@pytest.fixture
def atoms_client(atoms_root, research_file):
    from apartments.site.web import create_app

    app = create_app(
        atoms_root, allowed_hosts=["thelio.example.ts.net"], research_data=research_file
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_the_build_copies_atoms_and_noise_beside_the_database(atoms_root):
    current = atoms_root / "current"
    db = sqlite3.connect(current / "site.sqlite")
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key = 'stats'").fetchone()[0]
    )
    stored = dict(
        db.execute("SELECT audit_id, pred_lower_80 FROM listings WHERE method != 'kit'")
    )
    db.close()
    assert stats["ranges"]["rows"] == len(summary_rows()) - 1
    assert (current / ranges.NOISE_FILE).is_file()
    # Only the fallback row holds its range in the table.
    assert [a for a, v in stored.items() if v is not None] == ["a1"]


def test_ranges_on_request_match_the_exact_ranges(atoms_root):
    build_dir = (atoms_root / "current").resolve()
    sha = json.loads((build_dir / "build.json").read_text())["summary_sha256"]
    rows = summary_rows()
    for i, row in enumerate(rows):
        got = detail.likely_ask(build_dir, sha, row["audit_id"])
        if row["audit_id"] == "a1":
            assert got is None
            continue
        sd = NOISE_SD[i % 2]
        for name, lower, upper in ranges.RANGES:
            for side, p in (("lower", lower), ("upper", upper)):
                want = exact(row["estimate_median"], sd, p)
                assert math.log(got[f"pred_{side}_{name}"] / want) == pytest.approx(
                    0, abs=0.003
                )
    assert detail.likely_ask(build_dir, sha, "no-such-row") is None


def test_the_listing_page_shows_ranges_from_either_source(atoms_client):
    for audit_id in ("a1", "a2"):
        html = " ".join(
            atoms_client.get(f"/listings/{audit_id}").get_data(as_text=True).split()
        )
        assert "asks for this apartment likely fall in" in html, audit_id
        assert "That middle 80% is the likely ask range above" in html


def test_a_missing_noise_group_leaves_the_range_out(atoms_root, atoms_client):
    current = (atoms_root / "current").resolve()
    noise = json.loads((current / ranges.NOISE_FILE).read_text())
    del noise["groups"]["1"]
    (current / ranges.NOISE_FILE).write_text(json.dumps(noise))
    detail._open.clear()
    detail._cached_ranges.cache_clear()
    rows = summary_rows()
    # a2 is in group 1, a3 in group 0.
    assert rows[1]["audit_id"] == "a2" and rows[2]["audit_id"] == "a3"
    html = " ".join(atoms_client.get("/listings/a2").get_data(as_text=True).split())
    assert "95% sure the typical rent itself is" in html
    assert "likely fall in" in " ".join(
        atoms_client.get("/listings/a3").get_data(as_text=True).split()
    )


def test_a_build_without_atoms_has_no_ranges_file(site_root):
    assert not (site_root / "current" / detail.RANGES_FILE).exists()
    assert detail.likely_ask((site_root / "current").resolve(), "x", "a1") is None
