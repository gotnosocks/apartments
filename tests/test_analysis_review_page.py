"""UI contracts: residual selection and supported/unsupported feature contrasts."""
from pathlib import Path
import sys
from types import ModuleType

import pytest

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "pages/2_Contributions_and_Residuals.py"


@pytest.fixture
def review_page(monkeypatch, request):
    import math

    class Workspace:
        fields = {
            "bedrooms": {"label": "Bedrooms", "kind": "numeric", "minimum": 0, "maximum": 5, "step": 1},
            "laundry_type": {"label": "Laundry", "kind": "category", "options": ["in_unit", "shared"]},
        }
        summary = {"purpose": "in-sample diagnostic"}
        calls = []
        source_captures = []
        rows = [{"audit_id": "current", "bedrooms": 1, "laundry_type": None},
                {"audit_id": "history", "bedrooms": 2, "laundry_type": "shared"}]
        residuals = [{
            "audit_id": audit_id, "unit_id": f"unit-{audit_id}", "building_id": "example-building",
            "source_listing_id": str(i), "period": "2026-09-01", "current_capture": current,
            "asking_rent": ask, "fitted_rent": 4000, "asking_minus_fitted": ask - 4000,
            "asking_vs_fitted_percent": (ask / 4000 - 1) * 100,
            "absolute_log_residual": abs(math.log(ask / 4000)), "group_adjustment_percent": 0,
        } for i, (audit_id, current, ask) in enumerate((("current", True, 4400), ("history", False, 3000)))]

        @classmethod
        def load(cls, *paths):
            return cls()

        def detail(self, audit_id):
            row = next(row for row in self.rows if row["audit_id"] == audit_id)
            residual = next(row for row in self.residuals if row["audit_id"] == audit_id)
            return {"source_record": row, "feature_values": row, "residual": residual, "log_components": {"reference": math.log(4000)},
                    "log_contributions_by_family": {"reference": math.log(4000)},
                    "unit_history": [residual], "warnings": [], "provenance": {"snapshot": "verified"},
                    "source_captures": self.source_captures}

        def contrast(self, audit_id, changes):
            self.calls.append((audit_id, changes))
            unsupported = "laundry_type" in changes
            return {"show_estimate": not unsupported, "status": "unknown_reference" if unsupported else "computed",
                    "estimate": {"baseline_rent": 4000, "changed_rent": 4500, "dollar_change": 500, "percent_change": 12.5},
                    "warnings": ["Recorded laundry is unknown."] if unsupported else [],
                    "support": [{"field": "bedrooms", "known_rows": 10}], "held_fixed": ["unit", "building", "date"]}

        def factor_support(self):
            return [{"field": "bedrooms", "known_rows": 10}]

    module = ModuleType("apartments.analysis_review")
    module.AnalysisWorkspace = Workspace
    module.bundle_signature = lambda *paths: request.node.nodeid
    monkeypatch.setitem(sys.modules, "apartments.analysis_review", module)
    page = AppTest.from_file(str(PAGE)).run(timeout=20)
    assert not page.exception
    return page, Workspace


def select(page, label):
    return next(item for item in page.selectbox if item.label == label)


def test_review_defaults_to_saved_current_then_filters_negative_history(review_page):
    page, _ = review_page
    assert select(page, "Observation to inspect").value == "current"
    select(page, "Observation scope").select("All fitted observations").run()
    select(page, "Review order").select("Ask below fitted rent").run()
    assert not page.exception
    assert select(page, "Observation to inspect").value == "history"
    assert any(metric.value == "$-1,000" for metric in page.metric)


def test_supported_feature_change_shows_conditional_estimate(review_page):
    page, workspace = review_page
    page.multiselect[0].set_value(["bedrooms"]).run()
    page.number_input[0].set_value(2)
    next(button for button in page.button if button.label == "Compare with recorded apartment").click().run()
    assert not page.exception
    assert workspace.calls == [("current", {"bedrooms": 2.0})]
    assert any(metric.label == "Changed apartment: fitted rent" and metric.value == "$4,500" for metric in page.metric)


def test_unknown_joint_comparison_suppresses_dollar_estimate(review_page):
    page, workspace = review_page
    page.multiselect[0].set_value(["bedrooms", "laundry_type"]).run()
    page.number_input[0].set_value(2)
    select(page, "Laundry").select("in_unit")
    next(button for button in page.button if button.label == "Compare with recorded apartment").click().run()
    assert not page.exception
    assert workspace.calls == [("current", {"bedrooms": 2.0, "laundry_type": "in_unit"})]
    assert not any(metric.label == "Changed apartment: fitted rent" for metric in page.metric)
    assert any("Recorded laundry is unknown" in item.value for item in page.warning)


def test_archived_description_is_plain_text_with_capture_provenance(review_page):
    page, workspace = review_page
    assert any("No matching archived description" in item.value for item in page.info)
    workspace.source_captures = [{"capture_id": 42, "description": "Terrace <script>alert('source')</script>",
                                 "source_collected_at": "2026-09-18T12:00:00+00:00",
                                 "description_interpreted_at": "2026-09-18T13:00:00+00:00", "body_sha256": "a" * 64}]
    page.run()
    assert not page.exception
    assert page.text[0].value == "Terrace <script>alert('source')</script>"
    assert "Capture 42" in select(page, "Saved capture").options[0]
    assert any("a" * 64 in item.value for item in page.json)


@pytest.mark.skipif(not (PAGE.parents[1] / "data/model/chelsea-reviewed-analysis-20260918-v3/model/complete.json").exists(),
                    reason="Local verified Chelsea analysis is not present")
def test_saved_analysis_page_end_to_end(tmp_path):
    """Exercise the real frozen model, not only synthetic UI responses."""
    page = AppTest.from_file(str(PAGE)).run(timeout=90)
    assert not page.exception
    assert next(metric.value for metric in page.metric if metric.label == "Saved current observations") == "13"
    next(item for item in page.text_input if item.label == "Find advertisement ID or unit URL").set_value("5155651").run()
    assert any(len(item.value) > 100 for item in page.text)
    next(item for item in page.text_input if item.label == "Find advertisement ID or unit URL").set_value("5153890").run()
    assert "5153890" in select(page, "Observation to inspect").options[0]
    assert any(len(item.value) > 100 for item in page.text)
    page.multiselect[0].set_value(["laundry_type"]).run()
    assert select(page, "Laundry").value == "in_unit"
    select(page, "Laundry").select("in_building")
    next(button for button in page.button if button.label == "Compare with recorded apartment").click().run()
    assert not page.exception
    assert any(metric.label == "Changed apartment: fitted rent" for metric in page.metric)
    select(page, "Laundry").select("in_unit")
    next(button for button in page.button if button.label == "Compare with recorded apartment").click().run()
    assert any("different from the observation" in item.value for item in page.error)
    assert not any(metric.label == "Changed apartment: fitted rent" for metric in page.metric)
    page.multiselect[0].set_value(["physical_floor"]).run()
    page.number_input[0].set_value(4)
    next(item for item in page.checkbox if item.label == "Floors above ground is unknown").uncheck()
    next(button for button in page.button if button.label == "Compare with recorded apartment").click().run()
    assert not page.exception
    assert not any(metric.label == "Changed apartment: fitted rent" for metric in page.metric)
    assert any("fewer than two observed known values" in item.value for item in page.warning)
    next(item for item in page.text_input if item.label == "Model bundle").set_value(str(tmp_path / "missing-model")).run()
    assert not page.exception
    assert any("saved analysis could not be loaded" in item.value for item in page.error)
