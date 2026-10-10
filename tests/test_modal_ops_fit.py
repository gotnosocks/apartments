import datetime
import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

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


def test_a_fit_waits_for_its_dollars_and_an_overrun_leaves_the_balance_negative(
    tmp_path,
):
    ledger = tmp_path / "ledger.jsonl"
    usd = cap.estimate(*cap.SERVED_FIT)
    per_fit = datetime.timedelta(days=1) / 10  # the balance accrues 10 full fits a day
    t0 = cap.START + per_fit
    launch, left = cap.reserve("run-0", "A100-40GB", usd, ledger, t0)
    assert left == pytest.approx(0, abs=0.01)
    with pytest.raises(cap.CapReached):  # spent: the next fit waits for its estimate
        cap.reserve("run-1", "A100-40GB", usd, ledger, t0 + per_fit / 2)
    # It ran over by $0.50: accrual continues from the negative balance.
    cap.settle(launch, usd + 0.5, ledger, t0)
    rows = cap.launches(ledger)
    assert cap.balance(rows, t0) == pytest.approx(-0.5, abs=0.01)
    ready = cap.ready_at(rows, usd, t0)
    assert ready - t0 == pytest.approx(
        per_fit * (1 + 0.5 / usd), abs=datetime.timedelta(minutes=1)
    )
    with pytest.raises(cap.CapReached):
        cap.reserve(
            "run-1", "A100-40GB", usd, ledger, ready - datetime.timedelta(minutes=2)
        )
    # A cheaper exploration fit spends less; across midnight ET, in any zone.
    cap.reserve("run-1", "A100-40GB", usd, ledger, ready.astimezone(datetime.UTC))
    assert [row["name"] for row in cap.launches(ledger) if "kind" not in row] == [
        "run-0",
        "run-1",
    ]
    assert cap.estimate(2, 100, 600) < cap.estimate(2, 300, 3600) < usd


