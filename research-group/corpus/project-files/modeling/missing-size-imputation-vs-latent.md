# Missing square footage: imputation vs. full Bayesian latent size

Written 2026-10-10 while the sizefill fit runs. The PyMC code is illustrative: our production sampler is a custom Student-t Gibbs sampler, not PyMC. The sketches show the model structure, not a drop-in replacement.

## Setup (what both approaches share)

- Size is a **unit** attribute: one true size per unit, constant over time.
- About 40% of rows end up with no size even after sizefill (25% stated, 35% filled from unit, line or building history).
- In the price model, size enters as `beta_size[building] * (log_size[unit] - bedroom_median[bedrooms])`. That is a global slope plus a partially pooled per-building slope.
- The problem: when `log_size` is unknown, the model plugs in 0 (the bedroom median) plus one global `sqft_unknown` offset. At 423 E 12th that treats the 300 sqft rear units as median 1BRs.

Two families of fix:

1. **Imputation:** decide on a size (or several) *before* the price model, then fit the price model treating those sizes as data.
2. **Full Bayesian latent size:** make each unknown size a parameter *inside* the price model, with its own prior (the "size model"), and sample it together with everything else.

---

## 1. Imputation

### 1a. Single imputation (what sizefill is)

**Concept.** Fill each missing size with one best guess, then fit as if it were observed. Sizefill is a *hierarchical hot-deck*: use the unit's own earlier size, else its line's, else its building's median for that bedroom and bath count, using only data known as of the row's date. Flags tell the price model which level the guess came from, so each level gets its own offset.

**Strengths.** Cheap, rent-blind, and uses real information. No change to the sampler.

**Weakness.** It treats the guess as certain. A building-median guess for a rear unit at 423 is confidently wrong, so the posterior is too narrow and slightly biased where guesses are poor.

**In PyMC.** Nothing changes in the model. Sizefill just produces a different `x_size` column:

```python
x_size = df["log_sqft_asof"] - df["bed_median_log_sqft"]      # 0 where still missing
flags  = df[["sqft_unknown", "sqft_from_line", "sqft_from_bldg"]].to_numpy()

with pm.Model(coords=coords) as m:
    beta_size_g = pm.Normal("beta_size_g", 0, 1)
    s_bsize     = pm.HalfNormal("s_bsize", 0.3)
    z_bsize     = pm.Normal("z_bsize", 0, 1, dims="building")
    beta_size_b = beta_size_g + s_bsize * z_bsize               # partial pooling
    gamma_flag  = pm.Normal("gamma_flag", 0, 0.5, dims="flag")  # one offset per fill level

    mu = (alpha + bldg_eff[b] + walk[b, t] + unit_eff[u]
          + beta_size_b[b] * x_size
          + flags @ gamma_flag
          + X_other @ beta_other)
    pm.StudentT("y", nu=nu, mu=mu, sigma=sigma_row, observed=log_rent)
```

### 1b. Multiple imputation (MI)

**Concept.** Instead of one guess, draw *M* plausible sizes per missing unit from an imputation model that captures the uncertainty. Fit the price model *M* times, once per completed dataset, then pool. With Bayesian fits, pooling is easy: concatenate the posterior draws from all *M* fits. Between-imputation spread then widens the posterior honestly.

The imputation model is fit on sizes only (rent-blind), for example:

`log_size[u] ~ Normal(bed_median[k] + line_eff[line] + bldg_eff[b], tau)`

with line effects nested in buildings. Stated sizes inform it. Units with no history in their line get the building's bedroom-level distribution, *with its spread*. At 423 that spread covers both 300 and 800 sqft rather than collapsing to 700.

**Strengths.** Honest uncertainty. The price model stays unchanged and conjugate. Rent-blind.

