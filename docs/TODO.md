# Project to-do list

The [project intent](project-intent.md) defines the NYC-wide objective. The
[research pipeline](data/research-pipeline.md) provides the tested baseline path.
The active goal is to refine **Chelsea first**, before expanding geography.
Latest evidence and reproducible artifacts are recorded in the
[September 18 amenity experiment](analysis/chelsea-amenities-2026-09-18.md) and
[recovery/validation follow-up](analysis/chelsea-recovery-ablation-2026-09-18.md).

Immediate pilot work:

**Priority clarification, September 18:** the product loop is scrape → transform
→ fit → analyze. Factor contributions, fitted residuals and apartment-specific
counterfactuals take priority over forecasting or unfamiliar-building performance.
The model should include the latest accepted listing evidence before analysis.

**Current research round:** Bayesian coefficient uncertainty and flexible bathroom
construction, alongside source review of large building/unit effects. These are
research directions rather than a fixed feature checklist.

**Main-model clarification:** use the PyMC Bayesian model for the main analysis.
Improve fit speed through compiled sampling and exact graph operations; do not
serve a surrogate regression in its place. The main contribution/residual page
and fitting/analysis CLI now use the verified PyMC posterior.

**Specification review, September 18:** listed floor should use separate threshold
increments, `sum_k beta_k * 1(listed_floor > k)`, like bedrooms. Every factor and
representation must justify its role; the earlier feature examples are directions,
not a checklist to maximize. Audit source meaning, independent unit/building
support, overlap, confounding with group offsets, prior sensitivity, residual
patterns, and whether a simpler representation suffices.

**Queued research directions, September 18:**

- [ ] Infer advertised floor from unit labels, beginning with patterns such as
  `3D → 3`. Preserve the original label, inference rule and provenance separately
  from explicit source-floor claims. Validate building-specific numbering and
  conflicts; investigate ambiguous labels, penthouses, duplexes and skipped
  labels rather than treating the prefix as physical height.
  The [first source-bound label audit](analysis/chelsea-unit-label-floor-2026-09-18.md)
  proposes candidates for 11,722 units; 29 of 164 units with comparable explicit
  claims have a disagreement. Building-specific numbering and source-reference
  errors need review before analytical integration.
- [ ] Test elevator × the selected floor metric, including threshold interactions
  if floor increments are retained. Report support on both sides of each
  interaction, posterior uncertainty and sensitivity to floor inference. The
  current model has an elevator main effect; its physical-floor interaction is
  inactive because physical height is unobserved.
  The [interaction support audit](analysis/chelsea-floor-elevator-support-2026-09-18.md)
  finds two-sided elevator/walk-up support only at explicit-floor thresholds
  2–5; 13 higher-floor products duplicate main-effect columns. Forty-three
  buildings have conflicting/changing elevator claims requiring source review.
- [ ] Extract and compare laundry levels: explicitly no laundry, in building,
  on floor and in unit, with unreported availability kept unknown. Review
  coexisting facilities and restrictions before choosing category rules. The
  accepted Bayesian model currently estimates only in-building versus in-unit
  laundry plus a separate unknown indicator; neither explicit no-laundry nor
  on-floor laundry has been separately tested. Its existing in-unit versus
  in-building association is +2.399% (95% credible interval +2.051% to +2.741%),
  stable under the tested stronger feature prior; see the
  [category sensitivity analysis](analysis/chelsea-bayesian-category-sensitivity-2026-09-18.md).
  The [location evidence review](analysis/chelsea-laundry-location-2026-09-18.md)
  finds each/every-floor wording for 140 units in 13 buildings and reviews 36
  cases, including coexisting facilities, hallway scope and hookup-only wording.
  A revised measurement policy and matched four-level fit remain pending.
