import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parents[1] / "ops" / "modal"


def load(name):
    sys.path.insert(0, str(OPS))
    spec = importlib.util.spec_from_file_location(
        f"modal_ops_{name}", OPS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = load("cap")
fit = load("fit")
ET = cap.ZONE


@pytest.fixture(autouse=True)
def no_real_grants(tmp_path, monkeypatch):
    # The repo's grants file names real days; these tests use their own.
    monkeypatch.setattr(cap, "GRANTS", tmp_path / "no-grants.json")


def test_cap_refuses_the_eleventh_launch_of_an_et_day(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    morning = datetime.datetime(2026, 10, 6, 0, 30, tzinfo=ET)
    for i in range(cap.MAX_PER_DAY):
        assert (
            cap.reserve(f"run-{i}", "A100-40GB", ledger, morning)
            == cap.MAX_PER_DAY - i - 1
        )
    with pytest.raises(cap.CapReached):
        cap.reserve("run-10", "A100-40GB", ledger, morning)
    assert len(cap.launches("2026-10-06", ledger)) == cap.MAX_PER_DAY


def test_cap_day_is_new_york_not_utc(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for i in range(cap.MAX_PER_DAY):
        cap.reserve(
            f"run-{i}", "L4", ledger, datetime.datetime(2026, 10, 6, 23, 0, tzinfo=ET)
        )
    # 03:30 UTC on Oct 7 is still Oct 6 in New York: refused.
    with pytest.raises(cap.CapReached):
        cap.reserve(
            "late",
            "L4",
            ledger,
            datetime.datetime(2026, 10, 7, 3, 30, tzinfo=datetime.UTC),
        )
    # Midnight ET starts a new day.
    assert (
        cap.reserve(
            "next", "L4", ledger, datetime.datetime(2026, 10, 7, 0, 0, tzinfo=ET)
        )
        == cap.MAX_PER_DAY - 1
    )


def test_plan_names_runs_like_drive_sh_and_reads_the_tier():
    argv = [
        "abc",
        "fullrun",
        "m7",
        "nb3",
        "2",
        "300",
        "3600",
        "9",
        "--sampler",
        "gibbs",
    ]
    args, rest = fit.parse(argv)
    spec = fit.plan(args, rest, "9371a186d8ca2c33")
    assert spec["name"] == "m7-nb3-rows-9371a18-fullrun"
    assert spec["tier"] == "full"
    assert spec["run_args"][-2:] == ["--sampler", "gibbs"]
    assert spec["run_args"][spec["run_args"].index("--chain-batch") + 1] == "2"
    args, rest = fit.parse([*argv[:8], "--tier", "exploration"])
    assert fit.plan(args, rest, "9371a18")["tier"] == "exploration"
    args, rest = fit.parse(["abc", "x-probe", *argv[2:8]])
    assert fit.plan(args, rest, "9371a18")["tier"] == "exploration"


def test_only_changed_inputs_are_uploaded(tmp_path):
    (tmp_path / "a").write_text("1")
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "b").write_text("2")
    current = dict(fit.files_under([tmp_path / "a", tmp_path / "d"]))
    assert sorted(current) == [str(tmp_path / "a"), str(tmp_path / "d" / "b")]
    assert fit.changed(current, current) == []
    (tmp_path / "d" / "b").write_text("22")
    assert fit.changed(
        current, dict(fit.files_under([tmp_path / "a", tmp_path / "d"]))
    ) == [str(tmp_path / "d" / "b")]


class FakeVolume:
    def __init__(self, files):
        self.files = files
        self.removed = []

    def iterdir(self, path, recursive):
        kind = type("Kind", (), {"name": "FILE"})
        return [
            type("Entry", (), {"path": p, "type": kind})
            for p in self.files
            if p.startswith(path.lstrip("/"))
        ]

    def read_file_into_fileobj(self, path, f):
        f.write(self.files[path])

    def remove_file(self, path, recursive):
        self.removed.append(path)


def test_finish_puts_a_good_run_where_thelio_fits_go_and_a_failed_one_aside(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(fit, "STATE", tmp_path / "modal")
    files = {
        "out/r/run/result.json": b"{}",
        "out/r/loo/r-9371a18/loo.json": b"{}",
        "out/r/fit.log": b"log",
    }
    volume = FakeVolume(files)
    assert fit.finish(volume, "r", {"exit": 0}) == tmp_path / "frontier"
    assert (tmp_path / "frontier/runs/r/result.json").exists()
    assert (tmp_path / "frontier/loo/r-9371a18/loo.json").exists()
    assert (tmp_path / "frontier/runs/r/modal/fit.log").read_text() == "log"
    assert (tmp_path / "frontier/runs/r/modal/modal.json").exists()
    assert volume.removed == ["/out/r"]
    assert fit.finish(FakeVolume(files), "r", {"exit": 1}) == tmp_path / "modal/failed"
    assert (tmp_path / "modal/failed/runs/r/modal/fit.log").exists()


def test_a_grant_from_ben_raises_one_days_cap(tmp_path):
    grants = tmp_path / "grants.json"
    grants.write_text(
        json.dumps({"2026-10-06": {"extra": 2, "by": "Ben", "words": "+2"}})
    )
    ledger = tmp_path / "ledger.jsonl"
    day = datetime.datetime(2026, 10, 6, 9, tzinfo=cap.ZONE)
    for i in range(cap.MAX_PER_DAY + 2):
        cap.reserve(f"run-{i}", "A100-40GB", ledger, day, grants)
    with pytest.raises(cap.CapReached):
        cap.reserve("one-more", "A100-40GB", ledger, day, grants)
    assert cap.limit("2026-10-06", grants) == cap.MAX_PER_DAY + 2
    assert cap.limit("2026-10-07", grants) == cap.MAX_PER_DAY
