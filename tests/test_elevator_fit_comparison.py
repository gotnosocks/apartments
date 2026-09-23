from copy import deepcopy
import json

import numpy as np
import pytest
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import elevator_fit_comparison as m
from models.bayesian_floor_increment_design import FeatureDesign
from tests.test_bayesian_category_contrasts import training
from tests.test_elevator_correction_projection import fixture, extend
from tests.test_quarantine_fit_comparison import protocols as previous_protocols


def protocols():
    _, a = previous_protocols()
    b = deepcopy(a)
    b["source_version"] = m.correction.VERSION
    b["implementation_sha256"]["elevator_corrections.py"] = "new"
    b["implementation_sha256"]["reviewed_source_lineage.py"] = "revised"
    return a, b


@pytest.mark.parametrize(
    "fault",
    [None, "rows", "draws", "prior", "math", "extra", "missing", "source", "storage"],
)
def test_protocol_changes_are_confined_to_verified_source_readers(fault):
    a, b = protocols()
    if fault == "rows":
        b["rows"] = 15
    elif fault == "draws":
        b["draws"] = 50
    elif fault == "prior":
        b["prior_multiplier"] = 2
    elif fault == "math":
        b["implementation_sha256"]["math.py"] = "changed"
    elif fault == "extra":
        b["implementation_sha256"]["extra.py"] = "added"
    elif fault == "missing":
        del b["implementation_sha256"]["elevator_corrections.py"]
    elif fault == "source":
        b["source_version"] = m.correction.PARENT
    elif fault == "storage":
        b["storage_policy"]["all_retained_draws"] = False
    if fault:
        with pytest.raises(ValueError):
            m.check_protocols(a, b)
    else:
        assert m.check_protocols(a, b) == ["reviewed_source_lineage.py"]


@pytest.mark.parametrize("fault", [None, "unrelated", "parent"])
def test_published_revision_has_exact_inverse_and_no_membership_or_price_change(
    tmp_path, fault
):
    row, *_ = fixture()
    parent, child = tmp_path / "parent", tmp_path / "child"
    publish_bundle(
        parent,
        {"observations.jsonl": canonical(row) + "\n"},
        {"version": m.correction.PARENT},
    )
    manifest = json.loads((parent / "complete.json").read_text())
    revised_manifest, rows, changes = extend(manifest, [row], index=0)
    if fault == "unrelated":
        rows[0]["asking_rent"] = 9999
    if fault == "parent":
        revised_manifest["source_manifest_sha256"] = "wrong"
    publish_bundle(
        child,
        {
            "observations.jsonl": "".join(canonical(r) + "\n" for r in rows),
            m.correction.SIDECAR: "".join(canonical(r) + "\n" for r in changes),
        },
        {k: v for k, v in revised_manifest.items() if k != "files"},
    )
    if fault:
        with pytest.raises(ValueError):
            m.verify_revision(parent, child)
    else:
        before, after, edits = m.verify_revision(parent, child)
        assert before == [row] and after == rows and len(edits) == 1


def designs():
    before = training()
    before["elevator"] = ([True] * 6 + [False] * 3 + [None]) * 24
    before["advertised_floor"] = np.arange(len(before)) % 5 + 1
    after = before.copy()
    after.loc[0, "elevator"] = False
    after.loc[1, "elevator"] = None
    return [
        {"design": FeatureDesign(frame), "data": frame} for frame in (before, after)
    ]


@pytest.mark.parametrize(
    "fault", [None, "price_feature", "centering", "prior", "category"]
)
def test_only_elevator_design_columns_change(fault):
    a, b = designs()
    if fault == "price_feature":
        b["data"].loc[0, "square_feet"] *= 2
    elif fault == "centering":
        b["design"].means[0] += 0.1
    elif fault == "prior":
        b["design"].prior_scales[0] *= 2
    elif fault == "category":
        b["design"].categories["laundry_type"]["frequencies"][0] += 0.01
    if fault:
        with pytest.raises(ValueError):
            m.check_designs(a, b)
    else:
        m.check_designs(a, b)


def test_raw_elevator_and_missingness_scenarios_have_correct_units_and_prior_variance():
    a, b = designs()
    output = [m.elevator_vectors(f["design"], f["data"]) for f in (a, b)]
    for fit, vectors in zip((a, b), output):
        d = fit["design"]
        center, scale = [d.numeric["elevator"][k] for k in ("center", "scale")]
        i, j = [d.features.index(k) for k in ("elevator", "elevator.unknown")]
        np.testing.assert_allclose(
            np.array([v["design_vector"] for v in vectors])[:, [i, j]],
            [[1 / scale, 0], [center / scale, 1], [(center - 1) / scale, 1]],
        )
        assert vectors[0]["raw_contrast_prior_sd"] == pytest.approx(0.15 / scale)
        assert vectors[1]["raw_contrast_prior_sd"] == pytest.approx(
            np.hypot(0.15 * center / scale, 0.2)
        )
        assert vectors[0]["support_before"]["rows"] == int(
            fit["data"].elevator.eq(False).sum()
        )
        assert vectors[1]["support_after"]["rows"] == int(
            fit["data"].elevator.isna().sum()
        )
    assert (
        output[0][0]["raw_contrast_prior_sd"] != output[1][0]["raw_contrast_prior_sd"]
    )


@pytest.mark.parametrize("fault", [None, "unmixed", "coordinates", "draw_count"])
def test_all_joint_draws_preserve_elevator_missingness_covariance(tmp_path, fault):
    fit, _ = designs()
    design = fit["design"]
    rng = np.random.default_rng(211)
    beta = rng.normal(0, 0.01, size=(4, 1000, len(design.features)))
    i, j = [design.features.index(k) for k in ("elevator", "elevator.unknown")]
    beta[:, :, i] = rng.normal(0, 0.2, size=(4, 1000))
    c = design.numeric["elevator"]["center"] / design.numeric["elevator"]["scale"]
    beta[:, :, j] = -0.99 * c * beta[:, :, i] + rng.normal(0.1, 0.001, size=(4, 1000))
    if fault == "unmixed":
        beta[0, :, i] += 10
    coords = design.features[::-1] if fault == "coordinates" else design.features
    p = xr.Dataset(
        {"beta": (("chain", "draw", "feature"), beta)}, coords={"feature": coords}
    )
    (tmp_path / "fit").mkdir()
    p.to_netcdf(tmp_path / "fit/posterior.nc", group="posterior", engine="h5netcdf")
    fit.update(
        root=tmp_path,
        protocol={
            "chains": 4,
            "draws": 50 if fault == "draw_count" else 1000,
            "prior_multiplier": 2,
        },
    )
    if fault:
        with pytest.raises(ValueError):
            m.elevator_contrasts(fit)
    else:
        result = m.elevator_contrasts(fit)
        expected = (c * beta[:, :, i] + beta[:, :, j]).ravel()
        np.testing.assert_allclose(
            [result[1]["log_effect"][k] for k in ("lower_95", "median", "upper_95")],
            np.quantile(expected, [0.025, 0.5, 0.975]),
        )
        assert result[0]["raw_contrast_prior_sd"] == pytest.approx(
            0.3 / design.numeric["elevator"]["scale"]
        )
