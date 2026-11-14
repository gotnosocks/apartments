"""Recode studio-coded rows on 5 or more rooms from their unit's 1+ bedroom ads (rule H1).

    python -m rentfrontier.b0studiohistory SRC
    python -m rentfrontier.b0studiohistory SRC --out OUT

StreetEasy codes some apartments of 5 or more rooms as studios. In S17
(`docs/notes/studio-rooms-2026-11-14.md`) such rows asked more than L1 expected for a studio
when their unit page also held an ad coded with 1 or more bedrooms within two years. That
test is rule H1. Here I give those rows the bedroom count of the unit's other ads, reading
coded fields only and never ad text.

I read SRC's `rows.parquet`, the ads file of SRC's own pipeline build (the manifest's
`build.ads`, checked against its SHA-256) and the room counts in the listing-codes file
(`CODES`). Then:

1. I mark a row when
   - it is coded as a studio,
   - its listing has between 5 and 20 coded rooms, since S16 and S17 treated larger counts
     as feed errors,
   - its unit page holds another ad coded with 1 or more bedrooms, put on the market within
     730 days of the row's ad, before or after it.

   The unit page is the ads file's `unit_id`. SRC's `unit_id` is often only a piece of the
   page, because the pipeline cuts a unit's history at each change of bedroom count
   (`unit-splits-v4`). On L1's dataset 230 marked rows have evidence ads that are also rows,
   and for 224 of them every such ad has another `unit_id`. I leave SRC's `unit_id` as it
   is.
2. For a row held out by the latest split, I keep only the evidence ads put on the market
   before the row's ad, since their coding was known when the row's ad went up
   (`docs/leak-free-scoring.md`). For a training row I keep ads on both sides. The split
   ignores bedrooms, so `splits.latest_split` draws the same rows from SRC and OUT.
3. I give the row the bedroom count of the evidence ad nearest to it in time. The row stays a
   studio in three cases:
   - several ads lie at that distance and give different counts;
   - the count is at least the row's coded rooms, as when a 5-room row would get 5
     bedrooms, which suggests the page mixes in another apartment;
   - the row is held out and has no earlier evidence ad.

   The guard on rooms is mine. S17's H1 has none, and S17's H2 (an ad's rooms within 1 of
   the row's) is a stricter variant I left unwritten.

Without `--out` I print the counts and write nothing. With it I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with `bedrooms` recoded as in step 3.
- `recoded.parquet`: the marked rows and their evidence, as `evidence` gives them.
- `set_aside.parquet`: SRC's, copied.
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `studio_history` entry
  giving SRC's path and rows SHA-256, the paths and SHA-256 of the ads and codes files, and
  the counts of `counts`.

SRC stays as it is, and OUT must not exist yet. `recode` returns its frame unchanged unless
it is given `rule=RULE`.

On L1's dataset (`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`) step 1 marks 243
rows (24 held out) in 228 units and 161 buildings, matching S17. Step 3 recodes 227 of them
in 216 units and 153 buildings, 216 in training and 11 held out, to 1 bedroom (82 rows),
2 (82), 3 (48) and 4 (15). On 28 recoded rows the evidence ads disagree, and I take the
nearest ad's count. The guard on rooms keeps 4 rows as studios (1 held out), all 5-room rows
whose nearest ad gives 5 bedrooms. Another 12 held-out rows have no earlier evidence ad, and
no row ends in a tie.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import splits
from .b0data import sha256
from .registry import EXTERNAL_ROOT

RULE = "studio-history-h1"
NEAR_DAYS = 730
ROOMS = (5, 20)
CODES = Path(
    os.environ.get(
        "FRONTIER_LISTING_CODES",
        EXTERNAL_ROOT / "listing-codes" / "20261023-ks" / "listing-codes.parquet",
    )
)
RECODED = "recoded"
AT_ROOMS = "bedrooms reach rooms"
TIE = "tie"
NO_EARLIER_AD = "no earlier ad"


def _counts_of(ads: pd.Series) -> tuple:
    return tuple(sorted({float(b) for b in ads}))


def evidence(
    frame: pd.DataFrame, ads: pd.DataFrame, codes: pd.DataFrame, heldout: np.ndarray
) -> pd.DataFrame:
    """The rows of `frame` that step 1 marks, indexed by listing id in `frame`'s order.

    `frame` needs `listing_id`, `building`, `unit_id` and `bedrooms`; `ads` needs
    `listing_id`, `unit_id`, `on_day` and `bedrooms`; `codes` needs `listing_id` and `rooms`.
    `heldout` is the split's mask over `frame`. The columns are:

    - `position`: the row's position in `frame`.
    - `heldout`, `building`, `unit` (building and `unit_id`) and `rooms`.
    - `ads_near`: the evidence ads of step 1. `ads_kept` counts those step 2 keeps.
    - `disagree`: whether the kept ads give more than one bedroom count.
    - `days`: the distance in days to the nearest kept ad, missing without one.
    - `nearest`: the listing ids of the kept ads at that distance, and `nearest_bedrooms`
      their bedroom counts.
    - `chosen`: the nearest ads' count when they agree on one.
    - `bedrooms`: the count step 3 gives, missing when the row stays a studio.
    - `outcome`: `RECODED`, `AT_ROOMS`, `TIE` or `NO_EARLIER_AD`.

    Listing ids must be unique in `frame` and in `ads`.
    """
    lid = frame.listing_id.astype(str)
    # `recoded` writes by position, and the merges below pair ads by listing id, so a
    # repeated id would recode one of its rows and leave the others.
    for name, listing_ids in (("rows", lid), ("ads", ads.listing_id)):
        if listing_ids.duplicated().any():
            raise ValueError(f"the {name} repeat listing ids")
    rooms = lid.map(codes.set_index(codes.listing_id.astype(str)).rooms)
    rows = pd.DataFrame(
        {
            "listing_id": lid.to_numpy(),
            "position": np.arange(len(frame)),
            "heldout": np.asarray(heldout, dtype=bool),
            "building": frame.building.to_numpy(),
            "unit": (
                frame.building.astype(str) + "|" + frame.unit_id.fillna("row:" + lid)
            ).to_numpy(),
            "rooms": rooms.to_numpy(),
        }
    )
    rows = rows[
        (frame.bedrooms == 0).to_numpy() & rows.rooms.between(*ROOMS).to_numpy()
    ]
    pages = ads[ads.unit_id.notna()].assign(
        listing_id=lambda a: a.listing_id.astype(str),
        on_day=lambda a: pd.to_datetime(a.on_day),
    )
    mine = rows.merge(
        pages[["listing_id", "unit_id", "on_day"]].rename(columns={"unit_id": "page"}),
        on="listing_id",
    )
    others = pages.loc[
        pages.bedrooms >= 1, ["listing_id", "unit_id", "on_day", "bedrooms"]
    ]
    pairs = mine.merge(
        others.rename(
            columns={
                "listing_id": "ad",
                "unit_id": "page",
                "on_day": "ad_day",
                "bedrooms": "ad_bedrooms",
            }
        ),
        on="page",
    )
    pairs = pairs[pairs.ad != pairs.listing_id]
    pairs = pairs.assign(gap=(pairs.ad_day - pairs.on_day).dt.days)
    pairs = pairs[pairs.gap.abs() <= NEAR_DAYS]
    kept = pairs[~pairs.heldout | (pairs.gap < 0)].assign(
        distance=lambda p: p.gap.abs()
    )
    nearest = kept[
        kept.distance == kept.groupby("listing_id").distance.transform("min")
    ]
    table = (
        pairs.groupby("listing_id")
        .agg(
            position=("position", "first"),
            heldout=("heldout", "first"),
            building=("building", "first"),
            unit=("unit", "first"),
            rooms=("rooms", "first"),
            ads_near=("ad", "size"),
        )
        .sort_values("position")
    )
    ids = table.index
    by_kept = kept.groupby("listing_id")
    by_nearest = nearest.groupby("listing_id")
    table["ads_kept"] = by_kept.size().reindex(ids, fill_value=0).astype("int64")
    table["disagree"] = (
        by_kept.ad_bedrooms.nunique().gt(1).reindex(ids, fill_value=False)
    )
    table["days"] = by_nearest.distance.first().reindex(ids)
    table["nearest"] = by_nearest.ad.agg(lambda a: tuple(sorted(a))).reindex(ids)
    table["nearest_bedrooms"] = by_nearest.ad_bedrooms.agg(_counts_of).reindex(ids)
    table["chosen"] = table.nearest_bedrooms.map(
        lambda k: k[0] if isinstance(k, tuple) and len(k) == 1 else np.nan
    ).astype("float64")
    table["bedrooms"] = table.chosen.where(table.chosen < table.rooms)
    table["outcome"] = np.select(
        [table.bedrooms.notna(), table.chosen.notna(), table.ads_kept > 0],
        [RECODED, AT_ROOMS, TIE],
        NO_EARLIER_AD,
    )
    return table


def recoded(frame: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """A copy of `frame` with the bedroom counts `table`'s recoded rows take."""
    done = table[table.outcome == RECODED]
    out = frame.copy()
    column = out.columns.get_loc("bedrooms")
    out.iloc[done.position.to_numpy(), column] = done.bedrooms.astype(
        out.bedrooms.dtype
    ).to_numpy()
    return out