**Weaknesses.**
- It costs *M* full fits (M = 5–20, so $10–40 and 2.5–10 hours at today's 30 minutes per fit).
- The imputation model ignores rent, so it can't learn that the cheap unsized units at 423 are probably the small ones. Statisticians call this an "uncongenial" imputation model: it's valid but less informed than the joint model.
- It doesn't fix the slow mixing at 423. Each of the *M* fits still has the slope versus unit-effect trade-off.

**In PyMC.**

```python
# Step 1: imputation model on sizes only (fast, units not rows)
with pm.Model(coords=coords) as imp:
    tau      = pm.HalfNormal("tau", 0.3)
    s_line   = pm.HalfNormal("s_line", 0.3)
    s_bldg   = pm.HalfNormal("s_bldg", 0.3)
    bldg_e   = pm.Normal("bldg_e", 0, s_bldg, dims="building")
    line_e   = pm.Normal("line_e", 0, s_line, dims="line")
    mu_size  = bed_median[k_u] + bldg_e[b_u] + line_e[line_u]
    # Masked array: PyMC automatically creates latent values for the masked (missing) entries
    log_size = pm.Normal("log_size", mu_size, tau,
                         observed=np.ma.masked_invalid(log_size_u), dims="unit")
    idata_imp = pm.sample()

# Step 2: take M posterior draws of the missing sizes -> M completed datasets
draws = az.extract(idata_imp, var_names="log_size_unobserved", num_samples=M)

# Step 3: fit the price model once per completed dataset, then pool
fits = [fit_price_model(fill_sizes(df, draws[:, j])) for j in range(M)]
idata_mi = az.concat(fits, dim="chain")   # pooled posterior
```

---

## 2. Full Bayesian latent size

**Concept.** Put the size model and the price model in *one* joint model. Every unsized unit's log size is a parameter. Two things inform it:

1. **The size model prior:** its bedroom count, line and building (same as the MI imputation model).
2. **The price likelihood:** if a 1BR at 423 rents for $2.3k while sized 1BRs there rent for $5k, the likelihood pulls its latent size toward the small end, given the building's size slope.

This is the textbook answer. Missing sizes get exactly the uncertainty the data supports. The size slope is estimated without the missing-indicator bias. The model is "congenial", meaning imputation and analysis share one model. Using rent to infer size here is a modeling choice inside the likelihood, not a data-cleaning rule, so it doesn't conflict with the rent-blind data rules. It does mean an unsized unit's size estimate depends on its rents.

**In PyMC.**

```python
with pm.Model(coords=coords) as joint:
    # --- size model (unit level) ---
    tau     = pm.HalfNormal("tau", 0.3)
    s_line  = pm.HalfNormal("s_line", 0.3)
    s_bldgS = pm.HalfNormal("s_bldgS", 0.3)
    bldgS   = pm.Normal("bldgS", 0, s_bldgS, dims="building")
    lineS   = pm.Normal("lineS", 0, s_line, dims="line")
    mu_size = bed_median[k_u] + bldgS[b_u] + lineS[line_u]
    log_size = pm.Normal("log_size", mu_size, tau,
                         observed=np.ma.masked_invalid(log_size_u), dims="unit")
    # log_size now mixes observed values and latent parameters (log_size_unobserved)

    # --- price model (row level) ---
    x_size      = log_size[u] - bed_median[k_u[u]]
    beta_size_g = pm.Normal("beta_size_g", 0, 1)
    s_bsize     = pm.HalfNormal("s_bsize", 0.3)
    z_bsize     = pm.Normal("z_bsize", 0, 1, dims="building")
    beta_size_b = beta_size_g + s_bsize * z_bsize
    mu = (alpha + bldg_eff[b] + walk[b, t] + unit_eff[u]
          + beta_size_b[b] * x_size + X_other @ beta_other)
    pm.StudentT("y", nu=nu, mu=mu, sigma=sigma_row, observed=log_rent)

    idata = pm.sample(nuts_sampler="nutpie")   # NUTS handles the slope × latent-size product
```

No `sqft_unknown` flag is needed, because missingness is handled by the latent values. A `sqft_unknown` term can still be added if we think units that hide their size differ in rent beyond their size ("informative missingness").

### Optional extensions

- **Measurement error:** units sometimes state different sizes across listings. Give each unit a true latent size and treat each stated size as true size plus noise.
- **Size-dependent missingness:** small units leave out their size more often. Add `pm.Bernoulli("missing", logit_p=a + b * log_size, observed=is_missing)`. Then "this unit never states a size" itself counts as weak evidence that the unit is small.

### Why it's not a free win here

- **Scale.** About 40% of units are unsized after sizefill (tens of thousands of extra parameters). NUTS can handle that, but our full fit is already about 30 minutes in Gibbs.
- **Fit with our Gibbs sampler.** Confirmed in the code: the sampler already writes Student-t as a normal scale mixture (gibbs.py:12, per-row precision at :1334). So the model is *conditionally* Gaussian in each latent size given the slopes, and in the slopes given the sizes. So it can be Gibbs-sampled in closed form, one more block. The cost is that slope and latent sizes are updated in separate blocks, which is exactly the trade-off where 423 already mixes slowly.
- **423 stays genuinely ambiguous.** "Small rear unit" versus "full-size unit that's cheap" both fit the rents. The latent model represents that ambiguity honestly, so the posterior there is wide and slow to mix. That's correct, but it won't pass a strict R-hat gate without a better sampler step: jointly updating each building's slope with its units' sizes and effects, or NUTS.
- **Rent feeds back into size.** Latent sizes are partly inferred from rent, so the size slope is partly fit to rent-informed sizes. That's coherent Bayes, but if the size model is misspecified it can quietly inflate the size effect. MI's "cut" avoids this.
- **The real fix at 423 is structural.** It's two buildings on one lot under one address. Data's front/rear split removes the ambiguity rather than modeling it.

---

## Summary

| | Sizefill (single) | Multiple imputation | Full Bayesian latent size |
|---|---|---|---|
| Uncertainty in missing size | ignored | yes, from size data only | yes, from size data and rents |
| Uses rent to infer size | no | no | yes, through the likelihood |
| Fit cost | 1× | M× | 1× plus latent parameters, slower mixing |
| Sampler change | none | none | one new block, or NUTS |
| Fixes 423 mixing | partly | no | no; represents the ambiguity honestly |
| When to use | now (base candidate) | as a check on how much fill uncertainty matters | research item, after Data's front/rear split |

The cheapest next step if 423 still fails after sizefill is still the per-building `sqft_unknown` offset: conjugate, one effect per building, and a clean single-change test.
