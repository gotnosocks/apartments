# Bathroom contribution stability under stronger feature priors

Halving every feature prior's standard deviation leaves the common bathroom
increments nearly unchanged, but substantially changes the second-half-bath
increment, which has only two supporting advertisements. Both compared fits pass
the predeclared parameter and derived-quantity diagnostics. This is one prior
sensitivity check, not proof of robustness to source errors or model construction.

| Conditional comparison | Original median [95% CrI] | Stronger prior median [95% CrI] |
| --- | ---: | ---: |
| 2 bedrooms: 1→2 full baths | +23.72% [22.91, 24.54] | +23.72% [22.91, 24.52] |
| 2 bedrooms: 2→3 full baths | +39.72% [37.16, 42.38] | +39.59% [37.06, 42.26] |
| 3 bedrooms: 2→3 full baths | +38.78% [36.74, 40.83] | +38.67% [36.65, 40.75] |
| 3 bedrooms: 3→4 full baths | +24.78% [19.63, 30.09] | +24.61% [19.48, 29.99] |
| First half bath, pooled across configurations | +13.64% [12.74, 14.54] | +13.63% [12.75, 14.50] |
| Second half bath, only two advertisements | +43.31% [10.37, 68.80] | +16.89% [−3.40, 40.90] |

![Bathroom prior sensitivity](../../data/model/chelsea-bayesian-prior-sensitivity-figure-20260918-v2/contrasts.png)

The second-half-bath term should remain a sparse research parameter rather than a
reliable apartment-value adjustment. Even its interval's exclusion of zero depends
on the prior setting. The common increments' stability does not establish a causal
renovation premium: the model holds encoded building, unit, date, area and other
features fixed, while measurement errors and omitted attributes remain possible.

The net-bathroom result also remains similar: for two bedrooms, eliminating a
one-full-bath shortage has a smaller fitted increment than adding a surplus bath;
for three bedrooms, the reverse holds. These differences mostly reflect the
absolute full-bath increment curve. The four-bedroom comparison remains supported
by only two units at its surplus endpoint, so a changed interval crossing is not
a basis for a general rule.

## Residuals and current apartments

Across all 52,711 identical observations, the signed log-residual rank correlation
is 0.999951 and the absolute log-residual rank correlation is 0.999807. None of the
13 current captured apartments changes its fitted median rent by as much as $8;
the largest absolute movement is $7.82. This leaves the existing source-review
priorities largely intact. The new source quarantine/masking projection has not
been used in either of these fits.

## Controlled comparison and diagnostics

Both fits use four chains and 4,000 retained draws per chain, the same source
membership and targets, byte-identical saved feature/time designs, identical
fitting code and package versions, and the same likelihood, group priors,
adaptation and target acceptance. The accepted stronger-prior retry uses 2,000
warmup iterations and seed 20260919, versus 1,000 and 20260918 for the reference.
Feature prior standard deviations are multiplied by 0.5, hence prior variances
are one quarter of their reference values.

The stronger-prior fit completed at 21:33:45 UTC. Parameter maximum R-hat is 1.00952,
minimum bulk/tail ESS 553/1,000, with zero divergences and zero maximum-depth events;
minimum E-BFMI is 0.418. Joint bathroom contrasts and scaled unit effects have
maximum R-hat 1.00377 and minimum bulk/tail ESS 576/1,113. The preceding shorter-
warmup run failed the R-hat gate and remains diagnostic-only; it is not part of
this comparison.

Each interval belongs to its own fitted model. Between-fit median movements are
descriptive sensitivity measures, not credible intervals for a difference.
Posterior draws from separate fits are never paired. Monte Carlo variation can
contribute to small movements.

## Artifacts and next check

- Accepted reference: `data/model/chelsea-bayesian-bathrooms-long-20260918`.
- Accepted stronger-prior fit: `data/model/chelsea-bayesian-bathrooms-prior-half-warmup-20260918`.
- Verified comparison: `data/model/chelsea-bayesian-prior-sensitivity-20260918`.
- Stronger-prior HTML/JSON report: `data/model/chelsea-bayesian-prior-half-report-20260918`.
- Authoritative PNG/SVG and plotting source: `data/model/chelsea-bayesian-prior-sensitivity-figure-20260918-v2`.

The figure was visually inspected. The latest complete regression suite passed
1,316 tests with two skips. The first bedroom-dependent residual-scale fit failed
its parameter diagnostic gate and remains diagnostic-only; an equivalent
parameterization passed its numerical checks and its retry is running. The separately
reviewed 52,704-row source revision still requires its own refit. The reviewed
serving model remains unchanged.
