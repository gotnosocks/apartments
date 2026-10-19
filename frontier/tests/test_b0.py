import json
import math

import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0, b0data, features


def frame_of(n=6000, weeks=120, seed=1):
    """Rows simulated from B0 itself, with the parameters that made them."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2019-01-07")
    day = start + pd.to_timedelta(rng.integers(0, 7 * weeks, n), unit="D")
    beds = rng.choice(
        [0, 1, 2, 3, 4, 5, 6], n, p=[0.2, 0.35, 0.25, 0.1, 0.05, 0.03, 0.02]
    )
    full = rng.choice([1.0, 2.0, 3.0, 4.0, np.nan], n, p=[0.6, 0.25, 0.07, 0.03, 0.05])
    half = rng.choice([0, 1], n, p=[0.85, 0.15])
    flags = {f: rng.random(n) < 0.05 for f in b0.FLAGS}
    frame = pd.DataFrame(
        {
            "listing_id": np.arange(n),
            "audit_id": [str(i) for i in range(n)],
            "building": rng.integers(0, 300, n).astype(str),
            "unit_id": rng.integers(0, 3000, n).astype(str),
            "price_at": day,
            "latest_day": day,
            "bedrooms": beds.astype(float),
            "full_baths": full,
            "half_baths": half.astype(float),
            **flags,
        }
    )
    d = b0.design(frame.assign(latest_ask=1.0))
    beta = np.zeros(len(d.names))
    beta[0] = math.log(2500)
    beta[1:6] = [0.2, 0.3, 0.2, 0.1, 0.05]
    beta[6:9] = [0.12, 0.08, 0.05]
    beta[9], beta[10] = 0.05, -0.03
    beta[11:15] = [0.02, -0.01, 0.005, 0.0]
    beta[15:] = [0.1, 0.15, -0.3, -0.2, -0.1]
    # The trend follows B0's own damped local linear trend: tau 0.0003, h 26 weeks, nu_T 3.
    tau, rho, g = 0.0003, 0.5 ** (1 / 26), 0.0006
    z = np.zeros(d.weeks)
    z[0] = rng.normal(0, tau / np.sqrt(1 - rho**2))
    for k in range(1, d.weeks):
        z[k] = rho * z[k - 1] + tau * rng.standard_t(3)
    L = np.concatenate([[0.0], np.cumsum(g + z)])
    trend = (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    sigma = np.array([0.12, 0.10, 0.11, 0.14])
    nu = 4.0
    y = d.x @ beta + trend + sigma[d.group] * rng.standard_t(nu, n)
    frame["latest_ask"] = np.exp(y)
    return frame, {"beta": beta, "sigma": sigma, "nu": nu, "L": L, "tau": tau}


def test_text_flags_copy_the_feature_patterns():
    for name, pattern in b0data.TEXT_FLAGS.items():
        assert features.DESCRIPTION_FLAGS[name] == pattern


def test_design_codes_cumulative_steps():
    frame = pd.DataFrame(
        {
            "latest_day": pd.to_datetime(["2020-01-06", "2020-01-09", "2020-01-20"]),
            "latest_ask": [2000.0, 3000.0, 4000.0],
            "bedrooms": [0.0, 2.0, 7.0],
            "full_baths": [1.0, np.nan, 3.0],
            "half_baths": [np.nan, 1.0, 0.0],
            **{f: [False, True, False] for f in b0.FLAGS},
        }
    )
    d = b0.design(frame)
    col = {n: d.x[:, j] for j, n in enumerate(d.names)}
    assert col["bed>=1"].tolist() == [0, 1, 1]
    assert col["bed>=2"].tolist() == [0, 1, 1]
    assert col["bed>=5"].tolist() == [0, 0, 1]
    assert col["full>=2"].tolist() == [0, 0, 1]
    assert col["full>=3"].tolist() == [0, 0, 1]
    assert col["bath_unknown"].tolist() == [0, 1, 0]
    assert col["half>=1"].tolist() == [0, 1, 0]
    assert col["flag:furnished"].tolist() == [0, 1, 0]
    assert d.group.tolist() == [0, 2, 3]
    # 2020-01-06 is a Monday: the grid starts there, and the 9th is 3/7 into week 0.
    assert d.start == pd.Timestamp("2020-01-06")
    assert d.week.tolist() == [0, 0, 2]
    assert np.allclose(d.frac, [0, 3 / 7, 0])
    assert d.weeks == 3


def test_slice_sampler_draws_a_normal():
    jax, jnp = b0._jax()

    def logp(x):
        return -0.5 * ((x - jnp.array([1.0, -2.0])) / jnp.array([0.5, 3.0])) ** 2

    step = jax.jit(lambda k, x: b0.slice_vec(k, x, logp, 1.0))
    x = jnp.zeros(2)
    key = jax.random.PRNGKey(0)
    out = []
    for _ in range(4000):
        key, sub = jax.random.split(key)
        x = step(sub, x)
        out.append(np.asarray(x))
    out = np.array(out[200:])
    assert np.allclose(out.mean(0), [1.0, -2.0], atol=0.15)
    assert np.allclose(out.std(0), [0.5, 3.0], rtol=0.1)


@pytest.fixture(scope="module")
def recovery():
    frame, truth = frame_of()
    d = b0.design(frame)
    settings = b0.Settings(chains=2, warmup=300, draws=400, keep_every=4, seed=3)
    out = b0.run(d, b0.Priors(), settings, log=lambda m: None)
    return d, truth, out


def test_sampler_recovers_simulated_coefficients(recovery):
    d, truth, out = recovery
    beta = out["kept"]["beta"].reshape(-1, len(d.names))
    lo, hi = np.quantile(beta, [0.005, 0.995], axis=0)
    # alpha and the trend share a level only through L_0 = 0, so alpha is checked with the
    # trend's level at week 0 folded in, and the rest on their own.
    miss = [
        n
        for j, n in enumerate(d.names)
        if j > 0 and not lo[j] <= truth["beta"][j] <= hi[j]
    ]
    assert len(miss) <= 1, miss
    assert abs(np.median(beta[:, 0]) - truth["beta"][0]) < 0.05


def test_sampler_recovers_scales_and_tails(recovery):
    d, truth, out = recovery
    sigma = out["kept"]["sigma"].reshape(-1, 4)
    assert np.allclose(np.median(sigma, 0), truth["sigma"], rtol=0.12)
    nu = np.median(out["kept"]["nu"])
    assert 2.5 < nu < 7
    L = out["kept"]["L"].reshape(-1, d.weeks + 1)
    shift = np.median(L, 0) - truth["L"]
    # The trend is identified up to the level alpha absorbs; its shape must match.
    assert np.std(shift[5:-5]) < 0.03


def test_diagnostics_and_summary(recovery):
    d, truth, out = recovery
    diag = b0.diagnostics(out["trace"], d.names)
    # At 50 rows a week the toy barely identifies the weekly slope shocks, so tau and nu_T stay
    # near their priors and mix slowly; the real fit's diagnostics cover them.
    trend = ("tau", "nu_t", "h", "g")
    rhat = {n: q["rhat"] for n, q in diag["per_quantity"].items() if n not in trend}
    assert max(rhat.values()) < 1.1, rhat
    s = b0.summarize(out["kept"], d.names)
    assert s["coefficients"]["bed>=2"]["median"] == pytest.approx(
        100 * math.expm1(0.3), abs=4
    )
    season = b0.season_curve(out["kept"], d.names)
    assert season["curve"].shape[1] == 365


def test_prior_predictive_is_plausible():
    frame, _ = frame_of(n=3000, weeks=880)
    d = b0.design(frame)
    pp = b0.prior_predictive(d, b0.Priors(), draws=100, rows=2000)
    assert pp["share_1000_30000"] > 0.8
    assert 1000 < pp["rent_quantiles"]["0.5"] < 10000


def test_run_and_score(tmp_path, monkeypatch):
    from rentfrontier import loo
    from rentfrontier import run as runmod

    frame, _ = frame_of(n=3000, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(loo, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "b0", "--features", "base-v1",
            "--chains", "2", "--warmup", "100", "--draws", "100", "--keep-every", "5",
            "--name", "b0-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "b0-test" / "result.json").read_text())
    assert result["sampler"] == "b0" and result["split"] == "latest"
    assert result["sizes"]["heldout"] > 0
    record, pointwise = b0.score("b0-test")
    assert record["rows"] == result["sizes"]["train"]
    assert np.isfinite(record["elpd_loo"])
    assert 0.5 < record["heldout"]["coverage_95"] <= 1
    assert len(record["scorecard"]) == 8
    assert pointwise["heldout_quantiles"].shape == (result["sizes"]["heldout"], 5)
    # Threads over several row blocks give every row the same numbers, and the same numbers as
    # one block holding every row.
    monkeypatch.setattr(b0, "LOO_BLOCK", 700)
    monkeypatch.setattr(b0, "PRED_BLOCK", 100)
    record2, pointwise2 = b0.score("b0-test", workers=3)
    for key in ("elpd_loo", "pareto_k"):
        np.testing.assert_allclose(pointwise2[key], pointwise[key], rtol=1e-12)
    assert record2["elpd_loo"] == pytest.approx(record["elpd_loo"], rel=1e-12)
    assert record2["pareto_k"] == record["pareto_k"]
    # Held-out draws are seeded by block, so they follow the block size but not the workers.
    record3, pointwise3 = b0.score("b0-test", workers=1)
    np.testing.assert_array_equal(
        pointwise3["heldout_quantiles"], pointwise2["heldout_quantiles"]
    )
    assert record3["heldout"] == record2["heldout"]
    assert record2["heldout"]["elpd"] == pytest.approx(
        record["heldout"]["elpd"], rel=1e-12
    )
    # Switching a step off leaves the other as it was and drops the first's fields.
    only_held, pw = b0.score("b0-test", workers=2, loo_step=False)
    assert "elpd_loo" not in only_held and "elpd_loo" not in pw
    assert only_held["steps"] == {"loo": False, "heldout": True}
    assert only_held["heldout"] == record2["heldout"]
    only_loo, pw = b0.score("b0-test", workers=2, heldout_step=False)
    assert "heldout" not in only_loo and "heldout_quantiles" not in pw
    assert only_loo["elpd_loo"] == record2["elpd_loo"]
    assert only_loo["summary"] == record["summary"]
    neither, pw = b0.score("b0-test", loo_step=False, heldout_step=False)
    assert "elpd_loo" not in neither and "heldout" not in neither
    assert neither["steps"] == {"loo": False, "heldout": False}


def test_psis_vectorized_matches_arviz():
    from rentfrontier import loo

    rng = np.random.default_rng(0)
    rows = 300
    scale = rng.uniform(0.05, 2.0, rows)
    ll = -0.5 * (rng.standard_t(4, (656, rows)) * scale) ** 2 - np.log(scale)
    ll[:, 5] = 1e-3 * rng.normal(size=656)
    # A short block and a long one.
    for draws in (60, 656):
        want = loo.psis_loo(ll[:draws], block=77, impl="arviz")
        got = loo.psis_loo(ll[:draws], block=77)
        for a, b in zip(want, got):
            np.testing.assert_allclose(b, a, rtol=1e-9, atol=1e-11, equal_nan=True)
    # The block size does not change a row.
    np.testing.assert_allclose(
        loo.psis_loo(ll, block=50)[0], loo.psis_loo(ll, block=300)[0], rtol=1e-12
    )


def test_loglik_rows_matches_scipy():
    from scipy.stats import t as student

    frame, _ = frame_of(n=500, weeks=60, seed=3)
    d = b0.design(frame)
    rng = np.random.default_rng(1)
    kept = {
        "beta": rng.normal(0, 0.1, (2, 5, d.x.shape[1]))
        + np.r_[8, [0] * (d.x.shape[1] - 1)],
        "L": rng.normal(0, 0.05, (2, 5, d.weeks + 1)),
        "nu": rng.uniform(3, 30, (2, 5)),
        "sigma": rng.uniform(0.1, 0.4, (2, 5, 4)),
    }
    beta, L = kept["beta"].reshape(10, -1), kept["L"].reshape(10, -1)
    mu = beta @ d.x.T + (1 - d.frac) * L[:, d.week] + d.frac * L[:, d.week + 1]
    want = student.logpdf(
        d.y[None] - mu,
        kept["nu"].reshape(-1)[:, None],
        scale=kept["sigma"].reshape(10, 4)[:, d.group],
    )
    np.testing.assert_allclose(
        b0.loglik_rows(d, kept, 0, len(d.y)), want, rtol=1e-12, atol=1e-14
    )


def test_record_flags_date_page_prices_by_the_off_market_day(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    import pyarrow as pa
    import pyarrow.parquet as pq

    def record(off, changes):
        return json.dumps(
            {
                "description": "a sunny one bedroom with roommate wanted",
                "offMarketAt": off,
                "statusChanges": [{"changedAt": d, "status": s} for d, s in changes],
            }
        )

    rows = {
        1: record("2014-09-19T04:00:00Z", [("2014-09-09T00:00:00Z", "ACTIVE")]),
        # A draft has no offMarketAt; its move off the market comes after its last ACTIVE change.
        2: record(
            None,
            [
                ("2018-07-06T00:00:00Z", "ACTIVE"),
                ("2023-07-27T00:00:00Z", "NO_LONGER_AVAILABLE"),
                ("2023-07-28T00:00:00Z", "DRAFT"),
            ],
        ),
        # Going into contract leaves the ad on the market.
        3: record(
            None,
            [
                ("2021-07-19T00:00:00Z", "ACTIVE"),
                ("2021-07-20T00:00:00Z", "IN_CONTRACT"),
                ("2021-07-21T00:00:00Z", "TEMPORARILY_OFF_MARKET"),
            ],
        ),
        4: record(None, [("2026-10-01T00:00:00Z", "ACTIVE")]),
        # A relisted ad's old offMarketAt gives way to its move off the market after relisting.
        5: record(
            "2019-03-01T00:00:00Z",
            [
                ("2019-02-01T00:00:00Z", "ACTIVE"),
                ("2019-03-01T00:00:00Z", "RENTED"),
                ("2020-05-01T00:00:00Z", "ACTIVE"),
                ("2020-05-20T00:00:00Z", "NO_LONGER_AVAILABLE"),
            ],
        ),
    }
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": list(rows),
                "collected_at": [1.76e9] * len(rows),
                "last_collected_at": [None] * len(rows),
                "raw_listing_json": list(rows.values()),
            }
        ),
        path,
    )
    con = duckdb.connect()
    con.execute(b0data.record_flags(path))
    got = dict(con.sql("SELECT listing_id, off_day FROM recf").fetchall())
    assert got == {
        1: "2014-09-19",
        2: "2023-07-27",
        3: "2021-07-21",
        4: None,
        5: "2020-05-20",
    }
    assert con.sql("SELECT bool_and(shared_space) FROM recf").fetchone()[0]
