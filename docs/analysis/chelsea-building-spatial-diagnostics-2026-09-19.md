# Spatial structure in the selected building-effect posterior

Update: the [completed source refit](chelsea-reviewed-quarantine-refit-2026-09-19.md)
is now selected. Its repeated spatial diagnostics use the exact 52,653-row source
cohort and confirm essentially unchanged results: five-neighbor Moran's I .22689
[.21263, .24147], or .22226 [.20778, .23698] after excluding all coincident-coordinate
buildings. The report below documents the preceding selected posterior and the
initial investigation; its warning about unreconciled posterior/location cohorts
has been resolved in the repeated analysis.

Nearby buildings have similar unexplained price effects in the selected Chelsea
model. This pattern survives excluding every building that shares identical
coordinates with another building. It motivates a controlled spatial-model
experiment, but does not establish a causal location premium or justify changing
the selected model yet.

| Location subset | Nearest neighbors | Buildings | Moran's I, median [95% posterior interval] |
| --- | ---: | ---: | ---: |
| All verified locations | 5 | 1,129 | .22680 [.21216, .24111] |
| All verified locations | 10 | 1,129 | .19131 [.17896, .20349] |
| Exclude all coincident-coordinate buildings | 5 | 1,094 | .22216 [.20741, .23669] |
| Exclude all coincident-coordinate buildings | 10 | 1,094 | .19106 [.17866, .20334] |

All 24,000 retained joint draws give positive values for all four summaries.
This is a conditional posterior result, not a frequentist p-value or a guarantee
of positive spatial association under different source measurements or priors.
The intervals retain posterior covariance among building effects; they are not
computed from independent draws of each building or from posterior medians.

![Building-effect map and joint posterior spatial intervals](../../data/model/chelsea-building-spatial-figure-final-20260919/spatial-diagnostics.svg)

The map shows posterior medians of building log-rent offsets, centered within
each draw on the 1,129 displayed buildings. It does not display uncertainty per
building; the per-building intervals remain in the artifact. The effect measures
unexplained building differences conditional on the existing feature, unit and
time terms. Higher offsets are not standalone location premiums. Exact-coordinate
overlap also means some map points cover others.

## Source and computation

The selected posterior is
`chelsea-bayesian-reviewed-corrections-floor-disk-20260919`: four chains with
6,000 retained draws each, fitted to 52,863 rows and 1,131 buildings. Location
evidence comes from `chelsea-cohort-spatial-candidates-20260919`, covering all
1,129 buildings in the 52,653-row revised source. Buildings
`202-west-24-street-new_york` and `516-west-20-street-new_york` are absent from that
location cohort and omitted from both primary graphs.

**The posterior has not been refitted to the revised source.** It still includes
the 210 rows awaiting quarantine in the next source fit. The location artifact
is an overlay for this diagnostic; none of its coordinates or candidate streets
have been inserted into the fitted design. Repeat this analysis after the source
refit before using it to assess a spatial extension.

For each draw, let z be its building-offset vector after subtracting its mean
over the displayed building population. The statistic is
`I = (n / sum(W)) * (z' W z) / (z' z)`. W is binary and symmetric: an edge exists
if either building selects the other among its k nearest neighbors. There are
no self edges and no row normalization. Distances use squared chords on the unit
sphere, which preserve spherical angular-distance ordering. Exact distance ties
use building IDs for deterministic ordering. See the primary
[PySAL Moran documentation](https://pysal.org/esda/stable/generated/esda.Moran.html)
for weight conventions and the distinction between the statistic and null-test
calculations.

The analytic randomization expectation is −1/(n−1): −.0008865 for 1,129 buildings
and −.0009149 for 1,094. It is a reference value, not a fitted spatial coefficient
or a null distribution estimated by this analysis. Moran's I is not Pearson
correlation and need not lie in [−1, 1].

The five-neighbor graph has 3,404 undirected edges and three connected components;
the ten-neighbor graph has 6,638 edges and one component. Degrees range from 5–10
and 10–20 respectively because of symmetrization. Both k values were chosen
before computing the first results. The coordinate exclusion is a subsequent
sensitivity check, prompted by graph quality review, not a preregistered test.

There are 67 coincident-coordinate pairs across 11 groups and 35 buildings. Two
groups contain eight buildings apiece: an Eighth Avenue/West 15th–16th Street
group, and a West 23rd–24th Street group. Other overlaps include
`213-west-28-street-new_york`/`maverick-condominium`. These may represent shared
complex locations, coordinate rounding, aliases or source problems; the present
analysis does not adjudicate that distinction. The sensitivity removes every
member, rather than choosing an arbitrary representative, and rebuilds both
neighbor graphs on the remaining buildings. Its graphs have 3,290/6,433 edges
and three/one components. All excluded identities are recorded.

Fresh diagnostics on the joint spatial statistics pass: maximum R-hat 1.000482
for the primary analysis and 1.000532 for the sensitivity;
minimum bulk ESS 9,349/9,716 and tail ESS 13,234/13,276 respectively. The original
parameter, derived and floor diagnostic gates are also verified. No divergences
or depth saturation; minimum energy BFMI .42848. Original posterior, source,
protocol, location and selected-configuration hashes are checked. Only the
building-effect posterior variable is loaded; hashes stream over the multi-GB
posterior file. All inputs are checked again before publication.

## Interpretation and next experiment

Spatially patterned omitted amenities, building age/quality, listing composition,
measurement errors and differing shrinkage can all contribute to this result.
Nearby buildings need not be exchangeable in these respects. A spatial term
would also compete with building offsets: the coordinate and street candidates
add no design rank once building indicators are present. Their decomposition
requires explicit prior assumptions.

After the pending source refit, compare a modest spatially structured building
prior or low-dimensional spatial term against the existing independent building
prior, keeping source and other feature definitions fixed. Evaluate convergence,
amenity-contribution sensitivity, current-unit residual changes, and sensitivity
to the spatial prior. Smaller training residuals alone should not select it.
Neither a spatial term nor street indicators have been fitted or promoted here.

## Artifacts and reproduction

Final primary artifact:
`data/model/chelsea-building-spatial-diagnostics-final-20260919`.
Sensitivity:
`data/model/chelsea-building-spatial-distinct-locations-20260919`.
Figure:
`data/model/chelsea-building-spatial-figure-final-20260919`.
The first diagnostic and first figure are preserved as development artifacts;
the final figure fixes overlapping longitude labels. Diagnostic artifacts contain
every joint statistic, graph edges, centered building summaries, full diagnostic
tables, source bindings and frozen implementation files.

**22 tests pass**, including exact dense/sparse agreement, shift/scale invariance,
joint dependence, exhaustive finite randomization expectation, geographic ties,
all-member coordinate exclusion, source identity, and actual NetCDF reading with
refusal of incorrect dimensions, unmatched sample coordinates, unmixed chains or
tree-depth saturation. These are correctness checks, not sampler benchmarks.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.spatial_group_diagnostics \
  --spatial data/model/chelsea-cohort-spatial-candidates-20260919 \
  --dataset data/model/chelsea-reviewed-price-basis-complete-analysis-20260919 \
  --output data/model/chelsea-building-spatial-diagnostics-final-20260919
```

Add `--exclude-coincident` and use the sensitivity output path for the second
analysis. Run `docs.analysis.scripts.plot_building_spatial_diagnostics` with
`--primary`, `--sensitivity`, and `--output` set to the three paths above to
reproduce the verified SVG. Optional `--preview /tmp/spatial-preview.png` renders
a PNG for visual inspection.
