# Bayesian feature identification and remaining sensitivity checks

The reviewed Chelsea cohort supports an interpretable conditional model, but most bathroom information compares different units. **Only 418 of 22,165 units have more than one distinct known full/half-bath composition.** A well-behaved sampler does not by itself establish that bathroom, building and unit contributions are separately determined by the data.

This audit reads the exact source and saved design of `data/model/chelsea-bayesian-bathrooms-long-20260918`. It does not fit a model, interpret the live chain output or claim that prior sensitivity has been completed. No new numerical implementation error was found in the reviewed bedroom/bathroom graph; the following are interpretation and identification limits.

## What information the cohort supplies

The source contains 52,711 advertisement observations, 22,165 units and 1,134 buildings. There are 10,448 units with one observation and 136 buildings with one observed unit. These observations still inform fitted asking rent; they provide limited direct evidence for separating a persistent unit deviation from building and measured-feature contributions.

| Attribute | Units with a known value | Units with multiple known observations | Units with varying known values |
| --- | ---: | ---: | ---: |
| Bedrooms | 22,165 | 11,717 | 1,447 |
| Scalar bathroom count | 22,165 | 11,717 | 433 |
| Known full/half composition | 22,116 | 11,694 | 418 |

“Varying” means different reported analytical values across advertisements. It does not prove a physical renovation, a verified change date, independent measurements or a causal before/after price comparison. Changes can also reflect marketing, corrections or measurement inconsistency. Unknown and flagged compositions are excluded from this variation count, while their observations remain in the fit.

Interior area is known for 18,553 observations representing 8,664 units. This makes the distinction between fixed-area and typical-size bedroom comparisons important.

## Sparse bathroom endpoints

| Feature or layout | Observations | Units | Buildings |
| --- | ---: | ---: | ---: |
| At least two half baths | 2 | 2 | 2 |
| At least five full baths | 14 | 9 | 5 |
| 2 bedrooms / 3 full baths / no half bath | 91 | 49 | 27 |
| 3 bedrooms / 4 full baths / no half bath | 12 | 10 | 6 |
| 4 bedrooms / 5 full baths / no half bath | 2 | 2 | 2 |

The second half-bath increment is therefore supported by only two advertisements in the whole cohort. The 4-bedroom net-bath comparison also reaches an endpoint observed twice. Reported intervals for these contrasts can legitimately reflect substantial pooling and prior influence. Satisfactory R-hat and effective sample size would assess Monte Carlo behavior, not increase the number of observed apartments.

## What is and is not separately identified

The saved 43-column feature matrix has rank 43. That rank check excludes the building and unit indicator block. If a feature is constant within every observed unit, its column can be expressed as a linear combination of unit indicators. For an individual unit whose attribute never changes, that unit's likelihood cannot distinguish the attribute contribution from a persistent unit deviation. Variation in other units can still inform the shared coefficient. Proper priors and pooling regularize how information from within-unit changes and between-unit comparisons is combined. They do not turn the resulting feature contribution into a measurement independent of the group model.

Building effects have an unweighted zero-sum constraint across buildings. Unit effects have independent zero-centered priors, but are **not constrained to sum to zero within each building**. Consequently, a building's average fitted unit offset need not be zero. For buildings with one or few observed units, especially, the division between building and unit terms depends on their prior scales and the wider population. The combined building-plus-unit adjustment should be computed within each posterior draw; adding marginal interval endpoints or separately transformed medians would lose covariance.

This does not invalidate using large group offsets to find unmodeled attributes or data issues. It limits interpreting those offsets as independently measured building quality or standalone apartment premiums. Ranking posterior medians with intervals is also different from estimating the probability that a group has the highest effect.

## Bathroom and bedroom construction

The full-bath increments are pooled across apartments. Writing `theta_f` for the base increment from `f` to `f + 1` full baths and `gamma` for the coefficient on `max(bedrooms − full_baths, 0)`, a full-bath increment at fixed bedrooms is:

