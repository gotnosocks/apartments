# Unit attribute features: penthouse, duplex, private outdoor, shared bath

Research, September 23. Design: `models/bayesian_attribute_design.py`. Runner:
`models/bayesian_attribute_experiment.py` (the building-drift structure model
plus these features).

## Evidence from individual rows

Rows of the bedroom-time fit whose deviation (unit effect + residual) exceeded
+40% were strongly enriched for "penthouse" (27% vs 2% of all rows) and
"duplex/triplex" (20% vs 4%). A penthouse *unit label* (`PH…`, `penthouse…`;
1,001 rows, 486 units) carries a mean deviation of +15.4%. Text-only
"penthouse" mentions average +2.4%; they are mostly building amenities such as
"penthouse lounge", so only the label is used. Explicit *private* outdoor
wording (5,671 rows) averages +3.9%. Shared-bath/SRO wording (62 rows, 7
buildings) averages −16.8%.

## Definitions

- `penthouse_label`: the canonical unit label starts with `ph` or `penthouse`.
- `duplex_unit`: any of the unit's own advertisement descriptions says duplex
  or triplex.
- `private_outdoor_unit`: any own description says private / your own /
  exclusive plus outdoor space, terrace, balcony, roof deck, rooftop, garden,
  patio or yard.
- `shared_bath_unit`: SRO, single room occupancy, shared bath(room) or kitchen.

Flags are unit-level because ad wording varies between relistings. A missing
description or no match means "not flagged", not absent. Coverage: 486, 940,
3,059 and 53 units. Each gets a N(0, 0.2) coefficient. Descriptions come from
the hash-verified archive bound to the dataset; the design stores the flagged
unit IDs and the archive's manifest hash.

## Screening

Conditional MAP on top of the half-year building walk (scales fixed at the
building-walk NUTS screen), paired ΔELPD on the declared splits:

| features | row split (5,264) | whole-unit split (5,226) |
|---|---|---|
| penthouse label | +26.5 ± 12.1 | +32.3 ± 18.8 |
| duplex, per-ad text | −12.9 ± 8.9 | +34.7 ± 6.4 |
| private outdoor, per-ad text | −23.0 ± 11.5 | +53.2 ± 8.6 |
| shared bath, per-ad text | −12.9 | +10.4 ± 5.9 |
| all four, per-ad text | +16.5 ± 16.6* | +105.0 ± 20.8 |
| duplex, unit-level | −3.2 ± 8.5 | — |
| private outdoor, unit-level | +10.0 ± 9.8 | — |
| **all four, unit-level** | **+60.9 ± 15.6** | **+142.9 ± 23.2** |

\*Three features, without shared bath.

Unit-level coefficients (log): penthouse +0.14, duplex +0.03–0.04, private
outdoor +0.057, shared bath −0.30. The per-ad text flags helped new units but
hurt repeat-unit rows, because the flag toggled within a unit. Unit-level flags
help on both splits.

## Caveats

These are advertised-attribute associations. "Private terrace" wording is not
a verified physical feature, and the earlier September 18 outdoor study showed
policy sensitivity in structured outdoor codes. Shared-bath units are arguably
out of scope (not self-contained apartments); modeling them with a flag keeps
them from distorting their buildings until a scope review decides.

## Full fit and decision

Protocol fit `data/model/chelsea-bayesian-product-scope-attributes-20260923`
(building drift + all four unit-level attributes) was launched September 23 at
~00:05 and **stopped at ~450 warmup iterations**. Disk: a building-walk fit is
estimated at ~39 GB when complete (trace, posterior and report caches, each
holding ~60k per-draw parameters), and two would not fit in the 75 GB free.
The drift-only fit finishes first. The partial directory cannot resume (the
disk sampler refuses); rerun into a new directory, locally or on Modal.

## Withdrawn, September 23: unit-level flags carried later ad text backward

The unit-level text flags ("any of the unit's own ads matches") put later
advertisements' wording onto the same unit's earlier listings. That breaks the
project rule that current attributes are not copied backward onto historical
price events, which the from-scratch model session pointed out. For private
outdoor space, about 1,090 of 8,650 flagged rows were flagged only from later
ads. The row-split gain (+60.9) is suspect for the same reason: held-out rows
could draw on later ads.

- The full fit `chelsea-bayesian-product-scope-attributes-20260923b` is
  withdrawn and not promotable. Its report stage had also been killed by a 6 GB
  memory cap; it was not rerun.
- Replacement: **as-of flags**. A listing is flagged when any of the unit's
  own ads at or before that listing's period matches, so an attribute persists
  forward once described but never backward. The penthouse flag stays a unit
  label, a stable identity like the building. Screening restarted with the
  as-of flags (`duplex_asof`, `private_outdoor_asof`, `shared_bath_asof` in
  `models/structure_screen.py`).
