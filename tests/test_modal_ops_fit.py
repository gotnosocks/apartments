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
    # The time the balance takes to accrue one served fit's estimate.
    per_fit = datetime.timedelta(days=usd / cap.RATES[0][1])
    t0 = cap.START + per_fit + datetime.timedelta(seconds=1)  # past float rounding
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
    # A row from the old launcher, after START, counts as an NB5 served full fit.
    old = {"day": "x", "at": day.isoformat(), "name": "o", "gpu": "A100-40GB"}
    with ledger.open("a") as f:
        f.write(json.dumps(old) + "\n")
    assert cap.balance(cap.launches(ledger), day) == pytest.approx(
        cap.RATES[0][1] - 0.3 - 0.8 - cap.NB5_SERVED_FIT_USD, abs=0.01
    )


def test_ten_served_fits_a_day_at_the_container_list_price(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    assert {
        gpu: round(app.usd_per_second(gpu) * 3600, 4) for gpu in app.FITS
    } == pytest.approx(cap.USD_PER_HOUR, abs=1e-4)
    assert cap.RATES[0][1] == pytest.approx(8.80)
    # Recalibrating the estimate never reprices the ledger's past.
    assert cap.NB5_SERVED_FIT_USD == 0.88
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
    # A tuning subset is exploration, unless it asks for the full tier.
    args, rest = fit.parse([*argv[:8], "--data-rules", "tune-b35-v1"])
    assert fit.plan(args, rest, "9371a18")["tier"] == "exploration"
    tier = ["--tier", "full", "--data-rules", "tune-holdout-lots-v1"]
    args, rest = fit.parse([*argv[:8], *tier])
    assert fit.plan(args, rest, "9371a18")["tier"] == "full"


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
        "out/r/newbuilding/r-abc1234/rows.parquet": b"x",
        "out/r/newbuilding/r-abc1234/result.json": b"{}",
        "out/r/explained/r-trees-abc1234/result.json": b"{}",
        "out/r/fit.log": b"log",
    }
    root = tmp_path / "frontier"
    (root / "variance" / "r-abc1234").mkdir(parents=True)
    (root / "variance" / "r-abc1234" / "result.json").write_text("old")
    fit.finish(FakeVolume(files), "r", {"exit": 0})
    assert (root / "newbuilding/r-abc1234/result.json").exists()
    assert (root / "newbuilding/r-abc1234/rows.parquet").read_bytes() == b"x"
    assert (root / "explained/r-trees-abc1234/result.json").exists()
    # An existing record is kept, and nothing is left half-written.
    assert (root / "variance/r-abc1234/result.json").read_text() == "old"
    assert not (root / ".incoming").exists()


