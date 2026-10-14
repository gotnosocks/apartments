"""Ads that don't fit the unit they are filed under.

The five one-bedroom asks at 110 W 26th St (quarantine-v18) carried the loft
labels 5F, 5R, 3 and 3R, with no square footage and at a third of the lofts'
asks. Nothing in the data rules caught them until a fit failed to converge on
the building. `screen` looks for rows like them across a dataset and sorts
each hit into a tier for reading:

1. A: the row's size doesn't fit its unit or building, and its price is far
   from its unit's or building's other asks.
2. B: the ad's words describe something other than a whole apartment in this
   building: a room share, a shared bath, a nightly or short stay, or a
   neighbourhood more than `FAR_KM` from the building.
3. C: size alone.
4. D: price alone.

The size checks compare each row with its unit's other stated sizes, left out
in turn:
- a stated size more than `SIZE_FACTOR` away from the unit's median;
- no stated size, with its bedroom count's typical size under `SMALL` of the
  unit's median;
- a unit with no stated size in a building with at least three, where the row's
  size (or its bedroom count's typical size) is under `SMALL` of the building's
  10th-percentile size.

Price only flags a row for reading. A row is held out only after someone reads
its whole ad and page and quotes the text or page field behind the verdict, so
`screen`'s output carries no rent and blanks dollar amounts in the snippet. A
read goes into a reads file (`READS`) with a verdict: `keep`, or one of the
quarantine actions or a unit, bedroom or field correction. Non-keep verdicts
go into the next version of the matching data rule. `verdict_problems` checks
a read before it is recorded. `frontier/scripts/ad_fit_screen.py` runs the
screen on a dataset and writes the hits nobody has read yet.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

REVIEWS = Path(__file__).resolve().parents[3] / "config" / "reviews"
# One line for each read: the row, its flags, the verdict and the quote behind it.
READS = tuple(sorted(REVIEWS.glob("ad-fit-reads-*.jsonl")))
# Dataset cohorts the screen has run on, one per line; a test checks that each
# registered dataset is among them.
SCREENED = REVIEWS / "ad-fit-screened.txt"
NTA_CENTRES = REVIEWS / "nta-2020-centres.json"

SIZE_FACTOR = 1.6
SMALL = 0.6
PRICE_FACTOR = 2.0
FAR_KM = 3.0
MIN_SQFT = 100

SIZE_FLAGS = ("size_far", "size_missing_small", "bldg_size_small")
TEXT_FLAGS = ("far_place", "room_share", "shared_bath", "short_stay")
PRICE_FLAGS = ("price_far_unit", "price_far_bldg")
FLAGS = SIZE_FLAGS + TEXT_FLAGS + PRICE_FLAGS
VERDICTS = (
    "keep",
    "quarantine_location_conflict",
    "quarantine_product_scope",
    "quarantine_price_basis",
    "brooklyn_misjoin",
    "unit_split",
    "unit_relabel",
    "correct_bedrooms",
    "correct_square_feet",
)

TERMS = {
    "room_share": (
        r"(?<!living )\broom for rent",
        r"\broom in an? (?:apartment|apt|shared)",
        r"private (?:bed)?room (?:in|available)",
        r"(?:looking for|seeking) (?:a |one )?room ?mate",
        r"room ?mate wanted",
    ),
    "shared_bath": (
        r"shared (?:bath|bathroom|toilet|shower|kitchen)s?\b",
        r"(?:bath|bathroom|toilet)s? (?:is |are )?shared",
        r"share (?:a |the )?(?:bath|bathroom|toilet|kitchen)",
        r"(?:hallway|common) (?:bath|bathroom|toilet)",
    ),
    "short_stay": (
        r"nightly (?:rate|rental|stay|price)s?\b",
        r"per night",
        r"minimum stay",
        r"short[- ]term (?:rental|stay|lease)s? only",
        r"vacation rental",
        r"(?<!no )(?<!or )summer (?:sublet|rental)",
        r"(?:\d|one|two|three|four|five|six) (?:week|month)s? (?:only|sublet|sublease)",
    ),
}
TERM_RX = {k: re.compile("|".join(f"(?:{t})" for t in v)) for k, v in TERMS.items()}
NEAR = (
    r"\b(?:in|located in|heart of|apartment in|unit in|steps (?:to|from)|near"
    r"|close to|minutes? (?:to|from)) (?:the )?(?:beautiful |historic |prime )?"
)
# Building names and phrases that read like a far place.
PLACE_FALSE_ALARMS = re.compile(
    r"kensington house|brooklyn fare|clinton (?:hill )?park"
)
DOLLARS = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?k?")


def loo_median(values: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Each row's group median over the group's non-missing values, with the
    row itself left out when it has a value; NaN when nothing is left."""
    values = np.asarray(values, float)
    out = np.full(len(values), np.nan)
    ok = ~np.isnan(values)
    frame = pd.DataFrame({"v": values[ok], "g": np.asarray(groups)[ok]})
    pos = np.flatnonzero(ok)
    for idx in frame.groupby("g", sort=False).indices.values():
        n = len(idx)
        if n < 2:
            continue
        order = np.argsort(frame.v.to_numpy()[idx], kind="stable")
        s = frame.v.to_numpy()[idx][order]
        rank = np.empty(n, int)
        rank[order] = np.arange(n)
        rest = n - 1

        def at(k):
            # The k-th smallest of the group with the row at `rank` left out.
            return s[np.where(k < rank, k, k + 1)]

        if rest % 2:
            med = at(np.full(n, rest // 2))
        else:
            med = (at(np.full(n, rest // 2 - 1)) + at(np.full(n, rest // 2))) / 2
        out[pos[idx]] = med
    # Rows with no value of their own get their whole group's median.
    full = frame.groupby("g", sort=False).v.median()
    missing = ~ok
    out[missing] = pd.Series(np.asarray(groups)[missing]).map(full).to_numpy(float)
    return out


def place_centres(path: Path = NTA_CENTRES) -> dict[str, list[tuple[float, float]]]:
    """Name parts of the 2020 NTAs, each with the centres of the NTAs that use it."""
    centres: dict[str, list[tuple[float, float]]] = {}
    for a in json.loads(path.read_text()):
        for part in re.split(r"[-()]", a["ntaname"]):
            part = part.strip().lower()
            if len(part) >= 5 and part not in {
                "north",
                "south",
                "east",
                "west",
                "central",
            }:
                centres.setdefault(part, []).append((a["lat"], a["lon"]))
    return centres


def _km(lat, lon, a, b):
    return math.hypot((lat - a) * 111.2, (lon - b) * 111.2 * 0.757)


def screen(
    frame: pd.DataFrame,
    text: pd.Series,
    coords: pd.DataFrame,
    centres: dict[str, list[tuple[float, float]]] | None = None,
) -> pd.DataFrame:
    """The rows of `frame` with at least one flag, each with its tier.

    `text` holds each row's ad text, lower-cased, on `frame`'s index, and
    `coords` holds each building's `latitude` and `longitude`, indexed by
    building. The result carries no rent, and its snippet has dollar amounts
    blanked."""
    frame = frame.reset_index(drop=True)
    text = pd.Series(np.asarray(text, object)).fillna("")
    centres = place_centres() if centres is None else centres
    sq = pd.to_numeric(frame.square_feet, errors="coerce")
    sq = sq.where(sq > MIN_SQFT).to_numpy(float)
    beds = frame.bedrooms.to_numpy(float)
    unit = frame.unit_id.to_numpy()
    building = frame.building.to_numpy()
    unit_sq = loo_median(sq, unit)
    typical = pd.Series(sq).groupby(beds).median()
    typ_sq = pd.Series(beds).map(typical).to_numpy(float)
    p10 = pd.Series(sq).groupby(building).quantile(0.1)
    n_sq = pd.Series(~np.isnan(sq)).groupby(building).sum()
    bld_p10 = pd.Series(building).map(p10).to_numpy(float)
    bld_n = pd.Series(building).map(n_sq).to_numpy()
    unit_any = pd.Series(~np.isnan(sq)).groupby(unit).transform("any").to_numpy()

    flags = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        flags["size_far"] = np.abs(np.log(sq / unit_sq)) > math.log(SIZE_FACTOR)
        flags["size_missing_small"] = np.isnan(sq) & (typ_sq < SMALL * unit_sq)
        flags["bldg_size_small"] = (
            ~unit_any
            & (bld_n >= 3)
            & (np.where(np.isnan(sq), typ_sq, sq) < SMALL * bld_p10)
        )
        lr = frame.log_rent.to_numpy(float)
        key = pd.Series(building).astype(str) + "|" + pd.Series(beds).astype(str)
        flags["price_far_unit"] = np.abs(lr - loo_median(lr, unit)) > math.log(
            PRICE_FACTOR
        )
        flags["price_far_bldg"] = np.abs(
            lr - loo_median(lr, key.to_numpy())
        ) > math.log(PRICE_FACTOR)

    phrase = {k: np.full(len(frame), None, object) for k in TEXT_FLAGS}
    place_rx = re.compile(
        NEAR
        + "("
        + "|".join(re.escape(k) for k in sorted(centres, key=len, reverse=True))
        + r")\b(?! (?:ave|avenue|st|street|sq|square|pl|place|park)\b)"
    )
    lat = coords.latitude.reindex(building).to_numpy(float)
    lon = coords.longitude.reindex(building).to_numpy(float)
    for i, ad in text.items():
        for k, rx in TERM_RX.items():
            if m := rx.search(ad):
                phrase[k][i] = m.group(0)
        if np.isnan(lat[i]):
            continue
        for m in place_rx.finditer(PLACE_FALSE_ALARMS.sub(" ", ad)):
            d = min(_km(lat[i], lon[i], a, b) for a, b in centres[m.group(1)])
            if d > FAR_KM:
                phrase["far_place"][i] = m.group(0)
                break
    for k in TEXT_FLAGS:
        flags[k] = pd.notna(phrase[k])

    hit = pd.DataFrame(flags)
    size = hit[list(SIZE_FLAGS)].any(axis=1)
    words = hit[list(TEXT_FLAGS)].any(axis=1)
    price = hit[list(PRICE_FLAGS)].any(axis=1)
    tier = np.select([size & price, words, size, price], ["A", "B", "C", "D"], "")
    rows = []
    for i in np.flatnonzero(tier != ""):
        ad = text[i]
        found = [k for k in FLAGS if hit.at[i, k]]
        rows.append(
            dict(
                audit_id=frame.at[i, "audit_id"],
                source_listing_id=str(frame.at[i, "source_listing_id"]),
                building=building[i],
                unit_id=unit[i],
                neighbourhood=frame.at[i, "neighbourhood"],
                period=str(frame.at[i, "price_at"])[:7],
                tier=str(tier[i]),
                flags=found,
                bedrooms=None if np.isnan(beds[i]) else float(beds[i]),
                square_feet=None if np.isnan(sq[i]) else float(sq[i]),
                unit_rows=int((unit == unit[i]).sum()),
                unit_square_feet=None if np.isnan(unit_sq[i]) else float(unit_sq[i]),
                phrases={k: phrase[k][i] for k in TEXT_FLAGS if phrase[k][i]},
                snippet=DOLLARS.sub("$...", ad[:600]),
            )
        )
    return pd.DataFrame(rows)


def read_ids() -> frozenset:
    """Audit ids in the reads files."""
    ids = set()
    for path in READS:
        with open(path) as f:
            ids |= {json.loads(line)["audit_id"] for line in f if line.strip()}
    return frozenset(ids)


def verdict_problems(read: dict) -> list[str]:
    """What keeps a read from being recorded: an unknown verdict, or a non-keep
    verdict without a quote from the ad or the page, or one resting on price."""
    problems = []
    verdict = read.get("verdict")
    if verdict not in VERDICTS:
        problems.append(f"unknown verdict {verdict!r}")
    if verdict == "keep":
        return problems
    quote = (read.get("quote") or "").strip()
    if read.get("quote_source") not in ("ad", "page"):
        problems.append("quote_source must be 'ad' or 'page'")
    if not DOLLARS.sub("", quote).strip(" .,;:-"):
        problems.append("a hold-out or correction needs a quote that is not a price")
    if not read.get("reason"):
        problems.append("no reason")
    return problems
