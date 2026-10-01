"""A tiny summary bundle, dataset and registry in the shape of the real ones."""

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

TERMS = ["market", "bedrooms", "building", "unit"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parquet(path: Path, rows: list[dict]) -> None:
    source = path.with_suffix(".jsonl")
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    connection = duckdb.connect()
    connection.execute(
        f"COPY (SELECT * FROM read_json_auto('{source}')) TO '{path}' (FORMAT parquet)"
    )
    connection.close()
    source.unlink()


# (audit_id, unit, building, url label, period, ask, estimate, in_fit, unit rows,
#  pit, pareto_k, bedrooms, current)
LISTINGS = [
    (
        "a1",
        "u1",
        "the-grove-250-west-19th-street-new_york",
        "11c",
        "2019-03-01",
        3000.0,
        3100.0,
        True,
        3,
        0.40,
        0.1,
        1.0,
        False,
    ),
    (
        "a2",
        "u1",
        "the-grove-250-west-19th-street-new_york",
        "11c",
        "2021-06-01",
        2600.0,
        3050.0,
        False,
        3,
        0.05,
        None,
        1.0,
        False,
    ),
    (
        "a3",
        "u1",
        "the-grove-250-west-19th-street-new_york",
        "11-C",
        "2026-09-01",
        3500.0,
        3400.0,
        True,
        3,
        0.60,
        0.9,
        1.0,
        True,
    ),
    (
        "a4",
        "u2",
        "the-grove-250-west-19th-street-new_york",
        "2a",
        "2024-01-01",
        5200.0,
        4000.0,
        True,
        1,
        0.97,
        0.2,
        2.0,
        False,
    ),
    (
        "a5",
        "u3",
        "134-west-23-street-new_york",
        "4th",
        "2015-05-01",
        2000.0,
        2100.0,
        True,
        2,
        0.45,
        0.0,
        0.0,
        False,
    ),
    (
        "a6",
        "u3",
        "134-west-23-street-new_york",
        "4th",
        "2018-05-01",
        2300.0,
        2250.0,
        True,
        2,
        0.55,
        -0.1,
        0.0,
        False,
    ),
]


# Listings the quarantine-v1 rule leaves out of the bundle: one in a building
# with other listings, one on a page with no others. (audit_id, building,
# label, period, ask, action, reason, evidence)
QUARANTINED = [
    (
        "q1",
        "the-grove-250-west-19th-street-new_york",
        "retail",
        "2016-02-01",
        8500.0,
        "quarantine_nonresidential",
        "A ground-floor retail space.",
        "ground floor retail space",
    ),
    (
        "q2",
        "103-8-avenue-new_york",
        "2l",
        "2017-07-01",
        3295.0,
        "quarantine_location_conflict",
        "MapPLUTO records the lot as an office building with no apartments.",
        "",
    ),
]


def rule_file_lines():
    return [
        {
            "audit_id": audit,
            "unit_id": f"q-{audit}",
            "building": building,
            "unit_label": label.upper(),
            "action": action,
            "evidence": evidence,
            "reason": reason,
            **({} if evidence else {"external_evidence": "MapPLUTO: office (O6)."}),
        }
        for audit, building, label, _, _, action, reason, evidence in QUARANTINED
    ]


def summary_rows():
    rows = []
    for (
        audit,
        unit,
        building,
        _,
        period,
        ask,
        est,
        in_fit,
        unit_rows,
        pit,
        k,
        _,
        _,
    ) in LISTINGS:
        parts = {"market": est * 0.9, "bedrooms": 0.0, "building": est * 0.08}
        parts["unit"] = est - sum(parts.values())
        row = {
            "audit_id": audit,
            "unit_id": unit,
            "building": building,
            "period": period,
            "asking_rent": ask,
            "in_fit": in_fit,
            "unit_fit_rows": unit_rows,
            "estimate": est,
            "estimate_method": "psis" if in_fit else "heldout",
            "estimate_lower_95": est * 0.9,
            "estimate_upper_95": est * 1.1,
            "estimate_median": est * 0.99,
            "residual_usd": ask - est,
            "residual_pct": ask / est - 1,
            "pareto_k": k,
            "pit": pit,
            "fitted_rent": (est + ask) / 2,
            "fitted_rent_lower_95": est * 0.92,
            "fitted_rent_upper_95": est * 1.08,
        }
        for name, value in parts.items():
            lower = 0.0 if name == "bedrooms" else value - 50
            upper = 0.0 if name == "bedrooms" else value + 50
            row[f"{name}_usd"] = value
            row[f"{name}_usd_lower_95"] = lower
            row[f"{name}_usd_upper_95"] = upper
        row["inputs"] = json.dumps({"text:renovated": 1.0, "label:penthouse": 1.0})
        rows.append(row)
    return rows


def observations():
    out = []
    for (
        audit,
        unit,
        building,
        label,
        period,
        ask,
        _,
        _,
        _,
        _,
        _,
        beds,
        current,
    ) in LISTINGS:
        out.append(
            {
                "audit_id": audit,
                "unit_id": f"dataset:{unit}",
                "building": building,
                "canonical_unit_url": f"https://streeteasy.com/building/{building}/{label}",
                "source_listing_id": audit[1:] + "000",
                "asking_rent": ask,
                "period": period,
                "price_at": period + "T00:00:00+00:00",
                "analysis_price_basis": "current_capture_gross_ask"
                if current
                else "historical_initial_own_advertisement_ask",
                "bedrooms": beds,
                "bathrooms": 1.0,
                "reported_full_bathrooms": 1,
                "reported_half_bathrooms": 0,
                "square_feet": 650.0 if audit == "a3" else None,
                "listed_floor": 11 if unit == "u1" else None,
                "label_derived_floor": None,
                "elevator": True,
                "doorman_type": "full_time",
                "laundry_type": "in_unit",
                "hvac_type": None,
                "pet_policy": "not_allowed",
                "view_exposures": {"city": True, "park": None},
                "window_exposures": {"south": True},
                "concession": "<script>alert(1)</script>" if audit == "a3" else None,
                "collected_at": "2026-09-19T00:00:00+00:00" if current else None,
            }
        )
    return out


def quarantined_observations():
    return [
        {
            **observations()[0],
            "audit_id": audit,
            "unit_id": f"dataset:q-{audit}",
            "building": building,
            "canonical_unit_url": f"https://streeteasy.com/building/{building}/{label}",
            "source_listing_id": "9" + audit[1:],
            "asking_rent": ask,
            "period": period,
            "price_at": period + "T00:00:00+00:00",
            "analysis_price_basis": "historical_initial_own_advertisement_ask",
            "concession": None,
        }
        for audit, building, label, period, ask, *_ in QUARANTINED
    ]


def make_bundle(root: Path, *, gate=True, rule_lines=None) -> Path:
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    source = dataset / "observations.jsonl"
    source.write_text(
        "".join(
            json.dumps(r) + "\n" for r in observations() + quarantined_observations()
        )
    )
    external = root / "external"
    external.mkdir()
    _parquet(
        external / "buildings.parquet",
        [
            {
                "building": "the-grove-250-west-19th-street-new_york",
                "label": "250 WEST 19 STREET, New York, NY, USA",
                "bbl": "1007680059",
                "latitude": 40.742,
                "longitude": -73.998,
            },
            {
                "building": "134-west-23-street-new_york",
                "label": "134 WEST 23 STREET, New York, NY, USA",
                "bbl": "1007990001",
                "latitude": 40.743,
                "longitude": -73.994,
            },
        ],
    )
    _parquet(
        external / "pluto.parquet",
        [
            {
                "bbl": "1007680059",
                # As in the MapPLUTO snapshots: numbers stored as strings.
                "yearbuilt": "1986",
                "numfloors": "20.0000000",
                "unitsres": "200",
                "bldgclass": "D9",
                "landmark": None,
                "histdist": None,
            }
        ],
    )
    bundle = root / "summary"
    bundle.mkdir()
    _parquet(bundle / "rows.parquet", summary_rows())
    _parquet(
        bundle / "market.parquet",
        [
            {
                "period": f"{year}-01-01",
                "reference_rent": 3000.0 + 50 * i,
                "reference_rent_lower_95": 2900.0 + 50 * i,
                "reference_rent_upper_95": 3100.0 + 50 * i,
                "reference_rent_deseasoned": 3010.0 + 50 * i,
                "reference_rent_deseasoned_lower_95": 2910.0 + 50 * i,
                "reference_rent_deseasoned_upper_95": 3110.0 + 50 * i,
            }
            for i, year in enumerate(range(2015, 2027))
        ],
    )
    _parquet(
        bundle / "buildings.parquet",
        [
            {
                "building": "the-grove-250-west-19th-street-new_york",
                "fit_rows": 3,
                "fit_units": 2,
                "level_pct": 10.4,
                "level_pct_lower_95": 8.0,
                "level_pct_upper_95": 13.0,
                "trend_pct_per_year": 1.8,
                "trend_pct_per_year_lower_95": 1.6,
                "trend_pct_per_year_upper_95": 2.0,
            },
            {
                "building": "134-west-23-street-new_york",
                "fit_rows": 2,
                "fit_units": 1,
                "level_pct": -3.0,
                "level_pct_lower_95": -9.0,
                "level_pct_upper_95": 2.5,
                "trend_pct_per_year": 0.2,
                "trend_pct_per_year_lower_95": -0.5,
                "trend_pct_per_year_upper_95": 0.9,
            },
        ],
    )
    _parquet(
        bundle / "coefficients.parquet",
        [
            {
                "feature": "bedrooms=2",
                "group": "bedrooms",
                "pct": 30.0,
                "pct_lower_95": 28.0,
                "pct_upper_95": 32.0,
                "probability_positive": 1.0,
            }
        ],
    )
    (bundle / "terms.json").write_text(
        json.dumps(
            [
                {"name": n, "label": n.capitalize(), "description": f"The {n}."}
                for n in TERMS
            ]
        )
    )
    rules = bundle / "data-rule-quarantine-v1.jsonl"
    rules.write_text(
        "".join(
            json.dumps(r) + "\n"
            for r in (rule_file_lines() if rule_lines is None else rule_lines)
        )
    )
    files = {p.name: _sha(p) for p in sorted(bundle.iterdir())}
    record = {
        "version": "frontier-summary-v1",
        "run": "m-test-run",
        "run_commit": "a" * 40,
        "commit": "b" * 40,
        "created_at": "2026-09-26T18:00:00+00:00",
        "dataset": str(dataset),
        "dataset_observations_sha256": _sha(source),
        "data_rules": ["unit-labels-v1", "quarantine-v1"],
        "data_rule_files": {"quarantine-v1": rules.name},
        "feature_set": "unitdesc-v1",
        "feature_sources": {
            "registry": {
                "path": str(external / "buildings.parquet"),
                "sha256": _sha(external / "buildings.parquet"),
            },
            "pluto": {
                "path": str(external / "pluto.parquet"),
                "sha256": _sha(external / "pluto.parquet"),
            },
        },
        "model": {"name": "m-test"},
        "split": "rows",
        "sampler": "nuts",
        "fit_seconds": 745.0,
        "fit_hardware": "Test GPU",
        "fit_started_at": "2026-09-26T05:27:03-0400",
        "draws": 2200,
        "gate": {
            "passes": gate,
            "max_rhat": 1.006,
            "min_ess": 669.0,
            "divergences": 0,
            "group_rhat_max": 1.01,
            "group_rhat_method": "test",
        },
        "psis_loo": {"elpd_loo": 45815.1, "elpd_loo_se": 228.8},
        "rows": len(LISTINGS),
        "rows_in_fit": sum(1 for r in LISTINGS if r[7]),
        "estimate_pareto_k": {"threshold": 0.7, "over_threshold": 1, "max": 0.9},
        "terms": TERMS,
        "files": files,
    }
    (bundle / "complete.json").write_text(json.dumps(record))
    return bundle


@pytest.fixture(name="make_bundle")
def make_bundle_fixture():
    return make_bundle


@pytest.fixture
def bundle(tmp_path):
    return make_bundle(tmp_path / "inputs")


@pytest.fixture
def site_root(tmp_path, bundle):
    from apartments.site import build

    root = tmp_path / "site"
    build.build(bundle, root, scope="Chelsea")
    return root


def research_data():
    """The dashboard build's data.json, in the shape of rentfrontier.dashboard's."""
    served = {
        "id": "m-test/unitdesc-v1/nuts@aaaaaaa",
        "key": "m-test/unitdesc-v1/nuts@aaaaaaa [m-test-run]",
        "design": "m-test",
        "feature_set": "unitdesc-v1",
        "hardware_class": "thelio RTX 2060 SUPER",
        "fit_seconds": 745.0,
        "other_cores": 0.2,
        "grade": "full",
        "passes_checks": True,
        "frontier": True,
        "current_best": True,
        "psis": {
            "delta": 5221.3,
            "delta_se": 120.4,
            "validation": {"heldout_rows": 5264},
        },
        "splits": {"rows": {"run": "m-test-run", "delta": -12.5, "delta_se": 30.1}},
    }
    served["available_at"] = "2026-09-30T08:00:00+00:00"
    served["key"] = served["id"]
    other = dict(
        served,
        id="m-other",
        key="m-other",
        frontier=False,
        current_best=False,
        psis={"delta": 4100.0, "delta_se": 110.0},
        fit_seconds=600.0,
        complexity=12,
        why_not_served="it was fit with no data rules, not the current quarantine-v2",
        available_at="2026-09-25T08:00:00+00:00",
        splits={"rows": {"run": "m-other-run"}},
    )
    failing = dict(
        other,
        id="m-failing",
        key="m-failing",
        passes_checks=False,
        psis={"delta": 5000.0, "delta_se": 100.0},
        why_not_served="it fails the convergence gate",
        splits={"rows": {"run": "m-failing-run"}},
    )
    baseline = dict(
        other,
        id="L0-mean",
        key="L0-mean",
        psis={"delta": -72000.0, "delta_se": 250.0},
        fit_seconds=30.0,
        splits={"rows": {"run": "L0-run"}},
    )
    subset = dict(
        other,
        id="m-subset",
        key="m-subset",
        psis=None,
        splits={"rows": {"run": "m-test-nb-facing-v1-rows-abc-gibbs-2060-nb-tune35"}},
    )
    cpu = dict(other, id="m-cpu", key="m-cpu", hardware_class="thelio CPU")
    entries = [other, served, failing, baseline, subset, cpu]
    for e in entries:
        e.setdefault("complexity", None)
    gpu = "thelio RTX 2060 SUPER"
    return {
        "snapshots": [
            {
                "at": "2026-09-25T08:00:00+00:00",
                "by_class": {
                    gpu: {"best": "m-other", "frontier": ["m-other", "L0-mean"]}
                },
            },
            {
                "at": "2026-09-30T08:00:00+00:00",
                "by_class": {
                    gpu: {"best": served["key"], "frontier": [served["key"], "L0-mean"]}
                },
            },
        ],
        "generated_at": "2026-10-01T11:33:00+00:00",
        "gate": {"rhat": 1.01, "ess": 400, "all_effects_rhat": 1.05},
        "baseline": "m0-base/base-v1/gibbs@5cc0809",
        "entries": entries,
        "milestones": [
            {
                "kind": "pr",
                "at": "2026-09-30T10:00:00+00:00",
                "pr": 90,
                "title": "Older change",
            },
            {
                "kind": "selection",
                "at": "2026-10-01T02:00:00+00:00",
                "model": "m-test",
                "title": "Serve m-test",
            },
            {
                "kind": "pr",
                "at": "2026-10-01T07:24:28+00:00",
                "pr": 97,
                "title": "Newest <b>change</b>",
            },
        ],
    }


@pytest.fixture
def research_file(tmp_path):
    path = tmp_path / "dashboard" / "data.json"
    path.parent.mkdir()
    path.write_text(json.dumps(research_data()))
    return path


@pytest.fixture
def client(site_root, research_file):
    from apartments.site.web import create_app

    app = create_app(
        site_root,
        allowed_hosts=["thelio.example.ts.net"],
        research_data=research_file,
    )
    app.config["TESTING"] = True
    return app.test_client()
