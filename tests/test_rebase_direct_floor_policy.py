from copy import deepcopy

import pytest

from apartments.reviewed_cohort_quarantine import sha
from docs.analysis.scripts.rebase_direct_floor_policy import rebase_cases


@pytest.mark.parametrize(
    "fault", [None, "price", "order", "floor_removed", "extra_removed", "no_removal"]
)
def test_rebase_only_unchanged_reviewed_rows(fault):
    before = [
        {"audit_id": str(i), "source_listing_id": ad, "rent": 3000}
        for i, ad in enumerate(["1", "2938067", "2", "3"])
    ]
    policy = {
        "source_manifest_sha256": "old",
        "cases": [
            {
                "audit_id": "0",
                "source_row_sha256": sha(before[0]),
                "witnesses": [{"capture_id": 1}],
            }
        ],
    }
    after = deepcopy([before[0], before[2], before[3]])
    if fault == "price":
        after[1]["rent"] = 1
    if fault == "order":
        after.reverse()
    if fault in ("floor_removed", "extra_removed"):
        after.pop(0 if fault == "floor_removed" else -1)
    if fault == "no_removal":
        after = deepcopy(before)
    saved = deepcopy((policy, before, after))
    if fault:
        with pytest.raises(ValueError):
            rebase_cases(policy, before, after, "new")
    else:
        result = rebase_cases(policy, before, after, "new")
        assert result == {**policy, "source_manifest_sha256": "new"}
        result["cases"][0]["witnesses"][0]["capture_id"] = 2
    assert (policy, before, after) == saved
