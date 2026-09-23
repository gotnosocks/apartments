from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from models import amenity_contrast_bootstrap as boot


def sample():
    rows = []
    for building in range(5):
        for unit in range(3):
            for year in (2018, 2019):
                rows.append(
                    {
                        "building": f"b{building}",
                        "building_id": f"b{building}",
                        "unit_id": f"b{building}:u{unit}",
                        "audit_id": f"{building}-{unit}-{year}",
                        "period": pd.Timestamp(year, 1, 1),
                        "bedrooms": 1.0,
                        "bathrooms": 1.0,
                        "square_feet": 600.0,
                        "laundry_type": ("in_building", "in_unit", None)[unit],
                        "asking_rent": 3000.0 + 100 * unit,
                        "log_rent": np.log(3000.0 + 100 * unit),
                    }
                )
    return pd.DataFrame(rows)


def protocol(frame):
    return boot.prepare_protocol(
        frame,
        {"settings": boot.model.SETTINGS, "unit_effect": True},
        draws=200,
        seed=123,
    )


def test_duplicate_draw_copies_keep_all_rows_independent_ids_and_source_provenance():
    source = sample()
    before = source.copy(deep=True)
    drawn, selection = boot.resample_clusters(source, ["b0", "b0", "b2"], replicate=7)
    assert len(drawn) == 18  # No unit-month dedup after resampling.
    assert drawn.building.nunique() == 3 and drawn.unit_id.nunique() == 9
    assert (
        drawn[boot.SOURCE_BUILDING].nunique() == 2
        and drawn[boot.SOURCE_UNIT].nunique() == 6
    )
    assert drawn.audit_id.value_counts().max() == 2
    assert not set(drawn[drawn[boot.COPY_POSITION] == 0].unit_id) & set(
        drawn[drawn[boot.COPY_POSITION] == 1].unit_id
    )
    assert selection[0]["source_building"] == selection[1]["source_building"] == "b0"
    assert selection[0]["sampled_building"] != selection[1]["sampled_building"]
    pd.testing.assert_frame_equal(source, before)


def test_draws_are_stable_independent_of_vocabulary_order_and_other_replicates():
    buildings = list("abcdef")
    first = boot.draw_buildings(buildings, 123, 9)
    boot.draw_buildings(buildings, 123, 100)
    assert first == boot.draw_buildings(list(reversed(buildings)), 123, 9)
    assert len(first) == len(buildings)
    assert first != boot.draw_buildings(buildings, 123, 10)


def test_fit_records_absent_categories_and_centered_contrasts():
    frame = boot.prepare_frame(sample())
    result, draw = boot.fit_replicate(frame, protocol(frame), 0)
    assert result["status"] == "converged"
    assert result["contrasts"][0]["status"] == "estimated"
    assert result["contrasts"][0]["centering_cancellation_error"] < 1e-12
    assert all(
        c["status"] == "absent_category" and c["log_difference"] is None
        for c in result["contrasts"][1:]
    )
    assert len(draw) == 5 and result["sampled_unit_months"] == 30
    assert result["encoder"]["amenity_active_columns"]
    assert result["stationarity_diagnostic"]["relative_infinity_norm"] < 1e-4


def test_failed_replicate_is_explicit_not_zero_or_replaced(monkeypatch):
    frame = boot.prepare_frame(sample())

    def fail(*args, **kwargs):
        raise RuntimeError("simulated numerical failure")

    monkeypatch.setattr(boot.baseline, "fit", fail)
    result, _ = boot.fit_replicate(frame, protocol(frame), 3)
    assert result["status"] == "fit_failed"
    assert result["error"]["message"] == "simulated numerical failure"
    assert result["contrasts"][0]["status"] == "fit_failed"
    assert result["contrasts"][0]["log_difference"] is None
    assert result["contrasts"][1]["status"] == "absent_category"


def test_summary_keeps_failed_and_absent_denominators():
    frame = boot.prepare_frame(sample())
    p = protocol(frame)
    record, _ = boot.fit_replicate(frame, p, 2)
    results = [deepcopy(record) for _ in range(20)]
    for i, r in enumerate(results):
        r["replicate"] = i
        r["contrasts"][0]["log_difference"] = 0.01 + i * 0.001
    failed = deepcopy(record)
    failed["status"] = "fit_failed"
    failed["contrasts"][0].update(
        status="fit_failed", log_difference=None, percent_difference=None
    )
    results.append(failed)
    summary = boot.summarize(results, p)
    assert (
        summary["completed_replicates"] == 21 and summary["planned_replicates"] == 200
    )
    contrast = summary["contrasts"][0]
    assert contrast["available_estimates"] == 20
    assert contrast["status_counts"] == {"estimated": 20, "fit_failed": 1}
    assert contrast["positive_fraction_among_available"] == 1
    assert contrast["approximate_replicates_in_each_2_5_percent_tail"] == 0.5
    assert summary["contrasts"][1]["available_estimates"] == 0
    assert summary["contrasts"][1]["percentile_percent_difference_2_5_50_97_5"] is None


def test_worker_checkpoints_match_protocol_and_deterministic_fit(tmp_path):
    frame = boot.prepare_frame(sample())
    p = protocol(frame)
    boot._worker_init(frame, p, tmp_path)
    assert boot._worker(2) == (2, "converged")
    manifest, files = boot._verified_bundle(
        tmp_path / "replicates" / "00002", retain={"result.json"}
    )
    assert manifest["protocol_sha256"] == boot._hash(p)
    assert boot._worker(2) == (2, "converged")
    assert boot._verified_bundle(
        tmp_path / "replicates" / "00002", retain={"result.json"}
    ) == (manifest, files)


def test_checkpoint_copied_to_wrong_replicate_is_rejected(tmp_path):
    import shutil

    frame = boot.prepare_frame(sample())
    p = protocol(frame)
    boot._worker_init(frame, p, tmp_path)
    boot._worker(2)
    path = tmp_path / "replicates" / "00002"
    assert boot.read_checkpoint(path, frame, p, 2)["replicate"] == 2
    copied = tmp_path / "replicates" / "00003"
    shutil.copytree(path, copied)
    with pytest.raises(ValueError, match="identity/seed/draw/count"):
        boot.read_checkpoint(copied, frame, p, 3)
