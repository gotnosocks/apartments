"""The Deals page's table: the ads on the market, scored by the drift model.

`python -m rentfrontier.drift_deals publish` writes the site's `deals/` folder: `deals.json`,
one row per ad on the market on the scoring day, `meta.json` (the run, the scoring day, the
model's held-out scores) and `validation.json` (the backtest: what happened to the ads of a
year earlier, by where their first ask sat in the model's range). The page reads those three
files and nothing else, so it shows whatever was published last and never a half-written
file: the publish step writes each file under a temporary name and renames it. `meta.json`
is written last and holds the sha256 of the other two, and the page shows a meta or a
backtest only when it was published with the table beside it.

`below_share` is the share of the model's predictive distribution for the apartment that lies
below the ask. The page shows its complement as "lower than": an ask lower than 95% of what the
model expects for this apartment, on this date, is a candidate deal.

A row's `cautions` are reasons its ask may be low that the model does not know
(`rentfrontier.cautions` writes the codes). The page leaves cautioned ads out of the list
unless asked for them, says how many it left out, and names each ad's cautions when shown.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

SORTS = {
    "score": "Lowest ask for the apartment",
    "discount": "Largest gap to the model's middle estimate",
    "new": "Newest on the market",
}
SHOWN = 200
FILES = ("deals.json", "meta.json", "validation.json")
LISTING = "https://streeteasy.com/rental/"
# A caution's code as the page words it. A code the page does not know is not shown.
CAUTIONS = {
    "income": "the ad says it is income-restricted or in an affordable-housing program",
    "not_home": "the ad reads like an office, not a home",
    "owners_only": "open only to the building's owners",
    "beds": "listed before with a different bedroom count",
    "off_market": "temporarily off the market",
}
OFF_MARKET = "TEMPORARILY_OFF_MARKET"
# What a table writes for a missing name.
NO_NAME = {"", "nan", "none", "<na>", "null"}


@lru_cache(maxsize=4)
def _read(path: str, stamp: tuple[int, int]):
    """The file's content and its sha256."""
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _file(folder: Path, name: str):
    path = folder / name
    try:
        stat = path.stat()
        return _read(str(path), (stat.st_mtime_ns, stat.st_size))
    except (OSError, ValueError):
        return None, None


def _name(value) -> str | None:
    """A name from the table, or None for a missing one."""
    value = "" if value is None else str(value).strip()
    return None if value.lower() in NO_NAME else value


def listing_url(row) -> str | None:
    """The ad's page on StreetEasy, and nothing else: the row's own link when it points
    there, else one built from a numeric listing id."""
    url, listing = str(row.get("url") or ""), str(row.get("listing_id") or "")
    if url.startswith("https://streeteasy.com/"):
        return url
    return LISTING + listing if re.fullmatch(r"\d+", listing) else None


def lower_words(lower_than: float) -> str:
    """'99.2%', '87%', or 'over 99.9%': the page never claims an ask lower than all of the
    model's range."""
    if lower_than > 99.9:
        return "over 99.9%"
    return f"{lower_than:.1f}%" if lower_than >= 95 else f"{lower_than:.0f}%"


