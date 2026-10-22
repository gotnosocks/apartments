# Canonical candidates (merge order)

1. nb-lpd-clustered — New-building log score and lot-clustered paired SEs with a same-target guard (plus a free chain-split A/A) (measurement change (code, then free back-fill on thelio); p=0.65; cost: Modal $0 on thelio (optionally about $0.65-0.80 to rescore 5-6 fits on Modal at $0.13 each; after that about +$0.05-0.15 per future fit for the lpd). Oxylabs $0)
2. explain-screen-v2 — Explanation screen v2: score candidate facts in points of new-building miss against the whole static building part, with lot and block folds and a ceiling for data already held (measurement change; p=0.5; cost: Modal $0 (thelio, standing free-check approval); Oxylabs $0; other $0. Effort: Modeling, about 1.5 days of code plus a reviewed PR, and 2-4 h of thelio compute )
3. quality-reads — LLM quality grades from the ads' lead photos and description text: one costed sample screen, then a full run and one fit only for an arm that clears the bar (new data source (free counts, about $35-45 costed sample screen, gated full run and fit); p=0.35; cost: Modal $0 for the screen; about $2.1 per gated fit. Oxylabs $0 if images fetch directly as in the pilot (unverified). If they must go through Oxylabs: up to $4 f)
4. time-split — Time-split refit of C: as-of new-unit, seen-unit-forward and new-building coverage (measurement change (one Modal fit; free row count first); p=0.65; cost: Modal $1.6-2.6 (fit + PSIS-LOO + summary + calibration) + $0.13 holdout score. Oxylabs $0; other $0. Modeling: about 1 day of code, tests and a reviewed PR; 2-3)
5. walk-ar1 — Mean-reverting (AR(1)) building walk nesting C, gated by free walk-origin diagnostics; a building scale by PLUTO size is the alternative single fit (free check then fit (model term); p=0.38; cost: Modal about $2.1-2.2 (+$2 if the gate needs more draws). Oxylabs $0; other $0. Modeling: 2-3 h of free checks, 2-3 days of gibbs.py/model.py/newbuilding.py code)
6. mw-external — Midtown West as an unseen-area test of C, with a labels-redrawn (features-only) new-building rung, scored before any Midtown West fit (measurement change (code plus free scoring; rides the running crawl); p=0.45; cost: Modal $0 on thelio ($0.13-0.26 on Modal). Oxylabs $0 beyond the running, approved crawl (whose own cost is undocumented). Other $0. Modeling 1-1.5 days; Data im)
7. size-completion — Size completion: free check of GraphQL history-digest sizes, then one size fit (history sizes if real, otherwise the held predsize) (new data source / data fix (free check; about $0.3 of Oxylabs re-read only if real; then one fit); p=0.2; cost: Modal $0 for the checks; about $2.25 for the one fit. Oxylabs $0 for the check; about $0.25-0.6 for about 226 GETs (+ about $6 if building ids must be fetched),)
8. amenity-services — Building services from StreetEasy's coded amenity lists already archived (pool, concierge, garage, gym, roof deck): extract, fill as of each date, screen, fit only if it clears 5% (data fix (free extraction and screen; one fit only if gated); p=0.3; cost: Modal $0 for the extraction and screen; about $2.25 if it passes. Oxylabs $0; other $0. Data improvements about 1 day (extraction, as-of fill, feature set, test)
9. concession-rows — Keep coded-concession listings (2020+) with a coded months-free share instead of dropping them (data fix (free check, then a dataset rebuild and one fit); p=0.45; cost: Modal about $2 (one fit + new-building score with a pinned split; about $4 if a control refit replaces the pin). Oxylabs $0 (the pricing JSON is archived); othe)
10. wv-nta-step — West Village 2020-NTA 2022 step and drift in place of the held areatime rerun (free check then fit (feature set); p=0.65; cost: Modal about $2.1 (fit + $0.13 score). Oxylabs $0; other $0. About 0.5 day in features.py plus the 30-min check, then one fit; 1-2 days elapsed. Ben's go and his)
11. family-bedroom-curve — One family-market bedroom curve in place of the three bedroom-group curves, gated by a free information-arithmetic loss estimate validated on lognoise (free check then fit (model-term swap); p=0.45; cost: Modal about $2.1 (fit + $0.13 score), only if gated; the arithmetic and class split are $0 on thelio. Oxylabs $0; other $0. Modeling: about 4 h of free checks, )

# Dropped at merge
- calib-score-v2 (part): new-building lpd as an autoselect tie-break and incumbent guard: Violates project-intent.md:67-68: unseen-building performance is not a serving gate. Kept only as nb-lpd-clustered's flag, which holds an automatic switch for Ben to decide.
- photo-quality-screen (part): building grades averaged over all of a building's ads, including later ones: Leak: a later renovation would land on earlier rows as future information. Replaced in quality-reads by an as-of building mean over strictly earlier ads, as elevfill does.

# Merge notes
All 24 proposals survive in 11 candidates. None was dropped whole; only the two sub-parts listed above were cut. Ranking by rough EV per dollar and week: the two free instruments first, then the one plausible explanation lever, then the honest-uncertainty fits, then the cheap data checks, then the small fits.

Convergence across lenses:
(1) Three lenses (measurement, uncertainty, outside view) independently asked for a new-building log score plus building- or lot-clustered paired SEs and a same-target guard.
(2) Three (parsimony, uncertainty, outside view) found the 2010 walk origin and want the free year breakdown before any walk fit.
(3) Three (data, explanation, outside view) named quality data, from photos or ad text, as the only lever with a path to the ~9% of building variance a 0.5 pp new-building cut needs.
(4) Every lens rejected the held queue as it stands: the areatime rerun (label crutch; the WV step replaces it), retail/noise/trees/crime/hpd (1.4-2.4% screen shares, expected ties), petsfill (building-constant fills), and lister (weak free check; belongs on the time split).
(5) Every lens that discussed Brooklyn would hold its restart until Midtown West is scored.

No candidate's median prediction cuts the new-building miss by 0.5 pp; only quality-reads has a plausible path. With the stopping rule, that argues for data over model terms.

Open disagreements:
- AR(1) walk vs anchoring at entry vs a building scale by size for the over-width; the free diagnostics decide.
- Photos vs text first.
- As-of new-unit coverage: 68/89 (measurement) vs 76/93 (uncertainty).
- Midtown West miss: 13% vs 15%.
- predsize timing: one lens for running it now, five against.
- Amenity gate: 1.5% (explanation) vs 5% (outside view).
- Whether explained-share v2 is worth building: explanation for, measurement against; the offset and ceiling parts are uncontested.

Merges made to meet the cap, beyond true duplicates:
- bscale-units folded into walk-ar1 as the alternative branch picked by the same free diagnostics.
- Ad-text grades folded into the photo screen as a second arm on the same sampled ads.
- The noise-arithmetic gate folded into the bedroom-curve swap as its kill rule.
- Clustered PSIS-LOO SEs folded into the new-building log score, as calib-score-v2 already did.

Where a proposal bundled several fits, the extra fits are in depends_on: rho fixed at the variogram half-life, the identity-leg unit-paths fit, the second quality arm, separable noise.
