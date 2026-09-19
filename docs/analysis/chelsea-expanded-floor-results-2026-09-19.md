# Expanded advertised-floor results and source review

The floor-only test is complete and diagnostic-accepted. It substantially
improves measurement and identifies a gradual cumulative floor association,
while changing typical fitted rents very little. The matched floor/elevator
interaction completed at 21:37:44 UTC and passed its diagnostic gates.
Promotion of these increment specifications is deferred after the
[model geometry and specification review](chelsea-floor-model-geometry-review-2026-09-19.md):
passing convergence checks is insufficient to justify this parameterization
and its floor priors.

This is the captured Chelsea cohort, not a citywide representative sample.
The source contains 52,653 asking-price observations from 22,155 units and
1,129 buildings. The projection increases known floors from 349 to 29,907 rows
(56.8%), including 95 of 172 capture-time ACTIVE rows. It retains explicit
claims, reads each observation's own captured unit label, and leaves uncertain
labels unknown. See the [protocol and reproduction command](../model/label-floor-experiment-2026-09-19.md).

## Completed floor-only fit

The accepted experiment is
`data/model/chelsea-bayesian-label-floor-block-depth14-disk-20260919`, on
`data/model/chelsea-label-floor-analysis-20260919`. It uses the real PyMC model,
nutpie/Numba, an exact independently compressed graph, four chains with 4,000
warmup and 6,000 retained draws each, target acceptance 0.93, and maximum depth 14.
Statistical terms and priors match the predeclared comparison; there is no
surrogate fit. All source and frozen implementation checks passed.

Sampling finished at 19:24:46 UTC and the completed reports were published at
19:43:54 UTC. Parameter and floor-contrast gates pass: maximum R-hat 1.004052,
minimum bulk ESS 2,075.06, minimum tail ESS 2,793.72, minimum BFMI 0.44151,
zero divergences and zero maximum-depth hits. The earlier default-depth run is
preserved as a rejected diagnostic artifact; it is not the fit interpreted here.

The additive floor term is `sum_k beta_k * 1(listed_floor > k)`, with a separate
unknown-floor indicator and unconstrained Normal(0, 0.15) increment priors.
Most individual adjacent-floor intervals include zero. The cumulative pattern
is more clearly estimated:

| Listed floor versus floor 2 | Median floor contribution | Pointwise 95% interval | Observations / units / buildings at endpoint |
|---|---:|---:|---:|
| 5 | +0.22% | −0.57% to +1.02% | 3,306 /1,250 /384 |
| 6 | +1.22% | +0.26% to +2.18% | 1,854 /760 /182 |
| 10 | +3.09% | +1.61% to +4.55% | 730 /279 /76 |
| 20 | +5.23% | +2.58% to +8.08% | 182 /62 /14 |
| 30 | +8.28% | +5.24% to +11.39% | 184 /53 /8 |
| 40 | +10.10% | +4.33% to +16.23% | 71 /13 /2 |
| 52 | +20.69% | +13.24% to +28.65% | 43 /9 /1 |

These are joint-posterior contrasts, retaining covariance between increments,
holding the other fitted factors and building/unit/time effects fixed. Each
nonzero plotted cumulative contrast also passes its own diagnostics. They are
conditional associations, not verified physical-height effects or causal
premiums. High-floor observations are concentrated in a few buildings, and
unmeasured views, private outdoor space, layouts and finishes can contribute
to the fitted floor pattern. Repeated advertisements are not independent units.

Adding 34 supported levels also changes the induced prior variance over some
long-range contrasts: the expanded design has 51 increments versus 17 before.
The comparison checks unchanged nonfloor columns and priors, records this floor
prior change explicitly, and does not treat independently sampled fits as paired
posterior draws. Low-floor 2→5 retains the same three-increment construction.

## Residual and contribution comparison

The immutable matched result is
`data/model/chelsea-label-floor-block-depth14-comparison-20260919`.
All observations, prices, nonfloor features, time terms and group membership
match the previous selected fit. The source projection has an exact inverse.

| Source slice | Rows | Previous median absolute log residual | Expanded-floor median absolute log residual | Median absolute fitted-rent change |
|---|---:|---:|---:|---:|
| All | 52,653 |0.034978 |0.035141 |$5.38 |
| Captured ACTIVE |172 |0.024683 |0.024666 |$6.26 |
| Newly inferred floor |29,558 |0.036095 |0.036000 |$7.05 |
| Previously explicit floor |349 |0.030420 |0.034100 |$18.05 |
| Still missing floor |22,746 |0.033709 |0.034093 |$3.57 |

