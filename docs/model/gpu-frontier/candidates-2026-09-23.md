# Candidate designs and features (2026-09-23)

Starting point: `m0-base/base-v1`, which passes all checks. Row split
ΔELPD −827 ± 50 against the promoted model; 83 s and $0.18 per fit on one H100.
The Gibbs sampler handles anything that stays **conditionally Gaussian given
the Student-t weights and a few scale parameters**, including nested
per-building or per-unit blocks. That makes GPU-heavy structure cheap, so
the design list leans on it.

The expected gain column is my prior, not a measurement. Every candidate is
scored with the same pipeline, and feature gains are attributed by also
scoring the new feature set with the previous best model.

## Model designs

| # | Design | Why it should help | Expected gain | Risks / cost |
|---|---|---|---|---|
| D1 | **Per-building time walk** (half-year knots, `m1-walk`, running) | The promoted model's biggest ingredient; its fitted walk scale (0.054 per half-year) is as large as the unit spread | Large (most of the −827 gap) | Per-building block grows to 35 dims; still batched-Cholesky-cheap |
| D2 | **Per-building bedroom slopes** (random slope on bedrooms/size within each building, in the building block) | Luxury and walk-up buildings price an extra bedroom very differently; one global bedroom premium mixes them | Medium–large | Needs enough multi-size buildings; interpretation becomes "premium in this building" plus a global mean |
| D3 | **Bedroom-group market curves** (the promoted model's other ingredient) | Studios and 3-bedrooms moved differently (2020–22) | Medium | +3×201 global columns; Schur system ~860 dims, still fast |
| D4 | **Heteroscedastic noise by building** (σ_k = σ·exp(τ·z_k)) | Some buildings are noisy (mixed stock, data errors) | Small–medium | Needs a Metropolis step per building (vectorised); the promoted line found price-level noise unhelpful |
| D5 | **Unit drift** (a per-unit slope in time, or a renovation-style step) | Units relisted years apart drift from their building | Small–medium on rows; none on units | 22k extra latents; still diagonal given the rest |
| D6 | **Non-Gaussian structures if needed** (e.g. mixture noise for data errors) | Large residuals include extraction errors | Small | Breaks conjugacy; only if residuals show a clear second mode |

## Feature sets

| # | Features | Source | Expected gain | Hygiene risks |
|---|---|---|---|---|
| F1 | **Better floor** (expanded floor projection, penthouse/duplex labels) | Dataset sidecars already in the bundle; unit label | Small–medium | Label ≠ physical floor; keep "unknown" separate |
| F2 | **Description flags** (renovated, dishwasher, washer/dryer in unit, private outdoor space, no fee, furnished, short-term, shared bath, concessions such as "1 month free") | Listing descriptions in the archive (own advertisement only) | Medium | Text belongs to that advertisement; never copy one listing's text to another; "not mentioned" ≠ "no" |
| F3 | **PLUTO building record** (year built, floors, units, building class, historic district) | NYC PLUTO | Small for ΔELPD (building effects absorb it); helps interpretation | Use the release current at listing time where possible; building↔lot mapping mismatches |
| F4 | **Listing-level context** (days since the unit was last listed, relist count so far) | Price histories in the archive | Small–medium | Only information published before the listing date |

## Proposed order

1. D1 (running), then D2 and D3. They are cheap on this sampler and target the known gap.
2. F2 (description flags) is the most promising new-data feature. I'll ask the
   other sessions before any memory-heavy extraction from the archive.
3. D4/D5 only if the residuals point there. F1 and F3 are for interpretability and small gains.
