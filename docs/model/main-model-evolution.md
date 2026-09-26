# Complete model-version history

**Status:** all major model generations through the selected pointer in `config/main-analysis.json`

This report covers the full model history, including the pre-reset Sierra and
multi-building Bayesian line, the September 8 all-Chelsea model, the canonical-unit
robust and Bayesian generations, the source-bound feature posteriors, and the
currently selected expanded-floor spline. It distinguishes three things that are
easy to conflate:

1. a change to the **source cohort**;
2. a change to the **mathematical representation**; and
3. a change to **execution, diagnostics or reporting**.

A completed research experiment was not automatically a new main model. Promotion
required a verified source, an immutable protocol, a completed posterior, parameter
and derived-quantity diagnostics, matched comparisons, source review and a real
analysis-page check.

> **Authority note.** Some earlier documents, especially
> `docs/model/current-analysis.md`, describe an earlier selected fit. For the
> present state, the authoritative pointer is `config/main-analysis.json`. Since 2026-09-26 it
> selects the summary of the frontier line's NumPyro fit `m0q-btrend` + `unitdesc-v1` (Ben's
> choice), described in [listing estimates](listing-estimates.md); this report ends at the last
> PyMC selection. Before that, on the
> `bedroom-time-20260922` line it bound
> `data/model/chelsea-product-scope-analysis-20260921` to
> `data/model/chelsea-bayesian-product-scope-structure-20260923` (step 10 below).
> Historical documents are retained as contemporaneous records and are not rewritten.

## Executive summary

The project has had several genuine main-model generations, not one continuous
posterior. The earliest model was a Sierra-only monthly Bayesian index. It became
a weekly Sierra model, then a shared-floor/facing model for three neighboring
buildings. On September 8 it was replaced by an all-Chelsea pooled Bayesian model.
The canonical-unit reset then introduced a fast robust point model and a separate
historical-amenity research line. An overnight Bayesian canonical-unit model was
selected for descriptive uncertainty but failed its final-period predictive
comparison against the robust point benchmark. The current post-reset main line
starts with the full Bayesian bathroom model, then changes source policy and floor
representation until reaching the expanded-floor spline fit.

The current post-reset model began as a hierarchical Bayesian log-rent model with
explicit bathroom composition and a shared Student-t residual scale. It then
acquired source-bound current observations and reversible source reviews.
Listed-floor information was first tested as observed-level increments, but that
representation was not promoted because its support was sparse and its independent
priors accumulated variance across many increments. The promoted floor
representation is now a regularized natural cubic spline. A broader, reviewed
unit-label extraction then increased known listed-floor observations from
**29,907 / 52,653 (56.80%)** to **35,992 / 52,653 (68.36%)** without changing the
model equation or other source fields. That expanded-floor spline fit is the
current main posterior.

The current fit has:

- **52,653 observations**, **22,155 units**, **1,129 buildings** and **172
  capture-time current observations**;
- **47 active feature columns**, of which five are spline coordinates and one is
  a listed-floor-unknown indicator;
- four chains, 4,000 warmup iterations and 6,000 retained draws per chain;
- 24,000 retained draws, zero divergences and zero depth-limit hits;
- maximum parameter R-hat **1.00398**, minimum bulk ESS **820.7**, minimum tail
  ESS **1,513.2**, and minimum BFMI **0.4357**.

These diagnostics establish numerical adequacy for this specification. They do
not establish causal amenity prices, complete market coverage, correct physical
floor measurements or calibrated uncertainty for unfamiliar buildings.

## Complete version inventory

