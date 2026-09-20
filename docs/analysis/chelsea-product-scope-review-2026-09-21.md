# Product-scope review and feature panel

**Status:** applied to the selected descriptive cohort on 2026-09-21.

The reviewed source projection is:

`data/model/chelsea-product-scope-analysis-20260921`

It starts from the expanded-floor Chelsea cohort and quarantines 15 exact
historical advertisement observations. Raw observations and source captures
remain in `residual-scope-quarantine.jsonl`; no asking price was replaced and
no current capture was removed.

## Applied exclusions

The following kinds of listings are not comparable to an unrestricted,
whole-apartment residential rental and are excluded from the ordinary fit:

- commercial/nonresidential offers such as restaurants, galleries, professional
  lofts and commercial white-box space;
- shared-housing products: SROs, shared bathrooms and roommate offers;
- explicitly income-restricted products with household income brackets;
- direct location or identity conflicts between the canonical building and the
  advertisement's own address or description;
- the previously reviewed 21 Chelsea #1206 price anomaly.

The exact decisions and literal source evidence are in:

`data/model/chelsea-product-scope-decisions-20260921-v2`

The resulting cohort has **52,638 rows**, **22,144 units**, **1,129 buildings**
and **172 current captures**. Fifteen rows are quarantined; the original
52,653-row source is reconstructable exactly.

## Flag-only feature panel

Penthouses, duplexes, lofts, private terraces and keyed/private elevators were
**not removed**. They remain in the cohort and are recorded as feature
candidates in:

`config/reviews/chelsea-nonstandard-feature-panel-20260921.json`

The panel currently contains nine flag-only cases covering:

- penthouses and private floors;
- duplexes and townhouse products;
- private terraces, roof terraces and keyed elevators;
- lofts, double-height ceilings and sleeping lofts; and
- one furnished, short-term service product retained for product-scope
  sensitivity review.

These records are not corrections and do not alter model membership. They are a
development panel for deciding whether the model needs additional measured
features. Evidence is linked to exact captures and literal description text.

## Refit

The same natural-cubic listed-floor spline specification was refit on the
retained cohort. The refit passed its gates:

- maximum parameter R-hat: **1.0036**;
- minimum bulk ESS: **894**;
- minimum tail ESS: **1,466**;
- divergences: **0**;
- minimum BFMI: **0.429**.

The selected pointer now binds:

`data/model/chelsea-bayesian-product-scope-spline-disk-20260921`

The residual review queue was rebuilt and is available at:

http://thelio.tail3983e0.ts.net:8767/

This is still a conditional, in-sample asking-rent model. Exclusion decisions
are source-scope decisions, not claims that the original prices were wrong.
Flag-only cases remain eligible for later matched feature experiments.
