"""Checks for ops/deals-refresh and the market -> b0closingraise -> b0bedtext chain."""

import json
import os
import shutil
import stat
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0bedtext, b0closingraise, building_attrs, market
from rentfrontier.b0data import sha256

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "deals-refresh"


def _write_exec(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _setup_sandbox(tmp_path: Path, build_hash: str = "deadbeef12345678"):
    """Isolated repo copy, APARTMENTS_ROOT tree, and stub runners (no /data1 or GPU)."""
    repo = tmp_path / "repo"
    (repo / "ops").mkdir(parents=True)
    script = repo / "ops" / "deals-refresh"
    shutil.copy2(SCRIPT, script)

    data = tmp_path / "data"
    (data / "pipeline" / "datasets").mkdir(parents=True)
    (data / "pipeline" / "datasets" / f"rows-{build_hash}.parquet").write_bytes(b"rows")
    nj_dir = data / "external" / "registry-nj" / "20261120-test"
    nj_dir.mkdir(parents=True)
    (nj_dir / "registry.parquet").write_bytes(b"nj")
    (data / "frontier" / "datasets").mkdir(parents=True)

    log_path = tmp_path / "calls.jsonl"
    bin_dir = tmp_path / "bin"

    _write_exec(
        bin_dir / "systemd-run",
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
sep = args.index("--")
cmd = args[sep + 1 :]
if cmd and cmd[0] == "env":
    cmd = cmd[1:]
    while cmd and "=" in cmd[0]:
        cmd = cmd[1:]
# cmd is [python_bin, "-m", "rentfrontier.<mod>", ...]
mod = cmd[2]
rest = cmd[3:]
with open(os.environ["TEST_LOG"], "a") as fh:
    fh.write(json.dumps({"cmd": mod, "args": rest}) + "\\n")
pos = [a for a in rest if not a.startswith("-")]
out = pos[0] if mod == "rentfrontier.b0data" else pos[1]
Path(out).mkdir(parents=True, exist_ok=False)
(Path(out) / "rows.parquet").write_bytes(b"ok")
""",
    )

    _write_exec(
        repo / "ops" / "job",
        """#!/usr/bin/env python3
import json, os, subprocess, sys

args = sys.argv[1:]
sep = args.index("--")
with open(os.environ["TEST_LOG"], "a") as fh:
    fh.write(json.dumps({"cmd": "ops/job", "args": args[:sep]}) + "\\n")
sys.exit(subprocess.call(args[sep + 1 :]))
""",
    )

    _write_exec(
        repo / "ops" / "market-dataset",
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["TEST_LOG"], "a") as fh:
    fh.write(json.dumps({
        "cmd": "ops/market-dataset",
        "args": args,
        "asof": os.environ.get("ASOF"),
    }) + "\\n")
if "market" in args[1:]:
    ds = Path(os.environ["APARTMENTS_ROOT"]) / "frontier" / "datasets"
    out = ds / f"b0-{args[0]}-alldata-dense-nyc-market"
    out.mkdir(parents=True, exist_ok=False)
    (out / "rows.parquet").write_bytes(b"ok")
""",
    )

    _write_exec(
        repo / "ops" / "modal-fit",
        """#!/usr/bin/env python3
import json, os, sys

with open(os.environ["TEST_LOG"], "a") as fh:
    fh.write(json.dumps({"cmd": "ops/modal-fit", "args": sys.argv[1:]}) + "\\n")
""",
    )

    def run(args, env=None):
        base_env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {"CLOSING_RAISE", "ASOF", "MODEL", "BASELINE", "SCALES", "COMMIT"}
        }
        base_env["APARTMENTS_ROOT"] = str(data)
        base_env["TEST_LOG"] = str(log_path)
        base_env["PATH"] = f"{bin_dir}:{base_env.get('PATH', '')}"
        if env:
            base_env.update(env)
        return subprocess.run(
            [str(script), *args],
            env=base_env,
            capture_output=True,
            text=True,
            check=False,
        )

    def read_log():
        if not log_path.exists():
            return []
        return [json.loads(line) for line in log_path.read_text().splitlines() if line]

    return repo, data, log_path, run, read_log


