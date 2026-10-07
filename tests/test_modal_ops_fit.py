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
    cap.settle(launch, usd + 0.5, ledger, t0 + per_fit / 4)
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
    assert cap.estimate(2, 100, 600) < usd < cap.estimate(2, 300, 4500)


def test_launches_before_the_budget_began_are_not_charged(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    before = cap.START - datetime.timedelta(hours=1)
    launch, _ = cap.reserve("old", "A100-40GB", 0, ledger, before)
    cap.settle(launch, 5.0, ledger, cap.START + datetime.timedelta(hours=1))
    rows = cap.launches(ledger)
    assert cap.balance(rows, cap.START) == 0
    assert cap.balance(rows, cap.START + datetime.timedelta(days=1)) == pytest.approx(
        cap.USD_PER_DAY
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
        cap.USD_PER_DAY - 0.3 - 0.8 - cap.estimate(*cap.SERVED_FIT)
    )


def test_ten_served_fits_a_day_at_the_container_list_price(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", mock.MagicMock())
    app = load("app")
    assert {
        gpu: round(app.usd_per_second(gpu) * 3600, 4) for gpu in app.FITS
    } == pytest.approx(cap.USD_PER_HOUR, abs=1e-4)
    assert cap.USD_PER_DAY == pytest.approx(10 * cap.estimate(2, 300, 3600))


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