def test_post_fit_steps_by_tier_and_explain(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    spec = {"name": "r", "tier": "full", "explain": ["a", "b"]}
    steps = app.post_steps(spec)
    # The summary bundle and its calibration are built on thelio (ops/modal/summarize).
    assert [s for s, _ in steps] == ["variance", "explained"]
    assert steps[0][1] == ["rentfrontier.variance", "r"]
    assert steps[1][1] == ["rentfrontier.explained", "r", "a", "b"]
    assert [s for s, _ in app.post_steps({"name": "r", "tier": "exploration"})] == [
        "variance"
    ]
    calls = []

    def run(cmd, env, log, timeout=None):
        calls.append((cmd[2], timeout))
        if cmd[2] == "rentfrontier.explained":
            raise OSError("boom")
        return 0

    monkeypatch.setattr(app, "_run", run)
    now = 1000.0
    monkeypatch.setattr(app.time, "time", lambda: now)
    done = app._post(spec, {}, None, now + 600)
    assert done["variance"]["exit"] == 0 and "boom" in done["explained"]["exit"]
    assert calls[0] == ("rentfrontier.variance", 600)
    assert app._post(spec, {}, None, now + 30)["variance"]["exit"].startswith("skipped")


def test_a_passing_full_row_fit_starts_its_summary_on_thelio(tmp_path, monkeypatch):
    monkeypatch.setattr(fit, "STATE", tmp_path / "modal")
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(fit, "REPO", tmp_path / "repo")
    full = {"name": "r", "tier": "full", "dataset": "/d"}
    assert fit.wants_summary(full, "rows") and fit.wants_summary(full, "all")
    assert not fit.wants_summary(full, "latest")
    assert not fit.wants_summary(full, "units")
    assert not fit.wants_summary({**full, "tier": "exploration"}, "rows")
    calls = []
    monkeypatch.setattr(fit.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    unit = fit.summarize(full)
    (cmd,) = calls
    # Its own unit, outside the modal-fit-* names the queue runners wait on.
    assert unit.startswith("modal-summary-") and f"--unit={unit}" in cmd
    assert cmd[:3] == ["systemd-run", "--user", "--quiet"]
    assert cmd[-2:] == [str(fit.HERE / "summarize"), "r"]
    assert f"--setenv=FRONTIER_OUTPUT_ROOT={tmp_path / 'frontier'}" in cmd
    assert "--setenv=FRONTIER_DATASET=/d" in cmd
    assert f"--setenv=MODAL_FIT_REPO={tmp_path / 'repo'}" in cmd
    assert not any("FRONTIER_RANGE_SAMPLE" in c for c in cmd)
    calls.clear()
    fit.summarize({**full, "range_sample": True})
    assert "--setenv=FRONTIER_RANGE_SAMPLE=1" in calls[0]
    assert not any("FRONTIER_RANGE_ATOMS" in c for c in calls[0])
    calls.clear()
    fit.summarize({**full, "range_atoms": True})
    assert "--setenv=FRONTIER_RANGE_ATOMS=1" in calls[0]

    def fail(cmd, **kw):
        raise fit.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(fit.subprocess, "run", fail)
    assert fit.summarize(full) is None


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


def test_only_finished_post_fit_records_leave_the_container(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "result.json").write_text("{}")
    (tmp_path / "cut").mkdir()
    (tmp_path / "cut" / "result.json").write_text('{"shares": {')
    assert [app._complete(tmp_path / d) for d in ("v", "cut")] == [True, False]


def test_the_new_building_score_lands_beside_the_run_and_never_fails_the_fit(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(fit, "STATE", tmp_path / "modal")
    files = {
        "out/r/run/result.json": b"{}",
        "out/r/newbuilding/r-abc1234/result.json": b"{}",
        "out/r/newbuilding.log": b"log",
    }
    fit.finish(FakeVolume(files), "r", {"exit": 0})
    root = tmp_path / "frontier"
    assert (root / "newbuilding/r-abc1234/result.json").exists()
    assert (root / "runs/r/modal/newbuilding.log").read_bytes() == b"log"


def test_scoring_an_existing_run_downloads_only_its_new_building_score(
    tmp_path, monkeypatch
):
    nb = load("newbuilding")
    monkeypatch.setattr(nb.fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(nb.fit, "STATE", tmp_path / "modal")
    files = {
        "out/r/run/result.json": b"{}",
        "out/r/newbuilding/r-only-lots-v1-abc1234/result.json": b"{}",
        "out/r/newbuilding.log": b"log",
    }
    volume = FakeVolume(files)
    (tmp_path / "frontier/newbuilding/r-old-abc1234").mkdir(parents=True)
    files["out/r/newbuilding/r-old-abc1234/result.json"] = b"new"
    nb.download(volume, "r")
    # An existing record is kept, and nothing is left half-written.
    assert not (tmp_path / "frontier/newbuilding/r-old-abc1234/result.json").exists()
    assert not (tmp_path / "frontier/.incoming").exists()
    root = tmp_path / "frontier"
    assert (root / "newbuilding/r-only-lots-v1-abc1234/result.json").exists()
    assert (tmp_path / "modal/logs/newbuilding-r.log").read_bytes() == b"log"
    assert not (root / "runs").exists()
    assert volume.removed == ["/out/r"]


def test_a_failed_new_building_container_is_still_charged(monkeypatch):
    clock = iter([100.0, 400.0])
    monkeypatch.setattr(fit.time, "monotonic", lambda: next(clock))

    def broken(spec):
        raise TimeoutError("container timeout")

    app = type(
        "App",
        (),
        {
            "newbuilding_cpu": type("F", (), {"remote": broken}),
            "nb_usd_per_second": staticmethod(lambda: 0.001),
        },
    )
    out = fit.score_new_buildings(app, {"name": "r"})
    assert out["usd_estimate"] == 0.3
    assert out["exit"].startswith("TimeoutError")


def test_scoring_an_existing_run_uses_the_dataset_it_was_fit_on(tmp_path, monkeypatch):
    nb = load("newbuilding")
    monkeypatch.setattr(nb.fit, "OUTPUT_ROOT", tmp_path)
    (tmp_path / "runs/r").mkdir(parents=True)
    (tmp_path / "runs/r/result.json").write_text(
        json.dumps({"dataset": str(tmp_path / "ds")})
    )
    spec = nb.spec_for("r", "abc", ["--holdout"])
    assert spec["dataset"] == str(tmp_path / "ds")
    assert spec["inputs"][0] == str(tmp_path / "ds")
    assert spec["newbuilding_args"] == ["--holdout"]


def test_a_c_sized_fit_is_under_the_per_fit_cap(tmp_path):
    usd, secs = cap.estimate(*cap.SERVED_FIT), cap.seconds(*cap.SERVED_FIT)
    assert (usd, secs) == (2.03, 3056)
    assert cap.over_cap(usd, secs) is None
    day = cap.START + datetime.timedelta(days=7)
    cap.reserve("c", "A100-40GB", usd, tmp_path / "ledger.jsonl", day, secs=secs)


def test_a_fit_over_an_hour_is_refused_whatever_the_balance(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    secs = cap.seconds(2, 300, 24000)  # the 24,000-draw AR(1) walk plan
    assert secs > cap.PER_FIT_SECONDS
    assert "over the per-fit cap of 60 min" in cap.over_cap(1.0, secs)
    day = cap.START + datetime.timedelta(days=7)
    with pytest.raises(cap.CapReached, match="refused: .*per-fit cap"):
        cap.reserve("ar", "A100-40GB", 1.0, ledger, day, secs=secs)
    assert not ledger.exists()  # nothing charged
    assert cap.over_cap(1.0, cap.PER_FIT_SECONDS) is None  # strictly over


def test_the_dollar_half_of_the_cap_waits_on_ben(monkeypatch):
    assert cap.PER_FIT_USD is None
    assert cap.over_cap(9.99, 600) is None
    monkeypatch.setattr(cap, "PER_FIT_USD", 2.00)
    assert "$2.17 estimate is over the per-fit cap of $2.00" in cap.over_cap(2.17, 600)
    assert cap.over_cap(2.00, 600) is None


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["--check", "2", "300", "24000"], 2),
        (["--check-launch", "abc", "lab", "m7", "nb8", "2", "300", "24000", "9"], 2),
    ],
)
def test_the_pre_checks_refuse_a_fit_over_the_cap(argv, code):
    import subprocess

    script = Path(__file__).parents[1] / "ops/modal/cap.py"
    done = subprocess.run(
        [sys.executable, str(script), *argv], capture_output=True, text=True
    )
    assert done.returncode == code
    assert "over the per-fit cap of 60 min" in done.stderr


def test_the_container_stops_a_runaway_at_75_minutes(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    assert app.TIMEOUT == 75 * 60
    assert app.FIT_CAP["full"] == 3600
    assert app.nb_usd_per_second() * 3600 == pytest.approx(
        cap.NEWBUILDING_USD_PER_HOUR, abs=1e-4
    )


def _modal_run(runs, model, features, fit_seconds, name="rows-abc1234-a100", exit=0):
    run = runs / f"{model}-{features}-{name}"
    (run / "modal").mkdir(parents=True)
    (run / "modal/modal.json").write_text(
        json.dumps({"fit_exit": exit, "stages": {"fit": fit_seconds}})
    )
    (run / "result.json").write_text(
        json.dumps(
            {
                "model": {"name": model},
                "feature_set": features,
                "sampler_settings": {"chains": 2, "warmup": 300, "draws": 4500},
            }
        )
    )
    return run


def test_a_model_slower_than_the_default_rate_is_estimated_at_its_own(tmp_path):
    # C's last fit stage ran 2,307 s, areatime's 3,340 s, at 2 x (300 + 4,500).
    _modal_run(tmp_path, "m7", "nb8-v1", 2307)
    _modal_run(tmp_path, "m7-areatime", "nb8-v1", 3340)
    _modal_run(tmp_path, "m7", "nb8-v1-wide", 4000)  # another feature set
    _modal_run(tmp_path, "m7", "nb8-v1", 9000, name="rows-def5678-a100", exit=124)
    c = cap.measured_rate("m7", "nb8-v1", tmp_path)
    assert c == pytest.approx(2307 / 4800)
    assert cap.over_cap(None, cap.seconds(*cap.SERVED_FIT, c)) is None
    area = cap.measured_rate("m7-areatime", "nb8-v1", tmp_path)
    assert cap.seconds(*cap.SERVED_FIT, area) == 800 + 3340 + 240
    assert "over the per-fit cap" in cap.over_cap(
        None, cap.seconds(*cap.SERVED_FIT, area)
    )
    # A faster model, or one never fitted on Modal, is estimated at the default rate.
    _modal_run(tmp_path, "m7-fast", "nb8-v1", 1000)
    assert (
        cap.seconds(*cap.SERVED_FIT, cap.measured_rate("m7-fast", "nb8-v1", tmp_path))
        == 3056
    )
    assert cap.measured_rate("m7-new", "nb8-v1", tmp_path) is None


def test_the_pre_check_reads_the_model_from_modal_fit_arguments():
    argv = ["--gpu", "L4", "abc", "lab", "m7-x", "nb8-v1", "2", "300", "4500", "9"]
    assert cap.fit_model(argv) == ("m7-x", "nb8-v1")


def test_a_large_fit_has_its_own_container_price_and_no_hour_cap(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    assert {
        gpu: round(app.usd_per_second(gpu, large=True) * 3600, 4)
        for gpu in app.LARGE_FITS
    } == pytest.approx(cap.USD_PER_HOUR_LARGE, abs=1e-4)
    assert app.LARGE_FIT_CAP < app.LARGE_TIMEOUT
    secs = cap.seconds(2, 300, 24000)
    assert cap.over_cap(1.0, secs) and cap.over_cap(1.0, secs, large=True) is None
    assert cap.estimate(2, 300, 4500, "H100", large=True) > cap.estimate(
        2, 300, 4500, "H100"
    )
    # Unmeasured, a large fit runs at the row-scaled rate, with no new-building container:
    # a short probe fits a full balance, and the full fit is over the ceiling.
    assert cap.seconds(2, 50, 150, large=True) == round(
        cap.OVERHEAD_SECONDS + 2.1 * 200
    )
    assert cap.seconds(2, 300, 4500, 1.0, large=True) == round(
        cap.OVERHEAD_SECONDS + 4800 * 1.0
    )
    probe = cap.estimate(2, 50, 150, "H100", large=True)
    assert probe < cap.CEILING < cap.estimate(2, 300, 4500, "H100", large=True)
    day = cap.START + datetime.timedelta(days=7)
    cap.reserve("big", "H100", 1.0, tmp_path / "l.jsonl", day, secs=secs, large=True)
    argv = ["--large", "--gpu", "H100", "c", "l", "m7", "all", "2", "300", "4500", "9"]
    args, rest = fit.parse(argv)
    spec = fit.plan(args, rest, "c" * 40)
    assert spec["large"] and spec["tier"] == "full" and "--large" not in rest
    assert cap.fit_size(argv) == ("2", "300", "4500", "H100")
    # The container builds a large fit's summary, so thelio doesn't.
    assert not fit.wants_summary(spec, "rows")
    assert fit.wants_summary({**spec, "large": False}, "rows")


def test_a_large_fit_builds_its_summary_and_calibration_in_the_container(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    monkeypatch.setattr(app, "OUTPUT", tmp_path)
    calls = []

    def run(cmd, env, log, timeout=None):
        calls.append((cmd[2:], timeout))
        if cmd[2] == "rentfrontier.summary":
            bundle = tmp_path / "summaries" / "r-abc1234"
            bundle.mkdir(parents=True)
            (bundle / "complete.json").write_text("{}")
        return 0

    monkeypatch.setattr(app, "_run", run)
    now = 1000.0
    monkeypatch.setattr(app.time, "time", lambda: now)
    done = app._summarize({"name": "r"}, {}, None, now + 7200)
    assert done == {
        "summary": {"exit": 0, "seconds": 0.0},
        "calibration": {"exit": 0, "seconds": 0.0},
    }
    assert calls == [
        (["rentfrontier.summary", "r"], 7200),
        (["rentfrontier.calibration", str(tmp_path / "summaries" / "r-abc1234")], 7200),
    ]
    # A bundle counts once its complete.json parses; downloads take both directories.
    assert app._complete(tmp_path / "summaries" / "r-abc1234")
    assert {"summaries", "calibration"} <= set(app.POST_KINDS) & set(fit.POST_KINDS)
    calls.clear()
    app._summarize({"name": "r", "range_sample": True}, {}, None, now + 7200)
    assert calls[0] == (["rentfrontier.summary", "r", "--range-sample"], 7200)
    calls.clear()
    app._summarize(
        {"name": "r", "range_sample": True, "range_atoms": True}, {}, None, now + 7200
    )
    assert calls[0] == (
        ["rentfrontier.summary", "r", "--range-sample", "--range-atoms"],
        7200,
    )
    # Without a bundle, calibration is skipped.
    calls.clear()
    monkeypatch.setattr(app, "_run", lambda *a, **k: 1)
    (tmp_path / "summaries" / "r-abc1234" / "complete.json").unlink()
    done = app._summarize({"name": "r"}, {}, None, now + 7200)
    assert done["summary"]["exit"] == 1 and done["calibration"]["exit"] == "skipped"


def test_a_fit_outside_the_budget_is_recorded_but_leaves_the_balance_alone(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    day = cap.START + datetime.timedelta(days=1)
    have = cap.balance([], day)
    launch, left = cap.reserve("all", "H100", 17.71, ledger, day, outside=True)
    assert left == pytest.approx(have)
    cap.settle(launch, 20.0, ledger, day)
    rows = cap.launches(ledger)
    assert [r.get("kind") for r in rows] == ["outside", "settle"]
    assert cap.balance(rows, day) == pytest.approx(have)
    with pytest.raises(cap.CapReached):
        cap.reserve("all", "H100", 17.71, ledger, day)


def test_a_large_fit_can_stop_before_its_summary():
    argv = ["abc", "all", "m7", "all-scraped-v1", "2", "300", "4500", "9"]
    args, rest = fit.parse(["--large", "--gpu", "H100", *argv])
    assert fit.plan(args, rest, "9371a18")["summary"]
    args, rest = fit.parse(["--large", "--no-summary", "--outside-budget", *argv])
    assert args.outside_budget and not fit.plan(args, rest, "9371a18")["summary"]
    assert "--no-summary" not in rest and "--outside-budget" not in rest


def test_publish_only_names_the_existing_run_and_carries_the_gate_override():
    argv = ["abc", "x", "m7", "all-scraped-v1", "2", "300", "4500", "9"]
    args, rest = fit.parse(
        ["--large", "--publish-only", "--allow-failing", "--run", "old-run", *argv]
    )
    spec = fit.plan(args, rest, "9371a18")
    assert spec["name"] == "old-run"
    assert spec["publish_only"] and spec["allow_failing"]
    assert not {"--publish-only", "--allow-failing", "--run"} & set(rest)
    assert not spec["range_sample"] and not spec["range_atoms"]
    args, rest = fit.parse(["--large", "--publish-only", "--range-sample", *argv])
    assert (
        fit.plan(args, rest, "9371a18")["range_sample"] and "--range-sample" not in rest
    )
    args, rest = fit.parse(["--large", "--publish-only", "--range-atoms", *argv])
    assert (
        fit.plan(args, rest, "9371a18")["range_atoms"] and "--range-atoms" not in rest
    )


def test_a_publish_builds_the_bundle_kit_and_map_in_order(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    monkeypatch.setattr(app, "OUTPUT", tmp_path)
    vol = tmp_path / "vol"
    (vol / "out" / "r" / "run").mkdir(parents=True)
    (vol / "out" / "r" / "run" / "result.json").write_text("{}")
    monkeypatch.setattr(app, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(app, "LOO", tmp_path / "loo")
    monkeypatch.setattr(app, "_stage", lambda spec: None)
    real_path = app.Path
    monkeypatch.setattr(
        app, "Path", lambda p, *a: real_path(str(p).replace("/vol", str(vol), 1), *a)
    )
    calls, caches = [], []

    def run(cmd, env, log, timeout=None):
        calls.append(cmd[2:])
        caches.append(env.get("FRONTIER_DESIGN_CACHE"))
        if cmd[2] == "rentfrontier.summary":
            bundle = tmp_path / "summaries" / "r-abc1234"
            bundle.mkdir(parents=True)
            (bundle / "complete.json").write_text("{}")
        if cmd[2] == "rentfrontier.rentmap":
            return 1
        return 0

    monkeypatch.setattr(app, "_run", run)
    meta = app._fit(
        {
            "name": "r",
            "publish_only": True,
            "allow_failing": True,
            "range_sample": True,
            "range_atoms": True,
            "dataset": "d",
        }
    )
    bundle = str(tmp_path / "summaries" / "r-abc1234")
    assert calls == [
        [
            "rentfrontier.summary",
            "r",
            "--workers",
            "7",
            "--allow-failing",
            "--range-sample",
            "--range-atoms",
        ],
        ["rentfrontier.kit", "r", "--summary", bundle, "--allow-failing"],
        ["rentfrontier.calibration", bundle],
        ["rentfrontier.rentmap", "r"],
    ]
    # Every step reads the design the summary pickled.
    assert caches == ["1"] * 4
    # The run was copied in from the Volume; a failed rent map leaves the kit alone but fails
    # the publish.
    assert (tmp_path / "runs" / "r" / "result.json").exists()
    assert meta["exit"] == 1 and meta["post"]["kit"]["exit"] == 0
    out = vol / "out" / "r-publish"
    assert (out / "summaries" / "r-abc1234" / "complete.json").exists()
    assert json.loads((out / "publish.json").read_text())["exit"] == 1


def test_a_publish_downloads_beside_the_run_it_belongs_to(tmp_path, monkeypatch):
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    files = {
        "out/r-publish/summaries/r-abc1234/complete.json": b"{}",
        "out/r-publish/kits/r-abc1234/complete.json": b"{}",
        "out/r-publish/maps/r-abc1234/map.json": b"{}",
        "out/r-publish/publish.log": b"log",
    }
    root = tmp_path / "frontier"
    fit.download(FakeVolume(files), "r-publish", root, local="r")
    assert (root / "summaries/r-abc1234/complete.json").exists()
    assert (root / "kits/r-abc1234/complete.json").exists()
    assert (root / "maps/r-abc1234/map.json").exists()
    assert (root / "runs/r/modal/publish.log").read_bytes() == b"log"
    assert not (root / "runs" / "r-publish").exists()


def test_a_failed_summary_skips_the_steps_reading_its_bundle(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    monkeypatch.setattr(app, "OUTPUT", tmp_path)
    vol = tmp_path / "vol"
    (vol / "out" / "r" / "run").mkdir(parents=True)
    monkeypatch.setattr(app, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(app, "LOO", tmp_path / "loo")
    monkeypatch.setattr(app, "_stage", lambda spec: None)
    real_path = app.Path
    monkeypatch.setattr(
        app, "Path", lambda p, *a: real_path(str(p).replace("/vol", str(vol), 1), *a)
    )
    calls = []
    monkeypatch.setattr(
        app,
        "_run",
        lambda cmd, *a, **k: (
            calls.append(cmd[2]) or (cmd[2] != "rentfrontier.rentmap") * 1
        ),
    )
    meta = app._fit({"name": "r", "publish_only": True, "dataset": "d"})
    assert calls == ["rentfrontier.summary", "rentfrontier.rentmap"]
    assert meta["post"]["kit"] == meta["post"]["calibration"] == {"exit": "skipped"}
    assert meta["exit"] == 1


def test_a_saved_design_goes_to_the_cache_and_the_summary_reads_it(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    monkeypatch.setattr(fit, "STATE", tmp_path / "modal")
    argv = ["abc", "x", "m7", "all-scraped-v1", "2", "300", "4500", "9"]
    args, rest = fit.parse(["--save-design", *argv])
    assert (
        fit.plan(args, rest, "9371a18")["save_design"] and "--save-design" not in rest
    )
    files = {
        "out/r/run/result.json": b"{}",
        "out/r/design/design-0123456789abcdef.pkl": b"pickle",
    }
    fit.finish(FakeVolume(files), "r", {"exit": 0})
    designs = tmp_path / "frontier" / "designs"
    assert (designs / "design-0123456789abcdef.pkl").read_bytes() == b"pickle"
    assert [p.name for p in designs.iterdir()] == ["design-0123456789abcdef.pkl"]
    assert not (tmp_path / "frontier/runs/r/modal/design").exists()
    # Every fit uploads the cache directory as an input; the designs stay out of it.
    assert not any(
        str(designs).startswith(i) or i.startswith(str(designs)) for i in fit.INPUTS
    )
    assert not (tmp_path / "frontier" / "cache").exists()
    # A failed fit's design stays off thelio, and so does a large fit's.
    fit.finish(FakeVolume(files), "r", {"exit": 1})
    assert not (tmp_path / "modal/failed/designs").exists()
    designs.joinpath("design-0123456789abcdef.pkl").unlink()
    fit.finish(FakeVolume(files), "r", {"exit": 0}, design=False)
    assert not any(designs.iterdir())
    assert not (tmp_path / "modal/failed/runs/r/modal/design").exists()
    calls = []
    monkeypatch.setattr(fit.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    full = {"name": "r", "tier": "full", "dataset": "/d"}
    fit.summarize(full)
    assert not any("FRONTIER_DESIGN_CACHE" in c for c in calls[0])
    fit.summarize({**full, "save_design": True})
    assert "--setenv=FRONTIER_DESIGN_CACHE=read" in calls[1]


def test_the_container_saves_the_runs_design_and_a_publish_reads_it_back(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    monkeypatch.setattr(app, "OUTPUT", tmp_path / "frontier")
    monkeypatch.setattr(app, "RUNS", tmp_path / "frontier" / "runs")
    monkeypatch.setattr(app, "LOO", tmp_path / "frontier" / "loo")
    monkeypatch.setattr(app, "_post", lambda *a: {})
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: mock.Mock(stdout=""))
    vol = tmp_path / "vol"
    real_path = app.Path
    monkeypatch.setattr(
        app, "Path", lambda p, *a: real_path(str(p).replace("/vol", str(vol), 1), *a)
    )
    cache = tmp_path / "frontier" / "cache"
    # A design that came in with the staged inputs is not the run's.
    monkeypatch.setattr(
        app,
        "_stage",
        lambda spec: (
            cache.mkdir(parents=True, exist_ok=True),
            (cache / "design-5555555555555555.pkl").write_bytes(b"staged"),
        ),
    )

    def run(cmd, env, log, timeout=None):
        if cmd[2] == "rentfrontier.run":
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "design-0123456789abcdef.pkl").write_bytes(b"design")
        else:
            # A later step's own design stays in the container.
            (cache / "design-fedcba9876543210.pkl").write_bytes(b"other")
        return 0

    monkeypatch.setattr(app, "_run", run)
    spec = {"name": "r", "tier": "full", "run_args": [], "dataset": "d"}
    app._fit(spec)
    assert not (vol / "out" / "r" / "design").exists()
    for p in cache.iterdir():  # each fit gets a fresh container
        p.unlink()
    app._fit({**spec, "save_design": True})
    saved = vol / "out" / "r" / "design"
    assert [p.name for p in saved.iterdir()] == ["design-0123456789abcdef.pkl"]
    # A publish container starts with that design in its cache.
    for p in cache.iterdir():
        p.unlink()
    (vol / "out" / "r" / "run").mkdir(parents=True)
    monkeypatch.setattr(app, "_run", lambda *a, **k: 1)
    app._fit({**spec, "publish_only": True})
    assert (cache / "design-0123456789abcdef.pkl").read_bytes() == b"design"


def test_a_design_only_container_saves_the_new_design_and_its_record(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    monkeypatch.setattr(app, "OUTPUT", tmp_path / "frontier")
    monkeypatch.setattr(app, "RUNS", tmp_path / "frontier" / "runs")
    vol = tmp_path / "vol"
    real_path = app.Path
    monkeypatch.setattr(
        app, "Path", lambda p, *a: real_path(str(p).replace("/vol", str(vol), 1), *a)
    )
    cache = tmp_path / "frontier" / "cache"
    monkeypatch.setattr(
        app,
        "_stage",
        lambda spec: (
            cache.mkdir(parents=True, exist_ok=True),
            (cache / "design-5555555555555555.pkl").write_bytes(b"staged"),
        ),
    )
    calls = []

    def run(cmd, env, log, timeout=None):
        calls.append((cmd, env))
        (cache / "design-0123456789abcdef.pkl").write_bytes(b"design")
        log.write('loading\n{"key": "0123456789abcdef00"}\n')
        return 0

    monkeypatch.setattr(app, "_run", run)
    spec = {"name": "r", "dataset": "d", "result": {"dataset": "d", "split": "rows"}}
    meta = app._design(spec)
    ((cmd, env),) = calls
    assert cmd[1:] == ["-m", "rentfrontier.design", "r"]
    assert env["FRONTIER_DESIGN_CACHE"] == "1"
    assert env["FRONTIER_DATASET"] == "d"
    # The run's record is where rentfrontier.design reads it.
    assert json.loads((app.RUNS / "r" / "result.json").read_text())["split"] == "rows"
    out = vol / "out" / "r-design"
    assert [p.name for p in (out / "design").iterdir()] == [
        "design-0123456789abcdef.pkl"
    ]
    assert meta["exit"] == 0
    assert meta["designs"] == [{"file": "design-0123456789abcdef.pkl", "bytes": 6}]
    assert meta["record"] == {"key": "0123456789abcdef00"}
    assert json.loads((out / "design.json").read_text())["designs"] == meta["designs"]
    # A prep that loads the staged design of its key saves nothing and fails.
    monkeypatch.setattr(app, "_run", lambda *a, **k: 0)
    calls.clear()
    assert app._design(spec)["exit"] == "no new design"


def test_a_design_only_run_downloads_to_designs_beside_the_run(tmp_path, monkeypatch):
    files = {
        "out/r-design/design/design-0123456789abcdef.pkl": b"design",
        "out/r-design/design.json": b"{}",
        "out/r-design/design.log": b"log",
    }
    root = tmp_path / "frontier"
    volume = FakeVolume(files)
    fit.download(volume, "r-design", root, local="r")
    assert (root / "designs/design-0123456789abcdef.pkl").read_bytes() == b"design"
    assert (root / "runs/r/modal/design.log").read_bytes() == b"log"
    assert not (root / "cache").exists()
    assert not (root / "runs" / "r-design").exists()
    assert volume.removed == ["/out/r-design"]


def test_a_design_only_run_is_charged_its_container_hour_and_needs_the_run(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    # An hour of the design container is inside the per-fit cap and costs under a dollar.
    usd = app.DESIGN_TIMEOUT * app.design_usd_per_second()
    assert cap.over_cap(usd, app.DESIGN_TIMEOUT) is None
    assert 0.5 < usd < 1
    monkeypatch.setattr(fit, "OUTPUT_ROOT", tmp_path / "frontier")
    spec = {"name": "r", "inputs": ["x"], "dataset": "x"}
    with pytest.raises(SystemExit, match="not under"):
        fit.design_only(spec, "abc")
