# Adversarial Critique of the Improvement Plan (`plan.md`)

Checks: `/data1/apartments/tmp/pi-review/adv_check.py`, `adv_check2.py`, `adv_check3.py`, `adv_check4.py`.

## 1. Central Evidence Audit (P2 and P3)

### P2 (`b0closingraise` on Deals)
- **Diluted transfer from `c3` vs `b9`:** On 2025–2026 unchanged targets (`n=68,864`), `c3` beats `b9` by `+321.0 ± 58.4` elpd: `+202.7 ± 44.1` on `4,806` CR-unit ads (`6.98%`), `+130.3 ± 31.8` on `33,327` CR-building/non-CR-unit ads, and `-12.0 ± 11.8` on `30,731` untouched-building ads (`-183.3 ± 23.0` all years). On `range-j`, `33.9%` (`3,164/9,346`) of open ads have `unit_ads=0` (absent from `latest`), nearly halving CR-unit share to **`3.87%` (`345/8,906`)**. On live `range-m2`, `91/295` (`30.8%`) CR-unit ads are already cautioned; only `12/136` uncautioned `<5%` ads sit in CR units, and `verify_tail.log` (`w=0.5`) moves **`4/100`** top deals (bottom of `plan.md`'s `4–12` range).
- **Target changes & selection:** `b0closingraise.py:194` rewrites `latest_ask` on **`440/9,346`** backtest open ads whose post-`2025-11-10` close included a raise (`res=+0.0271`, `<5%=3.18%` vs `+0.0088`, `4.61%` on `8,906` unchanged). Dropping those `440` selects on a future post-day outcome (`61` CR-unit, `397` CR-building); scoring all `9,346` at `y_jcr` scores `range-j` on untrained targets.
- **Rent-in-feature check:** `b0closingraise.py:194-200` uses `latest_ask > before` to move **`latest_day`** earlier on **`49,862`** training rows (median `11`d, p90 `33`d, max `1,527`d), entering `L(t)`, season, `a_s(q)`, and OU gaps `|t_open-t_train|`. Open rows keep their scoring day (`0` changed), so no held-out rent enters a feature (target-date cleaning, not a leak).
- **Held scales fitted on old targets:** `b9→c3` shifted `nu` `+1.41%` (`+2.8` SD: `1.692→1.716`), `building_ar_sd` `-1.73%` (`-3.1` SD: `0.0770→0.0756`), `sigma[3]` `+1.26%`, `tau` `+3.41%`. Holding `base-j9`/`base-n9` avoids `c3`'s `-183.3` untouched-building penalty, but stacks a fourth unrefitted change (`bedtext`, `layout`, `layout-range`, `closingraise`; `base-short→bedbase-short` moved `unit_sd` `-1.51%`) onto `drift-building` scales—serviceable for one `$4.10` test, not indefinite stacking.

### P3 (Re-Pinned Floor-1 + Duplex) — Central Evidence Broken
- **12-sigma collapse bug & existing absorption:** `building_zones_floor.py` and `..._cap64.py` **already** pin both GPs at floor 1 (`f(log 1)=0`) with separate free steps: `unit:elev_f2=+0.0086±0.0007` vs `unit:walkup_f2=-0.0020±0.0005` (`range-m2`; `range-j`: `+0.0089` vs `-0.0024`; `l2bt`: `+0.0085` vs `-0.0033`)—a **`0.0106 ± 0.0009` (`12`-sigma)** difference. GP prior precision along a constant shift (`1'C^-1 1 = 806, 823`, `check_gp_ridge.py`) is `<0.04%` of data precision (`2–4×10^6`), so GP shrinkage of floor 1 is `<1e-4`. Re-pinning both GPs at floor 2 (`k>=3`, dropping `elev_f2`/`walkup_f2`) with a **single** `unit:floor_1` forces `f_elev(2)-f_elev(1)==f_walkup(2)-f_walkup(1)`, **destroying a 12-sigma parameter**. Even two separate floor-1 columns span the exact existing subspace.
- **Post-hoc emulation artifact:** `verify_tail.py`'s `+62.6 ± 11.6` elpd shifted `l2bt` `fl==1 & ~dup` predictions by `-0.0044/-0.0094` without refitting. In `l2bt`, `model_fl==1 & ~dup` (`unit_floor.floor_table`) worsens with history (`n_tr=1: -0.0074` → `n_tr>=4: -0.0124`), gap (`<=1.2y: -0.0075` → `>3y: -0.0192`), and post-2022 (`-0.002` in 2018–21 → `-0.009` in 2022–26)—`latest_split` survivorship/drift, not a missing static intercept.
- **Zero plain floor-1 gap on `range-j`:** Using `model_fl`, **`fl==1 & ~dup` (`n=501`, `+0.0037 ± 0.0047`) sits *above* `fl==2 & ~dup` (`n=838`, `+0.0028 ± 0.0038`)**, and unseen units (`model_fl==1 & ~has_u`, `n=253`) sit at `+0.0085 ± 0.0085`. `plan.md` compared `fl==1` to `+0.0097` overall only because `floor_unknown` sits at `+0.0196`; in `verify_extra.log`, floor-1 ads *lost* `-1.08` elpd on `range-j`.
- **`ad:floor_1_duplex` alone is tiny:** P3's only new term. On `l2bt` 2025–26 (`n=986`), `78.2%` of prior training ads are already `duplex` (absorbed by `u_i`), leaving `~+23.9 ± 4.7` elpd (not `+62.6`). On `range-j` (`n=135`, `-0.0170 ± 0.0094`), it gives `+3.86 ± 3.12` elpd. On live `range-m2` (`72` uncautioned, `4/136 <5%`), shifting `-0.015..-0.025` moves **`1–2/100`** top deals for **`$8.20`**.

## 2. Project Rules Check

- **P1 (`range-m3`):** Compliant once F1 updates `docs/notes/market-refresh-2026-11-20.md` caution range (`18–23%→22–28%`) before launch.
- **P2 (`b0closingraise`):** One change, no hashed module edited, predictions pre-committed; shares `c3`'s unchanged-target comparison caveat (`440/9,346` targets changed, `closing-asks-2026-11-11.md`).
- **P3:** **Fails "one change per fit"**—bundles (i) re-pinning/collapsing both floor GPs + `unit:floor_1`, (ii) `b0duplex` + `ad:floor_1_duplex`, and (iii) a `c3`-scales `latest` wrapper (`..._range_c3.py`). Also fails "Modal money only on terms that change which ads show as deals" (`1–2/100` deals for `$8.20`). Registry/ops files (`run.py`, `cap.py`, `app.py`) are not hash-locked (`ruff.toml`).

## 3. Costs and Acceptance-Rule Power

- **Ledger (`/data1/apartments/modal/ledger.jsonl`):** 31 settles since `2026-11-14`, `$76.35` spent, **`$23.65` left**; 7 held-scales Deals fits cost **`$1.95–$2.06`** (mean `$2.00`), matching `plan.md`.
- **P2's `+2.0`-SE gate is underpowered:** Scaling `c3-b9` 2025–26 strata to `range-j`'s `8,906` unchanged ads gives `E[d_elpd]=+29.1`, `SE=16.9` (`E[z]=1.72`, **`39.1%` power**; `45.7%` if untouched=`0`; `27.0%` all-years `c3-b9`). Adding 2-chain MCMC noise (`SE=5.91`, `range-j` chain 0 vs 1) lifts SE to `~17.9` (`~36%` power). Requiring `>+2.0` SE makes false rejection **`>60%` likely** for a fix proven at `5.5–6.4` SE on `69k–183k` ads (`verify_fast.log` got `-6.4±17.1` / `+4.6±18.9`).
- **P3 power:** Collapsing `elev_f2`/`walkup_f2` risks *negative* `d_elpd` on `latest`, wasting `$4.10`.

## 4. `ops/deals-refresh` Readiness for P2

`ops/deals-refresh` **cannot run P2 without edits**:
1. `datasets` (`ops/deals-refresh:67-86`) builds `...-market-bedtext` directly from `...-market`, omitting `rentfrontier.b0closingraise`. Edit: insert `b0closingraise` before `b0bedtext` (or behind an env flag).
2. `fit` (`ops/deals-refresh:88-99`) hardcodes `dataset=$datasets/b0-$hash-alldata-dense-nyc-market-bedtext` and `--split market` with no `DATASET` override, blocking `cr-m3` and `cr-j` (`...-asof-20251110-closingraise` exists; needs `b0bedtext` + direct `ops/modal-fit` with `base-j9`).
3. `publish` already honors `BACKTEST=...` (`drift_deals.py:_raised`/`validate` read `latest_ask`, updating `raised`/`share_raised` mechanically).

## 5. Verdicts and Alternative Allocation

- **F1–F4 ($0): Go** (F1 before P1; F2–F4 after P1).
- **P1 (`range-m3`, `~$2.05`): Go.**
- **P2 (`b0closingraise`, `~$4.10`): Go with changes:** (a) Replace the `<40%`-power `+2.0`-SE gate with a non-regression + targeted gate (`cr-j` passes convergence, `d_elpd>0` on `8,906` unchanged ads, CR-unit `n=345` `d_elpd>0` with `<5%` dropping to `4–7%`, non-CR `8,561 >= -1.0` SE); (b) land the `ops/deals-refresh` edits (plus direct `b0bedtext`/`ops/modal-fit` for `cr-j`); (c) narrow live top-100 prediction from `4–12` to `3–8`.
- **P3 (Floor-1 + Duplex, `$4.10–$8.20`): Drop.**
- **Saved `$8.20` (`~$17.50` left after P1+P2):** Keep `$4–$6` for 2–3 `range-m` refreshes and **bank `~$11.50–$13.50`** toward the `$22` free-scales base refit fixing the variance defects dominating top-100 deals (`changed-count`, `3+` baths, new-unit/lease-phase dispersion), folding `ad:floor_1_duplex` (keeping separate `elev`/`walkup` pins) and F5 hygiene into that refit at `$0` extra fit cost.
