import json
import math

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest
from models import bayesian_feature_report as m
from tests.test_bayesian_feature_report import (
    experiment,
    v3_fixture,
    rewrite_v3,
    publish_binary,
    diagnostics,
    interval,
)


@pytest.fixture
def floor_fit(experiment):
    root, source, protocol, files, _ = v3_fixture(experiment, "shared")
    rows = m.jsonl((source / "observations.jsonl").read_bytes())
    for row, floor in zip(rows, (1, 3, 8, None)):
        row.update(listed_floor=None, advertised_floor=floor)
    sm = publish_binary(
        source,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": "reviewed-scope-composition-projection-v2"},
    )
    common = {
        "floor_levels": [1.0, 3.0, 8.0],
        "floor_thresholds": [1.0, 3.0],
        "floor_increment_prior_scale": 0.15,
    }
    protocol.update(
        common,
        version=m.EXPERIMENT_V4,
        feature_design_version="observed-listed-floor-increment-design-v1",
        source_manifest_sha256=digest(source / "complete.json"),
        source_observations_sha256=sm["files"]["observations.jsonl"],
    )
    design = json.loads(files["feature-design.json"])
    design.update(common, version=protocol["feature_design_version"])
    design["features"] = [n for n in design["features"] if n != "listed_floor"] + [
        "listed_floor_gt_1",
        "listed_floor_gt_3",
    ]
    design["numeric"] = {}
    design["support"]["features"] = len(design["features"])
    files["feature-design.json"] = canonical(design) + "\n"
    files["coefficients.json"] = (
        canonical([{"feature": name, **interval()} for name in design["features"]])
        + "\n"
    )
    floors = {
        "version": "joint-listed-floor-component-contrasts-v1",
        "floor_levels": common["floor_levels"],
        "floor_thresholds": common["floor_thresholds"],
        "draws": 4000,
        "diagnostics": diagnostics(),
        "interpretation": m.FLOOR_INTERPRETATION,
        "contrasts": [],
    }
    for i, (lo, hi) in enumerate(((1.0, 3.0), (3.0, 8.0), (1.0, 8.0))):
        effect = interval(0.1)
        floors["contrasts"].append(
            {
                "lower_floor": lo,
                "upper_floor": hi,
                "support_lower": {"level": lo, "rows": 1, "units": 1, "buildings": 1},
                "support_upper": {"level": hi, "rows": 1, "units": 1, "buildings": 1},
                "kind": "adjacent_observed_levels" if i < 2 else "observed_range",
                "adjacent_overlap": {
                    "lower_supported_level": lo,
                    "upper_supported_level": hi,
                    "shared_buildings": 1 if i == 0 else 0,
                    "shared_units": 0,
                }
                if i < 2
                else None,
                "log_effect": effect,
                "percent_effect": {
                    **effect,
                    **{
                        b: 100 * math.expm1(effect[b])
                        for b in ("lower_95", "median", "upper_95")
                    },
                },
            }
        )
    summary = json.loads(files["summary.json"])
    summary.update(
        design_support=design["support"], floor_diagnostics=floors["diagnostics"]
    )
    files["summary.json"] = canonical(summary) + "\n"
    files["floor-contrasts.json"] = canonical(floors) + "\n"
    rewrite_v3(root, protocol, files)
    return root, source, protocol, files, floors, rows, design, summary


def test_v4_report_binds_floor_aliases_support_gaps_and_html(floor_fit):
    root, source, *_ = floor_fit
    result, _ = m.build_report(root, source)
    assert result["experiment_version"] == m.EXPERIMENT_V4
    assert result["floors"]["floor_levels"] == [1, 3, 8]
    assert len(result["floors"]["contrasts"]) == 3
    assert result["method"]["floor_increment_prior_scale"] == 0.15
    html = m.html_report(result)
    assert "Listed-floor increments" in html and "3 → 8" in html
    assert "Shared buildings at adjacent endpoints" in html


@pytest.mark.parametrize(
    "mutation",
    [
        "levels",
        "prior",
        "linear",
        "missing_contrast",
        "endpoint_count",
        "overlap",
        "gate",
        "percentage",
        "draws",
    ],
)
def test_rehashed_floor_contradictions_fail(floor_fit, mutation):
    root, source, protocol, files, floors, rows, design, summary = floor_fit
    if mutation == "levels":
        protocol["floor_levels"] = [1, 2, 8]
    elif mutation == "prior":
        protocol["floor_increment_prior_scale"] = 0.05
    elif mutation == "linear":
        design["features"].append("listed_floor")
    elif mutation == "missing_contrast":
        floors["contrasts"].pop()
    elif mutation == "endpoint_count":
        floors["contrasts"][0]["support_lower"]["rows"] = 2
    elif mutation == "overlap":
        floors["contrasts"][0]["adjacent_overlap"]["shared_buildings"] = 0
    elif mutation == "gate":
        floors["diagnostics"]["max_rhat"] = 1.02
    elif mutation == "percentage":
        floors["contrasts"][0]["percent_effect"]["median"] += 1
    elif mutation == "draws":
        floors["draws"] -= 1
    summary["floor_diagnostics"] = floors["diagnostics"]
    files.update(
        {
            "floor-contrasts.json": canonical(floors) + "\n",
            "feature-design.json": canonical(design) + "\n",
            "summary.json": canonical(summary) + "\n",
        }
    )
    rewrite_v3(root, protocol, files)
    with pytest.raises(ValueError):
        m.build_report(root, source)


def test_missing_floor_product_rejected(floor_fit):
    root, source, protocol, files, *_ = floor_fit
    del files["floor-contrasts.json"]
    rewrite_v3(root, protocol, files)
    with pytest.raises(ValueError, match="missing inference"):
        m.build_report(root, source)