| Date / version | Main-model role | Cohort or scope | Mathematical change | Disposition |
|---|---|---|---|---|
| 2026-08-01 · Sierra monthly | First Bayesian rent index | Sierra Chelsea; one median observation per unit-month | Log rent, unit effects, bedroom/bath/size controls, furnished flag and a monthly random walk | Historical predecessor |
| 2026-08-01 · Sierra weekly | Higher-frequency Sierra index | Sierra; one median observation per unit-week | Weekly time grid and evidence-based furnished/Blueground periods; cumulative first/second-bedroom terms | Historical predecessor |
| 2026-08-01 · multi-building weekly | Shared local-market model | Sierra, Stonehenge Gardens and 101 W 15th, later West 13th buildings | Shared building/floor effects, physical-floor curve, garden/skyline facing and interactions | Historical predecessor |
| 2026-09-08 · all-Chelsea pooled Bayesian | First broad Chelsea model | 2,386 monthly observations, 287 units, 147 buildings | Pooled building/unit/floor effects, Student-t log rent and monthly trend | Superseded by canonical transform |
| 2026-09-17 · minimal canonical robust | Canonical-unit point baseline | 53,899 unit-months, 22,424 units, 1,141 buildings | Robust penalized log-rent regression with incremental bedrooms, size, groups, trend and seasonality | Retained prediction benchmark |
| 2026-09-18 · historical amenity robust | Source-backed amenity research | Same canonical historical cohort; 42 matched ablation fits | Laundry, doorman, HVAC, pet, floor/view/exposure blocks and missingness controls | Research, not main |
| 2026-09-18 · canonical Bayesian overnight | Bayesian uncertainty branch on canonical data | 53,899 unit-months | Bayesian version of the canonical mean model; orthogonal drift, Student-t, unit/building effects | Descriptive branch; final-period prediction worse than robust baseline |
| 2026-09-18 · Bayesian bathrooms | First post-reset selected posterior | 52,711 rows, 22,165 units, 1,134 buildings, 13 current rows | Explicit full/half baths, bathroom shortfall, joint posterior contributions and residuals | First Bayesian main selection |
| 2026-09-18–19 · source/current/floor candidates | Evidence and current-cohort revisions | 52,704–52,863 rows; current cohort expanded to 172 | Mostly source projections; observed-level floor increments and durable disk execution | Intermediate candidates and research fits |
| 2026-09-19 · spline, narrow floor source | Regularized floor representation | 52,653 rows; 56.80% known floors | 51 independent increments replaced by five natural-spline coordinates | Selected, then superseded by broader floor source |
| 2026-09-19 · expanded-floor spline | Current main posterior | 52,653 rows, 22,155 units, 1,129 buildings, 172 current rows | Same spline equation; source adds 6,085 reviewed floor proxies | **Current selected model** |
| 2026-09-19–20 · residual/location/direct-floor revisions | Post-selection research | Exact-ad source revisions and 24 direct-floor additions | No promoted equation change; matched refits pending/recoverable | Not selected |

The rest of this report gives the equation and reason for each generation, not
just the final specification.

## Pre-reset model line: Sierra to all-Chelsea Bayesian

### 1. Sierra monthly Bayesian index — August 1

The first tracked model was a narrow **Sierra Chelsea** index. It retained one
median asking-rent observation per unit-month and modeled:

\[
\begin{aligned}
 y_i ={}& \log r_i \\
 \mu_i ={}& \alpha + \beta_f\,1(\text{furnished}_i)
 + \beta_1\,1(B_i=1) + \beta_2\,1(B_i\ge 2) \\
 &+ \beta_A z(\log A_i) + \beta_{A?}1(A_i\text{ missing})
 + g_{t(i)} + u_{u(i)}, \\
 y_i &\sim t_5(\mu_i,\sigma).
\end{aligned}
\]

The monthly trend \(g_t\) was a Gaussian random walk with a shared innovation
scale; unit effects captured persistent unit differences. This model was useful
as a first posterior index, but it was not designed for Chelsea-wide feature
identification. The furnished coefficient was explicitly a cohort effect until
historical furnished periods could be established.

**Why it changed:** the data were too narrow, the frequency choice was arbitrary,
and the model hard-coded one building. The next version tested weekly updating
and improved furnishing evidence.

Evidence: historical commits `d339727` and `b4334fd`; the original implementation
is preserved in Git history as `models/rent_model.py`.

### 2. Sierra weekly and multi-building shared-floor versions — August 1–2

The weekly version changed the time index and replaced the coarse bedroom terms
with cumulative indicators for the first and incremental second bedroom. It also
used evidence-based Blueground/furnished periods. Its core remained:

\[
\mu_i = \alpha + \beta_1 1(B_i\ge1) + \beta_2 1(B_i\ge2)
       + \beta_A z(\log A_i) + g_{week(i)} + u_{u(i)}.
\]

The next local-market version added Stonehenge Gardens and 101 W 15th, later
West 13th buildings. It introduced building offsets, a shared cumulative physical
floor curve and source-derived facing terms:

\[
\mu_i = \cdots + b_{j(i)} + C_{floor}(P_i) +
\beta_{face}F_i + \beta_{both}1(F_i=\text{both}).
\]

Adjacent floor changes were shrunk toward zero with a shared innovation scale,
while physical floor was kept separate from marketed floor and Sierra's skipped
13th-floor numbering was handled through source/building overrides.

**Why it changed:** model a local market rather than one building, borrow strength
across sparse floor levels, and represent known facing/floor evidence. These
versions still depended on a small, manually selected building set and were
superseded when the project moved to the full archive.

Evidence: commits `faa8a54`, `7ee71df`, `c6c7f42`, `fbc05f2`, `fe1e5c5`,
`8575fd0`, `cb6511b`, `5bfc995` and the archived implementation history.

### 3. All-Chelsea pooled Bayesian model — September 8

The first broad Chelsea model replaced the manually selected building set. It
used 2,386 monthly observations from 287 units and 147 buildings, with one median
price per unit-month, pooled building/unit effects, categorical floor levels,
bedroom/bathroom/size controls, missingness indicators and a Student-t likelihood:

