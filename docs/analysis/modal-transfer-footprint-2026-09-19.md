# Local transfer footprint for a future Modal experiment

Measured locally against the completed expanded analytical dataset and completed **original spline** experiment. No upload, remote execution, posterior compression, fit change, or new posterior load occurred. This is preparation for a remote roundtrip, not evidence that Modal is configured or that a stripped download works.

## Measurements

Each count includes `complete.json` and every file named by that manifest; MiB means 1,048,576 bytes.

| Bundle | Files | Bytes | MiB |
|---|---:|---:|---:|
| Expanded analytical input, `chelsea-expanded-label-floor-analysis-20260919` | 13 | 286,694,054 | 273.41 |
| Completed original spline `fit/` | 24 | 4,391,529,697 | 4,188.09 |
| Completed original spline `protocol/` | 29 | 299,076 | 0.29 |
| Original spline's **matching** label-floor dataset | 10 | 194,019,117 | 185.03 |
| Original spline offline artifact closure inferred below | 63 | 4,585,847,890 | 4,373.41 |

The expanded input compressed to **45,810,869 bytes (43.69 MiB)** as deterministic USTAR plus gzip level 6: **15.98%** of original bytes, or **6.26× smaller**. The stream was discarded through a counting sink; all input files were SHA-256 checked against the unchanged source manifest before and after compression. Repeated measurements produced the same archive digest, `f0b0dac4d25c7bf5066fe4ce18c47fbb41d542d8f4717e554253015f456ffbe1`. Python 3.12.14 / zlib 1.3.2 were used. Compression took approximately three seconds on this machine while other work was active; that is not a controlled speed benchmark.

Expanded input is mostly observations (171,887,255 bytes), expanded projection witnesses (60,959,540), and original label witnesses (48,784,027). The baseline `posterior.nc` alone is **4,341,888,980 bytes**. Its compression ratio was deliberately not measured during the active fit/report job. Baseline fit/protocol/matching-source totals use manifest-listed file sizes and manifest identities; their large contents were not rehashed during this study.

The expanded input plus baseline-sized fit/protocol would total 4,678,522,827 bytes. That is only a planning estimate: **the baseline posterior does not belong to the expanded dataset**, so that combination must never be loaded as an analysis bundle. Measure the actual expanded fit after completion.

## Filesystem closure inferred from the current code

**Remote fitting input:** the entire 13-file expanded analytical bundle, plus the source checkout and its pinned execution environment (`pyproject.toml`, `uv.lock`, and the invoked model/runner code). `bayesian_feature_experiment_v3.load_data` verifies the bundle, then follows reversible projection lineage using its retained sidecars and embedded parent manifests. It does not traverse the original scrape database, raw HTML, external description archive, or parent dataset directories. Scraping credentials are not an input to this fitting path. Keep source/protocol identities unchanged when relocating files; remote runner arguments and output paths belong in the new run's own protocol.

**Offline contributions, residuals, and counterfactuals:** inspection of `BayesianAnalysis.load`, `bayesian_feature_report.build_report`, and `bayesian_source_sensitivity.verify_design` indicates that the completed `fit/`, `protocol/`, and the fit's exact matching dataset bundle are the required data artifacts. A compatible repository/runtime is also required: numerical design reconstruction checks selected local implementation hashes and NumPy/Pandas/SciPy versions against the frozen protocol. Archived Python files alone are not a self-contained runnable environment.

The existing bundle verifier hashes **every manifest-listed file**, even when `retain` selects only a few for further use. Therefore all 24 baseline fit files and all 29 protocol files must be downloaded unchanged; removing `prior.nc`, diagnostics CSVs, or archived code simply because a report does not retain their contents fails verification. This is a manifest-preserving closure, not a proposal to rewrite old manifests.

| Experiment item | Current offline reader dependency inferred from code |
|---|---|
| `trace/` raw Zarr directory | Not opened. Keep `fit/trace-manifest.json` and `fit/storage.json`; the reader checks their metadata relationships and posterior binding. |
| `report-cache/` directory | Not opened. Keep `fit/reporting-cache.json` and the fit's archived `bayesian_report_cache.py`. |
| `reporting-protocol/` directory | Not opened by the inspected offline path. Its manifest hash is recorded inside fit metadata, but the reader does not resolve that directory. |
| Progress files, lock files, generated standalone HTML reports | Not required by the inspected analysis path. |

Omitting those large auxiliary directories from an **analysis download** is an inference, not authorization to delete the durable originals. Raw trace retains warmup and detailed sampler events used for restart/audit/sampler research; report cache supports report recomputation. Offline metadata verification does not independently reverify omitted raw trace bytes.

The main application has an additional closure when annotations are selected: the selection JSON, the complete description-evidence bundle, and the selected source-review and source-issues bundles. Those provide literal evidence and warnings rather than posterior calculations. They must be copied unchanged and selection paths resolved for the destination. Their bytes are **not included** in the table above.

## Reproduce and remaining verification

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.measure_modal_transfer_footprint \
  --dataset data/model/chelsea-expanded-label-floor-analysis-20260919 \
  --experiment data/model/chelsea-bayesian-spline-floor-disk-20260919 \
  --output /tmp/modal-transfer-footprint-new.json
```

The output must not already exist. Source measurement: [script](scripts/measure_modal_transfer_footprint.py). Recorded file inventories, environment, compression digest and evidence limits: `data/model/modal-transfer-footprint-20260919-v2.json`.

Still required: an actual clean-directory/download roundtrip with the correct fitted dataset, bundle integrity checks, successful `BayesianAnalysis.load`, agreed fixed-unit contribution/residual/floor-counterfactual comparisons, and annotated UI checks. Test with raw trace/cache/reporting-protocol directories genuinely absent and verify no fallback to the original workspace. Test extraction and complete source-byte recovery for the upload archive. Separately measure real transfer time, remote setup/compile/sampling/report time, download time, and cost before preferring remote execution. No such roundtrip or remote performance result is claimed here.