- [ ] Create and test address-based spatial features: raw or centered latitude/
  longitude, interpretable relative-location measures and street indicators.
  Validate geocoding/address identity, compare simple representations, and assess
  overlap and confounding with building effects. Judge their value for factor
  contributions and residual structure in the fitted buildings, rather than
  prioritizing prediction for unseen buildings. Use Oxylabs for any new scraping.
  The [current spatial audit](analysis/chelsea-current-spatial-features-2026-09-18.md)
  binds coordinates for 172 listings / 85 buildings and constructs centered
  coordinate and 22 street-label candidates; historical coverage and matched
  Bayesian spatial experiments remain pending.

- [ ] Replace the linear listed-floor term in a versioned Bayesian specification,
  preserving unknown floors and the distinction from physical height. Inspect
  threshold support and gaps, and compare joint floor contrasts and residuals on
  the same cohort before promoting the fit.
  The [isolated increment design](model/listed-floor-increment-design.md) is
  implemented with a versioned runner, reports and reconstruction checks;
  main-model promotion remains pending. The full floor fit is running with durable
  sampling and bounded reporting after successful source-report recovery.
- [ ] Complete a skeptical parameter audit and matched Bayesian simplification
  experiments. Include nuisance reporting indicators, group effects and priors,
  time/season bases and likelihood choices, as well as apartment amenities. A
  narrow interval or a nonzero coefficient alone does not justify inclusion.
  The [initial support audit and decision protocol](analysis/chelsea-bayesian-parameter-audit-2026-09-18.md)
  are complete; matched simplification fits remain to be done.

- [x] Rank all building/unit effects and review both tails against source text.
  The [group audit](analysis/chelsea-group-effects-2026-09-18.md) identifies shared
  bathrooms, basement units, flexible/railroad bedrooms and bundled luxury features.
- [x] Recover explicit full/half counts without deriving them from the scalar;
  review unusual counts and en-suite wording, and vary research seed phrases.
  The [bathroom audit](analysis/chelsea-bathroom-evidence-2026-09-18.md) retains
  52,712 observations, flags source contradictions, and documents new hypotheses.
- [x] Complete a Bayesian fit with passing parameter/derived uncertainty diagnostics
  on the full reviewed current cohort; report joint bathroom increments and
  bedroom-relative shortfall with source support. See the [first converged results](analysis/chelsea-bayesian-bathrooms-2026-09-18.md).
- [x] Complete a same-cohort stronger-feature-prior comparison with both diagnostic
  gates passing. [Common bathroom increments are stable](analysis/chelsea-bayesian-prior-sensitivity-2026-09-18.md),
  while the second-half-bath estimate depends strongly on the prior (only two ads).
- [ ] Test group-prior sensitivity and bedroom-dependent residual dispersion;
  the shared-noise fit misses larger-apartment residual tails. The bedroom-scale
  [first bedroom-scale experiment](analysis/chelsea-bayesian-residual-scale-2026-09-18.md)
  finished but failed the parameter convergence gate. Its equivalent centered
  retry passes both gates and improves larger-bedroom dispersion checks, while
  tail mismatch remains. Group-prior comparisons and selection remain pending.
- [x] Derive interpretable joint category comparisons and compare feature priors.
  [Laundry and common doorman contrasts are stable](analysis/chelsea-bayesian-category-sensitivity-2026-09-18.md)
  under this prior change; sparse HVAC categories remain weakly supported.
- [ ] Separate staffed attendance from remote/intercom access where both may
  coexist, and adjudicate the named identity conflict before a measurement
  sensitivity fit. The [doorman overlap review](analysis/chelsea-doorman-overlap-2026-09-18.md)
  covers eight ads and verifies no physical service transition in the two shared units.
  The [measurement follow-up](analysis/chelsea-doorman-measurement-policy-2026-09-18.md)
  reviews all 13 virtual-category ads in the overlap buildings and drafts separate
  service axes; three identity/location conflicts remain unresolved.
- [x] Apply separately reviewed nonresidential/location-conflict decisions and
  count-conflict masks. The [source revision](analysis/chelsea-bayesian-source-revision-2026-09-18.md)
  quarantines seven advertisements and masks five compositions, retaining 52,704
  observations and all 13 refreshed listings. Original prices and counts remain.
