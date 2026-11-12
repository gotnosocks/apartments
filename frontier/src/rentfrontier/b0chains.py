"""Write a B0 dataset with each chain of reposted ads collapsed into one row.

    python -m rentfrontier.b0chains SRC LINKS OUT

A lister who wants an ad back at the top of the search results closes it and opens a new ad
for the same apartment, usually the same day and often under a new unit label ("2" becomes
"2A"). StreetEasy starts a unit page for the new label, so the pipeline gives the new ad its
own unit id, and the dataset holds a row for every ad of the chain. A renter saw one offer of
one apartment through all of them. Only the chain's last ad went off the market, so only its
last ask is a closing ask. The outlier sprint of 2026-11-11 screened for these reposts and
had readers check a sample (`docs/notes/outlier-sprint-2026-11-11.md`, under "Reposts under
a new label").

LINKS is a parquet file with a row for each repost: `earlier` and `later`, the listing ids
of an ad and of the ad its lister opened in its place. I read it with SRC's `rows.parquet`
and the ads file of SRC's own pipeline build (the manifest's `build.ads`, checked against
its SHA-256), and then:

1. I keep the links with both ads in the ads file, so that a chain stops where SRC's build
   stopped. An ad with two links on the same side, or a ring of links, ends the run.
2. I follow the links from each ad with no earlier ad, which gives every linked ad its
   chain and its place in it.
3. Among a chain's rows in SRC I keep the row of the latest ad and drop the others. The kept
   row stays as SRC has it, with its own listing id, ask and days, so every table keyed by
   listing id still matches it. When the chain's last ad has no row in SRC (a furnished
   repost, say), the kept row is the latest ad with one, and its `replaced` is true: its
   ask stood on the market and did not close.
4. I give the kept row a unit id. A unit id is established for a chain when SRC holds a
   row of it outside the chain: the lister used that label at another time. When exactly
   one of the unit ids of the chain's rows is established, the kept row takes it, and the
   offer joins that label's history. With none, the kept row keeps its own unit id. With
   several, a wrong link could merge the histories of two apartments, so the kept row keeps
   its own unit id there too. Rows outside chains keep their unit ids.

I write OUT with:

- `rows.parquet`: SRC's kept rows in SRC's order, with `unit_id` set as in step 4 and four
  columns added. `chain_ads` counts the ads of the row's chain (1 outside a chain).
  `on_day` is the day the offer came on the market: the on-market day of the chain's first
  ad, or of the row's own ad outside a chain. `off_day` is the off-market day of the
  chain's last ad, or of the row's own ad outside a chain, and it is missing while that ad
  is open. The days from `on_day` to `off_day` count the offer's time on the market over
  the whole chain. `replaced` is described under step 3.
- `collapsed.parquet`: the dropped rows as SRC has them, each with `kept_listing_id`.
- `set_aside.parquet`: SRC's, copied.
- `manifest.json`: SRC's manifest with `rows`, `latest_day_how`, `flags` and `rows_sha256`
  updated for the kept rows, and a `chains` entry giving SRC's path and rows SHA-256, the
  path and SHA-256 of LINKS, and the counts of links, chains, dropped rows and moved rows.

The module leaves each kept row's ask alone, and `b0closing` and `b0closingraise` change
asks a listing at a time, so the two rules give the same rows in either order.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from .b0data import sha256


def chains(links: pd.DataFrame) -> pd.DataFrame:
    """A row for each ad of `links` (columns `earlier`, `later`): `listing_id`, `chain` (the
    listing id of the chain's first ad), `place` (0 for the first ad) and `ads` (the chain's
    length)."""
    for side in ("earlier", "later"):
        twice = links[side][links[side].duplicated()]
        if len(twice):
            raise SystemExit(
                f"LINKS gives {twice.iloc[0]} as the {side} ad of two links"
            )
    after = dict(zip(links.earlier, links.later))
    walked = []
    for first in sorted(set(links.earlier) - set(links.later)):
        ad, place = first, 0
        while ad is not None:
            walked.append((ad, first, place))
            ad, place = after.get(ad), place + 1
    table = pd.DataFrame(walked, columns=["listing_id", "chain", "place"])
    if len(table) != len(set(links.earlier) | set(links.later)):
        raise SystemExit("LINKS holds a ring of links")
    table["ads"] = table.groupby("chain").place.transform("size")
    return table


def kept_units(unit: pd.Series, chain: pd.Series) -> pd.DataFrame:
    """For each chain with a row in `unit` (the unit id of each row; `chain` gives its
    chain, missing outside one): `established`, how many of the unit ids of the chain's
    rows have a row outside the chain, and `unit`, the first of them."""
    inside = chain.notna().to_numpy()
    here = (
        pd.DataFrame({"chain": chain[inside].to_numpy(), "unit": unit[inside]})
        .value_counts()
        .rename("rows")
        .reset_index()
    )
    total = unit.value_counts()
    held = here[here.unit.map(total).to_numpy() > here.rows.to_numpy()]
    return (
        held.sort_values(["chain", "unit"])
        .groupby("chain")
        .unit.agg(established="size", unit="first")
    )


def collapse(src: Path, links_path: Path, out: Path) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    ads_file = manifest["build"]["ads"]
    if sha256(Path(ads_file["path"])) != ads_file["sha256"]:
        raise SystemExit(f"{ads_file['path']} does not match the manifest's SHA-256")
    ads = pd.read_parquet(ads_file["path"], columns=["listing_id", "on_day", "off_day"])
    on_day = pd.Series(ads.on_day.to_numpy(), index=ads.listing_id.astype(str))
    off_day = pd.Series(ads.off_day.to_numpy(), index=on_day.index)
    links = pd.read_parquet(links_path, columns=["earlier", "later"]).astype(str)
    built = links.earlier.isin(on_day.index) & links.later.isin(on_day.index)
    table = chains(links[built]).set_index("listing_id")

    frame = pd.read_parquet(src / "rows.parquet")
    lid = frame.listing_id.astype(str)
    if lid.duplicated().any():
        raise SystemExit("SRC holds two rows of one listing")
    chain = lid.map(table.chain)
    place = lid.map(table.place)
    if (frame.building.groupby(chain).nunique() > 1).any():
        raise SystemExit("LINKS joins ads of two buildings")
    last = place.groupby(chain).transform("max")
    drop = (chain.notna() & (place < last)).to_numpy()
    held = kept_units(frame.unit_id, chain)
    one = chain.map(held.established).eq(1).to_numpy()
    unit = frame.unit_id.where(~one, chain.map(held.unit))
    latest = ~drop & chain.notna().to_numpy()
    kept_of = pd.Series(lid[latest].to_numpy(), index=chain[latest].to_numpy())
    ends = table.index[table.place + 1 == table.ads]
    end_day = pd.Series(
        ends.map(off_day).to_numpy(), index=table.chain[ends].to_numpy()
    )

    collapsed = frame[drop].assign(kept_listing_id=chain[drop].map(kept_of).to_numpy())
    kept = frame[~drop].assign(
        unit_id=unit[~drop],
        chain_ads=lid[~drop].map(table.ads).fillna(1).astype("int64"),
        on_day=chain[~drop].map(on_day).fillna(lid[~drop].map(on_day)),
        off_day=chain[~drop]
        .map(end_day)
        .where(chain[~drop].notna(), lid[~drop].map(off_day)),
        replaced=(place[~drop] + 1 < lid[~drop].map(table.ads)).to_numpy(),
    )
    out.mkdir(parents=True, exist_ok=False)
    kept.to_parquet(out / "rows.parquet", index=False)
    collapsed.to_parquet(out / "collapsed.parquet", index=False)
    shutil.copy(src / "set_aside.parquet", out / "set_aside.parquet")
    in_rows = chain.dropna()
    several = chain[~drop].map(held.established).gt(1)
    manifest |= {
        "rows": len(kept),
        "latest_day_how": kept.latest_day_how.value_counts().to_dict(),
        "flags": {name: int(kept[name].sum()) for name in manifest.get("flags", {})},
        "rows_sha256": sha256(out / "rows.parquet"),
        "chains": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "rule": "a chain of reposted ads keeps the row of its latest ad, under the "
            "chain's one established unit id when it has one",
            "links": str(links_path),
            "links_sha256": sha256(links_path),
            "links_read": len(links),
            "links_outside_build": int((~built).sum()),
            "chains": int(table.chain.nunique()),
            "chains_with_rows": int(in_rows.nunique()),
            "rows_in_chains": len(in_rows),
            "rows_dropped": int(drop.sum()),
            "kept_rows_replaced": int(kept.replaced.sum()),
            "kept_rows_moved": int((kept.unit_id != frame.unit_id[~drop]).sum()),
            "chains_with_several_established": int(several.sum()),
            "unit_ids_before": int(frame.unit_id.nunique()),
            "unit_ids_after": int(kept.unit_id.nunique()),
            "collapsed_sha256": sha256(out / "collapsed.parquet"),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("links", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    manifest = collapse(args.src, args.links, args.out)
    print(json.dumps(manifest["chains"], indent=2))


if __name__ == "__main__":
    main()
