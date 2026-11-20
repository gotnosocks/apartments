# Closing-raise cleaning for Deals (2026-11-20)

On 2026-11-20 the owner approved applying `rentfrontier.b0closingraise` before
`rentfrontier.b0bedtext` on the Deals datasets (`CLOSING_RAISE=1` in `ops/deals-refresh`, added
by PR #1465). That
step drops a price raise typed within 5 minutes before an ad's off-market status event or after
it, replacing it with the ask standing before the raise (`docs/notes/closing-asks-2026-11-11.md`).
Everything else stays the same: the model (`drift-building-bedtext-layout-range`), the held
scales (`base-j9` for backtest, `base-n9` for market), the sampler settings (`2 200 3600 20
--seed 1 --level-dof 4 --no-loo --no-heldout` on one H100), the cautions code, and all hashed
model modules. Two fits are planned at about $2.05 each on Modal: backtest run `...-cr-j` on
`b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-closingraise-bedtext` (`50,723` training
rows repriced, `base-j9`, compared with `range-j`), and market run `...-cr-m3` on
`b0-4f487ef77bb6ca61-alldata-dense-nyc-market-closingraise-bedtext` (`base-n9`, compared with
`range-m3`, the Nov 20 refresh fit on build `4f487ef77bb6ca61` without the cleaning). The market
fit runs only if `cr-j` is accepted. On the backtest, `440` of the `9,346` held-out ads receive a
different target under `b0closingraise` because their later close included a raise, so backtest
comparisons are stated on the `8,906` unchanged-target ads, with the `440` reported separately.

## Acceptance rule

Fixed before launch, written on 2026-11-20 at 3:25 PM ET. The owner approved the critique's
non-regression and targeted rule over a `+2` SE gate. Scaling `c3` minus `b9` on 2025-2026
unchanged ads to `range-j`'s strata yields an expected gain of `+29.1` elpd with a
building-clustered SE of `16.9` (`E[z] = 1.72`, `39%` power at `+2` SE, falling to about `36%`
with 2-chain Monte Carlo noise), so a `+2` SE threshold would reject a fix already established at
`5.5` to `6.4` SE on `69,000` to `183,000` ads more than `60%` of the time.

`cr-j` is accepted if all four conditions hold (no reseeding on any failure):

- Convergence gate passes: worst split R-hat at most `1.01` and least bulk ESS above `400` on
  every scalar and coefficient.
- Overall `d_elpd` (`cr-j` minus `range-j`), as a point estimate, is above `0` on the `8,906`
  unchanged-target ads.
- Closing-raise-unit `d_elpd`, as a point estimate, is above `0` on the `345` closing-raise-unit
  ads among those `8,906`.
  This group is the set of unchanged-target open ads whose non-null `(building, unit_id)` key has
  at least one training row (`open == False`) repriced by `b0closingraise` (`latest_ask_how ==
  "latest, before closing raise"` in the cleaned dataset). Group membership reads only training
  rows and unit keys, without reading any held-out rent.
- Remaining-ads `d_elpd` on the other `8,561` unchanged-target ads, divided by its own
  building-clustered SE, is at least `-1.0`.

If `cr-j` is accepted, `cr-m3` launches; if `cr-m3` passes the same convergence gate, Deals
publishes from `cr-m3` with `cr-j` as its backtest. If any condition fails for `cr-j`, the gate
included, `cr-m3` is not launched and Deals stays on `range-m3` and `range-j`. If `cr-m3` misses
the gate, Deals stays on `range-m3` and `range-j` as well.

## Predictions, written before the builds and fits

- Cost: `$1.90 to $2.20` per container (central `$2.05`; `$3.80 to $4.40` for both fits). Source:
  verified in `/data1/apartments/modal/ledger.jsonl` across 7 held-scales Deals runs (`$1.95 to
  $2.06`, mean `$2.00`; `range-j` `$2.04`, `range-m2` `$2.05`).
- Gate outcome: both `cr-j` and (if launched) `cr-m3` pass in one container, with worst split
  R-hat `1.003 to 1.008`, least bulk ESS `550 to 900`, and sweep time `0.32 to 0.37 s`. Source:
  verified in `result.json` for `range-j` (`1.0042`, ESS `676`, `0.330 s`), `range-m` (`1.0057`,
  ESS `789`, `0.356 s`), and `range-m2` (`1.0061`, ESS `757`, `0.354 s`).
- `d_elpd` (`cr-j` minus `range-j`, SE clustered by building): `+10 to +55` overall on the
  `8,906` unchanged-target ads (central `+29`, SE `14 to 20`), `+3 to +35` on the `345`
  closing-raise-unit ads (central `+15`, SE `9 to 15`), and `-5 to +35` on the remaining `8,561`
  ads (central `+15`, SE `10 to 15`). Source: verified from `c3` minus `b9` `pred_scores.npz` on
  2025-2026 unchanged ads (`n = 68,863`, `+321.0`, SE `58.4`), scaled to `range-j`'s exact strata
  (`345` closing-raise-unit ads, `4,168` other ads in repriced buildings, `4,393` in buildings
  with no repriced row), aligning with `plan.md` and `plan-critique.md`. The `440` changed-target
  ads are reported separately by median absolute error on each model's own target.
- Share of the `345` closing-raise-unit ads below the 5% point: `9.57%` (`33` of `345`) in
  `range-j`, falling to `4.0% to 7.0%` (`14 to 24` ads, central `5.2%`) in `cr-j`. Source:
  baseline verified via `drift_score.score_run` on `range-j`; range from `plan-critique.md` (`4%
  to 7%`) and `plan.md` (`4.5% to 6.7%`), matching the `44%` relative drop in `c3` vs `b9`
  (`6.37%` to `3.54%`) and the `range-j` emulation (`4.06%`).
- Backtest interval coverage on the `8,906` unchanged-target ads: 80% coverage stays in `0.788 to
  0.798` (`0.793` in `range-j`) and 90% coverage stays in `0.887 to 0.897` (`0.892` in `range-j`).
  Source: baseline verified via `drift_score.score_run` on `range-j`; `0.005` band from `c3` vs
  `b9` `pred_scores.npz` shifts (`-0.0003` for 80%, `-0.0005` for 90% overall) plus 2-chain and
  finite-sample noise with scales held fixed.
- Live top 100 uncautioned deals changed between `range-m3` and `cr-m3`: `3 to 8` from score
  shifts with cautions held fixed (`plan-critique.md`, from `range-m2` emulations moving `4` to
  `9` of 100), and `5 to 13` in the published uncautioned top 100 once dropped `raised` cautions
  enter. Rechecking the Nov 9 market pair (`ddd2fe8f5da041b8-market` vs `...-closingraise`) shows
  `127` dropped `raised` marks uncautioning `90` ads, `11` of which stood below the top-100 cutoff
  before building-level drops (`-0.04` to `-0.18` log shift) push roughly half back out, leaving
  about `3 to 5` extra entries. Unverified on build `4f487ef77bb6ca61`, as neither its cleaned
  dataset nor `range-m3` is on disk yet.
- Change in `raised` cautions: `-95 to -155` on the Nov 20 live market (`cr-m3` vs `range-m3`,
  central `-124`, from the verified uncleaned count of `653` of `6,502` open ads down to roughly
  `498 to 558`), scaled from the `-19.0%` drop verified on the Nov 9 market pair (`669` to `542`,
  `-127`, `0` added). Unverified on build `4f487ef77bb6ca61` until its cleaned dataset is built. On
  the backtest (`final=True`), the drop is `-336` (`1,028` to `692`, `-32.7%`), already verified
  from `b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110` and its `-closingraise` copy.

The plan and its critique, written by Gemini sessions and cited above as `plan.md` and
`plan-critique.md`, are in `docs/notes/deals-closingraise-2026-11-20/`. The cost range is for a
completed container and leaves out aborted launches such as the `$0.10` first attempt of
`range-m2`.

## Scored

| Metric | Prediction | Result | Verdict |
| --- | --- | --- | --- |
| Cost per fit (`cr-j` / `cr-m3`) | `$1.90 to $2.20` each | `cr-j` `$1.97`; `cr-m3` not run | inside |
| Gate (`cr-j` / `cr-m3`) | R-hat `<= 1.01`, ESS `> 400` | `cr-j` passed: worst R-hat `1.0060`, least bulk ESS `696`, `269` quantities, `0.332 s` a sweep; `cr-m3` not run | inside (R-hat `1.003 to 1.008`, ESS `550 to 900`, sweep `0.32 to 0.37 s`) |
| `d_elpd` on `8,906` unchanged ads | `+10 to +55` (gate `> 0`) | `-59.1`, SE `31.4`, z `-1.88` (`9,601.4` to `9,542.3`) | outside, wrong sign; gate failed |
| `d_elpd` on `345` closing-raise-unit ads | `+3 to +35` (gate `> 0`) | `+13.1`, SE `15.1`, z `+0.87` (`400.4` to `413.6`) | inside; gate passed |
| `d_elpd` on `8,561` remaining ads | `-5 to +35` (gate: `d_elpd / SE >= -1.0`) | `-72.2`, SE `27.4`, z `-2.63` (`9,200.9` to `9,128.7`) | outside; gate failed |
| Closing-raise-unit `<5%` share (`345` ads) | `9.57%` (`range-j`) to `4.0% to 7.0%` (`cr-j`) | `9.57%` (`33`) to `4.35%` (`15`) | inside |
| Backtest 80% / 90% coverage (`8,906` ads) | `0.788 to 0.798` / `0.887 to 0.897` | `0.790` / `0.893` (`range-j` `0.793` / `0.892`) | inside both |
| Changed-target `440` ads (separate report) | median abs error on own target | `0.0525` for `cr-j` against `0.0524` for `range-j`, each at its own target; median log target change `-0.0871`. Below the 5% point `13` (`2.95%`) in `range-j`, `58` (`13.18%`) in `cr-j`; 80% / 90% coverage `0.780` / `0.895` against `0.752` / `0.830`. `d_elpd` `-48.8`, SE `43.9`, at its own target; `-235.8`, SE `52.6`, with `cr-j` held to the old target | reported, no prediction range |
| Live top 100 uncautioned deals changed | `3 to 8` (scores) / `5 to 13` (net) | not run (depends on `cr-m3`) | not run |
| `raised` cautions delta (`cr-m3` / `cr-j`) | `-95 to -155` / `-336` | `cr-m3` not run; the backtest `-336` is a count from the datasets and was not read from this fit | not run |

### Acceptance rule outcome

Gate: pass. (a) `d_elpd > 0` on the `8,906`: fail (`-59.1`). (b) `d_elpd > 0` on the `345`: pass
(`+13.1`). (c) z at least `-1.0` on the `8,561`: fail (`-2.63`). Under the failure rule `cr-j`
is rejected, `cr-m3` is not launched, and Deals stays on `range-m3` with backtest `range-j`.
Spend: `$80.43` of the `$100` after this fit, `$19.57` left.

### Other splits of the `8,561` remaining ads

| Group | n | `range-j` | `cr-j` | `d_elpd` | SE | z |
| --- | --- | --- | --- | --- | --- | --- |
| remaining, in buildings with a repriced row | `4,168` | `4,857.3` | `4,831.0` | `-26.3` | `26.4` | `-1.00` |
| remaining, other buildings | `4,393` | `4,343.6` | `4,297.7` | `-45.9` | `7.3` | `-6.32` |
| all held-out | `9,346` | `10,042.1` | `9,934.3` | `-107.8` | `65.5` | `-1.65` |

Below the 5% point (`range-j`, `cr-j`): all held-out `433` (`4.63%`) and `390` (`4.17%`);
unchanged `420` (`4.72%`) and `332` (`3.73%`); remaining `387` (`4.52%`) and `317` (`3.70%`).
Median absolute error on the unchanged ads is `0.0465` and `0.0470`. Mean log ask minus
prediction on the full held-out set is `+0.0097` for `range-j` and `+0.0151` for `cr-j`.

The scoring script and its table are `docs/notes/deals-closingraise-2026-11-20/score.py` and
`docs/notes/deals-closingraise-2026-11-20/range-j__cr-j.json`. The per-ad parquet stays on
`/data1/apartments/tmp/po-crj-score/`, where the script was run (`score.py --old range-j --new
cr-j`); it writes its outputs beside itself unless `--out` names another folder.

## What it shows

The cleaning did what it was aimed at on the `345` closing-raise-unit ads: their share below the
5% point fell from `9.57%` to `4.35%`, inside the `4.0%` to `7.0%` prediction, and `d_elpd` on
them is positive, within one SE. Lowering `50,723` training asks also lowered predictions on
average.
Bias rose from `+0.0097` to `+0.0151`. The loss is clearest in buildings with no repriced row
(`-45.9`, z `-6.3`), where the change would have to arrive through shared terms. So as a
whole-dataset change it appears to cost more than it gains. A narrower form, such as repricing
only as the unit's own record or only for scoring cautions, is a candidate and is untested. The
prediction of `+10 to +55` overall was wrong in sign.