- [x] Refit that source revision and compare contributions. Preserve uncertain
  prices, physical change dates and unit aliases until supported by evidence.
  The first 52,704-row shared-scale refit failed the parameter gate at R-hat
  1.01039. The 4,000-warmup/6,000-retained retry was killed for memory exhaustion
  after sampling and has no posterior checkpoint. Validated disk storage now
  supports an unchanged retry; neither previous attempt supplies accepted intervals.
  The disk retry and report-only recovery now pass both diagnostic gates. The
  matched source comparison changes each of the 13 current fitted rents by less
  than $4. A [joint-posterior movement review](analysis/chelsea-source-movement-review-2026-09-18.md)
  decomposes the three largest distinct-unit changes, including the weakly
  supported single-observation townhouse building effect.
- [x] Expose accepted Bayesian bathroom/category intervals, prior comparisons and
  all 13 current residuals in the separate [research page](model/bayesian-research-page.md).
  The page verifies source/report bindings and withholds failed experiments.
- [x] Use the accepted PyMC posterior in the main contribution/residual page and
  `fit-pricing` / `analyze-apartment` CLI. Preserve previous robust workflows
  with explicit legacy labels; verify all 13 current fitted intervals and joint
  counterfactuals against saved posterior draws.
- [ ] Connect selected Bayesian current-fit residuals to preference/frontier
  scoring. The main page uses PyMC; `score-apartments` still names the documented
  legacy robust search path and must be migrated explicitly.
- [ ] Fold the ordered saved-design loader into the next model version after
  same-code prior experiments finish; do not use the original unsafe reload for
  apartment-level reconstruction. The v2 checker and full-cohort parity proof are complete.
- [x] Convert reviewed shared-bath access and nonresidential findings into explicit
  versioned research decisions. The [bathroom research revision](analysis/chelsea-bathroom-research-revision-2026-09-18.md)
  quarantines one office advertisement, masks composition for 17 shared-access
  advertisements and accepts two corroborated multiple-half layouts. All surviving
  reported counts and earlier reviewed fits remain preserved.
- [ ] Test contribution sensitivity to these source decisions using the revised
  52,711-row research projection; all 13 refreshed observations remain included.
- [ ] Validate en-suite access separately from fixture composition. Unmentioned
  access remains unknown; a phrase-positive sample cannot establish recall.
  The [four-plan visual pilot](analysis/chelsea-floorplan-visual-review-2026-09-18.md)
  distinguishes assigned bathrooms from attached access and finds a missing
  powder room. A [second four-plan review](analysis/chelsea-floorplan-second-review-2026-09-18.md)
  adds an office/hall access distinction; all four show one suite bathroom.
  Neither batch yet establishes a matched en-suite count comparison.

- [x] Fit refreshed capture-time evidence before analysis; the pilot now includes
  13 fresh ACTIVE captures alongside 53,218 historical unit-months, with current
  in-sample residuals, building/unit contributions and training inclusion visible.
- [x] Build a residual review queue and inspect the first ten cases against 18
  verified archived responses. The [source audit](analysis/chelsea-residual-review-2026-09-18.md)
  found rapid price corrections, commercial spaces, a location/net-effective
  conflict, unresolved prices and a plausible duplex/ceiling/light feature gap.
- [x] Apply a first versioned price/scope review across the cohort, refit, and
  compare residuals and feature contrasts on identical retained rows. The
  [reviewed-cohort result](analysis/chelsea-reviewed-cohort-2026-09-18.md) quarantines
  503 unresolved net-effective observations, ten reviewed commercial offers and
  two transient initial asks, preserving every source price. Typical fitted values
  change only $2.36; the cohort definition improves without a large accuracy gain.
- [ ] Continue review of unresolved price histories, mixed-use listings and gross/
  net terms. The first decision bundle is a bounded policy version, not proof
  that the remaining cohort has no source or scope problems.
  The [net-rent wording follow-up](analysis/chelsea-net-rent-wording-followup-2026-09-18.md)
  finds 96 retained observations with reversed-order net-price statements absent
  from the first screen. Adjudicate their event-time price basis before a new
  source overlay; the broader 2,429-observation keyword queue also includes
  descriptions that do not claim the advertised price is net.
