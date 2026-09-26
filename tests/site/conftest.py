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


def make_bundle(root: Path, *, gate=True) -> Path:
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    source = dataset / "observations.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in observations()))
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
                "yearbuilt": 1986,
                "numfloors": 20.0,
                "unitsres": 200,
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
    files = {p.name: _sha(p) for p in sorted(bundle.iterdir())}
    record = {
        "version": "frontier-summary-v1",
        "run": "m-test-run",
        "run_commit": "a" * 40,
        "commit": "b" * 40,
        "created_at": "2026-09-26T18:00:00+00:00",
        "dataset": str(dataset),
        "dataset_observations_sha256": _sha(source),
        "data_rules": ["unit-labels-v1"],
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


@pytest.fixture
def client(site_root):
    from apartments.site.web import create_app

    app = create_app(site_root, allowed_hosts=["thelio.example.ts.net"])
    app.config["TESTING"] = True
    return app.test_client()