There is no material overall residual improvement. This does not by itself
decide feature usefulness for contribution analysis: much of the change is
reallocation between floors, buildings and units. With a common unweighted
building reference, median building log contributions move by −0.09227 for
Beatrice, −0.06235 for 606W30, −0.03372 for Ohm, −0.03018 for 777 Sixth Avenue,
and −0.03015 for Chelsea Stratus. These are component changes, not rent cuts.

The largest raw unit-offset shift is −0.09862 log points for 435 West 23rd #17B,
whose explicit floor 17 agrees with its own source. Three Beatrice floor 52
units shift by about −0.073 to −0.076 as floor contribution increases; the
letter-only Beatrice #C shifts +0.07366 while its floor remains unknown.
This is consistent with the hierarchical allocation mechanism, not direct
evidence of changing apartment quality.

## Manual review of 33 moved source cases

The review covers all 25 largest distinct-unit fitted-rent movements, plus
examples for the five largest unit-offset and five largest building-effect
movements: 35 selection reasons across 33 observations. Every distinct full
own-capture description was read. It is an outlier development review, not a
representative sample or an independent test set. The source builder and the
manual quote-span publication both reproduce byte-identical artifacts.

Inputs: `data/model/chelsea-label-floor-movement-review-inputs-20260919`.
Decisions: `data/model/chelsea-label-floor-movement-manual-review-20260919`.
Each decision binds the exact source row, capture/body/description hashes,
literal quote offsets and its interpretation date. No numerical correction,
unit merge or new physical-floor assertion is applied to these frozen fits.

The accepted label proxies in this reviewed subset do not reveal a new literal
floor contradiction. Important findings remain:

- **Unknown penthouse floors matter.** Beatrice #PHC (ad 1192015) moves from a
  fitted $14,727 to $13,191 against its $19,500 ask; PHB/PHA and PH4 also move
  down as the building effect falls. Their floors remain unknown, so they do
  not receive the newly measured high-floor contribution. The template saying
  residences start on 26 does not identify any penthouse floor. PH4's own
  advertisement (775133) does market three-bedroom penthouse residences with
  53rd-floor views; that is a focused source-review lead, not a universal
  penthouse-to-floor rule. The shared Cloud Lounge on 54 is not an apartment.
- **Source histories corroborate two unit identity splits.** The same displayed PHB is
  represented by canonical URL suffixes `ph-b` and `phb` (1177674/1893537);
  similarly PHA appears as `ph-a` and `pha` (1177683/2894491). They currently
  have distinct unit IDs. A subsequent raw-payload review found identical
  property-history listing sets and identical latest-listing pointers across
  all seven selected captures, with the same source building ID 13264 and exact
  property address/label. PHB has a shared nine-ad history and latest listing
  3724354; PHA has a shared six-ad history and latest listing 2894491. This
  corroborates StreetEasy's identity linkage beyond label similarity. The
  source-supported alias groups are recorded for the next identity projection;
  the frozen floor fits retain their original IDs. Linkage does not validate
  bathroom counts, establish physical renovation dates, or justify copying
  attributes across historical advertisements.
- **A concrete price-basis conflict appears in Chelsea Centro #17I.** Its
  explicit floor 17 is corroborated. Target $4,040 matches the net rent in the
  lease-assignment description, which separately says gross $4,446 and names
  a tenant incentive (3091654). A subsequent own-payload check confirms
  structured price $4,040 and a June 23, 2020 price-change event at that amount;
  every own-ad rental-history event, including its first ACTIVE event on
  June 24, also reports $4,040 in both archived captures. The structured
  `netEffectiveRent` field is null. The review recommends quarantining this
  row from the gross-ask cohort in the next projection until explicit dated
  gross-price and lease-assignment handling is applied. Its fitted value rises from $4,238 to $4,748;
  that estimate is not evidence for the true advertised price.
- **A concrete bathroom conflict appears in Beatrice PHB.** Ad 1893537 has
  structured 4 full + 1 half bathrooms but describes three and a half bathrooms
  and three bedroom en suites. This remains a source conflict rather than an
  inferred renovation or a model-based count correction.
- **Floor alone misses luxury and property-type distinctions.** One High Line
  #31B's fitted rent rises from $41,779 to $43,622 against a $48,000 ask; the own
  source describes river views, corner exposures and new finishes. Other
  reviewed homes have private pools, terraces, duplex layouts or whole-house
  occupation. Soori #10C is a duplex penthouse; ABI PH2 is not floor 2; the
  four-story 344 West 22nd townhouse has no single apartment floor. These are
  useful feature leads, not reasons to overwrite their floor labels.