- [x] Screen the fitted cohort for advertised ceiling measurements, levels,
  floor-through layouts and skylights, preserving exact text and capture scope.
  The [interior audit](analysis/chelsea-interior-evidence-2026-09-18.md) finds 7,055
  candidate observations and supports four further reviewed scope quarantines.
  The latest fit has 52,712 rows; matched fitted values change a median of $0.32.
- [x] Adjudicate a development sample of interior evidence and run matched
  reporting-versus-value fits under three group penalties. The [interior model
  experiment](analysis/chelsea-interior-model-2026-09-18.md) completed nine fits;
  magnitudes add little beyond reporting, and level counts have sparse support.
- [ ] Refine feature-specific interior scope separately from renovation status,
  validate beyond the development sample, and examine cross-advertisement height
  changes before interpreting them as physical changes.
- [x] Audit private/shared outdoor fields and area wording; compare structured
  versus text-corroborated type contributions across 18 matched fits. The
  [outdoor experiment](analysis/chelsea-outdoor-model-2026-09-18.md) finds material
  source-policy sensitivity and records six changed-residual source reviews.
- [ ] Improve outdoor measurement: distinguish unit access, explicit private
  claims, shared facilities and views; handle coexisting private/shared types
  and confidence separately. Validate beyond development samples. Outdoor area
  remains excluded pending access-scope and measurement rules.
- [x] Publish occurrence-level outdoor claims and evaluate on 40 development
  units plus 25 untouched units. The [scope follow-up](analysis/chelsea-outdoor-scope-2026-09-18.md)
  finds improved development agreement but weak independent access coverage;
  the measurements remain review evidence, without another model refit.
- [ ] Resolve outdoor subject, access, exclusivity and temporary availability
  jointly before model promotion. Distinguish area exclusions from denied access,
  and future-tenant wording from planned construction. Keep unknown effective
  dates rather than dating physical changes from archive capture times.
- [ ] Audit unit-private elevator access and other luxury facilities suggested
  by changed residuals, preserving planned/completed status and source dates.
- [x] Expose supported apartment-specific joint contrasts in the
  [analysis review page](model/analysis-review-page.md), recomputing interactions,
  showing what is held fixed, and withholding unsupported or reporting-only values.
- [x] Provide factor support, contributions, residual history and archived source
  text in the main analysis review. Keep model uncertainty and earlier contrast
  stability studies explicit rather than presenting a forecast score as the goal.
- [ ] Integrate source-review decision recording and linked contrast-stability
  artifacts into the read-only analysis page; current correction workflows remain
  separate and experimental encodings are not promoted automatically.

- [x] Scale the verified Flight-description recovery from its 10-page audit to
  the 27,240 affected captures, preserving body hashes, interpretation clocks,
  original parsed values and a new derived version. Raw source datasets stay immutable.
- [x] Review stratified source-text samples of existing and recovered descriptions;
  fix definite scope/negation errors with regression cases. Agent-labeled samples
  are not human ground truth or population accuracy estimates.
- [x] Compare the enriched model with missingness-only controls. Known-only centered
  contrasts prevent categorical ridge penalties from confounding the comparison;
  actual values improve error beyond reporting patterns on all evaluated folds.
- [x] Run individual-feature-block ablations to identify which known-value families
  explain the additional benefit and which rely mostly on reporting patterns.
  All 36 fits completed; elevator/floor information provides most of the improvement.
  See the [feature-family results](analysis/chelsea-feature-blocks-2026-09-18.md).
- [x] Expand the amenity comparison to all five building folds, four earlier-year
  holdouts, and crossed unseen-building/future-time tests (42 converged fits).
- [x] Improve the large 2021 errors separately from amenity estimation; evaluate
  rolling short-horizon updates appropriate for apartment search alongside annual
  forecasts and report staleness explicitly. All 72 monthly fits completed;
  pooled median error falls from 9.82% to 7.97%, with 2021 falling from 18.84% to
  10.44%. See the [monthly results](analysis/chelsea-monthly-validation-2026-09-18.md).