\[
\begin{aligned}
 y_i &\sim t_5(\mu_i,\sigma),\\
 \mu_i &= \alpha + X_i\beta + b_{j(i)} + u_{u(i)} + g_{t(i)}.
\end{aligned}
\]

The floor term was categorical, with an explicit unknown category. Unsupported
first-digit guesses were treated as unknown. Furnished/Blueground units were
excluded conservatively, including earlier history for an affected unit.

The full fit reported maximum R-hat 1.0057, minimum bulk ESS 819 and zero
divergences. A separate 2026 holdout had 459 observations and 6.51% median
absolute percentage error for all held-out rows, versus 11.61% for the
last-observed-rent baseline among previously seen units. The validation was
retrospective because later-captured attributes and full-data size scaling were
available.

**Why it changed:** this was the first model with enough scope to be a Chelsea
market analysis rather than a small-building demonstration. It was later
superseded by the canonical-unit transformation because source identities,
attribute time semantics and review overlays needed a cleaner contract.

Evidence: `docs/analysis/chelsea-2026-09-08.md`,
`docs/analysis/chelsea-2026-09-08.json`, commit `e844d94` and the subsequent
convergence checkpoint `ac5cc95`.

## Canonical-unit and robust point-model line

### 4. Minimal canonical-unit robust model — September 17

The September 17 reset changed the analytical unit of work. It retained
advertisement-owned attributes and canonical unit memberships, selected one
whole initial-ask row per unit-month, and fit a robust penalized log-rent model:

\[
\hat\theta = \arg\min_\theta
\sum_i \rho\left(y_i - \mu_i(\theta)\right)
+ \lambda_b\lVert b\rVert^2
+ \lambda_u\lVert u\rVert^2
+ \lambda_t\lVert g\rVert^2,
\]

with

\[
\mu_i = \alpha + X_i\beta + b_{j(i)} + u_{u(i)} + g_{t(i)} + s_{m(i)}.
\]

The feature block used incremental bedroom thresholds, bathrooms, relative
within-bedroom size, size missingness, building/unit effects, a smooth trend and
month-of-year seasonality. The model had 53,899 unit-month observations, 22,424
units and 1,141 buildings. Its withheld-2026 median absolute error was 7.1%,
versus 17.8% for the bedroom-only baseline; the complete local fit ran in about
23 seconds.

**Why it changed:** canonical-unit membership and own-advertisement provenance
made historical reconstruction more explicit, while robust fitting provided a
fast stable point baseline for residual and search work. It does not provide
posterior coefficient uncertainty and remains a prediction benchmark rather than
the current contribution model.

Evidence: `docs/analysis/chelsea-minimal-2026-09-17.md` and
`docs/model/robust-candidate-scoring.md`.

### 5. Historical amenity robust model — September 18

The amenity model extended the minimal robust design with source-backed laundry,
doorman, HVAC, pet, exposure, elevator and floor blocks, while keeping unknown
values distinct. It used matched ablations, train-only vocabularies/scales and
fixed penalties. Its development equation remained a penalized log-rent model,
but with an expanded \(X_i\):

\[
\mu_i = \alpha + X_{layout,i}\beta_{layout}
+ X_{amenity,i}\beta_{amenity} + b_{j(i)} + u_{u(i)} + g_{t(i)} + s_{m(i)}.
\]

All 42 reported fits completed. In the recovered-amenity development experiment,
unseen-building median error was 18.26% for baseline and 14.04% with reported
amenities. This supported continued source measurement but did not establish
causal amenity premiums or promote the robust amenity model to the main Bayesian
analysis.

**Why it changed:** residual review indicated omitted amenities could matter, but
source measurement and missingness controls had to be tested before interpretation.

Evidence: `docs/analysis/chelsea-amenities-2026-09-18.md`,
`docs/analysis/chelsea-recovery-ablation-2026-09-18.md`.

### 6. Canonical-unit Bayesian overnight generation — September 18

The overnight canonical-unit Bayesian branch converted the minimal mean structure
to a joint posterior with cumulative bedroom terms, bathroom/size controls,
monthly trend, seasonality and building/unit effects. It added an identified
annual drift term after removing linear/seasonal overlap:

\[
\mu_i = \alpha + X_i\beta + q_{t(i)}^\mathsf{T}\gamma
+ \delta d_{t(i)} + s_{m(i)}^\mathsf{T}\eta + b_{j(i)}+u_{u(i)}.
\]

The selected validation configuration was units + available size + annual drift
+ Student-t residuals. On 2025 it reached 6.77% median error and the highest
mean log predictive density among the passing variants. On the separate January–
August 2026 test it reached 9.41% median error versus 7.10% for the robust point
model, with negative bias worsening through the year.

