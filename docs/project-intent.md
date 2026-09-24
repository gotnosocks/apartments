# NYC rental search and pricing research

The project helps an individual find rental apartments in New York City by
separating market asking prices from that individual's preferences. Its intended
outputs are interpretable price comparisons, attribute tradeoffs in dollars, and
an efficient frontier of available homes under explicit willingness to pay.
StreetEasy is the primary listing source; NYC public records can supply additional
building evidence. Chelsea is the existing pilot, not the geographic definition
of the project.

## Data contract

1. **Collection.** All listing scraping uses Oxylabs. Keep the requested URL,
   provider response metadata with secrets removed, response body, fetch time,
   status, parser version, discovery scope, and coverage failures. Retries and
   subsequent refreshes add observations; neither replaces old evidence.
2. **Interpretation.** Parsed captures are reproducible interpretations of raw
   responses. A listing episode, an advertised unit label, a canonical unit URL,
   a physical apartment, a building, and a tax lot are distinct identities.
   Conflicting identities remain unresolved until evidence supports a mapping.
3. **Corrections.** Human changes are append-only overlays with author, reason,
   evidence, target, recording time, and effective interval. Corrections never
   edit raw pages. Retraction and revision preserve earlier ledger states.
4. **Analytical projection.** Explicit input versions, cutoffs, code, and patches
   determine the output. Equal inputs produce equal records and content hashes;
   retrying a completed publication must verify and reuse it. Partial or changed
   outputs must never masquerade as complete datasets.
5. **Model and search.** Fit only the selected analytical dataset. Save the
   training encoding, parameters, validation, input hashes, and exclusions.
   Market coefficients and the user's willingness to pay are separate inputs.

## Attribute history

Keep **effective time** (when an assertion applies) separate from **knowledge
time** (when the evidence or correction became available). A correction entered
today can assert that unit 1D was a studio on `[date0, date1)` and a one-bedroom
on `[date1, present)`. A reconstruction made before that correction must exclude
it. An observed difference does not establish an exact renovation date: it may
also indicate marketing, a source error, a parser error, or an identity mismatch.

Carry-forward from an observation is a documented assumption, not a verified
validity interval. Never attach a current apartment's features to every historical
price on its page. Prices from an inactive advertisement are historical asks,
not evidence of current availability. Asking rent, net effective rent,
concessions, furnished rent, and signed lease rent are different outcomes.

Unknown is distinct from false. Missing amenities must not silently become
absent amenities. Preserve contradictory evidence and exclusions for inspection.

## Price model

The intended operating loop is **scrape → transform → fit → analyze**. Fit the
latest accepted evidence before analyzing apartments, including their buildings'
current listings. The main direction is feature contributions and residual
analysis. These use cases illustrate that direction, rather than a fixed product
checklist:

- **Factor analysis:** supported marginal associations between features and
  advertised price, with reference values, interactions and identification limits.
- **Residual analysis:** a particular apartment's advertised price versus its
  fitted value. In-sample residuals are legitimate diagnostics; show how the
  apartment's own observations and building/unit effects enter the fit.
- **Counterfactual analysis:** the fitted value of the same apartment under an
  explicit change, such as one additional bedroom, holding the other specified
  attributes and group effects fixed and recomputing all interactions.

Straightforward forecasting and transfer to unseen buildings are secondary.
Unseen-building predictive performance is not a gate for the main workflow.
Validation should primarily assess extraction quality, feature support,
identification, coefficient/contrast stability, sensitivity to group effects,
residual structure and reproducibility. Do not force freshly analyzed listings
out of the fit merely to describe their residuals as out-of-sample predictions.

Use large residuals to drive modeling iterations: inspect the underlying listing
and comparable observations for omitted features, incorrect extraction, identity
or timing problems, and unusual price terms. A large residual is a review signal,
not proof of a data error or a bargain. Preserve review decisions and source
evidence; correct supported errors through overlays, or add a feature when the
evidence supports a recurring mechanism. Refit and compare residual structure
and feature contributions, including units beyond the motivating review cases.

The primary estimand is advertised monthly asking rent, conditional on available
evidence. Feature families include building/location; bedrooms, bathrooms, and
area; advertised floor and physical floors above ground; street/courtyard views;
north/east/south/west windows; laundry, doorman, elevator, HVAC, and pet rules;
floor × elevator interactions; calendar seasonality; and long-run price trend.
Feature extraction must retain its evidence and avoid interpreting a unit number
as a reliable floor. A skipped floor label needs a building-specific mapping.

The main model is hierarchical Bayesian with an exact joint posterior. The
implementation is free (PyMC NUTS, a custom JAX sampler, or another exact method),
but convergence must be checked independently, e.g. against a well-mixed reference
sampler on the same model, plus R-hat and ESS over every group effect. Use efficient
tensor operations and exact reuse of identical feature rows to reduce fit time.
Preserve the actual likelihood and joint posterior; do not substitute a robust
regression or another surrogate for the main model.
Retained non-Bayesian fits are historical comparisons. Report posterior feature
and group uncertainty and joint contrasts in dollars and percentages with their
reference apartment and date.
Effects are conditional associations, not causal renovation returns. Building
effects can absorb building-level amenities; correlated or rarely observed
features do not support separately identified premiums just because a coefficient
can be computed.

Use temporal and grouped holdouts as secondary diagnostics of overfitting and
transferable associations, not as the primary product objective. For any reported
holdout comparison, keep imputation, scaling, category selection and tuning inside
its training partition. Separate retrospective reconstruction from forecasting
with information actually known at the historical cutoff.
Repeated crawling must not weight a home according to scrape frequency.
Publish missingness and feature variation alongside coefficients. Unobserved
amenities and short observation windows must remain visible limitations.

## Preference search

Users specify monthly dollar values for amenities or attribute increments and
hard constraints such as budget. A candidate's preference surplus is the sum of
those values minus asking rent. Its market residual is a separate comparison
with predicted rent. Keep the Pareto frontier in price and valued attributes;
do not assume the highest predicted rent is the best apartment. Negative
preferences reverse the desired direction. Unknown valued attributes require an
explicit policy, and equally good duplicates must be treated consistently.

Candidate sets must identify their observation cutoff and source availability.
A saved September snapshot is not a list of apartments available today.

## Delivery and research gates

- Preserve and test the current raw archive, review ledger, and canonical-unit
  work. Keep older model results labeled by their exact assumptions.
- Establish a tested capture → overlay → analytical → model → preference path,
  including a dated studio-to-one-bedroom correction and deterministic reruns.
- Grow repeated, current observations across NYC boroughs and neighborhoods
  under bounded Oxylabs budgets; publish coverage by place, date, and source.
- Audit attribute extraction and unit identity before interpreting amenity
  premiums. Add dated public-record joins by supported building/lot identifiers.
- Establish multi-season coverage, feature support, uncertainty and sensitivity
  analysis before presenting citywide marginal-price conclusions. Unseen-building
  validation is optional supporting evidence rather than a main-workflow gate.

The current archive's size and historical price depth alone do not establish
NYC-wide representativeness or historical amenity coverage. Those are measured
research requirements, not assumptions granted by this project description.