def _init_git_origin_master(repo: Path) -> str:
    """Create a commit on origin/master inside the sandbox repo."""
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=git_env)
    subprocess.run(
        ["git", "add", "ops/deals-refresh"], cwd=repo, check=True, env=git_env
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=repo, check=True, env=git_env
    )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, env=git_env
    ).strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/master", head],
        cwd=repo,
        check=True,
        env=git_env,
    )
    return head


def test_deals_refresh_usage_and_invalid_switch(tmp_path):
    _, _, _, run, _ = _setup_sandbox(tmp_path)
    res = run([])
    assert res.returncode == 2
    assert "backtest-datasets" in res.stderr
    assert "backtest-fit" in res.stderr

    bad = run(["datasets", "no-such-hash"], env={"CLOSING_RAISE": "yes"})
    assert bad.returncode == 2
    assert "CLOSING_RAISE must be 0 or 1" in bad.stderr


@pytest.mark.parametrize("subcmd", ["datasets", "backtest-datasets"])
def test_dataset_steps_stop_on_missing_rows_file(tmp_path, subcmd):
    _, _, _, run, read_log = _setup_sandbox(tmp_path)
    res = run([subcmd, "no-such-hash"], env={"CLOSING_RAISE": "1"})
    assert res.returncode == 1
    assert "no rows-no-such-hash.parquet" in res.stderr
    assert read_log() == []


def test_datasets_default_chain_matches_master_and_skips_on_rerun(tmp_path):
    h = "deadbeef12345678"
    _, data, log_path, run, read_log = _setup_sandbox(tmp_path, h)
    ds = data / "frontier" / "datasets"
    base = ds / f"b0-{h}-alldata"

    res = run(["datasets", h])
    assert res.returncode == 0, res.stderr
    calls = read_log()
    assert [c["cmd"] for c in calls] == [
        "ops/job",
        "rentfrontier.b0data",
        "rentfrontier.b0trim",
        "rentfrontier.b0nyc",
        "ops/market-dataset",
        "ops/market-dataset",
        "rentfrontier.b0bedtext",
    ]
    assert calls[2]["args"] == ["--allow-thin-last", str(base), f"{base}-dense"]
    assert calls[4]["args"] == [
        h,
        "codes",
        "amenities",
        "units",
        "attrs",
        "age",
        "market",
    ]
    assert calls[5]["args"] == [h, "verify"]
    assert calls[6]["args"] == [
        f"{base}-dense-nyc-market",
        f"{base}-dense-nyc-market-bedtext",
    ]

    # Rerun skips every existing output and runs verify again.
    log_path.unlink()
    rerun = run(["datasets", h])
    assert rerun.returncode == 0, rerun.stderr
    assert read_log() == [
        {"cmd": "ops/market-dataset", "args": [h, "verify"], "asof": None}
    ]


def test_datasets_closing_raise_inserts_step_before_bedtext(tmp_path):
    h = "deadbeef12345678"
    _, data, log_path, run, read_log = _setup_sandbox(tmp_path, h)
    ds = data / "frontier" / "datasets"
    base = ds / f"b0-{h}-alldata"
    for suffix in ("", "-dense", "-dense-nyc", "-dense-nyc-market"):
        Path(f"{base}{suffix}").mkdir()

    res = run(["datasets", h], env={"CLOSING_RAISE": "1"})
    assert res.returncode == 0, res.stderr
    calls = read_log()
    assert calls == [
        {"cmd": "ops/market-dataset", "args": [h, "verify"], "asof": None},
        {
            "cmd": "rentfrontier.b0closingraise",
            "args": [
                f"{base}-dense-nyc-market",
                f"{base}-dense-nyc-market-closingraise",
            ],
        },
        {
            "cmd": "rentfrontier.b0bedtext",
            "args": [
                f"{base}-dense-nyc-market-closingraise",
                f"{base}-dense-nyc-market-closingraise-bedtext",
            ],
        },
    ]

    log_path.unlink()
    rerun = run(["datasets", h], env={"CLOSING_RAISE": "1"})
    assert rerun.returncode == 0, rerun.stderr
    assert read_log() == [
        {"cmd": "ops/market-dataset", "args": [h, "verify"], "asof": None}
    ]