`theta_f − gamma × I(f < bedrooms)`.

For `b` bedrooms, the reported comparison of net full baths −1→0 versus 0→+1 is:

`theta_(b−1) − theta_b − gamma`.

Thus differences across bedroom counts can come from the absolute full-bath increments as well as the shared shortfall term. The model does not estimate a fully flexible curve over every bedroom/bathroom cell. Half-bath increments are also pooled; repeated bedroom-specific report rows show endpoint support for the same pooled effect, not independent estimates of different half-bath values.

A fixed-area bedroom counterfactual must change both the bedroom threshold and the within-bedroom size reference, plus the bathroom-shortfall feature where applicable. The current size-reference medians are 500, 704, 1,127, 1,978, 2,277 and 2,660 square feet for 0 through 5 bedrooms. With observed area, a `b → b + 1` bedroom comparison includes `beta_size × log(median_b / median_(b+1))`. With area unknown, the size feature remains at its imputed reference, so that comparison cannot be described as holding a measured area fixed.

The existing bathroom contrast helpers correctly change full/half counts and the scalar bathroom total together. A future general counterfactual interface must preserve that consistency: changing only one count would intentionally trigger the unknown-composition mask, producing a reporting-state comparison instead of the intended bathroom-value comparison. Scenarios outside supported bedroom/bathroom ranges should be flagged rather than silently treated as ordinary increments.

## Next sensitivity checks

1. **Feature-prior sensitivity on the identical reviewed cohort:** vary the feature prior multiplier while retaining the source policy, observation membership and target. Compare draw-wise bathroom contrasts and residual rankings, not just coefficient medians. This has not yet been completed.
2. **Group-versus-feature allocation sensitivity:** in a separately versioned model, vary the building and unit scale priors as well. The existing feature multiplier changes beta priors only; it is not a sensitivity analysis of all pooling assumptions.
3. **Between-unit versus within-unit evidence:** review a bounded sample of the 418 composition-varying units for credible same-unit changes and source problems. A subsequent model can distinguish unit/building mean covariates from within-group deviations where data support it. Such comparisons remain observational and may coincide with other renovations.
4. **Sparse-layout influence:** inspect both second-half-bath advertisements and the rare high-full-bath cases, then test sensitivity to their supported inclusion and measurement choices. Never replace their prices with fitted values merely to reduce residuals.
5. **Derived quantity checks:** retain diagnostics for joint bathroom contrasts and scaled unit effects. If combined group adjustments or selected unit-specific feature decompositions are published, calculate their posterior draws and assess those derived quantities directly.

The model targets the conditional median of advertised rent through a Student-t likelihood on log rent. Fitted intervals describe latent median uncertainty. A lognormal mean correction is not appropriate for this likelihood, and residuals remain in-sample source-review signals.

## Reproducibility

Immutable support artifact: `data/model/chelsea-bayesian-identification-support-20260918`, containing `support.json`, `report.md` and the exact computation script. Publication verifies source file hashes, protocol identity, saved-design membership and composition-knownness counts. An identical replay reproduces the artifact.

- Source manifest SHA-256: `137f72a4a9bc38a67c82e3051a42341bf41f9f5683875ad982d5d4dc0e3ec7eb`
- Source observations SHA-256: `6f4a05b01139d3d094ecaa2a7c305c02cb066e1c236dfe547c663a4d18b49b1f`
- Experiment protocol SHA-256: `1bb586f80ac1b8e994d03c0f9fa2713cb2e4bb7a09bc2c0f4961d8d64e6cbdde`
- Feature-design SHA-256: `d0cee90cc965ceb486b928400737d82c36960d25974bba9e417b65802f12bbf3`
- Time-design SHA-256: `fa821a28ce4276db89efc407b4c7aaf187c9f775ce9b307821d582bebde2f218`