def test_launches_before_the_budget_began_are_not_charged(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    before = cap.START - datetime.timedelta(hours=1)
    launch, _ = cap.reserve("old", "A100-40GB", 0, ledger, before)
    cap.settle(launch, 5.0, ledger, cap.START + datetime.timedelta(hours=1))
    rows = cap.launches(ledger)
    assert cap.balance(rows, cap.START) == 0
    assert cap.balance(rows, cap.START + datetime.timedelta(days=1)) == pytest.approx(
        cap.RATES[0][1]
    )


def test_a_retry_of_a_run_is_charged_as_its_own_launch(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    day = cap.START + datetime.timedelta(days=1)
    first, _ = cap.reserve("run", "A100-40GB", 0.8, ledger, day)
    cap.settle(first, 0.3, ledger, day)
    cap.reserve("run", "A100-40GB", 0.8, ledger, day + datetime.timedelta(seconds=1))
    # A row from the old launcher, after START, counts as a served full fit.
    old = {"day": "x", "at": day.isoformat(), "name": "o", "gpu": "A100-40GB"}
    with ledger.open("a") as f:
        f.write(json.dumps(old) + "\n")
    assert cap.balance(cap.launches(ledger), day) == pytest.approx(
        cap.RATES[0][1] - 0.3 - 0.8 - cap.estimate(*cap.SERVED_FIT), abs=0.01
    )


def test_ten_served_fits_a_day_at_the_container_list_price(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    assert {
        gpu: round(app.usd_per_second(gpu) * 3600, 4) for gpu in app.FITS
    } == pytest.approx(cap.USD_PER_HOUR, abs=1e-4)
    assert cap.RATES[0][1] == pytest.approx(8.80)
    assert cap.USD_PER_DAY == 10.0


def test_the_pre_check_reads_the_fit_size_from_modal_fit_arguments():
    argv = [
        "--gpu",
        "L4",
        "--input",
        "x",
        "abc",
        "lab",
        "m7",
        "nb3",
        "2",
        "300",
        "4500",
        "9",
    ]
    assert cap.fit_size([*argv, "--sampler", "gibbs"]) == ("2", "300", "4500", "L4")
    assert cap.fit_size(argv[4:]) == ("2", "300", "4500", "A100-40GB")


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


def test_the_balance_stops_at_ten_full_fits_and_restarts_below_it(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    week = cap.START + datetime.timedelta(days=7)
    assert cap.balance([], week) == pytest.approx(cap.CEILING)
    launch, left = cap.reserve("run", "A100-40GB", 1.0, ledger, week)
    assert left == pytest.approx(cap.CEILING - 1.0)
    # Accrual resumes from below the ceiling; a refund can't lift it over.
    hour = datetime.timedelta(hours=1)
    rows = cap.launches(ledger)
    assert cap.balance(rows, week + hour) == pytest.approx(
        cap.CEILING - 1.0 + cap.USD_PER_DAY / 24
    )
    cap.settle(launch, 0.2, ledger, week + hour)
    assert cap.balance(cap.launches(ledger), week + hour) == pytest.approx(cap.CEILING)
    assert cap.ready_at(rows, cap.CEILING + 1, week) is None


def test_the_rate_rose_to_ten_dollars_a_day_without_repricing_the_past():
    change = cap.RATES[1][0]
    hour = datetime.timedelta(hours=1)
    assert cap.accrued(change - hour, change) == pytest.approx(8.80 / 24)
    assert cap.accrued(change, change + hour) == pytest.approx(10.0 / 24)
    assert cap.accrued(change - hour, change + hour) == pytest.approx(18.80 / 24)


def test_time_at_the_old_ceiling_does_not_earn_the_new_one():
    change = cap.RATES[1][0]
    hour = datetime.timedelta(hours=1)
    # No launches: the balance sat at the old $8.80 ceiling until the change.
    assert cap.balance([], change - hour) == pytest.approx(8.80)
    assert cap.balance([], change) == pytest.approx(8.80)
    assert cap.balance([], change + hour) == pytest.approx(8.80 + 10.0 / 24)
    assert cap.balance([], change + 2 * datetime.timedelta(days=1)) == pytest.approx(
        10.0
    )


def test_ready_at_before_start_uses_the_first_rate():
    early = cap.START - datetime.timedelta(days=1)
    assert cap.ready_at([], 1.0, early) is not None


def test_post_fit_statistics_land_whole_beside_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(fit, "STATE", tmp_path / "modal")
    files = {
        "out/r/run/result.json": b"{}",
        "out/r/variance/r-abc1234/result.json": b"{}",
        "out/r/summaries/r-abc1234/rows.parquet": b"x",
        "out/r/summaries/r-abc1234/complete.json": b"{}",
        "out/r/explained/r-trees-abc1234/result.json": b"{}",
        "out/r/fit.log": b"log",
    }
    root = tmp_path / "frontier"
    (root / "variance" / "r-abc1234").mkdir(parents=True)
    (root / "variance" / "r-abc1234" / "result.json").write_text("old")
    fit.finish(FakeVolume(files), "r", {"exit": 0})
    assert (root / "summaries/r-abc1234/complete.json").exists()
    assert (root / "summaries/r-abc1234/rows.parquet").read_bytes() == b"x"
    assert (root / "explained/r-trees-abc1234/result.json").exists()
    # An existing record is kept, and nothing is left half-written.
    assert (root / "variance/r-abc1234/result.json").read_text() == "old"
    assert not list(root.glob("*/*.tmp"))


def test_post_fit_steps_by_tier_and_explain(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    spec = {"name": "r", "tier": "full", "explain": ["a", "b"]}
    assert app.post_steps(spec) == [
        ("variance", ["rentfrontier.variance", "r"]),
        ("summary", ["rentfrontier.summary", "r"]),
        ("explained", ["rentfrontier.explained", "r", "a", "b"]),
    ]
    assert [s for s, _ in app.post_steps({"name": "r", "tier": "exploration"})] == [
        "variance"
    ]
    calls = []

    def run(cmd, env, log, timeout=None):
        calls.append((cmd[2], timeout))
        if cmd[2] == "rentfrontier.summary":
            raise OSError("boom")
        return 0

    monkeypatch.setattr(app, "_run", run)
    now = 1000.0
    monkeypatch.setattr(app.time, "time", lambda: now)
    done = app._post(spec, {}, None, now + 600)
    assert done["variance"]["exit"] == 0 and "boom" in done["summary"]["exit"]
    assert calls[0] == ("rentfrontier.variance", 600)
    assert app._post(spec, {}, None, now + 30)["variance"]["exit"].startswith("skipped")


def test_plan_carries_the_candidate_sets_to_explain():
    args, run_args = fit.parse(
        [
            "--explain",
            "a",
            "--explain",
            "b",
            "c",
            "l",
            "m",
            "f",
            "2",
            "300",
            "4500",
            "1",
        ]
    )
    assert fit.plan(args, run_args, "c" * 40)["explain"] == ["a", "b"]
    assert "--explain" not in fit.plan(args, run_args, "c" * 40)["run_args"]