def test_backtest_datasets_missing_asof_stops_with_market_dataset_hint(tmp_path):
    h = "deadbeef12345678"
    _, _, _, run, read_log = _setup_sandbox(tmp_path, h)

    res = run(["backtest-datasets", h], env={"CLOSING_RAISE": "1"})
    assert res.returncode == 1
    assert f"b0-{h}-alldata-dense-nyc-asof-20251110" in res.stderr
    assert f"ops/market-dataset {h}" in res.stderr
    assert "backtest" in res.stderr
    assert read_log() == []


def test_backtest_datasets_skips_existing_asof_and_closingraise(tmp_path):
    h = "deadbeef12345678"
    _, data, log_path, run, read_log = _setup_sandbox(tmp_path, h)
    ds = data / "frontier" / "datasets"
    asof_dir = ds / f"b0-{h}-alldata-dense-nyc-asof-20251110"
    cr_dir = Path(f"{asof_dir}-closingraise")
    asof_dir.mkdir()
    cr_dir.mkdir()
    sentinel = cr_dir / "keep.txt"
    sentinel.write_text("existing")

    # Mirrors build ddd2fe8f5da041b8: asof and asof-closingraise already exist.
    res = run(["backtest-datasets", h], env={"CLOSING_RAISE": "1"})
    assert res.returncode == 0, res.stderr
    assert sentinel.read_text() == "existing"
    assert read_log() == [
        {"cmd": "ops/market-dataset", "args": [h, "verify"], "asof": "2025-11-10"},
        {
            "cmd": "rentfrontier.b0bedtext",
            "args": [str(cr_dir), f"{cr_dir}-bedtext"],
        },
    ]

    # When closingraise does not exist yet (new ASOF), closingraise runs before bedtext.
    log_path.unlink()
    asof2 = ds / f"b0-{h}-alldata-dense-nyc-asof-20260115"
    asof2.mkdir()
    res2 = run(
        ["backtest-datasets", h], env={"CLOSING_RAISE": "1", "ASOF": "2026-01-15"}
    )
    assert res2.returncode == 0, res2.stderr
    assert read_log() == [
        {"cmd": "ops/market-dataset", "args": [h, "verify"], "asof": "2026-01-15"},
        {
            "cmd": "rentfrontier.b0closingraise",
            "args": [str(asof2), f"{asof2}-closingraise"],
        },
        {
            "cmd": "rentfrontier.b0bedtext",
            "args": [f"{asof2}-closingraise", f"{asof2}-closingraise-bedtext"],
        },
    ]


