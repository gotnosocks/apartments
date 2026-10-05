# Data improvements — handoff

Updated 2026-10-05 19:45 ET. Thread owner: the Data improvements project thread (bridge session on thelio).

## State
- **Greenwich Village fold-in: done on the data side.** #292 (cohort, listing extras, alias table
  `config/unit-aliases/wv-gv-20261005.jsonl`, rule `unit-labels-v5`, feature sets
  `nb3-coded-v1` / `nb3-prevprice-v1` / `nb3-lineface-v1` on the three-neighbourhood snapshots
  dated 20261005) and #297 (three-name neighbourhood labels in term text, listing summaries and
  the rent map's area caveat). Snapshot names carry the pre-rebase commits 2d5b3b6 / 77068ea.
- **Modeling owns the GV fits** (units `frontier-gvfit`, `frontier-gvfrontier`,
  `frontier-gvrefit-early`; logs in `/data1/apartments/tmp/bridge/`). Plan for the night of Oct 5:
  GV explorations (lineface pair ~20:00 ET), served design + nb3-coded-v1 refit ~21:30 ET at
  3600 draws (4500 would overrun 2 h on 21% more rows), then nb3-coded-v1 vs nb3-prevprice-v1 on
  the latest split ~23:30–05:30, then a prevprice rows serving fit in the morning if it wins by
  more than 2 SE. Modeling reports the paired numbers to this thread.
- **Prevprice (pre-GV):** passed the leak-free latest-split gate (+75.5 ± 15.7 PSIS-LOO, ~4.8 SE)
  but its rows serving fit overran the 2 h cap (16:02 Oct 5); not served, not retried on the old
  data. Prevprice is slower per draw, so the GV serving fit is borderline on time.

- **LPC as-of (#307, merged):** `nb3-coded-v2` / `nb3-prevprice-v2` date the landmark and
  historic-district flags by the LPC's designation dates (`external lpc`, snapshot
  `/data1/apartments/external/lpc/20261005-8946d6f/`). This fixes 94 + 37 rows flagged for
  designations made after the listing, and puts 420 condo-lot rows in a district MapPLUTO leaves
  blank. Ben approved moving tonight's GV refit and the latest-split pair to v2 (unit
  `frontier-gvrefit-v2`, from ~21:00 ET).
- **Footprints as of the listing year: measured, NOT shipped.** Neighbours built after a listing
  change 708 rows' building sides, but only ~50 rows' facing features (side street versus rear).
  Dating them cost 154 s per feature build against 10 s. The patch (`nb3-coded-v3`,
  `building_sides_as_of`) is kept at `/data1/apartments/tmp/suspect/lpc/sides-as-of.patch` in
  case it is wanted later.

## Next
- Relay to Ben: the lineface paired score and the prevprice outcome when Modeling sends them.
- After the GV switch, Modeling updates the "map grows less than the median ask" note figures.
- #222 `unit-labels-v4` waits for a batch full fit; the next unit-labels version should add the
  Morton Square + 100 Morton join.
- Backlog: other present-day MapPLUTO fields (numfloors, unitsres, bldgclass for condo
  conversions; DOB permits would date them), Jane St registry fix, 13 excluded new-building rows, confirm
  q-v3/q-v4 on held-out rows, gross rent, unit splits, relist gap.

## Rules that bind this thread
- Rule-based changes, one PR per change, no future information; descriptions never override coded
  fields; no new LLM calls, image downloads or scraping beyond what Ben approved.
- PRs: reviewer subagent, annotated `archive/pr-N` tag, `gh pr merge N --squash --match-head-commit`.
- Tests through `ops/job light` with `TMPDIR=/data1/apartments/tmp/suspect/tmpdir`; venv
  `/data1/apartments/venvs/data-line`, ruff via `uvx ruff`.
