# Predictions: C on the West Coast wing rule (2026-10-14)

I wrote these before the fit, as the coordinator's brief of 18:38Z on 2026-10-14 asks after Ben
approved the wing rule. If the fit passes, it is the next served model.

## The complex

The West Coast (95 Horatio Street, BBL 1006430001) is a single complex filling the block between
West, Horatio, Washington and Gansevoort Streets. The Landmarks Preservation Commission's 2003
Gansevoort Market report describes it as nine Manhattan Refrigerating Co. warehouses built 1897 to
1935, converted to apartments in 1980 to 82, with two warehouses at 97 to 103 Horatio joined in
1984. StreetEasy lists nearly all of it on the page the-west-coast, plus 8 rows on a
97-horatio-street-new_york page.

Its unit labels follow two schemes. Three-digit labels (620) run over floors 1 to 7, and
floor-and-letter labels (9L) run over floors 2 to 10. Ben's floor plans put 620 on West Street and
9L at the corner of Washington and Gansevoort, which fits the report: the West Street and Horatio
warehouses have 6 or 7 stories, and the Washington Street end has 9. As one building, the
complex failed the gate (group R-hat 1.283 on the latest-ask refit `...-rows-bcaac064-...`).
Under `tune-westcoast-split-v1`, with the schemes as two buildings, it passed with a max group
R-hat of 1.026.

## The fit

C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` on `nb8-nostuy-v1`,
or its twin with the wing in the registry, row split) with C's sampler settings, on master's rules
at launch. Against the split C fit
(`...-rows-f469edaa-...-tune-westcoast-split-v1`), these rules differ:

- `building-joins-v1` (#769) folds the 97 Horatio page's 8 rows into the-west-coast.
- The wing rule from Data improvements (`west-coast-wings-v1`) replaces the tune rule. It moves three-digit rows to
  the-west-coast-west-wing, a registry entry with the complex's lot, BIN 1012154 and coordinates.
  The grouping matches the split C apart from the 8 folded rows. The three-digit wing now gets
  the complex's footprint and facade features instead of those of BIN 1012155, the 1984 section.
- `latest-ask-v3`, `quarantine-v14` and `unit-labels-v16` replace v2, v13 and v15.

The full list at the time of writing is `baths-ad-v3`, `bedrooms-ad-v3`, `building-joins-v1`,
`fields-review-v3`, `latest-ask-v3`, `quarantine-v14`, `unit-labels-v16`, `unit-reviews-v1`,
`unit-splits-v4` and the wing rule, `west-coast-wings-v1`.

The fit is priced at the latest ask, like the split C. I compare it with the
served C, which is priced at the first ask, on the latest ask over the held-out rows both share
(`rentfrontier.finalask`). PSIS-LOO can't pair across prices, and it can't pair with the split C
either, since the quarantine and label rules change rows.

The split C's fit took 1,653 s. `cap.py --check-launch` must pass the 3,600 s cap before launch.
The summary bundle now runs on thelio (#761), so the container no longer spends 1,200 s on it.

## Predictions

| Quantity | Prediction | Basis |
|---|---|---|
| Gate | Passes, 80% likely; max group R-hat under 1.05 | split C 1.026; the wings are unchanged |
| Fit time, cost | 1,600 to 2,300 s fitting, $1.30 to $1.90 | split C 1,653 s; no summary in the container |
| Held-out median miss against the latest ask | 3.65 to 3.80% | split C 3.73%, served C 4.02% |
| Held-out 80% / 95% coverage | 79.0 to 80.0 / 94.6 to 95.2 | split C 79.4 / 94.9, served C 76.8 / 93.6 |
| New-building score: miss | 11.8 to 12.3% | split C 12.0% |
| New-building 80% / 95% coverage | 90.0 to 90.9 / 97.9 to 98.4 | split C 90.4 / 98.1 |
| Serve test: no worse than the served C on miss and coverage against the latest ask | Passes, 85% likely | split C beat it by 0.29 pp and 2.6 / 1.3 points |

If it passes the gate and the serve test, the thelio summary unit builds its bundle and
calibration, and I serve it with `autoselect-publish` once the site shows both wing names as The
West Coast.

## Follow-up after the refit

C uses PLUTO's lot-level year built (`building era=...`) and floor count (`log_numfloors`). Both
wings take the lot's values, and so they get the same era and floor count, which fit the Washington
Street end better than the older West Street warehouses. Per-wing values from the LPC report
would correct that for one complex. I'll write it up as a separate proposal and not hold this fit
for it.