@pytest.mark.parametrize(
    "step,switch,suffix,baseline,scales",
    [
        (
            "fit",
            None,
            "market-bedtext",
            "drift-building-b0-market-67d14e17-n9",
            "base-n9",
        ),
        (
            "fit",
            "0",
            "market-bedtext",
            "drift-building-b0-market-67d14e17-n9",
            "base-n9",
        ),
        (
            "fit",
            "1",
            "market-closingraise-bedtext",
            "drift-building-b0-market-67d14e17-n9",
            "base-n9",
        ),
        (
            "backtest-fit",
            None,
            "asof-20251110-bedtext",
            "drift-building-b0-market-67d14e17-j9",
            "base-j9",
        ),
        (
            "backtest-fit",
            "1",
            "asof-20251110-closingraise-bedtext",
            "drift-building-b0-market-67d14e17-j9",
            "base-j9",
        ),
    ],
)
def test_fit_and_backtest_fit_select_dataset_and_scales(
    tmp_path, step, switch, suffix, baseline, scales
):
    h = "deadbeef12345678"
    repo, data, _, run, read_log = _setup_sandbox(tmp_path, h)
    commit = _init_git_origin_master(repo)
    env = {"CLOSING_RAISE": switch} if switch is not None else {}

    ds_dir = data / "frontier" / "datasets" / f"b0-{h}-alldata-dense-nyc-{suffix}"
    # Missing dataset stops before launching Modal.
    miss = run([step, "dryrun", h], env=env)
    assert miss.returncode == 1
    assert f"no dataset {ds_dir}" in miss.stderr
    assert read_log() == []

    ds_dir.mkdir()
    (ds_dir / "rows.parquet").write_bytes(b"ok")
    res = run([step, "dryrun", h], env=env)
    assert res.returncode == 0, res.stderr
    calls = read_log()
    assert len(calls) == 1
    assert calls[0]["cmd"] == "ops/modal-fit"
    argv = calls[0]["args"]
    assert argv == [
        "--outside-budget",
        "--gpu",
        "H100",
        "--dataset",
        str(ds_dir),
        "--input",
        str(data / "pipeline" / "datasets" / f"rows-{h}.parquet"),
        "--split",
        "market",
        "--baseline",
        baseline,
        commit,
        "dryrun",
        "drift-building-bedtext-layout-range",
        "b0",
        "2",
        "200",
        "3600",
        "20",
        "--seed",
        "1",
        "--level-dof",
        "4",
        "--scales-fixed",
        scales,
        "--no-loo",
        "--no-heldout",
    ]


def _raw_record(status, changes, statuses, description, off=None):
    payload = {
        "status": status,
        "description": description,
        "onMarketAt": "2025-10-01T00:00:00Z",
        "pricing": {
            "price": changes[-1][1],
            "priceChanges": [
                {"changedAt": t if "T" in t else f"{t}T12:00:00Z", "price": p}
                for t, p in changes
            ],
        },
        "statusChanges": [{"changedAt": t, "status": s} for t, s in statuses],
    }
    if off is not None:
        payload["offMarketAt"] = f"{off}T00:00:00Z"
    return json.dumps(payload)


def _synthetic_source(tmp_path):
    """Minimal b0nyc-like dataset, ads file and records file."""
    desc = "Bright renovated apartment in a quiet elevator building with flex 2 bedroom layout."
    plain_desc = (
        "Spacious renovated one bedroom apartment with hardwood floors and good light."
    )
    records = {
        # Closed before as-of day with a closing raise typed 30 s before RENTED.
        "1": _raw_record(
            "RENTED",
            [
                ("2025-10-01", 3000),
                ("2025-10-20", 2900),
                ("2025-10-25T15:00:00Z", 3400),
            ],
            [
                ("2025-10-01T00:00:00Z", "ACTIVE"),
                ("2025-10-25T15:00:30Z", "RENTED"),
            ],
            desc,
            off="2025-10-25",
        ),
        # Open on 2025-11-10 and later RENTED with a closing raise.
        "2": _raw_record(
            "RENTED",
            [
                ("2025-11-01", 3100),
                ("2025-11-20T15:00:00Z", 3600),
            ],
            [
                ("2025-11-01T00:00:00Z", "ACTIVE"),
                ("2025-11-20T15:00:10Z", "RENTED"),
            ],
            plain_desc,
            off="2025-11-20",
        ),
        # Still ACTIVE on the market day.
        "3": _raw_record(
            "ACTIVE",
            [("2026-11-01", 3200), ("2026-11-05", 3500)],
            [("2026-11-01T00:00:00Z", "ACTIVE")],
            desc,
            off=None,
        ),
        # TEMPORARILY_OFF_MARKET on the market day with a raise 10 s before that status.
        "4": _raw_record(
            "TEMPORARILY_OFF_MARKET",
            [("2026-10-15", 3300), ("2026-11-02T15:00:00Z", 3700)],
            [
                ("2026-10-15T00:00:00Z", "ACTIVE"),
                ("2026-11-02T15:00:10Z", "TEMPORARILY_OFF_MARKET"),
            ],
            plain_desc,
            off="2026-11-02",
        ),
    }
    rec_path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": list(records),
                "listing_type": ["rental"] * len(records),
                "last_collected_at": [1] * len(records),
                "raw_listing_json": list(records.values()),
            }
        ),
        rec_path,
    )
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4"],
            "bedrooms": [2.0, 1.0, 2.0, 1.0],
            "latest_ask": [3400.0, 3600.0, 3500.0, 3700.0],
            "latest_ask_how": ["latest"] * 4,
            "price_at": pd.to_datetime(
                ["2025-10-01", "2025-11-01", "2026-11-01", "2026-10-15"], utc=True
            ),
            "latest_day": [
                date(2025, 10, 25),
                date(2025, 11, 20),
                date(2026, 11, 5),
                date(2026, 11, 2),
            ],
            "latest_day_how": ["change"] * 4,
        }
    )
    src = tmp_path / "b0-nyc"
    src.mkdir()
    rows.to_parquet(src / "rows.parquet", index=False)
    (src / "manifest.json").write_text(
        json.dumps(
            {
                "rows": len(rows),
                "rows_sha256": sha256(src / "rows.parquet"),
                "build": {
                    "records": {"path": str(rec_path), "sha256": sha256(rec_path)}
                },
            }
        )
    )
    ads = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4"],
            "status": ["RENTED", "RENTED", "ACTIVE", "TEMPORARILY_OFF_MARKET"],
            "first_day": [
                date(2025, 10, 1),
                date(2025, 11, 1),
                date(2026, 11, 1),
                date(2026, 10, 15),
            ],
            "first_ask": [3000.0, 3100.0, 3200.0, 3300.0],
            "off_day": [
                date(2025, 10, 25),
                date(2025, 11, 20),
                None,
                date(2026, 11, 2),
            ],
        }
    )
    ads_path = tmp_path / "ads.parquet"
    ads.to_parquet(ads_path, index=False)
    return src, ads_path