**Disposition:** this model established a usable Bayesian uncertainty workflow and
showed why prediction and contribution analysis should be separated. It was not
used as the final post-reset main model after the project adopted the richer
source-bound bathroom/current-capture workflow.

Evidence: `docs/analysis/chelsea-bayesian-2026-09-18.md`,
`docs/model/bayesian-local.md`, and `docs/operations/overnight-2026-09-18.md`.

## Post-reset Bayesian feature lineage

For the first post-reset Bayesian version and every later source/floor/spline
revision, the equation, promotion rationale and non-promoted branches are
recorded in the sections below. The initial post-reset version is the first
selection in this lineage; it is not the first Bayesian model in the repository.

## Current equation

For observation \(i\), let:

- \(r_i\) be the gross advertised monthly asking rent;
- \(y_i = \log r_i\);
- \(j(i)\) be its building;
- \(u(i)\) be its canonical unit identity;
- \(t(i)\) be its calendar month and \(m(i)\) its month-of-year;
- \(x_i\) be the centered 47-column feature vector;
- \(q_{t(i)}\) be the season-separated smooth time basis;
- \(d_{t(i)}\) be centered annual elapsed time;
- \(s_{m(i)}\) be the centered month-of-year contrast basis.

The likelihood is:

\[
 y_i \mid \mu_i,\sigma \sim t_{\nu=5}(\mu_i,\sigma).
\]

The latent conditional median on the log scale is:

\[
\begin{aligned}
\mu_i ={}& \alpha + x_i^\mathsf{T}\beta
       + q_{t(i)}^\mathsf{T}\gamma
       + \delta d_{t(i)}
       + s_{m(i)}^\mathsf{T}\eta \\
     &+ b_{j(i)} + \sigma_u z_{u(i)}
       + f_{g(i)}\bigl(t(i)\bigr)
       + w_{j(i)}\bigl(t(i)\bigr).
\end{aligned}
\]

Since step 9, \(f_g\) is the bedroom-group time deviation for
\(g(i)\in\{\text{studio},1,2,3+\}\). It is piecewise-linear between January
knots, a random walk with yearly step scale \(\tau\sim\operatorname{HalfNormal}(0.05)\),
zero-sum across groups and centered over each group's own months.
Since step 10, \(w_j\) is building \(j\)'s own piecewise-linear random walk on
half-year knots (step sd \(s\sqrt{0.5}\), \(s\sim\operatorname{HalfNormal}(0.1)\)),
centered over that building's training months.

The rent-scale interpretation is \(\exp(\mu_i)\), a conditional median rather
than an arithmetic mean. Residuals deliberately include the apartment's own
asking-price evidence, so they are in-sample review signals.

### Feature block

The current feature vector is centered using the training cohort. Its important
terms are:

\[
\begin{aligned}
x_i^\mathsf{T}\beta ={}&
\sum_{k=0}^{4}\beta^{bed}_k\,1(B_i > k) \\
&+ \sum_{k=1}^{4}\beta^{full}_k\,1(F_i > k)
 + \sum_{k=0}^{1}\beta^{half}_k\,1(H_i > k) \\
&+ \beta^{short}\max(B_i-F_i,0) \\
&+ \beta^{area}\log\left(\frac{A_i}{\operatorname{median}(A\mid B_i)}\right)
 + \beta^{area,missing}\,1(A_i\text{ unknown}) \\
&+ C_i^\mathsf{T}\beta^{amenity}
 + \beta^{floor,missing}\,1(L_i\text{ unknown})
 + C_{floor}(L_i)^\mathsf{T}\beta^{floor}.
\end{aligned}
\]

Here:

- \(B_i\) is bedrooms, with studios represented as zero;
- \(F_i\) and \(H_i\) are explicitly reported full- and half-bath counts;
- the shortfall term is the `full_half_balance` research construction;
- \(A_i\) is square footage, normalized within bedroom count;
- \(C_i\) contains supported numeric amenity terms, orthonormal category
  contrasts and separate unknown/reporting indicators;
- \(L_i\) is the normalized listed/advertised floor, not physical height;
- \(C_{floor}(L_i)\) is the current natural-cubic spline described below.

The exact column inventory, centering, active masks and priors are saved in the
fit's `fit/feature-design.json`. The equation above shows the scientific
construction; the saved design is authoritative for reproducing a draw.

### Current listed-floor term

The current floor source is `listed_floor`, falling back to the existing
`advertised_floor` alias. For the selected expanded source, knots are:

\[
\kappa = (1,5,10,20,35,57).
\]

Let \(Q\) be an orthonormal basis perpendicular to the all-ones vector, and let
\(h = Q\theta\) be the six zero-sum knot heights. The prior is:

\[
\theta \sim \mathcal{N}(0, 0.10^2 I_5).
\]

Let \(S(f;h)\) be the natural cubic interpolation of those heights. The reported
floor curve is:

