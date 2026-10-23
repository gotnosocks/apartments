# Kitchen sink thread: handoff

Ben asked on 2026-10-23 for a kitchen sink model: fit 8's surface, building levels and floor curves, plus every unit and building column we can code, without map or distance columns. He also asked for a twin with the surface at 150 m. Every aggregate over a building's or unit's ads reads only the row's ad and earlier training ads (Ben, 2026-10-23 21:09Z). The predictions are in `docs/notes/kitchen-sink-predictions-2026-10-23.md`.

## Code

- `frontier/src/rentfrontier/listing_codes.py` writes every code list of each listing's latest raw record to `/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet`.
- `frontier/src/rentfrontier/building_zones_kitchen_sink.py` builds the design (fit 8's, with the elevator, doorman, gym and top floor rebuilt past-only, plus the `ad:`, `bld:` and `umean:` groups).
- `frontier/src/rentfrontier/building_zones_kitchen_sink_150m.py` rebuilds the surfaces at 150 m.
- Scratch checks live in `/data1/apartments/tmp/kitchen-sink/` (`subset_design.py`, `full_design.py`, `waves.py`).

## Fits

| fit | run name | state |
|---|---|---|
| (a) 1 km | `ks-jointamp-w1000` | not launched |
| (b) 150 m | `ks150-jointamp-w1000` | not launched; H100 |

Launch line for (a), from serve/master after a fetch:

    ops/modal-fit --input /data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet \
      --dataset /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc \
      --split latest COMMIT ks-jointamp-w1000 building-zones-kitchen-sink b0 4 300 1000 5 \
      --seed 20261021 --joint-amp --no-loo --no-heldout

## Next

After each fit: convergence checks, PSIS-LOO on shared rows against the served fit and the latest split, the results note with coefficient intervals, within against between next to fit 4, the change in the rebuilt base coefficients against fit 8, the explainer artifact, and a copy of the note in `/mnt/project-files/modeling/` when that is reachable.