- [ ] Optional/deferred: validate prediction uncertainty for unfamiliar buildings. Sequential pooled
  fallback bands fail: adjusted nominal 95% coverage is only 68.39% over 193
  new-building rows. Do not serve those bands as calibrated; preserve an explicit
  unsupported-uncertainty state until building-transfer calibration is validated.
  A 420-fit protocol was prepared but **no fits launched** before the user clarified
  that this is secondary to factor, residual and counterfactual analysis.
- [x] Estimate conditional contrast sampling stability and sensitivity to building
  and unit shrinkage: 20 specification fits, 200 building-resampling refits, and
  tighter numerical checks completed. Laundry's positive direction survives;
  doorman remains unstable. These do not establish causal premiums or calibrated
  population intervals. See [stability results](analysis/chelsea-amenity-stability-2026-09-18.md).

- [ ] Expand the explicit Chelsea/West Chelsea discovery profile to configured NYC
  neighborhoods, with neighborhood-specific coverage audits and bounded Oxylabs
  collection budgets **after the pilot approach is satisfactory**. Building-scoped
  collection already accepts NYC building URLs.
- [x] Locate the completed `chelsea-granular-20260917-canonical-url-v1` dataset
  and connect its canonical memberships to corrected historical analytical rows.
  The older `-canonical-units` directory was not the latest completed artifact.
- [ ] Audit/migrate any desired legacy review decisions explicitly. The canonical
  pilot's fresh-start record intentionally did not import the older review state;
  do not silently apply it to differently identified data.
- [ ] Gather repeat observations across seasons, validate source-backed floor and
  amenity extraction, and add dated NYC public-record joins before estimating
  citywide marginal premiums. Track unknowns and ambiguous matches explicitly.
- [ ] Add rolling temporal validation, independent unseen-unit/building holdouts,
  and calibrated uncertainty to the baseline; compare with the retained Bayesian
  models using the same corrected analytical inputs. Robust temporal and building
  experiments are complete; new-building calibration and matched Bayesian comparison
  remain unfinished.
- [x] Connect the robust model to canonical capture-time candidate selection,
  freshness checks and the preference frontier. The [serving example](analysis/chelsea-serving-example-2026-09-18.md)
  refits 53,218 unit-months and scores 14 units under illustrative budget/preferences;
  stale models, inactive advertisement captures and identity conflicts stay explicit.
- [x] Refresh candidate evidence through bounded Oxylabs collection. All 23 chosen
  advertisements refreshed successfully: 13 remain source-reported ACTIVE, ten
  changed to excluded statuses, and one ACTIVE ask fell by $450. The fresh $6,000
  example selects seven units. See the [refresh results](analysis/chelsea-candidate-refresh-2026-09-18.md).
- [ ] Establish current Chelsea discovery coverage and repeat refresh operations.
  The bounded pass only revisited previously eligible recent advertisements; it
  did not discover new listings or refresh the 271 older ACTIVE advertisements.
  The [pagination audit](data/chelsea-current-discovery-audit-2026-09-18.md) finds
  repeated organic listings in four fresh Oxylabs pages; a validated next-link
  chain alone cannot establish complete inventory. An offline source-bound parser
  and bounded collection plan are ready.
- [ ] Add a renter-facing preference interface on top of the verified scoring API.
- [ ] Optional sensitivity: compare fitted residuals with leave-advertisement-out
  results where useful. Same-advertisement inclusion is expected in the main
  refit-before-analysis workflow, not a reason to suppress its in-sample residual.

- [ ] Review attribute shifts in a separate pass after unit identity merges. Compare bathrooms, bedrooms, square footage, layout, and other attributes across each unit's listings and captures. Distinguish real changes or renovations from source errors, extraction errors, measurement differences, and mistaken identity merges. Keep unresolved differences explicit; preserve observed values and collection dates, and record any supported corrections or effective-time assertions separately. Do not require attribute agreement to complete an otherwise justified identity merge.