\[
C_{floor}(f) = S(f;h) - S(2;h).
\]

The fitted feature design centers the raw spline coordinates over the training
cohort. That affects the intercept and contribution table but not a difference
between two floors. Unknown floor observations receive zero raw spline coordinates
and a separate \(\mathcal{N}(0,0.20)\) unknown indicator when that indicator varies.
Interpolation inside the observed range is supported; extrapolation is rejected.
There is no monotonicity constraint.

### Priors and group structure

The current protocol uses the following principal priors:

\[
\begin{aligned}
\alpha &\sim \mathcal{N}(\log 4500, 0.8^2), \\
\beta_k &\sim \mathcal{N}(0,s_k^2), \\
\gamma\mid\tau_t &\sim \mathcal{N}(0,\tau_t^2 s_{t,k}^2),
  &\tau_t &\sim \operatorname{HalfNormal}(0.15), \\
\delta &\sim \mathcal{N}(0.03,0.05^2), \\
\eta\mid\tau_s &\sim \mathcal{N}(0,\tau_s^2 I),
  &\tau_s &\sim \operatorname{HalfNormal}(0.10), \\
\mathbf b\mid\sigma_b &\sim \operatorname{ZeroSumNormal}(0,\sigma_b),
  &\sigma_b &\sim \operatorname{HalfNormal}(0.35), \\
z_u &\sim \mathcal{N}(0,1),
  &\sigma_u &\sim \operatorname{HalfNormal}(0.25), \\
\sigma &\sim \operatorname{HalfNormal}(0.25).
\end{aligned}
\]

Feature prior scales are part of the protocol, not informal defaults. The
current family uses approximately 0.25 for bedroom/full-bath increments, 0.20
for half-bath/shortfall/reporting terms, 0.35 for the within-bedroom area term,
0.15 for standardized amenity/category contrasts, 0.10 for spline coordinates,
and 0.20 for the floor-unknown indicator. The global feature prior multiplier is
1.0 in the selected fit.

Building effects are constrained to sum to zero for identifiability. Unit effects
are centered through their shared scale but are not a causal apartment-quality
measurement. Both group effects can absorb omitted features; this is why their
movement is reviewed alongside feature changes.

## Post-reset selected-model progression

### 0. Prehistory within the post-reset branch: robust and descriptive models

**Before September 18.** The project had a robust/ridge log-rent workflow with
bedrooms, bathrooms, area, building/unit effects and time terms, plus exploratory
amenity blocks. Its rough form was:

\[
\log r_i = x_i^\mathsf{T}\beta + b_{j(i)} + u_{u(i)} + g(t_i) + \epsilon_i,
\]

with regularization and robust fitting rather than a joint posterior. It was
useful for establishing the scrape → transform → fit → analyze loop and for
finding residual cases, but it did not provide the requested posterior uncertainty
or joint coefficient/counterfactual draws. It remains available explicitly as a
legacy workflow; it is not the main model.

**Why the change:** the project goal shifted toward interpretable feature
contributions, source-linked residual review and counterfactuals with explicit
uncertainty. A Bayesian model was chosen instead of a surrogate estimator.

Evidence: `docs/model/legacy-robust-analysis.md`,
`docs/model/pricing.md`, and the project intent in `docs/project-intent.md`.

### 1. First Bayesian bathroom model — September 18

**Fit:** `chelsea-bayesian-bathrooms-long-20260918`

**Source/cohort:** 52,711 observations, 22,165 units, 1,134 buildings and 13
refreshed current observations. The feature design had 43 active columns under
`full_half_balance`.

**Equation change:** the project moved to the hierarchical Student-t equation
above. The key new feature construction was separate composition:

\[
\begin{aligned}
\text{full terms} &: \sum_k \beta^{full}_k1(F_i>k),\\
\text{half terms} &: \sum_k \beta^{half}_k1(H_i>k),\\
\text{shortfall} &: \beta^{short}\max(B_i-F_i,0).
\end{aligned}
\]

Rows with missing, flagged, inconsistent or shared-access bathroom composition
kept their source values but contributed an explicit unknown indicator instead of
being silently treated as zero.

**Why:** a scalar bathroom count could not distinguish full from half baths or
ask whether eliminating a full-bath shortage differed from adding a surplus. The
user also asked for explicit coefficient uncertainty and joint bathroom
comparisons.

**Result:** four chains, 1,000 warmup and 4,000 retained draws; maximum R-hat
1.00767, minimum bulk/tail ESS 559/966, minimum BFMI 0.412 and zero divergences.
Both parameter and derived-quantity gates passed. The second-half-bath term had
only two supporting advertisements and remained a sensitivity result, not a
stable renter-facing premium.

Evidence: `docs/analysis/chelsea-bayesian-bathrooms-2026-09-18.md`,
`docs/model/bayesian-feature-research.md`.

### 2. Source-review overlays — September 18