def recode(
    frame: pd.DataFrame,
    ads: pd.DataFrame,
    codes: pd.DataFrame,
    heldout: np.ndarray,
    rule: str | None = None,
) -> pd.DataFrame:
    """`frame` itself when `rule` is None, or with H1's recodes when it is `RULE`."""
    if rule is None:
        return frame
    if rule != RULE:
        raise ValueError(f"unknown rule {rule!r}; the only rule is {RULE!r}")
    return recoded(frame, evidence(frame, ads, codes, heldout))


def counts(table: pd.DataFrame) -> dict:
    """Rows, units and buildings of `evidence`'s table, as marked, recoded and left alone."""

    def scope(t: pd.DataFrame) -> dict:
        return {
            "rows": len(t),
            "training": int((~t.heldout).sum()),
            "heldout": int(t.heldout.sum()),
            "units": int(t.unit.nunique()),
            "buildings": int(t.building.nunique()),
        }

    done = table[table.outcome == RECODED]
    return {
        "marked": scope(table),
        "recoded": scope(done)
        | {
            "bedrooms": {
                str(int(k)): int(n)
                for k, n in done.bedrooms.value_counts().sort_index().items()
            },
            "ads_disagree": int(done.disagree.sum()),
        },
        "unchanged": {
            outcome: scope(table[table.outcome == outcome])
            for outcome in (AT_ROOMS, TIE, NO_EARLIER_AD)
        },
    }


