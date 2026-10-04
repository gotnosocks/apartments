import importlib.util
import json
from pathlib import Path

from apartments import discovery_detail_refresh as detail
from apartments import discovery_review
from apartments import rental_discovery as discovery

# Reuse the discovery tests' saved-probe fixture (tests is not a package).
_spec = importlib.util.spec_from_file_location(
    "rental_discovery_fixtures", Path(__file__).with_name("test_rental_discovery.py")
)
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
saved_probe = _fixtures.saved_probe


def test_review_queue_feeds_the_detail_plan_for_every_seed(tmp_path, monkeypatch):
    def fake(url, mode, output, **kw):
        return saved_probe(url, mode, output, terminal=True, **kw)

    monkeypatch.setattr(discovery.capture_probe, "probe", fake)
    result = discovery.run(tmp_path / "run", max_requests=len(discovery.SEEDS))
    assert [s.rsplit("/", 1)[1] for s in discovery.SEEDS] == ["chelsea", "west-chelsea", "west-village"]
    report = Path(result["report_directory"])
    summary = discovery_review.publish(report, tmp_path / "review")
    assert summary["in_scope_advertisements_all_placements"] == 1
    assert set(summary["seeds"]) == {"/for-rent/chelsea", "/for-rent/west-chelsea", "/for-rent/west-village"}
    queue = [json.loads(s) for s in (tmp_path / "review" / "detail-review-queue.jsonl").read_text().splitlines()]
    # The test page carries the same advertisement on every seed, each in scope there.
    assert [len(q["observations"]) for q in queue] == [3]
    plan, _ = detail.prepare(tmp_path / "review", report, tmp_path / "details", max_targets=5)
    assert [t["url"] for t in plan["targets"]] == ["https://streeteasy.com/rental/123"]
    assert plan["max_provider_submissions"] == 3