Several source revisions were tested without changing the mathematical model:

- a bathroom/source-composition projection masked shared-access and unsupported
  composition claims;
- a residual-driven scope revision quarantined commercial and location-conflict
  advertisements;
- a later combined source revision retained 52,704 observations, 22,158 units
  and 1,131 buildings while preserving raw values and all 13 current captures.

**Equation change:** none. These were changes to \(\mathcal{D}\), the fit's
source dataset, not to \(\mu_i\), the likelihood or the priors.

**Why:** large residuals exposed commercial offers, location conflicts and
bathroom evidence that should not be interpreted as ordinary residential feature
variation. The policy was to preserve source evidence and apply reversible,
source-bound overlays rather than invent prices or corrected addresses.

**Disposition:** matched refits were required. A short source refit failed the
parameter gate; a longer disk-backed refit passed diagnostics after report
recovery. Source sensitivity changed median absolute log residual only
0.035191 → 0.035189 and moved each current fitted rent by less than $4. This
supported source-quality review but did not justify calling the change a large
model improvement.

Evidence: `docs/analysis/chelsea-bayesian-source-revision-2026-09-18.md`.

### 3. Refreshed current observations — September 18–19

**Source change:** a current-cohort refresh preserved 52,691 historical rows and
added 172 capture-time current rows, producing 52,863 observations, 22,189 units
and 1,131 buildings. The current fit was a temporary selected stage before later
source/floor revisions.

**Equation change:** none. The same Bayesian mean and Student-t likelihood were
refit on a source that included current observations before search filtering.

**Why:** the operating loop is fit current evidence, then analyze residuals. The
previous 13-current-listing fit was insufficient for the refreshed capture set.
Current attributes were not copied backward onto historical price events.

**Disposition:** accepted as a verified intermediate fit. Its residuals produced
the current source-review queue, including the unresolved studio/one-bedroom case
for advertisement 5155021.

Evidence: `docs/data/current-cohort-refresh.md`,
`docs/analysis/chelsea-current-fit-and-residual-review-2026-09-19.md`.

### 4. Listed-floor threshold increments — September 18–19 research branch

The parameter audit found that the existing linear listed-floor representation
had only 364 known rows in the cleaned cohort, and that physical floor, floor gap
and floor×elevator interaction had no usable support. The first replacement
research design used observed listed-floor levels only:

\[
C_{floor}^{inc}(f) = \sum_{k\in\mathcal{K},\ k<f}\beta_k^{inc},
\qquad
\beta_k^{inc}\sim\mathcal{N}(0,0.15^2).
\]

Unknown floors activate no increments and retain a separate unknown indicator.
The thresholds are observed labels, not every integer floor; an 11→14 contrast
is one observed-level contrast, not three unobserved increments.

**Why:** threshold increments avoid imposing a linear price slope and retain the
user-requested `sum(1(floor > k))` construction while preserving unknowns and
building-specific label uncertainty.

**Result:** 18 supported observed-level increments, 59 active columns in the
corrected-source fit, and passing diagnostics. Most intervals were broad; the
apparent floor-14 dip and floor-14/15 jump had no shared-building endpoint
support. The full-cohort residual improvement was tiny (0.035189 → 0.035149),
and the largest movements were source/group-effect review cases.

**Disposition:** completed research artifact, not automatically promoted as the
main model. The representation earned a fit but not a strong physical-floor
interpretation.

Evidence: `docs/model/listed-floor-increment-design.md`,
`docs/analysis/chelsea-bayesian-floor-increments-2026-09-18.md`.

### 5. Reviewed floor/laundry source corrections — September 19 intermediate

**Source change:** 17 ambiguous floor claims and one false-positive laundry claim
were masked through exact source-bound overlays. Prices, source clocks, unit
identities and 172 current observations were unchanged.

**Equation change:** none in the bathroom/amenity mean structure. The floor
increment branch used the same threshold equation, but the source's known-floor
support and feature centering changed.

**Why:** source review found photo-reference floor wording and a laundry
negation/extraction error. The goal was to remove unsupported interpretations,
not to reduce residuals.

**Disposition:** the corrected-source posterior was temporarily selected after it
passed all parameter, contribution and floor-contrast gates. Its current fitted
rents moved a median $1.29 and a maximum $13.21 relative to the immediately prior
source. It was later superseded by the broader floor-evidence/spline path.

Evidence: `docs/analysis/chelsea-corrected-main-fit-2026-09-19.md` and
`config/reviews/`.

### 6. Natural-cubic floor spline — September 19

The independent increment model used many correlated cumulative terms and
accumulated prior variance. The replacement retained the same nonfloor design and
replaced the 51 independent floor increments in the broader floor experiment with
five spline coordinates:

\[
C_{floor}^{spline}(f)=S(f;Q\theta)-S(2;Q\theta),
\qquad
\theta\sim\mathcal{N}(0,0.10^2I_5).
\]