def run(src: Path, out: Path | None = None, codes_path: Path = CODES) -> dict:
    """The `studio_history` entry for SRC, after writing OUT when `out` is given."""
    manifest = json.loads((src / "manifest.json").read_text())
    ads_file = manifest["build"]["ads"]
    if sha256(Path(ads_file["path"])) != ads_file["sha256"]:
        raise SystemExit(f"{ads_file['path']} does not match the manifest's SHA-256")
    needed = ["listing_id", "audit_id", "building", "unit_id", "bedrooms", "price_at"]
    columns = None if out else needed
    frame = pd.read_parquet(src / "rows.parquet", columns=columns)
    ads = pd.read_parquet(
        ads_file["path"], columns=["listing_id", "unit_id", "on_day", "bedrooms"]
    )
    codes = pd.read_parquet(codes_path, columns=["listing_id", "rooms"])
    table = evidence(frame, ads, codes, splits.latest_split(frame))
    entry = {
        "source": str(src),
        "source_rows_sha256": manifest["rows_sha256"],
        "rule": RULE,
        "description": "a studio-coded row on 5 to 20 coded rooms takes the bedroom count of "
        "the nearest ad of its unit page coded 1 or more bedrooms within 730 days, earlier "
        "ads only for a row the latest split holds out; a tie at the nearest distance, or "
        "a count at or above the row's coded rooms, leaves it a studio",
        "ads": ads_file["path"],
        "ads_sha256": ads_file["sha256"],
        "codes": str(codes_path),
        "codes_sha256": sha256(codes_path),
        **counts(table),
    }
    if out is None:
        return entry
    out.mkdir(parents=True, exist_ok=False)
    recoded(frame, table).to_parquet(out / "rows.parquet", index=False)
    table.reset_index().to_parquet(out / "recoded.parquet", index=False)
    shutil.copyfile(src / "set_aside.parquet", out / "set_aside.parquet")
    entry["recoded_sha256"] = sha256(out / "recoded.parquet")
    manifest |= {"rows_sha256": sha256(out / "rows.parquet"), "studio_history": entry}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return entry


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--codes", type=Path, default=CODES)
    args = p.parse_args(argv)
    print(json.dumps(run(args.src, args.out, args.codes), indent=2))


if __name__ == "__main__":
    main()