- **Additional extraction and cost-scope leads are explicit.** Chelsea Stratus
  #3E has a missing analytical area but its own text says 1,356 SF (872357).
  Walker Tower #18D explicitly says furnished while its analytical flag is
  unknown (2021775). Ohm #34E's headline says south/west while its template
  says north (4933515). Numeric 1701 at Lantern House, numeric 37056 at One Hudson
  Yards, and letter-prefix C46 at 606W30 need building-specific numbering
  evidence. Mandatory fees and included utilities belong in separate
  total-cost analysis; building amenities and floors are not unit attributes.

Floor extraction, source/identity review and feature representation should
continue as separate operations. A residual can nominate a case to inspect;
it cannot resolve a floor, bathroom count, gross price or unit identity.

The later identity evidence is preserved in
`data/model/chelsea-beatrice-source-supported-alias-review-20260919`, reviewed
at 20:31:14 UTC. Its producer verifies the reviewed cases, refreshed description
archive, original description parent, the exact serving-history export
`data/exports/chelsea-serving-history-20260918-asof1600`, selected archive-shard
hashes and each own raw-listing hash. Only property-address and property-history
fields support identity; the broker-license address is not an apartment floor.
The earlier 33-case review remains immutable, preserving when each conclusion
was known. No identity or attribute change is applied to either matched fit.

The dated price-basis finding is recorded in
`data/model/chelsea-centro-own-price-basis-review-20260919`, reviewed at 20:40:22
UTC. It verifies both own raw-listing hashes, archive shards, the full source
and description lineage, and the literal recovered-description quote. The raw
JSON description is a React reference (`$3f`); quote offsets refer to the
hash-verified resolved description and retain its interpretation timestamp.
The source supports the net/gross distinction but does not independently verify
a lease contract or establish the gross quote's validity on every past date.
No numerical replacement or cohort quarantine is applied to the frozen fits.

## Artifact bindings

- Accepted floor fit manifest: `92287aeec5d753c41c23a67cc3de41ecb935f5fc3d5cd2e2501e159184eec5c1`.
- Protocol manifest: `e5525fc5a7046c6c8dd9a0381070169048d04f7545baf0be9d2e9db85deda64f`.
- Matched comparison manifest: `366df6151fd2e5ce64143d0f2073894d9b14daa7971d94a369ca0d34c8956ca6`.
- Review inputs manifest: `b1d01feb59d747d6729995788ae51d32fc0ab6f9a0cac682b296de2ea65ef689`.
- Manual review manifest: `09222013419d68ac27060f4fcfe980fa4dbf4bd8c666b70714b5eab98cc2f05b`.
- Fixed eight-case review manifest: `6878f65fd7479d1fd9a47a99a216b5aed3283945043c3fdf1ab7dac0c1fb8295`.
- Subsequent source-supported alias review manifest: `049a21db47802d9d79a0b6b6a967560df6b907d729e86fe06dbc5695781fa2c9`.

The fixed eight-case residual panel has also completed on this accepted fit:
`data/model/chelsea-label-floor-fixed-residual-review-20260919`. Every case's
joint contribution diagnostics and the predefined bedroom counterfactual pass.
Membership remains the same eight advertisement IDs, regardless of new residual
rank; each case now separately reports its analytical floor and provenance.
This check does not resolve the known source bedroom conflict or turn the panel
into a holdout. The matched pooled interaction fit has completed, but its comparison was superseded by the requested spline specification.
Main selection has not changed.

The separately preselected 26-unit floor-coverage panel also has a completed,
source-bound comparison in
`data/model/chelsea-label-floor-fixed-coverage-comparison-20260919`. It retains
the same two units per nonempty floor-band/elevator cell. Median absolute
fitted-rent movement is $13.04 (maximum $184.35); median absolute log residual
changes from 0.01671 to 0.02151. These descriptive results likewise do not show
improved typical fit. The panel intentionally covers different floor/access
conditions and is not a population-weighted accuracy estimate.

## Subsequent specification change

The user requested a different floor specification. The new experiment retains
this exact expanded source and replaces 51 independent increments with five
regularized natural-spline coefficients; see
[the spline protocol](../model/floor-spline-experiment-2026-09-19.md) and
[completed comparison and source review](chelsea-spline-floor-results-2026-09-19.md).

The older expanded-floor/elevator variant completed with maximum R-hat 1.0036,
minimum bulk ESS 2,096, zero divergences and zero depth-limit hits. Its supported
floor-2-to-5 elevator-minus-no-elevator log-change contrast has a rent-multiplier
ratio difference of −2.41% (95% interval −3.86% to −1.01%). This is a conditional
association in that older specification, not evidence for a causal elevator
penalty or a coefficient to transfer into the spline. It warrants scrutiny of
comparability and omitted upper-floor attributes before any interaction is
promoted. The old variant remains a separate research artifact.
