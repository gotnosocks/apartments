"""The Deals page's table: the ads on the market, scored by the drift model.

`python -m rentfrontier.drift_deals deals` writes `deals.json`, one row per ad on the market on
the scoring day, and `ops/deals-publish` copies it to the site's `deals/` folder with
`meta.json` (the run, the scoring day, the model's held-out scores) and `validation.json` (the
backtest: what happened to the ads of a year earlier, by where their first ask sat in the
model's range). The page reads those three files and nothing else, so it shows whatever was
published last and never a half-written table: the publish step writes each file under a
temporary name and renames it.

`below_share` is the share of the model's predictive distribution for the apartment that lies
below the ask. The page shows its complement as "lower than": an ask lower than 95% of what the
model expects for this apartment, on this date, is a candidate deal.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

SORTS = {
    "score": "Lowest ask for the apartment",
    "discount": "Largest gap to the model's middle estimate",
    "new": "Newest on the market",
}
SHOWN = 200
FILES = ("deals.json", "meta.json", "validation.json")


@lru_cache(maxsize=4)
def _read(path: str, stamp: float):
    return json.loads(Path(path).read_text())


def _file(folder: Path, name: str):
    path = folder / name
    try:
        return _read(str(path), path.stat().st_mtime)
    except (OSError, ValueError):
        return None


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
                "gap_pct": 100 * (mid - ask) / mid,
                "bedrooms": _number(r.get("bedrooms")),
                "days_on_market": _number(r.get("days_on_market")),
                "unit_ads": int(_number(r.get("unit_ads")) or 0),
                "months_free": _number(r.get("months_free")) or 0.0,
                "hood_label": hood_label(r.get("neighbourhood")),
            }
        )
    return out


def load(root: Path) -> dict | None:
    """The published table, or None when none has been published."""
    folder = Path(root) / "deals"
    rows = _file(folder, "deals.json")
    if not isinstance(rows, list):
        return None
    out = load_rows(rows)
    return {
        "rows": out,
        "meta": _file(folder, "meta.json") or {},
        "validation": _backtest(_file(folder, "validation.json") or {}),
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
        "sort": sort if sort in SORTS else "score",
    }


def choose(rows, beds=None, max_rent=None, hood=None, known=False, sort="score"):
    """The rows the filters keep, in the chosen order. `beds` 3 means three or more, and
    `known` keeps the apartments with at least one earlier ad in the model's data."""
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
