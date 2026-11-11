"""Where a listing's ask is likely to fall (the predictive interval), when the
bundle has it; the range for the typical rent otherwise."""

import sqlite3

from apartments.site import build


def test_the_build_reads_the_bundle_fields():
    row = {"estimate_pred_lower_80": 100.0, "estimate_pred_upper_80": float("nan")}
    assert build._real(row.get("estimate_pred_lower_80")) == 100.0
    assert build._real(row.get("estimate_pred_upper_80")) is None
    assert build._real(row.get("estimate_pred_lower_95")) is None
    assert build.SCHEMA_VERSION == 5
