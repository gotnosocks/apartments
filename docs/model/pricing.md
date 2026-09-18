# Interpretable asking-rent baseline

`apartments.pricing` fits an auditable ridge-regularized log-linear model to the
flat, contemporary observations from `apartments.analytical`. It uses Python's
standard library and sparse coordinate descent, so it runs without the optional
Bayesian modeling dependencies. The older models in `models/` remain separate
experiments; their historical event/attribute joins are not used here.

```python
import json
from apartments.pricing import fit_pricing_model, PricingModel, rank_apartments

with open("observations.jsonl") as stream:
    records = [json.loads(line) for line in stream if line.strip()]
model = fit_pricing_model(records)
model.save("pricing.json")
print(model.report["holdout"])
print(model.marginal_contributions(records[0], {"elevator": True}))
```

## Observation and validation contract

Rows require `unit_id`, positive `rent`, and the actual `observed_at` collection
clock. Epoch seconds and ISO timestamps are accepted; naive times mean UTC.
`rent` is monthly gross asking rent. Known furnished, short-term, and concession
rows are excluded, with counts in the selection report. Unknown flags are retained;
selection is not proof that remaining listings lack concessions. Missing/invalid
prices, identity, and timestamps receive explicit exclusion counts.

The latest observation per unit per UTC calendar month is retained, so frequent
scrapes do not multiply a unit's weight. Contradictory modeled facts at the same
unit/timestamp fail instead of being resolved arbitrarily. This sampling choice
can overrepresent long-lived advertisements and does not estimate signed leases.

Validation holds out the final fraction of whole observed months. All feature
scales, missing-value centers, and category vocabularies use training rows only.
The saved model remains trained only on the early months. Reported later-month
metrics include all units and separate new-unit/new-building subsets. Fixed ridge
strength is not tuned on this holdout. A training-median baseline is included.

At least two months are needed for chronological validation. For initial collection
pilots, `holdout_fraction=0` permits an explicitly **descriptive, unvalidated** fit.
The report warns when fewer than 24 training months make trend and seasonality
particularly difficult to distinguish. A production evaluation should additionally
use rolling-origin folds, a distinct calibration period, neighborhood/time slices,
and a fresh final holdout.

## Features and interpretation

Supported numeric features are bedroom count (studio = 0), bathrooms, square feet,
listed floor and physical floor. The physical-floor/elevator interaction is
recomputed for every prediction and counterfactual. Physical floor is never
inferred from an advertised label; `floor_label_gap` represents their difference
when both are supplied. Invalid nonpositive area/bathroom counts and negative
bedroom counts become unknown.

Category effects cover building, laundry type, doorman type, HVAC type, and pet
rules. Explicit missing numeric indicators and unknown categories distinguish
unknowns from negative amenities. Window exposures (north/east/south/west) and
view exposures (street/courtyard/park/water/open) are separate indicators. Lists
can contain several exposures and must assert the complete set: `[]` means
explicitly none, while null means unknown. For partial source evidence use a
tri-state mapping such as `{"south": true, "west": false}`: north/east remain
unknown. The same semantics apply in modeling and preference ranking. Unrecognized exposure tokens are treated as unknown during modeling.
Seasonality uses annual sine/cosine terms and trend is linear in elapsed years.
Trend is frozen to zero when training coverage spans fewer than 90 days; seasonality
is frozen unless at least 12 calendar months cover every month of the year. These
support guards prevent extrapolating a few hours of capture timing into a price
trend. Disabled effects and reasons are recorded in feature support; predictions
list their frozen time effects.

The report includes feature support, missingness, and variation. Numeric effects
without observed variation and contrasts involving unseen categories receive
warnings. `decomposition(row)` returns additive log-rent components, which sum to
predicted log rent. Numeric coefficients use training-standardized units; use
`marginal_contributions(row, changes)` to get a joint contrast in monthly dollars
and percentage terms with interactions recomputed. Joint dollar contrasts are
not additive across separately changed attributes because the link is exponential.

Predictions are conditional median asking rents. `heuristic_low/high` use ±1.645
training residual RMS on the log scale. These are **not calibrated intervals**,
coefficient confidence intervals, or guarantees. Building-wide amenities are
confounded with building effects; regularization allocates associated price
between correlated terms. These estimates are not causal and do not reveal an
individual's willingness to pay.

## Preference and frontier contract

```python
ranking = rank_apartments(current_candidates, {
    "bedrooms": 500,                 # $/month per bedroom
    "laundry_type=in_unit": 150,     # $/month for an indicator
    "window_exposures.south": 100,
    "physical_floor": -20,          # signed aversion, $/month per floor
})
```

Monthly surplus is the sum of supplied dollar benefits minus asking rent; higher
is better. Preferences are independent user inputs, not inferred from model
coefficients. A candidate dominates another when its rent is no higher and every
signed preference benefit is no lower, with at least one strict improvement.
Equal candidates both remain on the frontier. This preference-specific frontier
ignores attributes with zero willingness to pay. The comparison is quadratic in
candidate count and intended for a filtered search shortlist.

Unknown valued attributes exclude a candidate by default and are listed in its
result. Explicit `unknown_policy="zero"` uses zero benefit instead; with negative
preferences this can favor unknowns, so use it intentionally. Unrecognized
preference keys raise an error. Apply a budget and other hard constraints to the
candidate set before ranking. Input should represent the current candidate set,
not every historical observation of each apartment.