def test_market_and_asof_closingraise_bedtext_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(building_attrs, "REGISTRY", building_attrs.REGISTRY)
    src, ads = _synthetic_source(tmp_path)
    inputs = {"rentfrontier.building_attrs.REGISTRY": str(tmp_path / "reg.parquet")}

    # Market chain: market -> closingraise -> bedtext.
    mkt = tmp_path / "market"
    mkt_cr = tmp_path / "market-closingraise"
    mkt_bt = tmp_path / "market-closingraise-bedtext"
    market.with_status(src, mkt, ads, inputs=inputs)
    b0closingraise.closing_raise(mkt, mkt_cr)
    m_bt = b0bedtext.bedtext(mkt_cr, mkt_bt)

    assert (mkt_bt / "inputs.json").read_bytes() == (mkt / "inputs.json").read_bytes()
    assert market.apply_inputs(mkt_bt) == inputs
    assert m_bt["rows_sha256"] == sha256(mkt_bt / "rows.parquet")
    assert m_bt["closing_raise"]["open_repriced"] == 1
    df = pd.read_parquet(mkt_bt / "rows.parquet").set_index("listing_id")
    # Closed rows 1 and 2 and TEMPORARILY_OFF_MARKET open row 4 are repriced; ACTIVE row 3 is not.
    assert df.loc["1", "latest_ask"] == 2900.0
    assert df.loc["2", "latest_ask"] == 3100.0
    assert df.loc["3", "latest_ask"] == 3500.0
    assert df.loc["4", "latest_ask"] == 3300.0
    # Open rows keep the scoring day from rentfrontier.market.
    assert pd.Timestamp(df.loc["3", "latest_day"]).date() == date(2026, 11, 5)
    assert pd.Timestamp(df.loc["4", "latest_day"]).date() == date(2026, 11, 5)
    assert bool(df.loc["1", "bed_flex_at"]) and bool(df.loc["3", "bed_flex_at"])
    assert not bool(df.loc["2", "bed_flex_at"])

    # Backtest as-of chain: asof -> closingraise -> bedtext.
    bt_src = tmp_path / "asof-20251110"
    bt_cr = tmp_path / "asof-20251110-closingraise"
    bt_bt = tmp_path / "asof-20251110-closingraise-bedtext"
    market.with_status(src, bt_src, ads, inputs=inputs, as_of="2025-11-10")
    b0closingraise.closing_raise(bt_src, bt_cr)
    b_manifest = b0bedtext.bedtext(bt_cr, bt_bt)

    assert (bt_bt / "inputs.json").read_bytes() == (bt_src / "inputs.json").read_bytes()
    assert (bt_bt / "set_aside.parquet").read_bytes() == (
        bt_src / "set_aside.parquet"
    ).read_bytes()
    assert b_manifest["rows_sha256"] == sha256(bt_bt / "rows.parquet")
    assert b_manifest["closing_raise"]["open_repriced"] == 1
    bdf = pd.read_parquet(bt_bt / "rows.parquet").set_index("listing_id")
    assert list(bdf.index) == ["1", "2"]
    assert bdf.loc["1", "latest_ask"] == 2900.0
    assert bdf.loc["2", "latest_ask"] == 3100.0
    assert pd.Timestamp(bdf.loc["2", "latest_day"]).date() == date(2025, 11, 10)
    assert bool(bdf.loc["1", "bed_flex_at"]) and not bool(bdf.loc["2", "bed_flex_at"])