**Why:** a smooth curve shares information across sparse floor labels, avoids
arbitrary independent jumps and substantially reduces sampling work. It was not
chosen because it produced a dramatic residual reduction.

On the 56.8%-coverage source, the design fell from 93 to 47 columns. Retained
leapfrog work fell from 6,959,168 to 1,512,000 transitions in the matched
comparison. The all-row median absolute log residual changed only 0.035141 →
0.035138; the motivation was coherent floor attribution and computational
geometry.

The spline fit used four chains, 4,000 warmup and 6,000 retained draws, with
zero divergences. It passed parameter, derived-contribution and floor-contrast
gates.

Evidence: `docs/model/floor-spline-experiment-2026-09-19.md` and
`docs/analysis/chelsea-spline-floor-results-2026-09-19.md`.

### 7. Expanded label-floor source — September 19

The source projection was broadened before the final spline fit. It added 6,085
inferred-floor rows from numeric-hundreds labels, wing prefixes, front/rear
suffixes and one ordinal label, while masking five reviewed photo-reference
errors. Known floors increased from 29,907 / 52,653 (56.80%) to 35,992 /
52,653 (68.36%).

**Equation change:** none. The spline knots changed only because the observed
source range changed: the upper endpoint moved from 52 to 57; interior knots
remained 5, 10, 20 and 35. This changes the induced prior and source support,
so it is not a pure data-only comparison.

**Why:** the earlier 56.8% coverage was a narrow extraction policy, not the amount
of floor information available in the archive. The broader policy was source-bound,
reviewed and reversible. It improved the evidence available for attribution while
keeping labels separate from physical height.

**Result and promotion:** the expanded source fit passed all diagnostic gates:
24,000 retained draws, maximum R-hat 1.00398, minimum bulk/tail ESS 821/1,513,
minimum BFMI 0.436 and zero divergences. Typical fitted rents moved little; the
selected reason was broader reviewed evidence plus a coherent posterior, not a
claim of superior prediction.

This is the current selected main model in `config/main-analysis.json`.

Evidence: `docs/analysis/chelsea-expanded-spline-floor-results-2026-09-19.md`,
`docs/analysis/chelsea-expanded-spline-floor-movement-review-2026-09-19.md`, and
the selected experiment's `protocol/protocol.json` and `fit/diagnostics.json`.

### 8. Post-selection source revisions — September 19–20 research, not main

Residual review continued after the expanded-floor promotion. A residual-scope
projection quarantined additional exact advertisements; a location-scope follow-up
added advertisement 2938067; and a direct-description floor projection added 24
previously unknown floors.

**Equation change:** none in the selected main model. These are alternative source
cohorts for future matched fits. A direct-floor spline refit was launched with the
same mathematical protocol, but its raw trace finished while finalization stalled;
the process was stopped and the trace retained for recovery. It was not promoted.

**Why:** source-bound evidence must be validated and compared against the selected
source without silently rebinding earlier reviews. The direct-floor additions and
location correction are useful candidates, not permission to change the current
posterior in place.

Evidence: `docs/analysis/chelsea-location-scope-followup-2026-09-20.md`,
`docs/analysis/chelsea-direct-floor-offers-2026-09-20.md`, and the corresponding
`data/model/` research artifacts.

The product-scope source (`chelsea-product-scope-analysis-20260921`, 52,638 rows)
was then selected with the unchanged spline equation as
`chelsea-bayesian-product-scope-spline-disk-20260921`.

### 9. Bedroom-group time deviations — September 22

**Equation change:** add \(f_{g(i)}(t(i))\), a separate smooth deviation from the
Chelsea trend for studios, one-, two- and three-plus-bedroom units. The source,
feature design, priors and sampler settings are unchanged.

**Why:** the previous fit's deviations (unit effect + residual) were signed by
bedroom group and era. In 2010–2013 studios were 2–4% below the fit and two-
and three-plus-bedroom units 4–10% above; in 2026 studios were 2% below and 3+
bedrooms 3% above.

**Evidence for promotion:** declared held-out screen ΔELPD +30.0 ± 9.5 (the
linear-per-group variant was +6.0 ± 5.1; a random-group negative control was
−0.5 ± 1.5). The full fit converged: max R-hat 1.0074, min ESS 787, 0 divergences,
with acceptable derived, floor and curve diagnostics. Group × year bias fell from
0.92% to 0.67%, other coefficients moved ≤ 0.009 log, and the eight source-review
cases were regenerated with passing contribution diagnostics. The main page
reconstructs every row, and bedroom counterfactuals move the time term jointly.

Evidence: `docs/model/bedroom-time-experiment-2026-09-22.md`.

### 10. Building-level price drift — September 23

**Equation change:** add \(w_{j(i)}(t(i))\), a per-building random walk on
half-year knots, centered over each building's own training months.

