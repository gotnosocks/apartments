# Chelsea pricing research backlog

## Served-model review and ranked hypotheses (2026-10-08, during the run pause)

This is a no-fit review of the served fit (coded-v2 refit on quarantine-v10 and ad-v3, PSIS-LOO
139,842.7 ± 386.4, 135,540 rows). It uses only the summary's rows, intervals and term columns,
with scripts in `/data1/apartments/tmp/bridge/review/`.

**Calibration.**
- Held-out rows (13,569): bias −0.6%, median absolute error 3.8%, 80% interval coverage 0.792,
  95% coverage 0.949.
- Weak spots in 95% coverage:
  - units with a single listing: 0.921 (32,500 rows), with a median absolute error of 6.0% against
    3.8% for repeat units;
  - 5-bedroom units: 0.891;
  - Greenwich Village: 0.931;
  - the top price quintile: 0.931, overpredicted by 0.5%;
  - elevator buildings: 0.942.
- Non-elevator rows are over-covered (0.954).
- Single-listing residuals have tails twice as wide as repeat units: the 1% and 99% quantiles are
  −43% and +47%, against −21% and +21%.

**Tested without a fit:**
- **Unit drift or decay: refuted as a gain.** Two things looked like drift:
  - Consecutive residuals of a unit grow more negatively correlated as the gap between them grows.
    For units with 3 to 5 rows, the correlation falls from −0.02 within a year to −0.34 past 8 years.
  - Held-out rows more than 4 years outside the unit's training span are overpredicted by 1.2%.

  But fading the unit effect with the time distance, `u · exp(−d/τ)`, does not improve those
  held-out rows. The best τ is 20 years, which moves median absolute error by −0.01 points, and
  shorter τ is worse. The unit premium persists. Unit drift (m8, +360 earlier, slow to mix)
  stays deprioritized.
- **First listing of a unit does not drift with year: refuted, keep the term.** The served fit
  gives `first_listing_of_unit` +23.8% (95% 14.6 to 33.2). Its share falls from 96% of rows in 2010
  to 25% in 2026, which is left-censoring at the start of the data. The median residual gap
  between first listings and the rest stays within ±0.9% every year from 2012 to 2026, with no
  trend. Data's check: `tmp/suspect/conc/firstlist.py`.