def test_onefit_launches_two_lean_h200_shards_or_scales_fixed_fast_refresh(tmp_path):
    h = "deadbeef12345678"
    repo, data, log_path, run, read_log = _setup_sandbox(tmp_path, h)
    commit = _init_git_origin_master(repo)
    ds_dir = data / "frontier" / "datasets" / f"b0-{h}-alldata-dense-nyc-market-bedtext"
    ds_dir.mkdir()
    (ds_dir / "rows.parquet").write_bytes(b"ok")

    res = run(["onefit", "c1-nov24", h])
    assert res.returncode == 0, res.stderr
    calls = read_log()
    assert len(calls) == 2
    for call, shard, seed in zip(calls, ("a", "b"), ("1", "2")):
        assert call["cmd"] == "ops/modal-fit"
        argv = call["args"]
        assert "--large" in argv and "--lean" in argv
        assert "--gpu" in argv and argv[argv.index("--gpu") + 1] == "H200"
        assert "--split" in argv and argv[argv.index("--split") + 1] == "onefit"
        assert f"c1-nov24-{shard}" in argv
        assert argv[argv.index("--seed") + 1] == seed
        assert commit in argv

    # Fast refresh with SCALES_FIXED launches a single container.
    log_path.unlink()
    fast = run(["onefit", "c1-fast", h], env={"SCALES_FIXED": "prev-run"})
    assert fast.returncode == 0, fast.stderr
    fcalls = read_log()
    assert len(fcalls) == 1
    fargv = fcalls[0]["args"]
    assert fargv[fargv.index("--scales-fixed") + 1] == "prev-run"
    assert "c1-fast" in fargv


def test_registry_glob_picks_newer_same_day_extend_hhmmss_by_mtime(tmp_path):
    """Both ops/deals-refresh and ops/market-dataset must pick YYYYMMDD-SHA-extend-HHMMSS
    over an earlier same-day YYYYMMDD-SHA-extend snapshot."""
    reg_root = tmp_path / "external" / "registry"
    first = reg_root / "20261123-1f0c240-extend"
    second = reg_root / "20261123-1f0c240-extend-180210"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    p1 = first / "registry.parquet"
    p2 = second / "registry.parquet"
    p1.write_bytes(b"old")
    p2.write_bytes(b"new")
    os.utime(p1, (1_700_000_000, 1_700_000_000))
    os.utime(p2, (1_700_003_600, 1_700_003_600))

    picked = subprocess.check_output(
        [
            "bash",
            "-c",
            f'ls -t "{reg_root}"/*-extend*/registry.parquet | head -1',
        ],
        text=True,
    ).strip()
    assert picked == str(p2)
    # Also confirm both ops scripts use the mtime-sorted *-extend*/registry.parquet pattern.
    assert "/*-extend*/registry.parquet" in SCRIPT.read_text()
    assert (
        "/*-extend*/registry.parquet" in (ROOT / "ops" / "market-dataset").read_text()
    )