**Why:** row-level review of the bedroom-time fit showed era means within a
building varying with an excess SD of 3.4% beyond noise, and a unit's residual
drift growing with the time between its listings.

**Evidence for promotion:** held-out +825.5 ± 45.0 (NUTS, declared row split)
and +379.5 ± 39.3 (whole-unit split); residual σ 0.065 → 0.050. The full fit
converged (max R-hat 1.0088 on alpha, min ESS 587, 0 divergences). Source
review was regenerated, and reconstruction verified.

Evidence: `docs/model/building-drift-experiment-2026-09-23.md`,
`docs/model/screen-log-2026-09-23.md`.

## What changed versus what did not

### Changed in the selected lineage

- estimator: legacy robust/descriptive workflow → hierarchical PyMC posterior;
- bathroom representation: scalar/earlier constructions → explicit full/half
  counts plus bedroom-relative full-bath shortfall;
- source input: reviewed historical cohort → source-reviewed/current-refreshed
  cohort → broader reviewed floor source;
- floor representation: earlier linear/research increments → regularized natural
  cubic listed-floor spline;
- execution: in-memory/short experiments → durable disk-backed exact NUTS traces,
  bounded report recovery and full posterior retention.

### Deliberately not in the current equation

- physical floor and physical-floor×elevator: insufficient observed support;
- a causal amenity premium: the coefficients are conditional associations;
- GP or random-walk floor priors: backlog research, not fitted/promoted;
- four-level laundry measurement experiment: not promoted into the selected fit;
- spatial coordinates or street indicators: audited candidates, not promoted;
- preference/WTP values: supplied by the renter separately from the market model;
- calibrated unfamiliar-building uncertainty: the new-building 95% coverage result
  was 68.39%, so the pooled fallback is not served as calibrated.

## Research branches that did not change the main equation

The following branches were deliberately kept separate. Their numerical results
are useful for deciding what to do next, but they are not hidden versions of the
current model:

| Branch | What changed | Why it was tested | Disposition |
|---|---|---|---|
| Feature-prior sensitivity | Multiplied feature coefficient prior scales, same source and design | Check whether bathroom/category associations were prior-driven | Common bathroom increments were stable; the sparse second-half-bath term moved substantially. No equation change. |
| Bedroom-dependent residual scale | Replaced shared \(\sigma\) with a bedroom-level hierarchy | Larger apartments had heavier residual tails under shared noise | Centered retry passed diagnostics and improved some dispersion checks, but tail mismatch and mean-model interpretation remained unresolved. Shared scale remains selected. |
| Floor×elevator interaction | Added floor/elevator products in research designs | Test whether floor value differs by building access | Physical floor had no usable support; several interaction columns duplicated main effects. Not promoted. |
| Four-level laundry | Split generic/in-building/on-floor/in-unit evidence | Separate facility location from reporting detail | Source scope and within-building overlap were insufficient for a physical premium. Not promoted. |
| Spatial coordinates/street terms | Candidate latitude/longitude and street indicators | Investigate residual geography beyond building effects | Audited as candidates; no spatial term is in the selected fit. |
| GP/random-walk floor priors | Proposed correlated priors for floor increments | Test alternatives to spline smoothness | Backlog research only; no promoted posterior. |
| Residual-scope/location/direct-floor revisions | Changed exact source membership or added reviewed floor observations | Follow residual witnesses and improve source scope | Reversible research projections; matched fits and rebinding remain required before promotion. |

This separation is part of the model contract: a smaller residual or a converged
research fit is not sufficient by itself to replace the selected posterior.

## Current interpretation contract

The selected posterior estimates conditional associations in captured gross asking
rents. It is appropriate for:

- joint feature contrasts with explicit endpoint support;
- building and unit contribution review;
- in-sample residual triage against immutable source evidence; and
- source-valued apartment counterfactuals when the endpoint is supported.

It is not, without additional work, a causal renovation model, a signed-lease
model, a complete Chelsea/NYC market index, a guaranteed live-availability feed,
or a calibrated prediction interval for an unfamiliar building. The selected
fit intentionally includes current observations and apartment-specific unit
effects, so its residuals are useful review signals but not independent forecast
scores.

## Reproduction and provenance

The current selection is fully bound by `config/main-analysis.json`, including:

- source dataset and source manifest;
- matching description-evidence archive;
- source-issue review bundle;
- experiment and fit manifests;
- protocol and implementation hashes.

For the exact current fit, inspect:

```text
data/model/chelsea-expanded-label-floor-analysis-20260919/
data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919/
config/main-analysis.json
```

The main analysis page independently verifies those bindings before loading the
posterior. Changing a source projection, model equation, prior, sampler settings
or evidence archive requires a new versioned artifact and a new matched comparison;
it must not overwrite the selected fit in place.