- **Concession asks: no drop rule.** Structured concessions (monthsFree, netEffectiveRent, 2020
  on) are already outside the cohort. Before 2020 a concession appears only in the ad text, on
  about 6% of rows. The served fit prices that text at −1.1% (95% −1.35 to −0.88), and those rows
  now miss by a median of +0.28% before 2020 and +0.17% after. Asks that equal a quoted net-effective
  figure are about 0.27% of rows. Data kept the rows and added the era-split set
  `nb5-concera-v1` (#551) to the resume queue. Script: `tmp/bridge/review/conc.py`.
- **Missing square feet: no gap.** Rows with and without square feet have the same bias, error and
  coverage. This lowers "Latent square footage" (Model structure, below).
- **Building effects are well pooled.** Among buildings with 20 or more rows, the mean residual
  varies by only 1.6%. Spatial priors matter for small buildings only, so "Small-building
  pooling" stays scoped to them.

**Neighbourhood label against location (Ben, 2026-10-08 16:29Z).** A Chelsea building beside the
West Village may be pricier from proximity, and separately carry a "Chelsea" label effect. Here
the label is StreetEasy's area for the building, fixed per building (no building has two labels).
So the split is identified only at the borders, as a spatial discontinuity: a label effect is a
step at the border, while proximity is a smooth gradient.

The no-fit border check (`review/rd.py`) uses the served fit's building level plus its label
term, in bins of distance to the nearest building with the other label:
- **Chelsea → West Village.** About +12%, mostly a step:
  - Chelsea buildings within 150 m of the border are flat (−1% to 0%), so there is no spillover
    on the Chelsea side.
  - West Village buildings within 75 m sit 6% below their label. Part of the label's step there
    is smooth.
- **Chelsea → Flatiron.** Smooth: Chelsea buildings within 150 m are already +4 to +5%.
- **Flatiron → Gramercy Park.** Gramercy Park's label is −14%, but its buildings within 150 m
  of Flatiron carry +7 to +9% building levels that undo most of it. That is proximity which
  the building effects absorb, one building at a time.
- **Greenwich Village → West Village.** Nearly continuous.

So the labels act as steps that the per-building effects partly undo near the borders. A smooth
location surface would pool that correction across buildings, which matters for small and new
buildings.

Test, on Modal when fits resume:
- `nb5p3-loc-v1` (queued): the labels plus 250 m bumps. Read the label effects (`effects.py`).
  If they shrink toward zero, the price was proximity; if they hold, it is the label.
- `nb5p3-locnolabel-v1` (#535): the surface without the labels. If its PSIS-LOO ties loc-v1, drop
  the labels (simpler model). If loc-v1 wins, the label carries a price beyond location.
- Later: label × time against a space × time surface (Model structure, below). A 250 m bump grid
  can mimic part of a step, so read the border bins again after the fits.

**Ranked for when fits resume:**
1. **Heteroscedastic noise beyond bedrooms.** Use a noise scale per neighbourhood and a smooth
   log-scale in log asking level or log size. The under-coverage in Greenwich Village, the top
   quintile and 5-bedroom units, and the over-coverage without an elevator, all point here, and
   the bedroom noise scales were a large gain (#142). This sharpens the open item of the same name
   under "Model structure for the full-data frontier": with Greenwich Village now in the data, use
   neighbourhoods rather than the two areas. It is a model-term change: one exploration
   fit, then a full fit if it gains.
   *No-fit check (2026-10-08):* I approximated each in-fit row's LOO predictive under the served
   fit as a Student-t, using its 80% and 95% intervals. Then I fitted a noise-scale multiplier per
   group on half the rows (even audit_id) and scored it on the other half. One global multiplier
   (1.037) gains +118 ELPD (doubled from the held half). Gains beyond that global multiplier:

   | Groups | Gain beyond global | Notes |
   |---|---|---|
   | Predicted-level quintile | +100 | top quintile 1.12, the rest 1.01–1.02 |
   | Neighbourhood | +66 | Greenwich Village 1.10, West Village 1.05, Chelsea 1.01 |
   | Single-listing units | +49 | single listings 1.09, repeat units 1.02 |
   | All three crossed | +276 | |

   Residual 5-bedroom inflation is 1.32, even with the bedroom noise scales. This is a post-hoc
   rescale of the predictive, not a refit, so a real fit will gain less. Still, it supports a
   design with three parts: a smooth noise log-scale in the predicted level, a scale per
   neighbourhood, and a single-listing scale. Script: `tmp/bridge/review/noisegain.py`.
2. **Intervals for new apartments.** This is the site's "new apartment" case (Website measured a
   9.4% miss on 517 asks). First, a no-fit audit of the single-listing rows with |residual| > 40%,
   for Data: wrong unit or bedroom count, or a furnished or short-term ask. Then a fit with
   Student-t unit effects (`t_units`) on Modal, where mixing time matters less than on the local RTX 2060 SUPER.
3. **The queue after the pause** is unchanged by this review: the pluto3 base, then the nb5p3
   rebased tests, then unical.
4. **Early years (2010–13).** Single listings are underpredicted by 1.6%, from sparse data. This is
   low priority: it fades with yearnoise, and few rows are affected.
5. **Line term, re-tested** (check 7 below). This ranks above items 2–4 on the resume queue. Same-line peers predict single-listing residuals
   (slope 0.64). Run one Modal full fit of line effects (`line_min_units=2`) on the NB5 base
   after the pause.

### Review checks, sections 9 and 10 (Ben, 2026-10-08 20:11Z)

These are 12 no-fit checks on the same served fit. Residual means log(ask / median estimate) on
fitted rows (121,971), unless a check says otherwise. Scripts:
`/data1/apartments/tmp/bridge/review/r12/` (c12.py, c3.py, c8.py, c9.py).

**Results at a glance:**

| # | Check | Result | Next step |
|---|---|---|---|
| 1 | Walk steps on DOB permits | Responds barely | Leave permits out |
| 2 | Bedroom-time curves outside 2020–22 | Not flat | Keep `bedtime`; no COVID-only window |
| 3 | Year × building class | Excess dispersion (χ²/df 2.34) | Low priority |
| 4 | Variance shares | Labels 2.1%; labels + building + walk + unit 15.7% | Board note only |
| 5 | Single-listing tails | Widest in a building's first year | Data audit first, then ranked item 2 |
| 6 | Residual SD by missing fields | Missing floor matters most | Floor-unknown noise scale |
| 7 | Line peers of single-listing units | Strong signal (slope 0.64) | Re-test the line term (new item 5) |
| 8 | Relative floor, top floor | Nothing beyond the floor terms | None |
| 9 | Spatial correlation, small buildings | Weak, out to 500 m | Low priority |
| 10 | GV/WV multiplier within cells | Concentrated in small buildings and non-C classes | Building-size noise scale |
| 11 | 5-bedroom ad phrases | No mean shift, wider tails | Noise, not a mean feature |
| 12 | Ledger: global ×1.037 | Noise scales under-dispersed out of sample | Fit-side noise design |

1. **The building walk barely responds to DOB permits** (#437/#478).
   - The regression is a WLS of each fitted 6-month walk step (×100) on A1/A2/NB filing
     indicators at lags 0–2, weighted by 1/sd².
   - Over 122,536 steps (14,583 with a permit), the coefficients are:
     - A1 at lag 0: +0.06% (SE 0.035);
     - A2 at lags 0 and 1: +0.02% and +0.03%;
     - NB and all other lags: about 0.
   - For buildings with at least 20 rows, A1 at lag 0 is +0.20% (SE 0.08).
   - A permit-dated step feature would move estimates by a fifth of a percent, so leave permits
     out of the model.
2. **The bedroom-time curves are not flat outside 2020–22.** They are slow trends, not a COVID
   bump:
   - 2BR: +0.4% (2010) → −2.9% (2019) → −3.4% (2020) → −2.0% (2026).
   - 3BR+: −0.4% → −3.8% (2019) → −6.4% (2020) → −3.9% (2026).
   - Studio: −1.4% (2011) → +2.0% (2019) → −0.7% (2021) → +1.3% (2026).

   46% of the 2BR months outside 2020–22 are more than 2 sd from 0. Keep `bedtime` as it is; a
   COVID-only window would lose the trend.
3. **Year × building class shows excess dispersion** (χ²/df 2.34 over 77 cells).
   - The notable cells are 2021 C −1.1% (z −5.1), 2021 R +1.0%, 2014 R +1.0% and 2020 D −0.6%.
   - Year × lift class gives χ²/df 2.76 over 34 cells, led by 2013 lift-unknown at +1.6% and
     2014 elevator/doorman at +0.9%.
   - Over all years, the class means are C +0.07%, D +0.02%, R +0.29%, S +0.24% and other
     +0.63%.
   - A class × time curve could take the 2021 rental (C) dip. It is low priority: the cells are
     about 1%.
4. **Variance shares**, as a share of the variance of the log median estimate (0.206 overall):
   - Neighbourhood labels as their own group: 2.1% overall, and 0 within a neighbourhood by
     construction.
   - Building 7.0%, building walk 3.3%, unit 2.3%.
   - The descriptive "where and which apartment" share (labels + building + walk + unit) is 15.7%
     overall. That is the variance of the sum, so it includes the covariances among the four
     (about +1 point net), not just the sum of their shares (14.7%). Per neighbourhood it is:
     - Chelsea 10.8%;
     - Flatiron 15.0%;
     - Greenwich Village 16.2%;
     - Gramercy 17.4%;
     - West Village 18.4%.
   - The other features take 77%, mostly bedrooms (28%), bathrooms (5%) and building size (3%).
   - The residual is 5.2% of total variance overall, and 3.9% (Chelsea) to 6.5% (WV, Gramercy)
     per neighbourhood.
   - Labels against building effects: the covariance term is −0.7%, so building effects slightly
     offset the labels rather than doubling them.
5. **Single-listing tails are widest in a building's first year on the data:**

   | Months since the building's first row | Rows | 1% / 99% residual | \|residual\| > 40% |
   |---|---|---|---|
   | 0–12 | 4,589 | −59% / +73% | 6.7% |
   | 12–36 | 4,271 | −38% / +50% | 2.6% |
   | 36–96 | 11,486 | n/a | 2.2% |
   | 96+ | 9,171 | n/a | 2.1% |

   - By era, the share with |residual| > 40% is 3.8% (2010–14), 2.8% (2015–19), 3.5% (2020–22)
     and 2.3% (2023–26). Repeat units: 0.2%.
   - The new-building tail adds to ranked item 2 (intervals for new apartments): a building with
     no history yet is the widest case.
   - The audit of those rows for Data comes first, since new-building rows are where bad joins
     land.
6. **Residual SD by missing fields: missing floor matters most.**

   | Fields | Repeat units | Single-listing units |
   |---|---|---|
   | All known | 7.9% | 15.5% |
   | Floor unknown, sqft known | 11.0% | 22.9% (6.2% of rows have \|residual\| > 40%) |
   | Sqft unknown, floor known | 7.4% | |
   | Sqft and floor unknown | | 17.0% |
   | Floor, sqft and description unknown | | 20.9% |

   A floor-unknown noise scale is a cheap addition to the noise design in ranked item 1.
7. **Line peers predict single-listing residuals.** This is the strongest new signal.
   - Sample: single-listing rows whose line (e.g. 4C) has other units with at least 2 fitted
     rows. That is 25,699 of 29,517 single-listing rows; the median line has 3 units.
   - Regressing the row residual (%) on the mean fitted unit effect of those peer units gives:
     - all such rows: slope 0.34 (SE 0.04);
     - lines with at least 2 peers: 0.64 (SE 0.05);
     - lines with at least 4 peers: 0.72 (SE 0.08).
   - The SD of the peer mean is 3.0%.
   - Line effects are off in the served fit. When they were last tested (research plan,
     2026-09-26), they gained +151 to +176 PSIS-LOO but failed the gate on line_scale R-hat
     (1.02–1.03).
   - The model has changed since then (walks, bedtime, noise terms, the NB5 data), and the slope
     says the signal is still there.
   - **New ranked item 5:** re-test the line term on the NB5 base with `line_min_units=2` as one
     Modal full fit after the pause. Whether R-hat passes on the A100 chain length is the
     question.
8. **Relative floor and the top floor add nothing beyond the floor terms.**
   - The floor is the listed floor where known. The floor count is PLUTO numfloors via the
     registry BBL.
   - Mean residual by floor / numfloors bin is −0.3% (below 0.2) and +0.3% (0.8–0.95); every
     other bin is within ±0.1%.
   - Top floor against the rest: −0.09% against −0.02%.
   - Split by lift, the top floor is −0.6% without an elevator (916 rows), −0.3% with lift
     unknown and +0.3% with an elevator. The walk-up penalty already in
     `log_floor_x_no_elevator` covers most of it.
   - No feature needed.
9. **Small buildings show weak spatial correlation out to 500 m.**
   - Sample: building mean residuals for the 1,225 buildings with 5 or fewer fitted rows.
     Significance comes from 199 permutations.

   | Distance band | Moran's I | p |
   |---|---|---|
   | 0–100 m | 0.035 | 0.01 |
   | 100–250 m | 0.010 | 0.03 |
   | 250–500 m | 0.007 | 0.015 |
   | 500–1,000 m | −0.008 | |
   | 1,000–2,000 m | 0.002 | |

   - Neighbouring small buildings share some residual. The size is small (I = 0.035 at 0–100 m),
     so a block-level smooth would help only these thin buildings.
   - It is behind the location items; the label-vs-location test (`nb5p3-locnolabel-v1`, queued)
     is the first look.
10. **The GV/WV noise excess sits in small buildings and non-C classes.**
    - Method: per-cell Student-t scale multipliers c on the served predictive (the noisegain
      method), within each neighbourhood.
    - Overall, c is 1.010 (Chelsea), 1.028 (Gramercy), 1.053 (WV), 1.055 (Flatiron) and 1.103
      (GV).
    - By rows per building:
      - 1–5 rows: c = 1.33–1.37 in every neighbourhood;
      - 6–20 rows: 1.06–1.34;
      - 21+ rows: 0.99–1.08 (WV 1.031, GV 1.081).
    - By class:
      - C: 0.995 in WV and 1.048 in GV;
      - D: 1.067 and 1.074;
      - R: 1.351 and 1.223;
      - other: 1.37 and 1.30.
    - So the WV multiplier falls to about 1.03 in large buildings and C buildings, but GV stays
      above 1.03 in every cell. The neighbourhood excess is mostly a mix of small, R and "other"
      buildings.
    - A noise scale on building row count (or on building class) would explain more than one per
      neighbourhood. This refines ranked item 1.
11. **5-bedroom ad phrases: no mean shift, wider tails.**
    - 433 rows have 5 or more bedrooms; 142 of them have an ad text.
    - Phrase counts are "duplex"/"triplex" 35, "entire floor"/"floor-through" 17,
      "townhouse"/"brownstone" 11 and "combined" 6.
    - Matched rows have median residuals between −1% and +6%, but a wider SD: 18.4% against
      16.2%. 6.2% of matched rows have |residual| > 40%, against 2.6% unmatched.
    - The sample is too small for a mean feature, and `text:duplex` already exists. It points to
      the noise side (ranked item 1's 5-bedroom inflation of 1.32), not a new term.
12. **Ledger note.** The global predictive-scale multiplier of 1.037 (ranked item 1) means the
    served noise scales are under-dispersed out of sample.
    - Checks 6 and 10 locate the under-dispersion: single-listing units, missing floor, buildings
      with few rows, and R/other classes.
    - A fitted noise design along those lines should take the multiplier to about 1. A
      calibration rescale on the site would only hide it.

**Follow-ups to the checks (coordinator relay, 2026-10-08 22:03Z).** Same served fit unless noted.
Scripts: `r12/c13.py` and `r12/loc.py`.

- **Bedroom-curve shape.** The 1BR curve is the reference (0), so each curve is its departure from
  1BR. Yearly means, with * where the year mean is more than 2 posterior sd from 0:
  - 3BR+ drifts below 1BR from 2015 (−2.5%) and is clearly below from 2017 (−4.4%*). It is
    deepest in 2020–24 (−5.2% to −6.4%*) and recovers to −3.9%* in 2026.
  - 2BR follows the same shape at about half the size: −2.5%* from 2017, −3.4%* in 2020, −2.0%*
    in 2026.
  - Studios rise above 1BR in 2015–19 (+1.2% to +2.0%*), dip in 2021 (−0.8%) and sit at about
    +1.5% since 2023.
  - So the large-unit discount builds through 2015–19, before COVID, peaks in 2020–24 and is
    easing now.
- **Noise design: no neighbourhood scales.** Check 10 puts the GV/WV excess in small buildings
  and non-C classes, so a scale per neighbourhood is not needed. The noise design to fit is
  bedroom group × single-listing unit × small building (≤ 5 rows): 16 scales in place of
  `yearnoise`. This replaces the "scale per neighbourhood" part of ranked item 1.
- **What the walk is.** These are fitted 6-month steps, in RMS %, against a mean posterior step
  sd of 2.8–3.1%. Before the building's first row there is no data, so every building's steps
  there come from the prior and have the same RMS.

  | Rows per building | Before the building's first row | First 3 years | Later |
  |---|---|---|---|
  | 1–5 | 0.44 | 0.52 | 0.36 |
  | 6–20 | 0.44 | 0.91 | 0.87 |
  | 21+ | 0.44 | 1.31 | 1.59 |

  - Steps are larger later than early (1.17 against 0.99 RMS), so the walk is not a lease-up term.
  - In small buildings the walk is shrunk to almost nothing, so it is not prior noise there
    either.
  - The walk is a slow drift that only data-rich buildings can show. Almost no step is more than
    2 posterior sd from 0. That share is 0.7% of steps after a building's first 3 years, and
    1.1% of steps in buildings with 21+ rows.
  - A coarser yearly-knot walk would lose little and is worth a test for elegance and speed.
- **The location surface, re-scored with no refit.** This is `nb3-loc-v1`, Gaussian bumps 250 m
  apart with SD 250 m, on the A100 pair at 8f40c96 (chelsea-wv-gv, 2,907 buildings,
  87 bumps).
  - The fitted surface has SD 6.7%. It takes 19.5% of the base fit's building variance: building
    SD falls from 12.2% to 11.0%, weighted by the base fit's building precision, so the 19.5%
    comes from unrounded variances.
  - Projecting the base fit's building effects on the bump basis (WLS) gives R² 0.131, against
    a permutation null of 0.041 (95% 0.051, p = 0.005).
  - Neighbourhood shifts: the surface's mean departs from the overall mean in each area, all
    with permutation p = 0.001:
    - Chelsea: −3.2%;
    - GV: +2.8%;
    - WV: +1.5%.
  - The label coefficients fall from 12.1% to 8.0% (WV) and from 8.1% to 2.8% (GV).
  - Held-out ΔELPD, loc − base:
    - all rows: −1.2 ± 1.5;
    - buildings with ≤ 5 fit rows: −1.0 ± 0.7 (166 rows);
    - 6–20 rows: −1.4 ± 0.9;
    - 21+ rows: +1.1 ± 1.0.
  - So the surface is real structure: it absorbs part of the labels and of the building effects.
    But it doesn't predict new rows better, even for thin buildings. The queued
    `nb5p3-locnolabel-v1` remains the deciding test.
- **Status of the 12 checks.** All 12 are done; none is open. The descriptive share (labels +
  building + walk + unit) on the served fit is 15.7% overall: Chelsea 10.8%, Flatiron 15.0%, GV
  16.2%, Gramercy 17.4%, WV 18.4%.
- **Resume queue.**
  - The line term (ranked item 5) goes ahead of the noise fit. Score it on all rows and on
    single-listing units in a line with peers.
  - The Gibbs sampler doesn't support `line_effects` yet (`gibbs.py` refuses it), so the line fit
    needs a Gibbs line block first. That is a code PR with no fit.

**Three more checks (coordinator relay, 2026-10-08 22:12Z).** No fits. Scripts are in
`/data1/apartments/tmp/bridge/review/r12` on thelio: `expl.py`, `c14.py` and `c15.py`.

- **What explains the location surface.** I took the `nb3-loc-v1` surface at its 2,907 buildings
  and ridge-regressed it on 30 candidates, averaged per building:
  - the subway line groups within 8 minutes;
  - parks, the High Line and the waterfront;
  - retail and food places;
  - 311 noise;
  - subway time to midtown;
  - the nearby amenities set;
  - street trees;
  - built FAR, historic district and landmark;
  - avenue or wide-street frontage.

  The results:
  - **Out-of-fold R²:** 0.758 with building folds (in-sample 0.763; ridge barely overfits 30 columns on 2,907 buildings) and **0.54 with 400 m spatial
    block folds**. The block-fold figure is the honest one: building folds leak through neighbours,
    since both the surface and the candidates are smooth in space.
  - **Families that matter, by drop-one block-fold ΔR²:** subway lines −0.16, parks −0.08,
    retail −0.04, nearby −0.04. Noise, trees, frontage and PLUTO are each 0.01 or less. The water
    and transit sets add nothing beyond these.
  - **Labels:** the area labels explain 14.1% of the surface's variance and 0.2% of the residual's. The shifts below are the same thing area by area: each area's mean minus the all-building mean.

  | Area | Surface shift (pp) | Residual shift (pp) |
  |---|---|---|
  | Chelsea | −3.15 | +0.11 |
  | GV | +2.81 | +0.29 |
  | WV | +1.47 | −0.26 |

  So the part of the surface that looks like a neighbourhood label is explained by named location
  features, mainly the N/Q/R/W and L lines, food density and park access. The residual surface
  carries almost none of the label. If `locnolabel` wins on resume, the named features are the
  more elegant replacement for the bump basis; the obvious test after it is `nb3-lines-v1` +
  `nb3-parks-v1` + `nb3-retail-v1` without labels.
- **Large-unit supply vs the bedroom curves.** I used the 44 dated PLUTO releases
  (`plutoreleases` d2a8364, registry lots only, so buildings without listings are missing). New
  units are lots whose `yearbuilt`, as each release records it, falls in the two years before the
  release year. They are split by building size: ≤ 5 units, 6–49, 50+. Each month reads the
  latest release published at least 7 days earlier.
  - The aggregate yearly series correlates with the 3BR+ and 2BR curves only through trend
    (mid-size buildings, r = +0.66 and +0.69).
  - Year-on-year differences give r = −0.06 to −0.42, with 17 years.
  - At the row level (new units within 1 km, year fixed effects, the served fit's residual), the
    3BR+ extra slope per log unit is:

    | Building size | 3BR+ extra slope (pp per log unit) |
    |---|---|
    | 50+ units | +0.09 ± 0.06 |
    | 6–49 units | −0.08 ± 0.11 |
    | ≤ 5 units | −0.53 ± 0.31 |

    The 2BR extra slope is ≈ 0 in every class. The aggregate r values are per-year means of the monthly curves against log new units in the footprint, so they're small-sample (17 years) and registry-only.
  - **No support** for local new supply driving the large-unit discount. A complete answer needs
    all lots within 1 km, not only registry lots: a full-borough PLUTO pull is listed for Data.
- **The West Village step.** On the served fit, the building level is the label plus the building
  effect, over 2,900 Chelsea, GV and WV buildings. I regressed it, weighted by 1/sd², on area
  dummies plus covariates. The covariates are:
  - the PLUTO class: 1–2 family, walkup ≤ 5 units, walkup 6+, mixed S, condo R, elevator D,
    other;
  - log rows;
  - historic district;
  - log minutes to the waterfront;
  - the surface's explained part and its residual (above).

  | Specification | WV (pp) | GV (pp) |
  |---|---|---|
  | Labels only | +11.5 ± 0.5 | +7.8 ± 0.6 |
  | + class | +11.7 | +7.6 |
  | + class, rows | +11.6 | +7.4 |
  | + class, rows, historic district | +11.4 ± 0.7 | +7.3 |
  | + waterfront | +10.5 | +8.1 |
  | + surface explained and residual | +9.3 ± 0.7 | +4.4 ± 0.8 |

  - Only the first, fourth and last rows show standard errors; they are similar for the others, so steps of ≤ 1 pp between neighbouring rows are within noise.
  - GV falls further than WV once the surface enters (+7.8 → +4.4): more of GV's step is location the candidates capture.
  - The step holds **within every class**. The mean building level, WV minus Chelsea within the same class, is +9.6 for 1–2 family, +11.1 for
    walkup 6+ and +10.4 for walkups ≤ 5.
  - Neither townhouse stock nor small-building stock explains it. Historic district adds
    nothing beyond the label.
  - About 2 pp is location: the waterfront and the surface. **About 9 pp remains a WV name or
    area premium** that the candidates don't capture. It is the main target for any further
    location work, such as street-graph position or block-face character.
- **Design notes for resume** (coordinator relay, 22:12Z):
  - **Noise.** The noise test becomes log-linear: log σ_i = a_bedroom + b·single +
    c·small_building(≤ 5) + d·floor_unknown + e·building_first_year. It replaces `yearnoise` and
    the bedroom scales. It is sampled with a collapsed Metropolis step.
  - **Walk.** `building_trend` goes in as an elegance test beside a yearly-knot walk.
  - **Line term.** The Gibbs line block is #576.

**Six more checks, numbered 0–5 (coordinator relay, 2026-10-08 22:31Z).** No fits. Scripts `c16.py` and
`c17.py` are in the same directory. Free, public downloads are in
`/data1/apartments/tmp/bridge/review/ext`:
- today's MapPLUTO for all of Manhattan (Socrata `64uk-42ks`: floors and coordinates);
- FRED `MORTGAGE30US`.

The WV-step regressions are those of the West Village step above: class dummies, log rows and
1/sd² weights. Their baseline is WV +11.6 ± 0.5. With the surface (explained part and residual)
it is +9.2 ± 0.5.

- **0. Subway lines and parks in the surface.** Ridge on the lines, parks and midtown-time
  columns alone: R² = 0.61.

  | Feature | pp per SD | Chelsea | GV | WV |
  |---|---|---|---|---|
  | N/Q/R/W within 8 min | +2.9 | 0.11 | 0.41 | 0.00 |
  | L within 8 min | +2.5 | 0.39 | 0.64 | 0.41 |
  | B/D within 8 min | +1.0 | 0.02 | 0.72 | 0.52 |
  | 2/3 within 8 min | +0.9 | 0.30 | 0.30 | 0.41 |
  | 4/5/6 within 8 min | −1.7 | 0.00 | 0.38 | 0.00 |
  | 1 within 8 min | −1.5 | 0.74 | 0.63 | 0.90 |
  | A/C/E within 8 min | −1.3 | 0.85 | 0.73 | 0.74 |
  | log walk minutes to a park | +1.1 | +0.21 | −0.14 | −0.06 |
  | Subway time to midtown (units of 10 min) | +3.6 | 1.05 | 1.22 | 1.32 |

  The area columns are each area's mean of the raw feature: the share of buildings for the line
  groups, and the centred mean for the park and midtown columns (in the column's own units). Signs are partial and the line groups are collinear, so read
  the contributions by family instead.

  | Family contribution (area mean minus all, pp) | Chelsea | GV | WV |
  |---|---|---|---|
  | Lines | −0.8 | +2.6 | −0.6 |
  | Parks | +0.4 | −0.3 | −0.2 |
  | Midtown time | −2.0 | +0.3 | +1.7 |

  - WV is poor on the positive line groups. It has no N/Q/R/W and fewer L stops than GV, so its
    lines contribution is −0.6 pp.
  - Midtown time is positive and largest for WV. It acts as a "downtown" gradient, not a
    commuting penalty.
  - The lines family alone puts WV 0.6 pp below the all-building mean, so the WV step is net of a
    small transit penalty, not a large one. With parks and midtown time the three families net
    WV +0.9 pp.
  - **Ledger note:** `nb3-lines-v1` and `nb3-parks-v1` are explanatory under the explained-share
    rule. Dropping them from the surface regression loses 0.16 and 0.08 of block-fold R². They
    were within noise under PSIS-LOO: lines-v1 +14.7 ± 15.8 and +20.5 ± 17.1 (two runs), parks-v1
    −5.2 ± 14.3. The generated
    `feature-tests.md` has no field for this yet, so the note lives here.
- **1. Street geometry (pre-1811 grid).** For each building I took the nearest street centerline
  in the six-neighbourhood basemap (median 20 m away). From it:
  - the angle off the 29° Manhattan grid, with off-grid meaning > 10°;
  - the segment (block) length;
  - "through", meaning the named street runs > 1.5 km in the basemap.

  | Area | Off-grid share | Mean angle |
  |---|---|---|
  | Chelsea | 0.4% | 0.2° |
  | GV | 8.1% | 4.1° |
  | WV | 89.7% | 31.3° |

  Off-grid is almost the WV label: r = 0.87 with the WV dummy.

  | Area | Off-grid on building level (pp) | Off-grid on surface residual (pp) |
  |---|---|---|
  | Chelsea | −13.2 ± 6.2 (only 0.4% off-grid) | |
  | GV | +3.7 ± 2.2 | |
  | WV | +4.2 ± 1.1 | +0.1 ± 0.4 |

  | Specification | WV (pp) | Off-grid (pp) |
  |---|---|---|
  | Geometry added to the step | +11.6 ± 1.2 (SE doubles) | +3.3 ± 1.0 |
  | Surface and geometry together | +9.7 ± 1.2 | +1.4 ± 1.0 |

  - **The prediction fails:** angle does not take the surface-adjusted step (+9.2). It has a real within-WV effect of
    about 4 pp, but it can't be separated from the label across areas.
  - Block length and through streets have mixed signs by area. The surface already carries the
    within-WV part: its residual is flat in off-grid.
- **2. Low-rise context.** Per building, the mean floors of the other lots within 100 m, from today's Manhattan
  PLUTO. It isn't dated by release; heights of old low-rise blocks rarely change. The median is
  5.3 in Chelsea, 5.0 in GV and 4.1 in WV (the median over buildings of that per-building mean).

  | Area | Surface residual per log floor (pp) |
  |---|---|
  | Chelsea | −2.1 ± 0.5 |
  | GV | +0.6 ± 0.9 |
  | WV | +3.2 ± 0.8 |
  | Pooled | −0.4 ± 0.3 |

  - In the WV step it adds nothing: WV +11.5, or +8.8 ± 0.6 with the surface (low-rise −1.4 ±
    1.0).
  - So low-rise context isn't the WV step. Its opposite signs inside Chelsea and WV suggest it
    stands in for something else, such as Chelsea's towers along the avenues.
- **3. Name or structure.** The served fit has no area-time term, so the drift lives in the
  building walks and residuals. Below are area-by-year means of row residual + building walk,
  minus Chelsea.

  | Area | 2014–19 (pp) | 2022 | 2023 | 2024 | 2025 | 2026 | Slope 2014–26 (pp/yr) |
  |---|---|---|---|---|---|---|---|
  | WV | between −1.2 and +0.3 each year | +1.6 | +2.5 | +2.9 | +3.8 | +5.6 | +0.48 |
  | GV | between −0.7 and +0.5 | −0.8 | +0.3 | +0.5 | −0.1 | +1.6 | +0.09 |
  | Gramercy | between −0.4 and +1.2 | +1.0 | +1.2 | −0.4 | +1.2 | +2.4 | +0.08 |
  | Flatiron | between −1.3 and +0.9 | −0.6 | −1.9 | −0.2 | −3.5 | −1.1 | −0.20 |

  - The building walks alone show it as well: by 2026 the mean WV walk is +1.6 pp and Chelsea's
    is −0.9 pp.
  - **The WV premium is growing** — fashion, or WV-specific demand — on top of a large constant
    step. The constant label under-predicts WV now by several pp. The walks and residuals absorb
    it building by building, which is weak for new buildings.
  - So an area-time term (`area_time`, already in the backlog as "Areatime as a full fit") moves
    up. It is cheap, and it would also stop the walks from carrying area trend.
- **4. Stabilized share.** The stabilized units in the latest tax bill up to 2024 (stab-v1 file),
  divided by PLUTO residential units. Mean share: Chelsea 0.17, GV 0.13, WV 0.15.
  - Building level per unit of share: −10.9 ± 1.5 pp within WV, −8.9 ± 0.9 across the three
    areas.
  - It is a strong building-level covariate. It doesn't explain the WV step (+11.4).
  - It supports Data's `stabopen-v2` and `explain-v1` sets as next-in-line tests.
- **5. Buyers in waiting.** The 30-year mortgage rate (monthly mean) against the monthly 3BR+ and
  2BR curves, 2010–2026, with the rate leading by 0–24 months:
  - 3BR+: levels r = −0.31 at lag 0, fading to +0.11 at 24 months. On 12-month changes, r is
    −0.13 to +0.03 at every lag. Annual changes: r = +0.12 (lag 0) and −0.17 (lag 1 year).
  - 2BR: levels r = −0.22 at lag 0, +0.23 at 24 months; 12-month changes −0.15 to +0.06; annual
    changes +0.18 and −0.04.
  - Monthly series are strongly serially correlated, so the effective n is near the 16 years;
    none of these r values is distinguishable from 0.
  - The level correlation has the wrong sign for buyers-in-waiting: high rates go with a *larger*
    3BR+ discount. Changes show nothing. **No support.**

### Follow-up checks A–E (2026-10-08, no fits)

The coordinator's 22:44Z list. Scripts: `/data1/apartments/tmp/bridge/review/r12/c18.py`,
`c18b.py`.

- **A. Did location prices change, or did WV move as an area?** Building levels (building effect
  plus mean residual) for the 1,607 buildings with ≥ 2 rows in both 2014–19 and 2022–26 (Chelsea
  658, WV 608, GV 341), regressed on the location features per period. Pre → post (difference ±
  400 m block-bootstrap SE):

  | Feature | 2014–19 | 2022–26 | Difference |
  |---|---|---|---|
  | N/Q/R/W | 3.35 | 2.90 | −0.45 ± 0.55 |
  | L | 0.22 | 0.54 | +0.32 ± 0.58 |
  | 1 | −2.18 | −1.30 | +0.88 ± 0.54 |
  | Park minutes | 1.20 | 1.77 | +0.57 ± 0.62 |
  | Waterfront | −0.38 | −1.88 | −1.50 ± 1.21 |
  | Food | −1.61 | −0.32 | +1.29 ± 0.95 |
  | Nightlife noise | −1.37 | −2.11 | −0.74 ± 0.84 |
  | Dog run | −0.49 | −1.34 | −0.84 ± 0.52 |
  | Trees | 1.11 | 1.24 | +0.13 ± 0.50 |

  - No coefficient moves by 2 SE. The area labels do move: WV −2.06 → +1.05, GV −0.16 → +1.73.
  - Off-grid within WV is stable: +9.33 ± 2.06 → +8.12 ± 2.37.
  - **Location prices are stable; WV rose as an area.** So `area_time` is the honest term, not
    period-varying location coefficients.
- **B. Stabilized share under the explained-share rule** (nb5-stab-v1 against its same-rows base,
  no refit).
  - Fitted coefficient −1.08 ± 0.44 pp per unit of share (feature sd 0.32).
  - It takes 1.2% of the base fit's building variance (building sd 12.05 → 11.97%).
  - R² of the base building effects on building-mean share: 0.032, against a permutation null of
    0.0004 (95th percentile 0.0014), p = 0.001.
  - Between buildings: −8.0 pp per unit. Within buildings (1,050 buildings, 61% of rows with
    varying share): +0.87 ± 0.25 on residual plus walk, +0.03 ± 0.22 on residual alone.
  - **The effect is cross-sectional.** A building's rent doesn't rise as its stabilized share
    falls. It is real but small, so it stays a candidate under the rule, not a priority.
- **C. Does WV off-grid survive an avenue-frontage control?** 168 of 1,179 WV buildings lie within
  25 m of 7 Ave S, 7 Ave, 8 Ave, Hudson, Greenwich Ave or West St; 92% of those are off-grid.
  - Off-grid: +4.72 ± 1.11 alone; +4.72 with on-avenue (on-avenue −0.04 ± 1.01); +4.68 adding log
    distance to the avenue.
  - **It survives.** The off-grid premium is not avenue frontage.
  - The size differs from A's (+8 to +9) because the sample and target differ: C uses all WV
    buildings and only these controls; A uses the buildings seen in both periods, with the full
    location regression. Compare within a check, not across.
- **D. 3BR+ against 1BR by building class and area.** The shared curve plus each group's mean
  residual gap, in pp:

  | Group | 2010–14 | 2015–19 | 2020–24 | 2025–26 |
  |---|---|---|---|---|
  | Elevator or condo (3,034 3BR+ rows) | 2.8 | −6.0 | −10.8 | −9.7 |
  | Other (4,827) | 2.3 | −3.4 | −7.9 | −1.1 |
  | Walkup (3,990) | −0.8 | −1.6 | −0.5 | 1.2 |
  | Chelsea | 1.5 | −4.7 | −6.8 | −2.4 |
  | Flatiron | 0.9 | −5.9 | −8.8 | −9.1 |
  | Gramercy | 0.7 | −3.4 | −8.3 | 1.6 |
  | GV | −1.4 | −3.6 | −7.2 | −6.6 |
  | WV | 4.1 | −2.0 | −3.3 | −3.3 |

  - **The 3BR+ discount sits in elevator and condo buildings** (the family market), not in
    walkups (the sharer market, flat throughout). Every area shows it in 2015–24, WV least in
    2020–24; in 2025–26 Gramercy reverses (+1.6) and Chelsea eases to −2.4.
  - A bedroom-time × walkup interaction is a candidate if the curves are kept.
- **E. One drifting per-bedroom slope or three curves?**
  [Plot](img/bedroom-curves-20261008.svg): studio, 2BR and 3BR+ against 1BR, served fit.
  - SVD of the centred curves: the first component carries 84.6% (then 12.6%, 2.9%), with
    loadings studio −0.26, 2BR 0.58, 3BR+ 1.
  - RMS misfit (pp) per curve, studio / 2BR / 3BR+: rank one with free loadings 0.96 / 0.47 /
    0.42; fixed linear-in-bedrooms loadings (−1, 1, 2) 1.01 / 0.52 / 0.55. Posterior sd of the
    curves: 1.00 / 0.99 / 1.73.
  - **One drifting slope β0 + β1·g(t) fits within posterior noise** for 2BR and 3BR+. The studio
    curve is mostly noise: its rank-one misfit (0.96) is about its posterior sd (1.00), and so is
    its whole RMS (1.13).
  - Elegance candidate: replace the three bedroom-time curves with a loading per bedroom group
    times one common g(t) (free loadings, or linear in bedrooms). It interacts with D: the drift
    is a family-building effect, so g(t) may want a walkup interaction instead.

### What moved the West Village? Checks 1–4 (2026-10-08, no fits)

The coordinator's 22:58Z list. Scripts: `/data1/apartments/tmp/bridge/review/r12/c19.py`,
`c20.py`, `c21.py`. **Drift** is a building's mean residual plus building walk in 2022–26 minus
2014–19, for buildings with ≥ 2 rows in each period. The served fit has a constant area label, so
an area's rise lands in the walks and residuals. Mean drift: WV +2.53 ± 0.48 pp (608 buildings),
Chelsea −0.90 ± 0.39 (658), GV −0.50 ± 0.76 (341).

- **1. Waterfront parks.** Distance is to the West St / 11 Ave / 12 Ave centreline (the river edge
  is about 50 m further west).

  | Distance (m) | WV drift | Chelsea drift |
  |---|---|---|
  | 0–200 | +1.4 ± 1.5 (50) | −5.0 ± 1.8 (22) |
  | 200–400 | +4.7 ± 1.0 (129) | −0.6 ± 1.3 (76) |
  | 400–600 | +2.5 ± 0.8 (238) | −0.3 ± 0.8 (126) |
  | 600–800 | +1.4 ± 0.9 (178) | −0.5 ± 0.8 (173) |
  | 800–1,200 | +1.5 ± 2.9 (13) | −1.4 ± 0.7 (234) |
  | 1,200–1,600 | — | +0.4 ± 2.0 (27) |

  - WV by side: west of Hudson St +4.2 ± 1.0 (116), Hudson St to 7 Ave S +2.7 ± 0.7 (325), east
    of 7 Ave S +1.0 ± 0.8 (167).
  - Slope on distance within WV: −4.6 ± 2.7 pp per km, controlling for off-grid (which is also
    western). Chelsea: −0.2 ± 1.4.
  - **Weakly as predicted.** By side, the WV drift is largest west of Hudson St and not
    distinguishable from 0 east of 7 Ave S. By distance it is not monotone: the 0–200 m band is
    among the lowest. The slope is only about 1.7 SE. Chelsea's west
    side shows no rise, even next to Pier 57 and Little Island, which sit at the Chelsea–WV
    border. So the parks alone can't be the story: the rise stops at the area line.
  - `parks.SECTIONS` dates the High Line (Gansevoort–W 20th 2009-06-08, W 20th–W 30th
    2011-06-08, the 10th Ave spur 2019-06-04) and Bella Abzug Park (2015-08-31). Hudson River Park
    is a state park and not in the parks source, so Little Island (2021), Pier 57's roof (2022) and
    the Gansevoort beach (2023) are in no feature; the waterfront feature is a static distance.
- **2. Composition.**
  - WV drift by building class: elevator (D) +4.7 ± 1.1 (93), walkup 6+ units +2.9 ± 0.6 (352),
    mixed S +1.1 ± 1.3 (69), condo R −1.1 ± 1.6 (49). **Not concentrated in R-class**; the
    elevator and walkup stock carry it.
  - The WV row mix by class barely moves (D 35% → 32%, R 6% → 6%, walkups 52% → 55%). The row-level
    WV drift is +4.75 raw and +4.97 at the pre-period class mix. It is larger than the
    building mean (+2.53) because it weights by rows and uses all rows, not only the panel
    buildings.
  - By pre-period price quintile (log rent against the bedroom × year mean), cheapest to dearest:
    WV +4.9, +2.3, +4.3, +1.4, −0.3; Chelsea +2.0, +0.5, −0.3, −0.4, −6.3. Both fall with price,
    which is mostly regression to the mean. WV sits 2 to 6 pp above Chelsea in every quintile.
    **Not a top-quintile effect.**
  - Ad text (all five areas' description files), % of rows:
    - No-fee falls everywhere after 2021: WV 18.7 (2020–21) → 6.9 / 7.7 / 11.6 (2022–23, 2024–25,
      2026), Chelsea 21.5 → 15.6–16.8, GV 12.1 → 3.2–6.7, Gramercy 17.4 → 6.2–7.2. WV's drop
      matches GV's and Gramercy's, so it doesn't explain a WV-only rise.
    - Sublet or short-term (0.6–1.6%), furnished (1.8–2.6%) and townhouse or brownstone (6–8%)
      mentions are flat in WV.
  - Every row comes through StreetEasy (Corcoran and Compass listings included), with one price
    basis apart from about 4% current captures in 2026, so the source can't shift.
  - **No sign that composition explains the drift.** Building class, price tier and the sublet,
    furnished and townhouse mentions don't move. Condo units are tested only through class R.
- **3. Open Restaurants and Open Streets.**
  - Open Restaurant Applications (Historical, `pitm-atqc`) has dated, geocoded applications:
    3,646 unique Manhattan restaurants approved for roadway seating, 80% from 2020. Dining Out NYC
    (`fpeh-f7ci`) has current licences (344 roadway in CB 1–6). Both are usable.
  - Open Streets Locations (`uiay-nctu`) has only the 2024 season, 126 Manhattan segments, so it
    is not usable by year.
  - Mean roadway sheds within 300 m (2020–23): WV 67, GV 77, Chelsea 33.
  - Cross-section: drift per sd of shed count is WV −0.74 ± 0.48 (terciles +3.1, +2.9, +1.6),
    Chelsea +0.75 ± 0.39 (about 1.9 SE, opposite sign to WV), GV +0.28 ± 0.75; pooled with area
    dummies −0.05 ± 0.37.
  - Panel (building-year residual plus walk, building and area × year fixed effects; exposure
    rises 2020–23, held in 2024, Dining Out roadway licences from 2025): −0.41 ± 0.08 pp per 10
    sheds in WV, −0.37 ± 0.05 across the three areas. Those SEs aren't clustered by building, so
    they are too small.
  - **The WV drift doesn't track shed density.** The within-building panel leans slightly
    negative, but with unclustered SEs that is suggestive at most.
- **4. 3BR+ family market and households with children.**
  - ACS 1-year PUMS household files, 2012–2024. The study buildings fall in 2010 PUMAs 3807
    (Chelsea) and 3810 (WV, GV), and in 2020 PUMAs 4104, 4165 (Chelsea) and 4121 (WV, GV).
    The geography changes in 2022, and 2020 is the experimental release.
  - Share of households with children: 11.9% (2012) → 9.9% (2024); renters 9.2% → 7.1%. The
    single-year sampling SE is about 1.4 pp, against a 2.0 pp change over 12 years, so year to
    year moves are mostly noise.
  - The elevator/condo 3BR+ curve is check D's (above), by year: the served 3BR+ curve plus the
    mean residual-plus-walk gap of 3BR+ over 1BR rows in D and R buildings. It goes +1.7 (2012) →
    −11.0 (2024) pp. Against it: levels r = +0.47 (p 0.11), renters
    +0.54 (p 0.06); annual changes +0.39 and +0.31 (n 12). After removing linear trends: r = +0.06
    and +0.02. Walkup 3BR+: levels −0.14 and −0.03.
  - **The only link is a shared downward trend.** Fewer households with children and a growing
    family-building 3BR+ discount point the same way, but the ACS is too noisy at this geography to
    test more than that.
- **What this means for the model.** The WV rise is area-wide, perhaps stronger west of
  Hudson St. It
  isn't composition and isn't outdoor dining. That is the `area_time` term again, perhaps with a
  west-of-Hudson-St split later. Nothing here argues for a new feature ahead of it.

### Label, geography, placebo lines and timing: checks 1–4 (2026-10-08, no fits)

The coordinator's 23:07Z list. Script: `/data1/apartments/tmp/bridge/review/r12/c22.py`. Drift is
as in the section above. **Level** is a building's served building effect plus its label's
coefficient, in pp.

- **1. Label vs geocode.** Every building has one label across all its listings. Against the 2020
  NTAs:
  - 98 GV-labelled buildings geocode into the West Village NTA, and 79 Chelsea-labelled ones into
    the Flatiron NTA.
  - Nothing labelled WV geocodes outside the WV NTA, and nothing labelled Chelsea geocodes into WV.
  - Buildings within 300 m of the WV NTA line (n is buildings; drift counts only buildings with
    ≥ 2 rows in both periods). That line encloses most of WV, which is why 804 here is far more
    than the 304 WV buildings near GV-labelled ones in check 2:

    | Label | Geocode | Level | Drift |
    |---|---|---|---|
    | West Village | West Village | +10.7 ± 0.4 (804) | +2.0 ± 0.6 (416) |
    | Greenwich Village | West Village | +9.6 ± 1.2 (98) | +5.3 ± 2.4 (42) |
    | Greenwich Village | Greenwich Village | +6.2 ± 0.7 (365) | −0.6 ± 0.8 (219) |
    | Chelsea | Chelsea | −0.1 ± 0.7 (269) | −0.5 ± 0.8 (185) |

  - **Both the step and the drift follow the geocode.** GV-labelled buildings inside the WV NTA
    price within about 1 pp of WV and drift at least as much as WV, even though the model gives them the GV
    label; their building effects make up the gap.
  - Claimed neighbourhood. 10,557 ads (354 buildings) are labelled Chelsea or GV and lie within
    150 m outside the WV NTA. Of these, 8% name the West Village in 2012–20 and 4% in 2021–26,
    against 0.7% and 0.4% further away.
  - Within a building, ads naming WV earn +0.36 ± 0.64 pp (2012–20) and −0.17 ± 1.04 (2021–26).
  - **The claim earns nothing and doesn't grow after 2020.** The premium belongs to the location,
    not to the name in the ad.
- **2. Placebo lines.** The drift on one side of a line minus the other, for buildings within 300 m
  of it and with one label (the sign follows the street's direction):

  | Line | Difference | Buildings |
  |---|---|---|
  | 8 Ave inside Chelsea | +0.2 ± 1.0 | 158 / 248 |
  | W 23 St inside Chelsea | +0.4 ± 1.1 | 272 / 98 |
  | Bleecker St inside WV | +1.0 ± 1.1 | 226 / 266 |
  | Hudson St inside WV | +2.0 ± 1.2 | 113 / 323 |
  | W 4 St inside GV | −0.1 ± 2.2 | 91 / 64 |
  | 6 Ave inside GV | +5.9 ± 2.5 | 42 / 219 |
  | Real: W 14 St, WV vs Chelsea | +3.2 ± 1.3 | 115 / 185 |
  | Real: WV vs GV labels, within 300 m of the other | +1.6 ± 1.1 | 304 / 219 |

  - 7 Ave S inside GV has GV-labelled buildings on one side only, so it can't be tested. 6 Ave is
    the nearest substitute, but it is not a placebo: its west side is the 42 GV-labelled buildings
    in the WV NTA (check 1).
  - **The true placebos are all within 2 SE of 0.** Only 8 Ave, 23 St and W 4 St are within
    1 SE; Bleecker St (+1.0) sits right at the predicted 1 pp limit.
    Hudson St (+2.0, 1.7 SE) repeats the west-of-Hudson pattern above. The real 14 St border
    (+3.2) is the biggest of the clean lines. With SEs of about 1 pp, these tests can only rule out
    lines of 2 pp or more.
- **3. Google Trends.** Skipped. The Trends API returns 429 to unauthenticated requests from
  thelio, and pytrends goes through the same endpoint.
- **4. Short-term rentals.**
  - Inside Airbnb's dated NYC snapshots aren't freely downloadable: only the latest (2026-09-14)
    is public, and older ones return 403 directly and from the Wayback Machine (archives are by
    request). The latest snapshot's reviews only cover listings still active, so they would
    understate pre-2023 density, which is the side of the comparison that matters. Not run.
  - Timing alone: mean residual plus walk, WV minus the other area, rows with ad text. Each cell
    is January–June, then July–December. 2026 is a partial year. No SEs; half-year cells have
    roughly 1,000 to 2,000 rows per area.

    | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
    |---|---|---|---|---|---|---|---|
    | −0.1, −0.9 | +0.1, +0.2 | −2.5, 0.0 | +1.3, +1.8 | +3.1, +2.3 | +3.5, +2.5 | +3.6, +4.4 | +6.2, +4.3 |

    That row is WV minus Chelsea. WV minus GV: 2019 +0.2, −0.6; 2020 +0.4, −0.5; 2021 0.0, +1.6;
    2022 +3.0, +2.5; 2023 +3.6, +2.0; 2024 +2.9, +2.9; 2025 +4.9, +2.7; 2026 +4.4, +2.7.
  - **No sign of a flattening caused by Local Law 18 (Sept 2023).** The WV gap opens in 2022. Against
    Chelsea it is roughly level from 2023 to 2025a and higher in 2025b–2026 (partial year); against
    GV it is level from 2022 on. A gap that stopped growing after 2023 would fit LL18, but it
    stopped growing against GV a year before LL18.
- **What this means for the model.** The WV premium and its rise belong to the place (the WV NTA
  area), not to the StreetEasy label or the name in the ad. An `area_time` term on labels would
  miss the 98 GV-labelled buildings inside the WV NTA. A geography-based area for that term (NTA,
  or the location surface's own cells) would be more honest, and it is a free choice to make
  before its fit.

### NTA re-base, market beta, shared shape and attention (2026-10-08, no fits)

These are post-hoc checks on the served fit. Each one has a prediction stated in advance; the
results are set against it. The script is `review/r12/c23.py` on thelio. "Residual" is the row
residual plus the building walk, in pp, as in the checks above. Areas are by 2020 NTA unless the
text says label.

- **1. NTA re-base (result): WV stays at +11, GV and Flatiron fall, and the area share falls by 1.6
  to 3.3 pp.**
  Building level = (building effect + label coefficient) × 100. The area means are re-estimated
  from these levels, weighted by 1 / (building sd² + 1), relative to Chelsea.

  | Area | Served label coefficient | Re-estimated, by label | Re-estimated, by NTA |
  |---|---|---|---|
  | West Village | +11.5 | +11.5 | +11.1 |
  | Greenwich Village | +8.0 | +7.9 | +7.1 |
  | Flatiron | +7.0 | +7.4 | +3.4 |
  | Gramercy Park | −8.4 | −7.4 | −7.3 |

  - Predicted: GV falls and WV rises toward +11. Against the by-label re-estimate, GV falls (−0.7). WV was
    already at +11 and moves −0.4. Flatiron moves most (−3.9; −3.5 against the served coefficient), because the 79 Chelsea-labelled buildings inside the Flatiron
    NTA are cheap (mean building effect −4.2 under labels).
  - Predicted: the descriptive share moves < 1 pp. The row-weighted share of building-level variance
    in the area means is 25.3% with the served coefficients, 23.6% with label means re-estimated, and
    22.0% by NTA. The fall is 1.6 pp on like-for-like means (3.3 pp, about 13% of the share, against the served
    coefficients), so the prediction fails.
  - Predicted: the 98 GV-labelled buildings in the WV NTA move toward 0. Their mean building effect
    goes from +1.6 to −1.5 (sd 12.3): it moves past 0 and changes sign, with about the same size. The 79
    Chelsea-labelled buildings in the Flatiron NTA go from −4.2 to −7.6.
  - Caveat: the building effects were shrunk toward the label means, so a re-base inside a fit
    would move these numbers further.
- **2. Market beta: there is no stable beta. The correlation comes from 2022 on.** Market level =
  yearly mean of the fitted `trend` × 100 (the served fit has no `market_drift`).

  | | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | WV − Chelsea | −1.1 | −1.0 | +0.4 | −0.7 | −0.6 | −0.5 | +0.3 | −0.9 | +1.6 | +2.3 | +2.6 | +3.6 | +5.1 |
  | Market | 18.5 | 21.5 | 22.8 | 22.6 | 23.1 | 25.5 | 18.1 | 20.8 | 37.7 | 41.3 | 44.9 | 51.4 | 57.5 |

  2026 is a partial year.

  - Regressed on market levels, 2014–2026: slope +0.14 pp per pp of market, r +0.96 (n 13), and
    r +0.85 detrended. The prediction (r > 0.8) holds as stated.
  - The fit is two regimes, though. In 2014–2021 the slope is +0.01 (r +0.03). In 2022–2026 it is
    +0.17 (r +0.99). On changes, r is +0.54 (p 0.07), and +0.17 without the 2022 step.
  - Predicted: a dip below 0 in 2020–21. There is no 2020 dip: the market fell 7 pp and WV −
    Chelsea rose to +0.3, against a 2014–19 mean of −0.6. 2021 is −0.94, only 0.37 below that mean (−0.57).
    A beta of 0.14 would have predicted about −1 pp in 2020.
  - Reading: WV did not move with the market before 2022. It moved with it after. That is a level
    change in 2022, not a beta.
- **3. Shared shape: PC1 holds 76%, and it is WV's.** The yearly residual series of the five areas,
  2014–2026, are centred and decomposed. The SEs come from 200 bootstrap draws of buildings.

  - Components: 75.9%, 17.5%, 4.6%, 1.4% and 0.6%. The prediction (> 80%) fails narrowly.
  - PC1 loadings, in pp per sd of the component: WV +2.39 ± 0.23, Gramercy Park +0.86 ± 0.39,
    GV +0.73 ± 0.30, Chelsea +0.54 ± 0.26, Flatiron −0.31 ± 0.74.
  - Predicted: only WV > 2 SE. GV, Gramercy Park and Chelsea are each just over 2 SE, so that fails
    too. WV's loading is 2.8 to 4.4 times theirs.
  - The component is a post-2022 step. It is large in WV and small (under 1 pp) in GV, Gramercy Park
    and Chelsea. Flatiron is noise, with its largest swings in 2020–21.
- **4. Attention: search interest in WV rose from 2021, but Wikipedia views did not until 2025.
  Once detrended, only Trends tracks the residual, and only weakly.**

  | WV share of the five areas (%) | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | Wikipedia views | 10.2 | 12.7 | 12.8 | 13.2 | 13.3 | 13.5 | 12.1 | 13.2 | 13.6 | 16.5 | — |
  | Google Trends | 11.7 | 12.6 | 12.5 | 11.6 | 11.6 | 13.9 | 14.7 | 15.0 | 15.9 | 16.5 | 17.9 |

  2026 is a partial year; Wikipedia uses full years only (it starts in 2015-07 and 2026 is partial).

  - Sources: Wikipedia monthly pageviews (all agents, 2015-07 to 2026-10) for the five area
    articles. East Village and NoMad were fetched but are not in the shares.
  - Google Trends: the New York DMA, 2014-01 to 2026-10. The terms are West Village, Chelsea,
    Greenwich Village, Gramercy and Flatiron. "Chelsea" is ambiguous (Chelsea FC) and takes about
    65% of the five terms, which dilutes WV's share. In index terms, WV went from 8.8 (2019) to
    15.0 (2026), while GV, Gramercy and Flatiron are at or below their 2019 levels.
  - Against WV's residual minus the other four areas' mean:
    - Trends: levels r +0.87, detrended r +0.56 (p 0.06), 2014–2025.
    - Wikipedia: levels r +0.60, detrended r −0.15, 2016–2025.
  - Pooled across the five areas, each area's share against its own residual series, detrended per
    area: r 0.00 (Trends) and −0.06 (Wikipedia).
  - Reading: WV's search share rises with its rent residual from 2021–22, a little ahead of it. That
    is consistent with a neighbourhood growing more popular, and equally with people searching
    because it is in the news. It explains none of the other four areas' moves. With 12 yearly
    points and one step, it is not evidence of cause.
- **What this means for the model.** Checks 2 and 3 point to a place-specific step around 2022,
  mostly in WV, not a market beta or a shared shape. If `area_time` is fitted, a per-area random walk (or a
  2022 step per area) on NTA areas is the right form, not a beta on the market curve. The NTA
  re-base lowers the descriptive area share by 1.6 to 3.3 pp and moves Flatiron's level by about 4 pp.

## Open-data survey: stabilization, permits, owners, dated MapPLUTO (2026-10-07)

Four free sources, sized against the 105,244 rows of `chelsea-wv-gv-analysis-20261005-2d5b3b6`
(2,941 buildings, 2,748 lots, 2,877 BINs, all in registry `20261005-2d5b3b6`). Scripts and raw
pulls are in `/data1/apartments/tmp/suspect/opendata/`. Nothing here is a feature yet. Each build
goes to Modeling's queue as its own Modal full fit, served if it passes the gate. Nothing needs paid
data. In order of expected value:

1. **Rent-stabilized units per lot, as of the listing (`nb3-stab-v1`).**
   - **Data.** DOF tax-bill counts of DHCR-registered stabilized units: taxbills.nyc for 2007–2017
     (`taxbillsnyc.s3.amazonaws.com/joined.csv`) and JustFix's DOF scrape for 2018–2024
     (`justfix-data/rentstab_counts_from_doffer_2024.csv`). Join on BBL.
   - **Coverage.** 1,068 of our lots appear. 73.0% of rows sit in a lot with stabilized units as of
     the listing; a lot that never appears has none. 2.1% of rows are in a lot with no bill year
     by then (2010 listings) and carry the earliest count back.
   - **It moves within buildings.** As a share of the lot's peak count, the as-of count ranges
     30–60% across a building's listings for 21,184 rows and 60% or more for 15,152. The building
     level is fixed over time, so it can't absorb deregulation. A falling stabilized share means a
     larger market-rate share among the listed apartments.
   - **Leak risk: low.** Use the latest bill year at or before the listing's year − 1. Carry
     forward over the 2020–2022 gaps (852–876 lots have bills, against about 990 in other years).
   - **Proposed terms.** The stabilized share of MapPLUTO's residential units, and its change since
     the building's first listing, both as of the listing.
2. **DOB alteration permits that name the apartment (`nb3-permit-v1`).**
   - **Data.** DOB job filings (BIS `ic3t-wcy2`, 57,833 jobs) and DOB NOW (`w9ak-ipjd`, 20,783),
     joined on BIN. Of 47,399 permitted A1, A2 and new-building jobs, 11,374 name an apartment
     ("APT 5F", "UNIT 4B") in the description or floor field.
   - **Coverage.** 1,210 rows (1.1%) are listed within 3 years after a permit naming their
     apartment, and 5,019 (4.8%) at any time after one. 247 units (1,132 rows) were listed both
     before and after their first naming permit. That before/after step is what the term would
     learn. At building level: an A1 (change of use or occupancy) in the 3 years before covers
     4.4% of rows, and 5 or more alteration permits in 2 years 19.2%.
   - **Leak risk: low.** Date by permit (`fully_permitted`, `first_permit_date`), never filing,
     strictly before `price_at`.
   - **Before the fit.** The label match needs a review sample. "UNIT" also means HVAC units, and
     labels need the same spelling joins as `unit-labels`. These permits also date alterations
     exactly, which retires MapPLUTO's present-day `yearalter1/2` (the leak in item 5 of the
     exact-dates section).
3. **MapPLUTO as of the listing (`nb3-plutoasof-v1`).**
   - **Data.** DCP's archived releases download freely from
     `s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/pluto/nyc_pluto_<YYvN>.zip`
     (10v1, 12v1, 14v1, 16v1 and 18v1 checked). Of our lots, 2,662 match in 10v1 and 2,718 in 18v1.
   - **How much the present-day values differ** (rows whose lot differs from today in 2010 /
     2018): building class 10.5% / 4.1%, residential units 19.8% / 5.3%, floors 3.8% / 1.5%,
     `yearalter1` 1.6% / 1.0%. Historic district reads 27.1% / 0.6%, mostly renamed districts.
     Class changes are mostly within a letter (D to D, C to C), plus 610 rows K to D and 589 G to D.
   - **Expected gain: small.** MapPLUTO facts added no accuracy before (A.1), and the earlier
     unit-count check found only about 1% of rows with a material change
     (`/data1/apartments/tmp/suspect/pluto-asof/FINDINGS.md`). The case is the no-future-information
     rule. Use the latest release before the listing; take the alteration years from item 2.
   - **Test.** One Modal full fit against the served set, swapping present-day MapPLUTO for the
     as-of values and nothing else.
4. **HPD registrations: owner and managing agent. Not proposed.**
   - **Coverage.** 94.7% of rows are in a registered building. 97% of those are corporate owners.
     809 agents; 72 manage 5 or more of our buildings, covering 30.2% of rows.
   - **Why not.** Open Data holds only each building's current registration: 2,117 of 2,332 registered buildings last
     registered in 2025–2026. An agent as of a 2012 listing isn't available, so the term would
     carry later information.
   - **Little to gain.** A shared agent effect would help only small buildings, and just 466 of
     the 2,286 rows in buildings with 5 rows or fewer are under a 5-building agent. HPD
     violations already tested null (`unitdescplutohpd-v1/v2`).
   - Revisit only if dated registration history turns up.

## Sound scores from HowLoud (Ben, 2026-10-07)

Normal priority; it comes up on the queue by the usual selection. Ben (17:49Z): "Item for the
feature backlog - sound scores from HowLoud". Not built yet.

- Judge it against the street-noise features that tested null: `nb3-quiet-v1` +8.1 ± 14.2 and
  `nb3-loud-v1` −10.1 ± 14.4 (`docs/model/feature-tests.md`), and street noise on Greenwich
  Village (+3.3, as reported to this thread). A score has to beat those, not just the base.
- Open questions before any build: data access, licensing and cost (Ben approves any spend); and
  whether scores are per address and fixed over time. A score built from recent traffic or
  complaints would carry later information into older listings.

## Loft buildings, nb3-loft-v1 (skipped, 2026-10-07)

`nb3-loft-v1` (#416) adds a loft-building flag (MapPLUTO D5, or at least half of at least 3 earlier
ads say loft) with its own bedroom and size gradients. It flags 7,890 rows. Ben skipped it at
17:46Z, before its exploration pair ran; the code stays on master, untested.

## Ad-text phrases, text-v2 (Ben, 2026-10-07)

Normal priority; it comes up on the queue by the usual selection. Ben: "Rather than simply
restoring the description phrases features, simply put that idea back in the research backlog."

- `nb3-text-v1` gained +106.4 ± 32.8 on all rows (exploration fits), but scored on the West Village and Greenwich Village rows
  alone it was +43.7 ± 23.5 (1.9 SE), short of 2 SE. It is not served.
- **text-v2:** the same phrases without `central_air` and `skyline_view`, fitted on `nb3-coded-v2`
  with the current rules (unit-labels-v9 and unit-splits). It is judged on the normal all-rows bar,
  with the West Village + Greenwich Village score reported alongside.

## Exact dates instead of months (Ben, 2026-10-03)

The daily Fourier season (`season_daily`, #168) beat 12 month effects by +77.0 ± 17.2 paired,
because a listing's own date (`price_at`) lets the end of one month flow into the next. Most other
time terms still read only the listing's month (`Arrays.month`, `calendar`, `period` = the first
of the month). Ben: "Brainstorm other opportunities to use specific dates instead of truncating
pieces of date info." Dates are UTC in the data; anything about the day itself (day of month,
weekday) converts to America/New_York first. Ranked by expected value:

1. **Continuous time in every time curve.** The market trend, the bedroom-group curves
   (`bedroom_time`) and the building walks interpolate their knots at the row's month index
   (`knot_basis`, `walk_position`). The NUTS-only `building_trend` and `market_drift` read the
   month too.
   - **The bedroom-group curves** gave +196.3 ± 30.6 paired on the daily-season design at the
     exploration tier (run `…-dayfourier-bedtime-…-ed278e5-x-2060-100w600d-nb-v4`, not yet on
     master).
   - **On the served design** (`m7-nocurves-floorslope-bednoise`, no bedroom curves), the item is
     the trend plus the walks.
   - **Gibbs cost:** the trend and bedroom curves are keyed columns (a function of bedroom group
     and month).
     - Keyed by bedroom group and *week* instead, about 4 × 874 keys keep the Gram exact at
       one-week resolution. The curves must then be interpolated at the row's week, not its
       exact date, or the keyed-basis check in `build_design` fails.
     - With month effects for the season (no `season_daily`), a week can straddle two calendar
       months. So this needs `season_daily`, or keys that never cross a month boundary.
     - The building walks are local columns and take the exact fraction directly.
   - **Test:** paired on the served design. Small buildings should be flat. The gain should
     show in the fast-moving years (2020–2022).
2. **Unit drift from exact dates.** `unit_time` is years from the unit's mean training *month*;
   use days instead. Cheap, and only matters for units with several listings close together.
3. **Within-month and weekly cycles.** NYC leases mostly start on the 1st, and listings posted
   late in a month compete for next month's move-ins. Add a K = 1 Fourier term on the
   day-of-month fraction and day-of-week indicators, in New York time. They are plain feature
   columns: being tried as `nb-bedtext-cycle-v1` (batch/dayfourier-v4).
4. **Time since the unit's previous listing.** Days between this ask and the same unit's previous
   ask (with unit-labels-v2 joins), as a feature. A quick relist (under 90 days) suggests a
   problem unit, a failed lease or a corrected ask; a long gap suggests a renovation. This is
   new information, not a refinement, so it's for the data session. Only earlier listings
   count, so there is no future information.
5. **Building age at the listing date.** Continuous years since construction (MapPLUTO
   `yearbuilt`) at the listing date, in place of era buckets.
   - Alterations need care. `yearalter1/2` are from a current snapshot, year-only, and only two.
     A 2018 alteration would apply to a 2012 listing; `altered_since_2000` already has this
     leak.
   - Use only alterations dated before the listing, which means DOB permit or C of O dates for
     exact timing.
   - Judge it on elegance as much as on PSIS-LOO.
6. **Exact event dates for the dated features.** Several features cut off at the start of the
   listing's month:
   - subway openings (`stops_not_open`);
   - 311 noise and HPD violation windows ("the `days` before the row's month");
   - High Line sections (`nb-openspace-v1`, only on `features/nb-openspace`, recorded null in
     #147).

   Cut off at the listing's own date instead (events strictly before `price_at`). That
   *loosens* the rule from "before the month started" to "before this listing". It is still no
   future information. The windows keep their length and move up to a month later, so they hold
   more recent history. `nearby_noise`'s per-month Chelsea reference would become per-date too.
   Expect small gains.
7. **Move-in date from the ad.** "Available 9/1", "immediate occupancy": the gap between the
   listing date and the stated move-in date, as an urgency or seasonality signal. This is
   ad-text work for the data session, and only worth doing if a few thousand rows state a date.
8. **Out-of-time validation.** Score models on the last N weeks by exact date, fit on
   everything before, as a secondary check that the time terms forecast rather than smooth.
   This is a diagnostic, not a selection rule.
9. **Lower priority:**
   - Holiday and academic-calendar bumps (Labor Day, NYU's semester start in the Village):
     daily K = 3 added nothing over K = 2, so only as fixed event windows if residuals show
     them.
   - Daily macro series (mortgage rates): the market trend already absorbs them.

## Model structure for the full-data frontier (2026-10-02)

These are ideas for the PSIS-LOO × fit-time × elegance frontier on the combined Chelsea + West
Village data, each to be tried first at the exploration tier on the leading design. Results so far are
in the research plan, under "Exploration results on the leading design".

- [ ] **Small-building pooling.** 47% of the high-k rows are in buildings with 5 or fewer rows, and
  72% are alone at a walk knot. Try shrinking a small building's level toward its neighbours rather
  than toward the area mean: a spatial prior on the building effect, not extra feature columns.
  The fixed Gaussian-bump surface (`nb-loc-v1`, #143) tied overall but helped small buildings
  (+16.8 ± 8.7).
- [ ] **A Gaussian-process location surface (HSGP).** This is a Hilbert-space approximate GP over
  coordinates, with a learned amplitude and length scale. It replaces the fixed bumps, so the data
  sets how smooth location is. With m basis functions it stays one Gaussian block for the Gibbs
  sampler.
- [ ] **A space × time surface.** Let the location surface drift over time: a separable HSGP in
  (x, y) × month, or one surface per half-year tied by a random walk. It could replace part of the
  per-building walk with a neighbourhood-level one. It would also make the rent map by time a model
  term rather than a summary.
- [ ] **Fourier seasonality.** Two harmonics tie the 12 month effects (#144). Try K = 1 and K = 3,
  and combine with the bedroom noise.
- [ ] **A shared building factor.** One latent "premium" per building that loads on the building's
  level, its bedroom slope and its size slope (a one-factor model), instead of independent
  per-building effects. That is fewer free effects per building and a single story ("a premium
  building is pricier, and more so for larger units").
- [ ] **Latent square footage.** Treat a missing or rounded size as a latent variable with a prior
  from the building, the bedroom count and the floor plan, instead of a missing-value column.
- [ ] **Heteroscedastic noise beyond bedrooms.** The bedroom scales are a large gain (#142). Try a
  scale per area (Chelsea and West Village) or a smooth log-scale in log size, then check whether
  the bedroom groups still carry it.
- [ ] **Richer ad text.** Flags chosen on held-out halves (`nb-text-v2`, #141). Also consider a
  low-dimensional text embedding with a shrinkage prior, if the flags replicate.
- [ ] **The low end of the frontier.** Under 5 minutes per fit: `m5-nocurves-bednoise`, `m0q` and
  `m1q` with the bedroom noise, and fewer walk knots.

## Data quality: clean the data so the model can be less defensive (Ben, September 25)

"If the data is cleaner, then the model doesn't have to be as defensive against outliers."

**Why it matters.**
- The frontier designs defend heavily against bad rows. The noise is Student-t with an estimated
  ν of about 2, and m7/m8 give the unit effects Student-t tails too.
- Heavy tails have three costs:
  - they down-weight informative rows along with the bad ones;
  - they slow the samplers (the ν and noise-scale geometry);
  - they make PSIS-LOO fragile, since high-k rows are often the outliers.
- If gross errors are fixed, or excluded by documented rules, a lighter-tailed model may fit as well
  or better: a larger fixed ν, or Gaussian noise.
- Gaussian noise would also allow exact analytic integration of all the Gaussian terms (trend,
  features, buildings, units): the largest sampler speed-up available to any library sampler.

**1. Find the rows the tails are protecting against.**
- Rank training rows by the fitted model's standardized residual (|y − μ| / σ), its PSIS-LOO
  pointwise density and Pareto k, and its Student-t weight, i.e. how strongly the fit discounts
  the row.
- Review the top few hundred and tally them by cause.

**2. Likely causes to check.**
- **Price basis:** net-effective vs gross rent, concessions (months free), furnished or short-term
  rentals, commercial units or parking in the residential feed.
- **Identity:** a listing linked to the wrong unit or building. One building can appear under two
  slugs: the building registry maps 104 slugs to 41 tax lots. Many are condominiums sharing a
  billing lot, but some look like one building listed twice (606 W 30th and "3 Eleven"), which
  splits its building effect.
- **Attributes:** bedrooms, bathrooms or square feet entered wrongly (a studio listed as a 3BR,
  square feet out of range), floor labels.
- **Price entry:** a missing or extra digit, weekly or annual amounts.
- **Time:** stale asks, relists, backdated price changes.

**3. Fix what can be verified, and document what can't.**
- Verify against the listing text, the listing's own history page, the building page or the
  external data (MapPLUTO units and floors, the registry).
- The source bundle stays read-only. Cleaning produces a new, versioned analysis dataset with a
  change log (row, change, reason, evidence), and every fit records its dataset version.
- Rules target errors, not unusual but real listings: a penthouse, or a rent-stabilized unit far
  below market, stays in.

**4. Measure.**
- Refit the same design on the cleaned data. Compare on a fixed evaluation set: PSIS-LOO over the
  rows present and unchanged in both versions, plus the held-out rows. Changing the row set changes
  the PSIS-LOO population, so whole-dataset totals are not comparable.
- Watch the posterior of ν: does it rise once the errors are gone?
- Then test lighter tails on the cleaned data: a larger fixed ν, and Gaussian noise. If they win,
  fit time and NUTS geometry improve too.

**Left open by `quarantine-v2` (September 30).**
- Two pages sit on lots MapPLUTO records without apartments. Their other ads stay in until each
  page is matched to the right building:
  - 256 West 23rd, lot 1007720075, is a theatre (J9) whose ads describe a "charming townhouse"
    walk-up;
  - 401 West 15th's lot is 75 Ninth Avenue, an office building (O6).
- 466 West 23rd has ads saying "466 west 22nd", but the same units' other ads say 23rd. It looks
  like a template slip, so the rows stay in.
- **Stated size against recorded square feet.** 1,442 rows have an ad that states the
  apartment's own size, found by phrases such as "1,100 sq ft two-bedroom" or "the apartment is
  approximately 850 square feet", with terraces, gardens and amenities left out. In 27 of them
  the size is more than 1.6× off the record. Most of those still describe another space ("a
  400 square foot" roof, "4,420 square feet across three apartments").
  - The few real conflicts are at 440 West 22nd: three ads say "1,625 sq.ft two bed" for units
    recorded as 825 sq ft one-bedrooms.
  - The 27 asks sit close to the model's estimates (0.8–1.4×, most near 1), so none is
    quarantined yet. A size rule would need the bedroom count to disagree as well.
  - Scratch script: `/data1/apartments/tmp/bridge/sqft_conflicts.py`.

## Column ("line") effects within buildings (Ben, September 25)

**Idea.** In most buildings, units with the same letter or line on different floors ("4C", "7C",
"12C") stack vertically. They usually share a floor plan, exposure, views, window orientation and
position (corner or interior, street- or courtyard-facing). A per-building column effect could
capture this, pooling information across floors where today each unit stands alone.

**Why it should help.**
- About 47% of units are listed only once. Their unit effect is essentially the prior, so PSIS-LOO
  leans on building and features alone.
- A column effect would let a single-listing 12C borrow strength from 4C and 7C's history.
- It's also more interpretable than an anonymous unit effect: "the C line in this building rents
  6% above its features".

**Steps.**
1. **Extract the line.**
   - Parse unit designations into floor plus line: "12C" → floor 12, line C; also "PH-A", "4R"/"4F"
     (rear/front), and numeric lines like "1204" → floor 12, line 04.
   - Record the parse rule and its coverage. Unparseable designations get no column, so the
     effect is 0 there.
   - Check against the advertised floor where both exist.
2. **Model shape.**
   - Add a column level between building and unit: rows ⊂ units ⊂ columns ⊂ buildings, with its
     own scale. Unit effects then become deviations from their column.
   - Keep the one-model-definition rule: a `ModelConfig` switch (`columns=True`) in
     `build_model`, fit with NUTS.
   - Use the same level-by-level centring: column totals centred on their mean features.
3. **Screen first.**
   - Project the m8 + desc reference onto m0q/m5-nocurves + columns to see whether columns take
     variance from the unit and building shares in the variance decomposition.
   - Then run a native NUTS fit within the fit window (30 minutes from 2026-09-29).
4. **Combine with orientation.** Columns are the natural carrier for the unit-orientation features
   in the external-data track (research plan, A′): street vs courtyard, the width of the facing
   street, window direction. A line faces one side of the building on every floor.

**Watch for.**
- Inconsistent designation schemes across buildings and over time.
- Renumbered or combined units.
- Lines that switch layout above a setback.
- Columns with a single unit add nothing and should fold into the unit effect.
- Compare PSIS-LOO on the same rows: the gain should show up mainly on units listed once.

## Rent map and building-level follow-ups (Ben, September 29)

**What prompted these.** Ben, watching the rent map (research dashboard, `map.html`): the areas of
high and low rents inside Chelsea seem "stable" and "driven more by certain buildings than by
streets or blocks". The map's own data (1-bedroom, the served model) put numbers on it:
- **Stable.** Buildings' premiums over Chelsea's median building keep their rank: correlation 0.97
  from 2012 to 2016 and 0.90 from 2012 to 2024. The spread of the 2012–2024 change is 0.12 in log
  rent, against a spread of 0.22 across the same buildings in 2024. Part of this is built into
  the model (one fixed level per building plus a slow path over time), but the data set how slowly
  the path moves: "building over time" is 1% of the variance.
- **Buildings more than blocks.** Premiums of building pairs correlate +0.25 within 50 m, +0.16 at
  50–100 m, +0.06 at 100–200 m and about 0 beyond. This matches the location-surface result (no
  gain; research plan A.2).

Ben chose to start with street-facing units (research plan A′, "Unit orientation"). These wait:
1. **Map: colour by change since a chosen year.** This makes the few buildings that moved stand out
   against the stable background. Three layout nits from the PR #56 review:
   - the "Hudson River" label stays at the frame's left edge after panning east;
   - street labels at the right edge sit under dots on small maps;
   - below 1,100 px the legend falls below the map.
2. **Building condition and management data.** The anonymous building level is still 8% of the
   variance. Condition, management and amenities are likelier sources of it than geography:
   - HPD violations and complaints per unit, as of the listing date;
   - DOB alteration permits, as a renovation proxy;
   - Local Law 84 energy scores.

   The research plan's A′ table lists these sources. Each needs as-of values (no future
   information) and a renter-facing glossary row.

## Registry follow-ups (September 30)

- **507 West Chelsea and AVA High Line.** Avalon West Chelsea is fixed (`unitdescpluto-v5`: its
  ads give 282 Eleventh Avenue, MapPLUTO lot 1007000009, 31 floors and 710 apartments).
  - 507 West Chelsea is on the right lot: 509 West 28th Street, three buildings and 372
    apartments, the "three towers" its ads name. But MapPLUTO records 13 floors, while the
    tallest footprint on the lot is 385 ft and the listings reach the 33rd floor, so the lot's
    floor count is low.
  - AVA High Line's page also sits on that lot, because its address field reads "507 West
    Chelsea". Its ads describe an AvalonBay building "on 28th st bet 10 & 11th avs" with a
    14th-floor roof deck, and its listings reach the 12th floor. That fits the lower part of
    the Avalon lot (539 West 28th), but the ads give no house number, so it stays.
- **Reverse-geocoded pages.** 99 pages remain matched by reverse geocoding. A check against
  the ads' own location statements ("located on …", house-number addresses) and the streets each
  building fronts (centerlines within 25 m of its footprints) sorts them:
  - 67 are confirmed: every statement names a street the building fronts.
  - 8 have statements that disagree, all for benign reasons: a corner or a second entrance (the
    Carteret, the Irvin House, the Sierra and Stonehenge Gardens on 15th Street, the same lot as
    108 West 15th), a sponsor's address, a broker's other building, or a slip ("151 east 21st").
  - 24 pages (2,987 rows) state no address, so nothing confirms them.
- **Pages with no footprint.** 18 pages (363 rows) match no footprint by BIN or lot, so their
  facing sides are unknown. Most are condominiums on a billing lot (75xx) with a placeholder BIN
  (1000000): Lantern House, The Seymour, Soori High Line, the Spears Building. GeoSearch on the
  address gives the real BIN (Lantern House, 515 West 18th: 1091605), so a registry version could
  resolve them.
- **Listings above their footprint's roof.** The registry BIN's footprint roof height is far
  below the listings' floors for eight buildings. No feature reads the roof height: building
  heights come from MapPLUTO's floor count, and for Chelsea29 (MapPLUTO 21 floors, listings to
  the 22nd), 551 W 21st (20, 17th) and 606 W 30th (45, 47th) it agrees with the listings. The
  footprints' heights are low for these BINs (89, 49 and 187 ft), perhaps a lower wing or a
  capture before completion.

## Pipeline review, September 20

Items from an end-to-end review of collection → transform → fit → analyze,
ordered by expected leverage. Numbers refer to the selected fit
(`chelsea-bayesian-expanded-spline-floor-disk-20260919`) and the
`chelsea-granular-20260917-canonical-url-v1` source unless stated.

### Residual review and model

- [x] **Report unit-level deviation as the primary review signal.** Done:
  review queue (`apartments build-review-queue`), September 20.
  Original rationale: The
  selected fit has `sigma` 0.066, `sigma_unit` 0.086 and 47% single-observation
  units. For a singleton, the split between unit effect and residual is set by
  the variance ratio, not by data: for moderate deviations roughly 63% of a
  unit's departure from building + features + time is absorbed into the unit
  effect and only ~37% appears as "residual" (Student-t tails reverse this for
  extreme outliers). The review queue's ranking therefore depends on the
  `sigma_unit` prior and on how often a unit was listed. Add
  `unit_effect + residual` (deviation from building/features/time) to
  `residuals.jsonl` and the main page, show both components, and rank the
  queue on it. Report-only change on saved draws; no refit.

- [ ] **Use the within-advertisement price path.** 27,473 of 65,350 own
  advertisements (42%) changed price while listed; median first→last change
  is −3.5% (p10 −13.2%, p90 +6.2%). Only the initial ask is used. Publish a
  per-advertisement table (`initial_ask`, `final_ask`, `n_cuts`,
  `days_listed`, `terminal_status`) from `event_mentions`; refit on final
  ask and compare coefficients with the initial-ask fit; carry
  `days_listed`/`n_cuts` as observables for current listings. History-table
  mentions of *other* advertisements are not a separate source of new data:
  of 74,674 (unit, listing) pairs, 68,836 are own-captured and the 5,838
  mention-only listings are almost all 2007–2013 (pre-canonical-page cohort).
  Extending the trend to 2007–2013 with masked attributes is a low-priority
  option only.

- [ ] **Align current and historical price basis.** 172 current rows use
  `current_capture_gross_ask` (possibly after cuts) while 52,481 historical
  rows use the initial ask, so stale or cut current listings look cheap.
  Either use the initial ask for current rows or add the price-path
  covariates above.

- [ ] **Publish the observation funnel as a standing artifact.** Raw
  own-captured listings 68,313 / 25,119 units (2.72 per unit; 42% singletons;
  median 1.7 years between repeat listings) → v4 accepted 54,105 → fitted
  52,481. Exclusions (furnished 4,587; concession 4,509; date window 1,259;
  no dated ACTIVE event 488; layout 262; extreme ask 243; conflicting
  same-month layouts 179) are in `coverage.json` but not surfaced. Check
  whether the 4,509 concession exclusions concentrate in recent luxury
  buildings and bias the current cohort.

- [ ] **Test coefficient stability over time.** One log premium per feature
  is shared across 2010–2026 with one Chelsea-wide trend and no bedroom×time
  interaction. Refit on 2019+ only and compare coefficients; add bedroom-group
  trend deviations. If premiums move materially, use era-specific
  coefficients or a restricted serving window.
  *September 22:* bedroom-group random-walk trend deviations fitted and
  converged (held-out ΔELPD +30.0 ± 9.5; group × year bias 0.92% → 0.67%);
  not yet promoted, see [bedroom-time experiment](bedroom-time-experiment-2026-09-22.md).
  The 2019+ coefficient refit is still open.

- [ ] **Building covariates in the building-effect mean.** 25% of buildings
  have ≤5 observations and are shrunk toward the Chelsea mean, inflating their
  units' residuals. Join PLUTO (year built, floors, units, building class),
  DOB elevator devices and coordinates, and place them in the mean of
  `building_effect`. Motivation is small-building shrinkage for fitted
  buildings, not unseen-building prediction. This would also replace
  listing-derived `elevator` (70% known; posterior +0.7%, mostly absorbed by
  building effects).

- [ ] **Relabel positive-only exposure features.** `window_exposures.*` and
  `view_exposures.*` are only ever `True` or missing, so the value columns
  are constant and dropped; the `.unknown` indicators in the design actually
  mean "mentioned". Rename (`mentioned_south`) or extract negations; stop
  presenting them as tri-state.

- [ ] **Improve sampling geometry.** Minimum ESS is on `alpha` (821) and
  bathroom contrasts while median ESS is 33k, indicating a centering problem
  among the intercept, zero-sum building effects and 22k non-centered unit
  effects. Test sum-to-zero unit effects within building; target the same ESS
  with 1,000/2,000 instead of 4,000/6,000 per chain. Also consider estimating
  `nu` instead of fixing 5.

- [ ] **Fast screening fits from the same graph.** Use `find_MAP`/Laplace or
  ADVI on the identical PyMC graph to screen feature experiments; reserve
  full NUTS for candidates that pass. The main model stays exact PyMC; the
  screen is for triage only.
  *September 22:* tested in [fast screening](fast-screening-2026-09-22.md).
  Raw joint `find_MAP` is degenerate (`sigma_building` → 0) and unusable.
  MAP with baseline variance components fixed reproduced a known +30 ΔELPD
  and a null control in minutes. Data subsets are unbiased but underpowered.

### Iteration speed (Ben, September 23: "I would like to be able to iterate more quickly")

Measured on the promoted building-drift fit (`chelsea-bayesian-product-scope-structure-20260923`):
4 chains × (4,000 tune + 6,000 draws) took ~6 h of sampling at 255 leapfrog
steps per iteration (tree depth 8), plus ~1 h of reports. It wrote ~40 GB,
with unit and building draws stored three times (trace, `posterior.nc`,
report caches). Convergence is limited by one parameter: `alpha` has bulk ESS
587 and R-hat 1.0088 (1.0103 on the Modal refit of the previous spec), while
most parameters have ESS in the tens of thousands. A NUTS screen
(1,000/1,000) takes ~2.5 h and ~5 GB; a conditional-MAP screen takes
3–6 min on one core. Targets: **protocol fit under 2 h and 12 GB; NUTS screen
under 45 min**, with the same convergence gates and the same held-out
conclusions. In priority order:

- [ ] **E1. Fix the intercept geometry.** `alpha` is the only slow direction.
  Test on short runs (4 × 500/500) of the promoted spec, measuring ESS/second
  for `alpha` and the global scales: (a) sum-to-zero unit effects within
  building; (b) the intercept absorbed into the building-effect mean
  (non-zero-sum building effects around `alpha`); (c) nutpie low-rank mass
  matrix adaptation (`--adaptation low_rank`). Keep the variant that removes
  the bottleneck with identical posteriors, checked by comparing
  coefficients, scales and residual intervals.
  *September 23, round 1* (Modal, 8 runs × 4 cores, 4 × 500/500, full data;
  `models/efficiency_benchmark.py`, `models/bayesian_structure_graph_v3.py`;
  results in `data/model/modal-runs/efficiency-20260923/`): **the intercept as
  the building-effect mean (b_j ~ N(α, σ_b)) fixes the bottleneck.** `alpha`
  bulk ESS rises from 30 to 2,803 (R-hat 1.107 → 1.000), about 90×. Low-rank
  adaptation did not help; unit centering within building added nothing.
  Steps per draw were 127 (depth 7) in every variant, so E2 needs other
  levers. The new slowest directions are `annual_drift` (ESS 130–215) and one
  or more coefficients (min ESS 25–54). Round 2 tests removing the common
  drift from the building walks and identifies the slow coefficients.
  *Round 2* (4 × 1,000/1,000): removing the common drift from the building
  walks (walk levels average zero across buildings at every knot, row-weighted)
  doubles annual-drift ESS (396 → 775) and the slowest coefficient's (91 →
  196). Adopted. The slowest coefficients were correlated pairs
  (`elevator`/`elevator.unknown`, `bedrooms_gt_1`/`full_bathroom_shortfall`).
  *Round 3:* a QR feature basis (sample θ = Rβ with β's exact N(0, s) prior
  added as a potential; verified identical log density) lifts the bedroom and
  bathroom block to ESS ≥ 450, but `elevator`/`elevator.unknown` stay at
  176–200. They are building-level attributes, confounded with building
  effects rather than with other columns. *Round 4* tests within-building
  feature centering: b_j ~ N(α + β·m̄_j, σ_b), with the row term on x − m̄_j.
  It is an exact reparameterization (verified identical log density), and
  the saved `building_effect` = b_j − α − β·m̄_j keeps readers' arithmetic
  unchanged.
  *Round 4 result:* within-building centering plus QR gives every parameter
  ESS ≥ 450 per 4,000 draws (slowest coefficient 91 → 454; annual drift
  1,049; slowest overall the building-walk scale, 546). Either change alone
  leaves the slowest coefficient near 200. **Adopted combination:** intercept
  as the building mean, walk centering, within-building features, QR basis.
  The page's reconstruction on a fit with this parameterization matches the
  saved residuals to 2e-15. The E3 validation fit (`models/bayesian_efficient_structure_experiment.py`,
  4 × 1,000/1,500) runs on Modal.
  *E3 result (September 23):* 2,500 iterations took 33 min on Modal (4
  cores), with depth 7 and no divergences. Per draw, minimum ESS is 3× the
  promoted fit's (434 from 6,000 draws vs 587 from 24,000). Coefficients
  match within 0.07 posterior SD; bedroom curves and interval widths are
  identical. Two problems:
  (1) 13 of 65k parameters sit at R-hat 1.010–1.016, the chance tail at this
  ESS, so the gate needs ~3,000 draws.
  (2) **Walk centering is a model change, not a reparameterization.** E3's
  fitted rents over-predict every half-year of 2021–22 by ~1.7% (median
  residual −0.016 to −0.020 vs ~0 in the promoted fit), with smaller
  shifts in 2016–17. The row-weighted common mode of the building walks,
  dominated by the largest buildings, was carrying the sharp 2021 rebound;
  removing it leaves that to the smoother citywide trend basis, which cannot
  follow it. **Walk centering is withdrawn.** The combined candidate uses
  only the three exact reparameterizations, at 4 × 1,000/3,000. An explicit
  citywide half-year walk alongside centered building walks would restore
  the common mode with its own scale; that is a candidate model change and
  needs a screen before adoption.
- [ ] **E2. Cut steps per iteration.** 255 leapfrog steps per draw dominates
  cost. Measure steps/iteration and ESS per gradient for E1's variants;
  low-rank adaptation or better-scaled global parameters should reach tree
  depth 5–6 (4–8× fewer gradients).
- [ ] **E3. Right-size the run.** Once `alpha` mixes like the rest, target the
  gate (min ESS ≥ 400, R-hat < 1.01) with margin: e.g. 4 × (1,000 tune +
  1,500 draws) instead of 4,000/6,000. Validate one protocol fit against the
  promoted posterior (coefficients, contributions, residual intervals,
  current-listing fitted rents) before adopting it as the default.
- [ ] **E4. Warm starts for incremental changes.** Most iterations add a term
  to an accepted model. Initialize from the previous posterior means and
  reuse its mass matrix and step size, so warmup falls from 4,000 to a few
  hundred. Check that the diagnostics gates still pass.
- [ ] **E5. Faster, smaller reports.** Vectorize `fitted_summary` (it builds
  52k rows with per-row pandas access). Build the report caches directly from
  the trace instead of storing draws three times; use float32 caches. With E3
  this takes a fit from ~40 GB to under ~12 GB.
- [ ] **E6. One screening command.** Run conditional MAP on both declared
  splits, then a short NUTS confirmation for survivors, as memory-capped
  systemd units with a queue, appending results to the screening log. Check
  whether 500/500 NUTS draws suffice for paired ΔELPD, which is much lower
  variance than parameter estimates.

### Collection and operating loop

- [ ] **E7. Sampler comparison with the from-scratch Gibbs sampler.** For the
  same m6 spec: PyMC/nutpie NUTS took 3.2 h on 4 CPUs (4 × 1,000/1,000, R-hat
  up to 1.05) on the row split. The from-scratch session's blocked Gibbs
  sampler took 44 min on one H100 ($3.24; 16 × 900/2,000; min ESS 3,267,
  R-hat ≤ 1.009). Its Student-t is a scale mixture: per-row weights λ are
  drawn exactly, then all latents jointly from one Gaussian (batched
  per-building Cholesky blocks plus a ~325-column global Schur system), so
  ν ≈ 2 changes weights, not geometry. Group scales use collapsed Metropolis
  steps tuned in warmup. NUTS instead pays for heavy tails in step size and
  tree depth. For the Pareto board, the PyMC line's value is as an
  independent check of model structure, not as the production sampler for
  heavy-tailed variants.
- [ ] **Scheduled active-listing refresh.** Collection is backfill-oriented
  and the current cohort is a one-off 172-row refresh; price cuts and
  delistings are not being observed. Add a systemd timer on thelio:
  discover active in-scope listings → re-fetch active detail pages every
  3–7 days until delisted → incremental transform → fit → publish.

### Transform and extraction

- [ ] **Schema-constrained LLM extraction over the 72k description captures**
  (floor, exposure, laundry level, outdoor access/type, ceiling height,
  renovation, commercial/SRO/income-restricted/net-effective/furnished/
  short-term) returning evidence spans. Keep manual review for calibration on
  a stratified sample. Use it to finish the 667-row commercial/net-effective
  screen.

- [ ] **Consolidate scope/quarantine overlays into the corrections ledger**
  with a `scope` field (commercial, sro, net_effective, short_term,
  whole_building, income_restricted). Replace the 12 bundles in
  `config/reviews/` and the per-batch `*_projection.py` / `*_revision.py`
  modules with one overlay mechanism and one projection step.

### Codebase and artifacts

- [ ] **Collapse the model module chain.** The main fit spans
  `bayesian_floor_spline_experiment → feature_experiment_v3 → v2 →
  feature_model → rent_model` plus graph/execution/disk modules; `models/`
  has 151 scripts including `_v2/_v3/_v4` copies and eight
  `*_fit_comparison.py` variants. Since the protocol hashes implementation
  files, git SHA + protocol JSON is sufficient for reproducibility: one
  `model.py` with an explicit versioned spec, old versions in git history.

- [ ] **Artifact retention.** `data/model/` is 284 GB over 408 directories;
  the selected fit is 16 GB with unit-effect draws stored three times (zarr
  trace, `posterior.nc`, report cache). Keep the raw trace only and derive
  the rest; retain protocol + summary + coefficients + residuals for every
  run and full posteriors only for selected and last-N.

- [ ] **Documentation shape.** Keep one short README, one
  `docs/model/current.md` rewritten on promotion, and dated notes under
  `docs/log/`; `main-model-evolution.md` already notes that
  `current-analysis.md` is stale.

- [ ] **Concurrent agents.** Use worktrees or branches per agent; the working
  tree currently carries uncommitted changes from two streams.

## Remote fit execution

- [ ] **Benchmark PyMC fitting on Modal: large CPU versus GPU** — user research
  idea, September 19, 2026. Compare local execution with a large CPU instance
  and a GPU on Modal using the same analytical dataset, model specification,
  full-length sampling protocol and convergence requirements. Prioritize the
  round-trip data burden: inventory the exact analytical inputs required for a
  reproducible fit and the fit products required for local contribution,
  residual and counterfactual analysis; measure their uncompressed and
  compressed sizes, file counts, upload/download times and transfer costs.
  Make per-fit transfer burden the primary decision criterion: report bytes
  uploaded for the analytical dataset and bytes downloaded for the usable fit
  bundle separately for a cold run, an unchanged-data refit and a data refresh.
  Report total turnaround and cost, separating transfer, environment startup,
  compilation, sampling, diagnostics and export. Compare first runs with
  repeated fits using unchanged or incrementally updated data; evaluate caching
  immutable inputs and reusing unchanged artifacts by content hash. Identify
  which raw traces, caches and intermediate products can remain remote without
  compromising local analysis, complete posterior uncertainty or reproducibility.
  Verify a downloaded fit bundle loads and reproduces the same local analyses
  before recommending an execution setup. Do not judge speed from short
  warmup/draw runs dominated by startup costs.
  A [local footprint study](../analysis/modal-transfer-footprint-2026-09-19.md)
  now measures the expanded analytical input at 286.7 MB uncompressed / 45.8 MB
  with gzip, and the original spline's inferred offline analysis closure at
  4.586 GB. These are local measurements and code-inspection findings; remote
  transfers, posterior compression and a clean bundle roundtrip remain untested.
  September 22 progress: `models/modal_remote_fit.py` uploads inputs as SHA-256
  blobs (cold 291 MB in 12 s; unchanged refit 0 bytes; one-file edit 10.8 KB),
  rebuilds the dataset at its original absolute path so the remote protocol
  equals a local one, and downloads verified fit/protocol bundles. A 100/100
  smoke fit matched the local protocol except draws/tune/seed, with byte-identical
  design files, for $0.052 billed. September 23: a full-length refit reproduced
  the local protocol hash, ran in 55.4 min for $0.38, downloaded 4.39 GB in 141 s,
  and agreed with the local fit within Monte Carlo error. It narrowly missed the
  R-hat gate (1.0103 on `alpha`), so loading a converged remote bundle in
  `BayesianAnalysis` is still open. Details:
  [remote fitting record](../analysis/modal-remote-fitting-2026-09-23.md).

The items below continue the September 22 Modal sampling campaign. Probe data:
`data/model/modal-runs/probe-*-20260922`.

September 23 findings (L4, NumPyro, 4 chains, 300 warmup + 100 draws;
`data/model/modal-runs/prec{64,32}-l4-20260923`):
- float64: 511 leapfrog steps every iteration, 0 divergences, max R-hat 1.11,
  median/min bulk ESS 922/38. nutpie on CPU needs about 50-90 steps, so a
  full-length NumPyro fit would take about 4.4 h on the L4, against about
  22 min of CPU sampling.
- float32: every iteration hit maximum tree depth (1,023 steps), chains did not
  move (ESS 4, R-hat infinite). float32 fails for this model as written.
- nutpie JAX backend with PyTensor gradients (canary, early warmup): about
  4 ms per step per chain on L4, against 2.3 ms on one CPU core. The ~30 ms
  single-chain cost below comes from JAX's own autodiff of this graph.
- Current conclusion: nutpie/Numba CPU remains fastest and cheapest per fit;
  Modal's benefit is running fits concurrently at about $0.35-0.40 each.

- [ ] **Single-chain JAX gradient is ~12× slower than one CPU core** — user
  directive, September 22, 2026. The spline model's logp+gradient takes about
  30 ms for one chain on H100, A100 and L4 (22 ms on the local RTX 2060 SUPER),
  against 2.6 ms for Numba on one CPU core, yet a vmapped batch of 4 chains
  costs only about 1.3 ms. nutpie's JAX backend with PyTensor-built gradients
  measured about 4 ms per step, so the cost is concentrated in JAX's own
  autodiff (likely the transposed per-unit/per-building gathers). Profile the JAX
  graph (e.g. `jax.profiler`, HLO dumps), identify the slow ops, and test
  equivalent formulations (segment sums, sorted indices, one-hot or sparse
  matmuls) in a new graph module. Show exact log-density/gradient parity with
  the frozen graph before any sampling. This decides whether nutpie's JAX
  backend, which evaluates chains one at a time, is viable on GPU.
- [ ] **Measure nutpie JAX on GPU** — the PyMC-developer recommendation as of
  June 2026. Only a 30-draw canary has run (about 4 ms/step/chain on L4). Run nutpie `backend='jax'` with `gradient_backend` pytensor and jax,
  4 chains and nutpie's shorter default tuning on H100 and L4. Compare wall
  time and ESS per second and per dollar with nutpie/Numba CPU, and with
  NumPyro vectorized chains.
- [ ] **Many vectorized GPU chains** — NumPyro's window adaptation needed 511
  steps per draw (see above), so batched chains lose on gradient count. Next,
  test adaptation built for many chains
  (BlackJAX ChEES/MEADS, or nutpie's normalizing-flow adaptation). Report
  lockstep leapfrog cost, warmup length needed, and ESS per dollar at
  24,000 retained draws.
- [ ] **float32 sampling** — log-density error is 5e-7 relative and gradient
  error 0.07% scaled, but NumPyro float32 sampling failed (see above). Revisit
  only with a rescaled model or a different sampler, with explicit tolerances.
- [ ] **CPU multi-chain scaling** — on a 16-core Modal container, aggregate
  Numba gradient throughput plateaued at about 2 chains' worth (4 processes:
  2× slowdown each; 16: 12.8×), probably memory bandwidth on a shared host.
  Repeat on dedicated or other CPU types before ruling out more-chains CPU fits.
  Any chain-count change needs a new sampling module, since
  `bayesian_disk_sampling.py` (`cores=min(chains, 4)`) is hashed into fit
  protocols.
- [ ] **Post-sampling report stage** — about 30 of the local fit's 56 minutes
  are single-threaded diagnostics and reports after sampling. Profile it and
  parallelize it across chunks or processes, or run it as a separate remote
  job. Faster samplers alone cannot cut a fit below this floor.
- [x] **Posterior transfer** — the complete 4.39 GB bundle downloaded in 141 s
  (31 MB/s). Experiments now download summaries only by default; `complete`
  fetches the posterior for promotion candidates.
- [ ] **Marginal R-hat for `alpha` at 6,000 draws** — the remote refit reached
  1.0103 against the 1.01 gate, with the same protocol that passed locally at
  1.0036. Assess whether the intercept's slow mixing warrants more draws,
  reparameterization, or a gate that accounts for run-to-run variation.

## Floor representation

- [ ] **Gaussian process for the floor increment model** — user research idea,
  September 19, 2026. Explore correlated increments across listed-floor levels
  using a Gaussian-process prior in PyMC. Compare against the selected natural
  cubic spline on the same frozen source cohort. Evaluate joint floor contrasts,
  coefficient uncertainty, prior sensitivity, residuals and full-length sampling
  diagnostics/work. Record kernel and length-scale assumptions explicitly;
  evaluate increments versus a GP on floor-price levels as distinct choices.
  This is a research candidate, not a change to the selected main model.

- [ ] **Random walk for floor increments** — user research idea, September 19,
  2026. Let neighboring floor increments vary while encouraging each increment
  to stay near the previous one (equivalently, a joint neighbor-difference
  penalty links it to both neighbors in the interior). Explore a learned
  innovation scale and an explicit starting/anchoring prior in PyMC. Distinguish
  a random walk on increments from a random walk on the floor-price levels;
  compare both interpretations with the GP and selected spline using the same
  frozen cohort, joint contrasts, prior sensitivity and full-length diagnostics.

## Floor measurement

- [x] Audit why the selected model has only 56.8% floor coverage. The
  [complete census](../analysis/chelsea-floor-coverage-reassessment-2026-09-19.md)
  identifies omitted formats and reviews all six new-rule disagreements.
- [x] Broaden the initial label parser beyond one/two digits plus one letter.
  Audit numeric labels, wing prefixes, multi-letter suffixes and floor-only
  labels against own-advertisement evidence and building numbering. Keep
  advertised labels separate from physical height and preserve source conflicts.
  The published expanded source reaches 68.36% observation coverage and is now
  used by the selected main fit after the matched refit and source/UI review.
  See the [source experiment](expanded-floor-source-experiment-2026-09-19.md).
- [x] Project the five confirmed reference-photo floor errors at 160 W22 through
  source-bound corrections, preserving their raw claims and separate numeric
  label evidence. Keep the 244 W16 `1RE` label/prose discrepancy explicit.
- [x] Complete and assess the full matched spline refit on the expanded source,
  including residual/source reviews and the support-dependent prior change,
  before updating the selected main analysis. The selected fit passes all full
  posterior gates and actual UI checks; the fixed 26-row panel gets slightly
  worse, and this is not claimed as a uniform residual improvement. See the
  [results](../analysis/chelsea-expanded-spline-floor-results-2026-09-19.md).
- [ ] Improve explicitly scoped description-floor extraction using the three
  corroborating cases in the [expanded-source panel](../analysis/chelsea-expanded-floor-source-panel-2026-09-19.md):
  a `53RD FLOOR!` headline, `3rd floor of a walkup building`, and `this 11th floor`.
  A replay of each full description through `attribute-evidence-v6` still yields
  no advertised-floor claim. Preserve photo-reference and shared-amenity scope
  protections; the current label projection already recovers matching values.
- [x] Recover initial named-unit introductions with explicit second/third-floor
  wording at 139 Eighth Avenue. The
  [v7 replay](../analysis/chelsea-named-unit-floor-extraction-2026-09-19.md)
  changes only eight captures for four reviewed ads across all 72,065 archived
  descriptions. These reveal existing label/prose disagreements; applying a
  source projection and resolving numbering remain pending below.

## Floor–elevator interaction

- [ ] Reassess the interaction on the expanded source after its matched base fit
  passes. The [support audit](../analysis/chelsea-expanded-floor-elevator-support-2026-09-19.md)
  has walk-up data only on floors 1–6, with especially thin floor-5-to-6 support.
  Check lower-floor contrasts, unit-effect pooling and opposing elevator claims;
  do not treat high-rise walk-up extrapolation as supported by the data.

## Source leads from the expanded-floor residual review

- [ ] Audit gross versus net-effective historical asks using explicit gross
  quotes and concession terms, beginning with 2834394, 2560481, 2362330 and
  2967520. The [full-description review](../analysis/chelsea-commercial-batch-two-2026-09-20.md)
  finds one exact net-effective arithmetic match and another mismatch. Align
  own-ad price events with dated concession evidence before any correction;
  later descriptions alone do not establish historical applicability.

- [ ] Distinguish base asking rent from mandatory recurring charges in renter
  cost comparisons. The [active-listing review](../analysis/chelsea-current-commercial-match-review-2026-09-20.md)
  finds four captured ads advertising a required $90-per-resident monthly fee.
  Preserve capture timing and explicit resident-count dependence; do not infer
  household size or apply later fee prose to historical prices. Evaluate a
  separate fee-inclusive comparison without silently changing the rent target.

- [ ] Apply evidence-bound residential-scope review to high-residual commercial
  offers: 1260588 explicitly offers professional/business loft space and 937046
  a turnkey restaurant with commercial terms. Verify exact own-capture witnesses
  and historical applicability, preserve quarantined records, and reassess
  contributions/residuals after a matched PyMC refit. Do not replace their prices.
- [ ] Resolve location/access conflicts in residual-tail advertisements 4953355,
  2993341 and 609730 before attributing their gaps to amenities. The first has
  third-floor-walkup prose but a captured condo/elevator/doorman record; the other
  two name locations inconsistent with their analytical building identities.
  Preserve conflicting claims; do not infer replacement addresses from residuals.
- [ ] Decide and document the analytical treatment of explicit SRO/shared-bath
  offers such as 2221592. Distinguish offered product scope from a conventional
  apartment's bathroom count, and test a supported representation or transparent
  scope sensitivity instead of treating the low asking rent as an error.

- [ ] Screen the complete retained cohort for commercial/event-space offers
  before another scope refit. The completed 27-case movement review found four
  more explicit cases: 1543471, 2391701, 806884 and 947730. Manually distinguish
  offered commercial products from residential home offices, live/work options
  and restaurant amenities. Preserve exact-ad evidence and avoid building-wide
  exclusions. Also review the composition conflicts on 790520, 1926797,
  4210456 and 916757, and unextracted explicit floors on 3967693 and 776029.
  See the [movement review](../analysis/chelsea-residual-scope-movement-review-2026-09-19.md).
  The [complete-cohort lexical screen](../analysis/chelsea-commercial-offer-screen-2026-09-19.md)
  now covers 71,806 captures and flags 667 rows (663 ads); manual adjudication
  remains incomplete. Initial full-text follow-up identifies explicit retail
  ad 1466274 and several mixed live/work offers requiring separate treatment.

- [ ] Test the retrospective same-ad attribute assumption against dated price
  changes, beginning with 1670174: initial ask $2,395, then $3,700 and $5,950,
  with later-captured luxury-duplex prose and a powder-room/count conflict.
  Define a temporal sensitivity without silently replacing initial asks with
  later prices. Also adjudicate 2833618's location/access evidence and 3591788's
  furnished/limited-term/service package and explicit second-floor claim. See
  the [candidate tail review](../analysis/chelsea-residual-scope-tail-review-2026-09-19.md).

- [ ] Review income-restricted rental products and dated price basis, starting
  with Port10 4761346 and 4758015, which rank fourth and eighth in the selected
  fit's absolute-log-residual tail. A full own-description language screen found
  12 candidates across five buildings, including distinct HDFC/AMI wording.
  Keep unmatched rows unclassified, separate minimum-income administration from
  eligibility ceilings, and verify historical timing before a coefficient or
  scope experiment. See the [research note](../analysis/chelsea-income-restriction-research-2026-09-19.md).
  The [full-description follow-up](../analysis/chelsea-income-claim-review-2026-09-19.md)
  reviews all 23 captures for the 12 candidates: nine explicit upper-bound
  claims, two AMI statements with unspecified boundary operators, and one
  restriction with unspecified terms. Preserve those distinctions and the
  furnished/short-term/utilities package on 4276224.

- [ ] Resolve the four newly reviewed label/prose floor disagreements at
  139 Eighth Avenue (4810936, 4817705, 4902655, 4968706) and the internally
  contradictory bedroom descriptions on 4837062 and 4902655. The first three
  floor differences are plus one, but 4968706 is plus two; do not apply a uniform
  building offset. Verify exact-unit identity, address association and numbering
  before a source projection. See the
  [full-description review](../analysis/chelsea-income-claim-review-2026-09-19.md).

- [ ] Resolve Lantern House 1704 / advertisement 4828991 bathroom composition.
  The fitted record has three full and zero half baths; its own description
  explicitly names a powder room and describes en-suite Jack-and-Jill bathrooms.
  Preserve the conflict until the number of distinct full bathrooms is supported;
  do not simply add a half bath to the existing full count. Review the related
  en-suite and shared-access evidence without counting one bathroom twice.
- [ ] Review 130 W17 / advertisement 3924616, fitted as three bedrooms and three
  full baths at a $4,500 historical initial ask. Its own sparse description does
  not establish those counts or justify a replacement; investigate structured
  records, exact-advertisement layout evidence and historical price scope.
  The large negative residual is a review signal, not a correction rule.
- [ ] Resolve the price basis for 3Eleven / advertisement 4982803. The analytical
  initial ask is $9,400, while the later captured description says two months
  free on a 14-month lease and "Net Rent Shown" without an explicit gross quote.
  Check the historical price event and concession timing before converting or
  excluding it; do not assume later prose applies to the initial ask.
  The three cases and their exact capture witnesses are retained in
  `data/model/chelsea-expanded-spline-floor-movement-review-inputs-20260919`.
- [ ] Review the dated offer scope for 406 W25 1FE / advertisement 1371705:
  the description offers furnished/unfurnished and short/long-term options.
  Establish which package the $2,850 historical initial ask represents before
  excluding or adjusting it. See the
  [complete movement review](../analysis/chelsea-expanded-spline-floor-movement-review-2026-09-19.md).