def _number(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def hood_label(name) -> str:
    """'west-village' -> 'West Village'. A name that already has capitals is kept."""
    name = str(name or "")
    return name if name != name.lower() else name.replace("-", " ").title()


def _backtest(validation: dict) -> dict:
    """The backtest's rows with `lower_than`, the page's wording of each band of `place`
    ('0.0 to 0.1' is an ask lower than 90% to 100% of the model's range)."""
    rows = []
    for v in validation.get("by_first_ask_place") or []:
        try:
            lo, hi = (float(x) for x in str(v["place"]).split(" to "))
        except (KeyError, ValueError):
            continue
        rows.append(
            v | {"lower_than": f"{100 * (1 - hi):.0f}% to {100 * (1 - lo):.0f}%"}
        )
    return validation | {"by_first_ask_place": rows}


def caution_words(row) -> list[str]:
    """The row's cautions in the page's words. A table from before the cautions still
    says when an ad is off the market, from its status."""
    codes = row.get("cautions")
    codes = [c for c in codes if isinstance(c, str)] if isinstance(codes, list) else []
    if row.get("status") == OFF_MARKET and "off_market" not in codes:
        codes.append("off_market")
    return [CAUTIONS[c] for c in dict.fromkeys(codes) if c in CAUTIONS]


def load_rows(rows) -> list[dict]:
    """The table's rows with the page's numbers. Rows without an ask, a score or a middle
    estimate are dropped."""
    out = []
    for r in rows:
        ask, share, mid = (
            _number(r.get(k)) for k in ("ask", "below_share", "model_median")
        )
        if ask is None or share is None or mid is None or ask <= 0:
            continue
        out.append(
            r
            | {
                "ask": ask,
                "below_share": share,
                "model_median": mid,
                "lower_than": 100 * (1 - share),
                "lower_words": lower_words(100 * (1 - share)),
                "url": listing_url(r),
                "neighbourhood": _name(r.get("neighbourhood")),
                "address": _name(r.get("address")),
                "unit": _name(r.get("unit")),
                "gap_pct": 100 * (mid - ask) / mid,
                "bedrooms": _number(r.get("bedrooms")),
                "days_on_market": _number(r.get("days_on_market")),
                "unit_ads": int(_number(r.get("unit_ads")) or 0),
                "months_free": _number(r.get("months_free")) or 0.0,
                "page_price": _number(r.get("page_price")),
                "hood_label": hood_label(_name(r.get("neighbourhood"))),
                "cautions": caution_words(r),
            }
        )
    return out


def load(root: Path) -> dict | None:
    """The published table, or None when none has been published."""
    folder = Path(root) / "deals"
    rows, rows_sha = _file(folder, "deals.json")
    if not isinstance(rows, list):
        return None
    out = load_rows(rows)
    # A meta from another publish than the table's says nothing about it, and neither does
    # a backtest the meta does not name.
    meta, _ = _file(folder, "meta.json")
    if not isinstance(meta, dict) or meta.get("deals_sha256") != rows_sha:
        meta = {}
    validation, validation_sha = _file(folder, "validation.json")
    if (
        not isinstance(validation, dict)
        or meta.get("validation_sha256") != validation_sha
    ):
        validation = {}
    return {
        "rows": out,
        "meta": meta,
        "validation": _backtest(validation),
        "hoods": sorted(
            {
                (r["neighbourhood"], r["hood_label"])
                for r in out
                if r.get("neighbourhood")
            },
            key=lambda pair: pair[1],
        ),
    }


def choice(args) -> dict:
    """The page's filters from its query string. Anything unreadable is left out."""
    beds = args.get("beds", "")
    max_rent = _number(args.get("max"))
    sort = args.get("sort", "score")
    return {
        "beds": int(beds) if beds in ("0", "1", "2", "3") else None,
        "max_rent": max_rent if max_rent and max_rent > 0 else None,
        "hood": args.get("hood") or None,
        "known": args.get("known") == "1",
        "cautioned": args.get("all") == "1",
        "sort": sort if sort in SORTS else "score",
    }


def choose(
    rows,
    beds=None,
    max_rent=None,
    hood=None,
    known=False,
    cautioned=False,
    sort="score",
):
    """The rows the filters keep, in the chosen order. `beds` 3 means three or more,
    `known` keeps the apartments with at least one earlier ad in the model's data, and
    ads with a caution are left out unless `cautioned`."""
    out = []
    for r in rows:
        b = r["bedrooms"]
        if beds is not None and (b is None or (min(round(b), 3) != beds)):
            continue
        if max_rent is not None and r["ask"] > max_rent:
            continue
        if hood is not None and r.get("neighbourhood") != hood:
            continue
        if known and r["unit_ads"] < 1:
            continue
        if not cautioned and r["cautions"]:
            continue
        out.append(r)
    if sort == "discount":
        out.sort(key=lambda r: -r["gap_pct"])
    elif sort == "new":
        out.sort(
            key=lambda r: (
                r["days_on_market"] if r["days_on_market"] is not None else math.inf
            )
        )
    else:
        out.sort(key=lambda r: r["below_share"])
    return out