- [ ] Detect listing descriptions such as “floor through”, “floor-through”, “floor thru”, and “floor-thru” as an observed unit-layout type. Explore using this as evidence of both street and courtyard/rear exposure, while keeping that inference separate from explicitly stated exposure and allowing unknowns or exceptions. Preserve the exact source wording and capture scope; do not apply a current layout claim to all historical prices.

- [ ] Explore using posted photos to identify listings that may represent the same physical unit. Treat exact or visually similar photos as supporting evidence, not proof: brokers sometimes reuse photos for different units in the same building column. Combine photo evidence with building, unit label, floor, layout, and dates; retain uncertain matches and source observations rather than automatically merging records. Evaluate false matches on known distinct units in the same column before using photo-based identity links in modeling.

- [ ] Track the brokerage firm and individual broker(s) associated with each listing observation. Preserve the source names and available identifiers/contact or profile references, including multiple brokers where present. Keep collection timestamps and source evidence so changes in representation remain visible; do not backfill current representation onto historical price events. Inspect archived payloads first and extract available information without a new scrape. Support auditable corrections through the separate review overlay.

- [x] Execute and replay a bounded Oxylabs discovery pass: 28 new requests plus
  four reused captures; 213 in-scope advertisement candidates preserved. The
  [coverage review](analysis/chelsea-rental-discovery-2026-09-18.md) documents
  repeated regular cards, incomplete coverage and the detail-review queue.
- [x] Add a [bounded discovery detail collector](data/discovery-detail-refresh.md)
  with source-bound queue verification, explicit unresolved unit identities,
  durable Oxylabs capture/replay and no product filtering before collection.
  Ninety-two focused tests pass; the one-target live preflight passed.
- [x] Finish and review the 213-target discovery detail run: 213 submissions,
  no retries, 204 canonical candidates and 168 eligible units. Network-disabled
  replay passed. The [nine-identity review](analysis/chelsea-discovery-detail-identities-2026-09-18.md)
  finds one historical-unit candidate, one conflicting alias case and seven
  unmatched cases; none has been automatically merged.
- [x] Build and replay the [current-cohort refresh](data/current-cohort-refresh.md):
  52,691 historical rows preserved exactly, 172 current rows, four earlier fresh
  captures retained and nine replaced. Failed refreshes cannot revive older ads.
- [ ] Review the new current source evidence, apply any source-bound corrections,
  and fit the refreshed 52,863-row cohort with PyMC. Unresolved unit identities
  remain separate; no automatic main-model promotion.
  The [172-row source audit](analysis/chelsea-current-source-review-2026-09-18.md)
  identifies one old description price, 14 approval-scope net-effective mentions,
  optional furnishings and a residentially described art-gallery scope case.
  The applied current review now preserves all 172 current rows, masks two
  description/structured bathroom conflicts and records seven residual-review
  cases. The reviewed 52,863-row input is ready; Bayesian loader integration and
  the expanded-cohort fit remain pending while the matched floor fit runs.
- [ ] Complete full-model validation of disk-backed nutpie traces and reporting.
  The longer source refit exceeded memory during result extraction; preserve
  exact chain/draw coordinates and all retained draws, and test against the
  current in-memory sampler. Actual parity and full-sized synthetic export checks
  pass. The source posterior and both diagnostic gates are complete; report-only
  recovery passed at 5.3 GiB peak RSS after a separate reporting OOM. The integrated
  bounded reporter is now being exercised by the full floor fit.

- [x] Audit the actual structured apartment-floor fields, independent of internal
  naming. The [canonical-field audit](analysis/chelsea-canonical-floor-field-2026-09-18.md)
  finds no structured floor key in the 71,906 relevant captured own-listing
  payloads; current known values use the existing alias/description evidence.
- [ ] Review broader apartment-floor description claims with varied phrase seeds
  and building-diverse examples. Shared amenities and tower-wide floor ranges
  must not become unit floors. The broad screen is a review queue, not new data.
