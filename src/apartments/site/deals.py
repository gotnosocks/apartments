"""The Deals page table: apartments on the market scored by the drift model.

`python -m rentfrontier.drift_deals publish` writes the site's `deals/` folder:
`deals.json` (one row per ad on the market on the scoring day), `meta.json` (the
run, scoring day, convergence gates and held-out scores) and `validation.json`
(what happened to last year's ads by where their first ask sat in the model's
range). When `<root>/diagnostics/` is also published, `facts.py` adds each ad's
basis (`unit`, `building` or `area`), building training ad count, floor and
detector flags.

By default the list orders ads by cautious saving, `(model_lo80 - ask) / model_lo80`,
which measures how far the ask sits below the model's 10th percentile and penalizes
wide ranges. The default population keeps ads whose estimate rests on the unit's own
earlier ads or on a building with at least 5 training ads, hides no-history ads more
than 35% below the model's middle as suspect, and hides cautioned ads unless toggled.

The peer check compares each ad with its building. `facts.Table.peers` counts the
building's other ads of the same bedroom count in the year up to the scoring day and
takes their median ask. An ad asking below the model's 80% range, with at least
`facts.PEER_MIN_ADS` peers and an ask of at least `facts.PEER_ASK_SHARE` of their
median, carries the caution `peers`: the building's own asks say the ask is ordinary
there, so the gap more likely shows the model sitting high for the building. Deals
hides these rows unless the reader includes them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup, escape

from . import boroughs, facts, tags

DEFAULT_SORT = "cautious"
SORTS: dict[str, str] = {
    "cautious": "Largest cautious saving",
    "score": "Lowest ask in the model's range",
    "discount": "Largest % under the model's middle",
    "new": "Newest on the market",
}
BEDROOMS: dict[str, str] = {
    "0": "Studio",
    "1": "1 BR",
    "2": "2 BR",
    "3": "3 BR",
    "4": "4+ BR",
}
SHOWN = 50
SUSPECT_GAP_PCT = 35.0
NET_FLOOR = 0.5
# Ends of the range bars' shared scale, as ratios to the model's middle.
RANGE_LOW = 0.6
RANGE_HIGH = 1.3
FILES = ("deals.json", "meta.json", "validation.json")
LISTING = "https://streeteasy.com/rental/"

# Caution codes (`rentfrontier.cautions.CODES`): full explanation and short chip label.
CAUTIONS: dict[str, str] = {
    "income": "the ad says it is income-restricted or in an affordable-housing program",
    "not_home": "the ad reads like an office, not a home",
    "owners_only": "open only to the building's owners",
    "takeover": "the rest of someone's lease, not a new one",
    "beds": "listed before with a different bedroom count",
    "off_market": "temporarily off the market",
}
CAUTION_LABELS: dict[str, str] = {
    "income": "income-restricted",
    "not_home": "non-residential",
    "owners_only": "owners only",
    "takeover": "lease takeover",
    "beds": "beds changed",
    "off_market": "off market",
}
PEERS = "peers"
PEERS_LABEL = "at building's asks"
# Tooltip of the Evidence chip, by basis.
BASIS_WORDS: dict[str, str] = {
    "unit": (
        "The model has seen this many earlier ads of this same apartment, so the "
        "estimate rests on the unit's own rent history."
    ),
    "building": (
        "The model has seen no earlier ad of this apartment. The estimate rests on "
        "this many ads of other apartments in the building."
    ),
    "area": (
        "The model has seen no earlier ad of this apartment and fewer than 5 in the "
        "building, so the estimate rests on the surrounding area."
    ),
}
UNKNOWN_CAUTION = "a caution this page has no words for ({})"
OFF_MARKET = "TEMPORARILY_OFF_MARKET"
NO_NAME = frozenset({"", "nan", "none", "<na>", "null"})
_AUTO = object()


@dataclasses.dataclass
class Choice:
    """Filters and order for Deals parsed from a query string."""

    hood: list[str] = dataclasses.field(default_factory=list)
    beds: list[str] = dataclasses.field(default_factory=list)
    max_rent: float | None = None
    min_sqft: float | None = None
    min_floor: int | None = None
    area: bool = False
    suspect: bool = False
    cautioned: bool = False
    tagged: bool = False
    peers: bool = False
    sort: str = DEFAULT_SORT
    page: int = 1
    # Query values that `choice` could not use, in words for the page.
    ignored: list[str] = dataclasses.field(default_factory=list)

    def args(self, **changes) -> dict:
        """Query-string items for a link with selected filters updated."""
        items: dict[str, object] = {
            "hood": list(self.hood) if self.hood else None,
            "beds": list(self.beds) if self.beds else None,
            "max": _fmt(self.max_rent),
            "min_sqft": _fmt(self.min_sqft),
            "floor": self.min_floor,
            "area": "1" if self.area else None,
            "suspect": "1" if self.suspect else None,
            "all": "1" if self.cautioned else None,
            "tagged": "1" if self.tagged else None,
            "peers": "1" if self.peers else None,
            "sort": None if self.sort == DEFAULT_SORT else self.sort,
            "page": self.page if self.page > 1 else None,
        }
        if "sort" in changes and "page" not in changes:
            changes["page"] = None
        items.update(changes)
        if items.get("sort") == DEFAULT_SORT:
            items["sort"] = None
        if items.get("page") in (1, "1"):
            items["page"] = None
        return {k: v for k, v in items.items() if v not in (None, [], "", False)}

    def active(self) -> bool:
        return bool(
            self.hood
            or self.beds
            or self.max_rent is not None
            or self.min_sqft is not None
            or self.min_floor is not None
            or self.area
            or self.suspect
            or self.cautioned
            or self.tagged
            or self.peers
        )

    def filters(self) -> list[tuple[str, dict]]:
        """Each narrowing filter in words, with the `args` changes that drop it."""
        out: list[tuple[str, dict]] = []
        for name in self.hood:
            label = f"All {name}" if name in boroughs.BOROUGHS else hood_label(name)
            out.append((label, {"hood": [h for h in self.hood if h != name]}))
        for key in self.beds:
            out.append((BEDROOMS[key], {"beds": [b for b in self.beds if b != key]}))
        if self.max_rent is not None:
            out.append((f"at most {_usd(self.max_rent)}", {"max": None}))
        if self.min_sqft is not None:
            out.append((f"at least {self.min_sqft:,.0f} ft²", {"min_sqft": None}))
        if self.min_floor is not None:
            out.append((f"floor {self.min_floor} or higher", {"floor": None}))
        return [(label, changes | {"page": None}) for label, changes in out]


@lru_cache(maxsize=4)
def _read(path: str, stamp: tuple[int, int]):
    """The JSON file's content and its sha256."""
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _file_stamped(folder: Path, name: str):
    path = folder / name
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        data, sha = _read(str(path), stamp)
        return data, sha, (str(path.resolve()), *stamp)
    except (OSError, ValueError):
        return None, None, None


def _file(folder: Path, name: str):
    data, sha, _ = _file_stamped(folder, name)
    return data, sha


def _name(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text.lower() in NO_NAME else text


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        cleaned = (
            value.replace(",", "").replace("$", "").strip()
            if isinstance(value, str)
            else value
        )
        num = float(cleaned)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _pos_number(value) -> float | None:
    num = _number(value)
    return num if num is not None and num > 0 else None


def _nonneg_number(value) -> float | None:
    num = _number(value)
    return num if num is not None and num >= 0 else None


def _pos_int(value) -> int | None:
    try:
        cleaned = str(value).replace(",", "").strip()
        if not re.fullmatch(r"\d+", cleaned):
            return None
        num = int(cleaned)
    except (TypeError, ValueError):
        return None
    return num if num >= 1 else None


def _fmt(value: float | None) -> str | None:
    return None if value is None else f"{value:g}"


def _usd(value: float) -> str:
    text = f"${abs(value):,.0f}"
    return ("−" if value < 0 and text != "$0" else "") + text


def listing_url(row: dict) -> str | None:
    """The ad's page on StreetEasy from its `url` or numeric `listing_id`."""
    url, listing = str(row.get("url") or ""), str(row.get("listing_id") or "")
    if url.startswith("https://streeteasy.com/"):
        return url
    return LISTING + listing if re.fullmatch(r"\d+", listing) else None


def lower_words(lower_than: float) -> str:
    """Format `100 * (1 - below_share)` without claiming 100.0%."""
    if lower_than > 99.9:
        return "over 99.9%"
    return f"{lower_than:.1f}%" if lower_than >= 95 else f"{lower_than:.0f}%"


def under_words(gap_pct: float) -> str:
    """Format `% under` (or `% over`) the model's middle estimate."""
    if abs(gap_pct) < 0.5:
        return "0% under"
    if gap_pct > 0:
        return f"{gap_pct:.0f}% under"
    return f"{abs(gap_pct):.0f}% over"


def hood_label(name) -> str:
    """Convert a slug like `'west-village'` to `'West Village'`."""
    text = str(name or "")
    return text if text != text.lower() else text.replace("-", " ").title()


def _backtest(validation: dict) -> dict:
    """Add `lower_than` labels ('90% to 100%') to each backtest tenth."""
    rows = []
    for item in validation.get("by_first_ask_place") or []:
        try:
            lo, hi = (float(x) for x in str(item["place"]).split(" to "))
        except (KeyError, ValueError):
            continue
        rows.append(
            item | {"lower_than": f"{100 * (1 - hi):.0f}% to {100 * (1 - lo):.0f}%"}
        )
    return validation | {"by_first_ask_place": rows}


def caution_items(row: dict) -> list[dict[str, str]]:
    """Caution chip dicts (`code`, `label`, `description`) for one row."""
    codes = row.get("cautions")
    codes = [codes] if isinstance(codes, str) else codes
    codes = (
        [c for c in codes if isinstance(c, str) and c]
        if isinstance(codes, list)
        else []
    )
    if row.get("status") == OFF_MARKET and "off_market" not in codes:
        codes.append("off_market")
    out: list[dict[str, str]] = []
    for code in dict.fromkeys(codes):
        description = (
            CAUTIONS[code] if code in CAUTIONS else UNKNOWN_CAUTION.format(code[:40])
        )
        label = CAUTION_LABELS.get(code, code[:24])
        out.append({"code": code, "label": label, "description": description})
    return out


def caution_words(row: dict) -> list[str]:
    """Full caution descriptions for `row`, keeping unknown codes visible."""
    return [item["description"] for item in caution_items(row)]


def basis_badge(basis: str, unit_ads: int, building_ads: int | None) -> str:
    """Badge text for an ad's training basis."""
    if basis == "unit":
        return f"unit history, {unit_ads:,} {'ad' if unit_ads == 1 else 'ads'}"
    if basis == "building":
        count = building_ads or 0
        return f"building, {count:,} {'ad' if count == 1 else 'ads'}"
    return "area only"


def price_cut(
    ask: float,
    first_ask: float | None,
    page_price: float | None,
    months_free: float,
) -> tuple[float | None, float | None, float | None]:
    """Compare `first_ask` with `ask` on a net-of-concessions basis.
    Returns `(first_net_ask, cut_usd, cut_pct)`."""
    if first_ask is None or first_ask <= 0:
        return None, None, None
    if months_free > 0:
        if page_price is None or page_price <= 0:
            return None, None, None
        ratio = ask / page_price
        if not (NET_FLOOR <= ratio < 1.0):
            return None, None, None
        base = first_ask * ratio
    else:
        base = first_ask
    if base - ask >= 1.0:
        cut = base - ask
        return base, cut, 100.0 * cut / base
    return base, None, None


def range_svg(
    ask: float,
    median: float,
    intervals: list[tuple[int, float, float]],
    prev_ask: float | None = None,
) -> Markup:
    """Compact inline SVG range bar (50/80/95 bands, middle tick, ask dot).

    Every bar uses the same scale, the log of the ratio to the model's middle from
    RANGE_LOW to RANGE_HIGH, so that the middle tick is at the same place in every
    row, a wide band shows an uncertain estimate, and the dot's distance from the
    tick shows the size of the gap. Values beyond the scale are drawn at its edge.
    A hollow ring marks `prev_ask`, the ask of the apartment's previous ad.
    """
    width, height = 170, 18
    left, right, top, band_h = 5, 5, 4, 10
    lo_all, hi_all = math.log(RANGE_LOW), math.log(RANGE_HIGH)

    def at(val: float) -> float:
        pos = math.log(max(val, 1e-9) / median)
        pos = min(max(pos, lo_all), hi_all)
        return left + (pos - lo_all) / (hi_all - lo_all) * (width - left - right)

    tip_parts = [f"Ask {_usd(ask)}", f"Middle {_usd(median)}"]
    for level, lo, hi in sorted(intervals, key=lambda item: item[0]):
        tip_parts.append(f"{level}% {_usd(lo)} to {_usd(hi)}")
    if prev_ask:
        tip_parts.append(f"Previous ad {_usd(prev_ask)}")
    tip = " · ".join(tip_parts)

    parts = [f"<title>{escape(tip)}</title>"]
    for level, lo, hi in sorted(intervals, key=lambda item: -item[0]):
        x = at(lo)
        w = max(at(hi) - x, 1.0)
        parts.append(
            f'<rect class="band band-{level}" x="{x:.1f}" y="{top}" '
            f'width="{w:.1f}" height="{band_h}" rx="2"/>'
        )
    mid_x, ask_x = at(median), at(ask)
    parts.append(
        f'<line class="median" x1="{mid_x:.1f}" x2="{mid_x:.1f}" '
        f'y1="1" y2="{height - 1}"/>'
    )
    if prev_ask:
        parts.append(
            f'<circle class="prev" cx="{at(prev_ask):.1f}" cy="{height / 2:.1f}" r="3.2"/>'
        )
    parts.append(
        f'<circle class="ask" cx="{ask_x:.1f}" cy="{height / 2:.1f}" r="3.8"/>'
    )
    return Markup(
        f'<svg class="deal-strip" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(tip)}">{"".join(parts)}</svg>'
    )


def peer_caution(
    ask: float, low: float | None, peers: dict | None, bedrooms: float | None
) -> dict[str, str] | None:
    """The `peers` caution chip for an ad, or `None` when the check does not apply.

    `low` is the bottom of the model's 80% range (the model's middle when the range
    is missing), and `peers` holds the `count` and `median` of
    `facts.Table.peers`."""
    if not peers or low is None or ask >= low:
        return None
    count, median = peers["count"], peers["median"]
    if count < facts.PEER_MIN_ADS or ask < facts.PEER_ASK_SHARE * median:
        return None
    beds = "same-bedroom" if bedrooms is None else beds_words(bedrooms)
    return {
        "code": PEERS,
        "label": PEERS_LABEL,
        "description": (
            f"asks about the same as {count:,} other {beds} ads in the building "
            f"(median {_usd(median)})"
        ),
    }


def beds_words(bedrooms: float) -> str:
    """'studio' or '2 BR' for a bedroom count."""
    beds = round(bedrooms)
    return "studio" if beds == 0 else f"{beds} BR"


def load_rows(
    rows: list[dict],
    diag: dict[str, dict] | None = None,
    peers: dict[str, dict] | None = None,
) -> list[dict]:
    """Prepare market ad rows with cautious savings, basis badges, cuts and chips.
    Rows missing `ask`, `below_share` or `model_median` are dropped. `peers` is the
    result of `facts.Table.peers`; a row with at least `facts.PEER_MIN_ADS` peers
    gets `peer_count` and `peer_median`, and `peer_caution` when the check trips."""
    out: list[dict] = []
    for raw in rows:
        ask, share, mid = (
            _number(raw.get(k)) for k in ("ask", "below_share", "model_median")
        )
        if ask is None or share is None or mid is None or ask <= 0 or mid <= 0:
            continue
        lid = _name(raw.get("listing_id"))
        extra = (diag or {}).get(lid or "") or {}

        bounds: dict[str, float | None] = {}
        for key in ("lo95", "lo80", "lo50", "hi50", "hi80", "hi95"):
            col = f"model_{key}"
            val = _pos_number(raw.get(col))
            bounds[key] = val if val is not None else _pos_number(extra.get(col))

        lo80 = bounds["lo80"]
        if lo80 is not None and lo80 > 0:
            cautious_saving: float | None = (lo80 - ask) / lo80
            cautious_usd: float | None = lo80 - ask
        else:
            cautious_saving = None
            cautious_usd = None

        intervals = [
            (lvl, bounds[f"lo{lvl}"], bounds[f"hi{lvl}"])
            for lvl in (50, 80, 95)
            if bounds[f"lo{lvl}"] is not None and bounds[f"hi{lvl}"] is not None
        ]

        gap_pct = 100.0 * (mid - ask) / mid
        u_raw = _nonneg_number(extra.get("unit_ads"))
        if u_raw is None:
            u_raw = _nonneg_number(raw.get("unit_ads"))
        unit_ads = int(u_raw or 0)

        b_raw = _nonneg_number(extra.get("building_ads"))
        if b_raw is None:
            b_raw = _nonneg_number(raw.get("building_ads"))
        building_ads = int(b_raw) if b_raw is not None else None

        basis = facts.resolve_basis(
            unit_ads,
            building_ads,
            _name(extra.get("basis")) or _name(raw.get("basis")),
        )
        suspect = (unit_ads == 0) and (gap_pct > SUSPECT_GAP_PCT)

        full_baths = _nonneg_number(raw.get("full_baths"))
        if full_baths is None:
            full_baths = _nonneg_number(extra.get("full_baths"))
        half_baths = _nonneg_number(raw.get("half_baths"))
        if half_baths is None:
            half_baths = _nonneg_number(extra.get("half_baths"))
        baths = None if full_baths is None else full_baths + 0.5 * (half_baths or 0.0)

        sqft = _pos_number(raw.get("square_feet")) or _pos_number(
            extra.get("square_feet")
        )
        floor_val = _number(extra.get("floor"))
        if floor_val is None:
            floor_val = _number(raw.get("floor"))

        months_free = (
            _pos_number(raw.get("months_free"))
            or _pos_number(extra.get("months_free"))
            or 0.0
        )
        page_price = _pos_number(raw.get("page_price"))
        first_ask = _pos_number(raw.get("first_ask")) or _pos_number(
            extra.get("first_ask")
        )
        first_net, cut_usd, cut_pct = price_cut(ask, first_ask, page_price, months_free)
        dom = _nonneg_number(raw.get("days_on_market"))
        if dom is None:
            dom = _nonneg_number(extra.get("days_on_market"))

        hood = _name(raw.get("neighbourhood"))
        c_items = caution_items(raw)
        bedrooms = _nonneg_number(raw.get("bedrooms"))
        near = (peers or {}).get(lid or "")
        if near and near["count"] < facts.PEER_MIN_ADS:
            near = None
        peer_item = peer_caution(ask, lo80 if lo80 is not None else mid, near, bedrooms)
        chips = c_items + ([peer_item] if peer_item else [])
        flag_list = extra.get("flags")
        if flag_list is None:
            flag_list = facts.flag_items(raw.get("flags"))

        out.append(
            raw
            | {
                "listing_id": lid,
                "ask": ask,
                "below_share": share,
                "model_median": mid,
                "model_lo95": bounds["lo95"],
                "model_lo80": bounds["lo80"],
                "model_lo50": bounds["lo50"],
                "model_hi50": bounds["hi50"],
                "model_hi80": bounds["hi80"],
                "model_hi95": bounds["hi95"],
                "cautious_saving": cautious_saving,
                "cautious_usd": cautious_usd,
                "lower_than": 100.0 * (1.0 - share),
                "lower_words": lower_words(100.0 * (1.0 - share)),
                "gap_pct": gap_pct,
                "under_words": under_words(gap_pct),
                "range_bar": range_svg(
                    ask, mid, intervals, _pos_number(extra.get("prev_ask"))
                ),
                "url": listing_url(raw),
                "neighbourhood": hood,
                "hood_label": hood_label(hood),
                "address": _name(raw.get("address")),
                "unit": _name(raw.get("unit")) or _name(extra.get("unit")),
                "bedrooms": bedrooms,
                "baths": baths,
                "square_feet": sqft,
                "floor": floor_val,
                "months_free": months_free,
                "page_price": page_price,
                "first_ask": first_ask,
                "first_net": first_net,
                "cut_usd": cut_usd,
                "cut_pct": cut_pct,
                "days_on_market": dom,
                "unit_ads": unit_ads,
                "building_ads": building_ads,
                "basis": basis,
                "basis_badge": basis_badge(basis, unit_ads, building_ads),
                "suspect": suspect,
                "cautions": [item["description"] for item in c_items],
                "caution_chips": chips,
                "peer_count": near["count"] if near else None,
                "peer_median": near["median"] if near else None,
                "peer_caution": peer_item["description"] if peer_item else None,
                "flags": flag_list,
                "tag": None,
                "ruled_out": False,
            }
        )
    return out


def hood_groups(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Neighborhood counts grouped by borough (`boroughs.grouped`)."""
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("neighbourhood"):
            label = row["hood_label"]
            counts[label] = counts.get(label, 0) + 1
    return boroughs.grouped(dict(sorted(counts.items())))


_enriched_lock = threading.Lock()
_enriched_cache: dict[
    tuple,
    tuple[tuple[dict, ...], bool, list[tuple[str, str]], dict[str, dict[str, int]]],
] = {}


def load(root: Path, diag: facts.Table | None | object = _AUTO) -> dict | None:
    """Load `<root>/deals/`, cache enriched market rows per `(deals, diagnostics)`
    stamp, and apply current tags after the cache."""
    root_path = Path(root)
    folder = root_path / "deals"
    raw_rows, rows_sha, deals_stamp = _file_stamped(folder, "deals.json")
    if not isinstance(raw_rows, list) or deals_stamp is None:
        return None

    diag_table = facts.load(root_path) if diag is _AUTO else diag
    if isinstance(diag_table, facts.Table):
        diag_stamp = (
            diag_table.stamp
            if diag_table.stamp is not None
            else ("table", id(diag_table))
        )
    else:
        diag_stamp = None

    cache_key = (deals_stamp, diag_stamp)
    with _enriched_lock:
        cached = _enriched_cache.get(cache_key)

    if cached is not None:
        base_rows, has_diagnostics, hoods, groups = cached
    else:
        diag_map: dict[str, dict] | None = None
        peer_map: dict[str, dict] | None = None
        if isinstance(diag_table, facts.Table):
            ids = [
                str(r.get("listing_id") or "") for r in raw_rows if isinstance(r, dict)
            ]
            diag_map = diag_table.ads_by_id(ids)
            peer_map = diag_table.peers(ids)
        built = load_rows(raw_rows, diag=diag_map, peers=peer_map)
        base_rows = tuple(built)
        has_diagnostics = diag_map is not None
        hoods = sorted(
            {
                (r["neighbourhood"], r["hood_label"])
                for r in base_rows
                if r.get("neighbourhood")
            },
            key=lambda pair: pair[1],
        )
        groups = hood_groups(built)
        with _enriched_lock:
            if len(_enriched_cache) >= 4:
                _enriched_cache.clear()
            _enriched_cache[cache_key] = (base_rows, has_diagnostics, hoods, groups)

    active_tags = tags.current_tags(root_path)
    if active_tags:
        out = [
            (
                row
                | {
                    "tag": active_tags[row["listing_id"]],
                    "ruled_out": (
                        active_tags[row["listing_id"]].get("group")
                        in tags.RULED_OUT_GROUPS
                    ),
                }
                if row.get("listing_id") in active_tags
                else row
            )
            for row in base_rows
        ]
    else:
        out = list(base_rows)

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
        "has_diagnostics": has_diagnostics,
        "hoods": hoods,
        "hood_groups": groups,
    }


def _arg_list(args, key: str) -> list[str]:
    if hasattr(args, "getlist"):
        raw = args.getlist(key)
    else:
        val = args.get(key)
        raw = (
            val
            if isinstance(val, (list, tuple))
            else ([val] if val is not None else [])
        )
    out: list[str] = []
    for item in raw:
        if isinstance(item, (str, int)):
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
    return out


def choice(args) -> Choice:
    """Parse `/deals` query parameters into a `Choice`. A value the page cannot use
    drops out, and `Choice.ignored` says so in words for the page."""
    ignored: list[str] = []

    def parsed(key: str, words: str, parse, expects: str):
        text = str(args.get(key) or "").strip()
        value = parse(text) if text else None
        if text and value is None:
            ignored.append(f'{words} "{text[:40]}" ({expects})')
        return value

    hood = [h[:60] for h in _arg_list(args, "hood")]
    asked_beds = _arg_list(args, "beds")
    beds = [b for b in asked_beds if b in BEDROOMS]
    for bad in asked_beds:
        if bad not in BEDROOMS:
            ignored.append(f'bedrooms "{bad[:40]}" (the choices are 0 to 4)')
    sort = str(args.get("sort") or "").strip()
    if sort and sort not in SORTS:
        ignored.append(f'order "{sort[:40]}" (not an order this page has)')
    return Choice(
        hood=hood,
        beds=beds,
        max_rent=parsed("max", "most you'd pay", _pos_number, "not a rent above $0"),
        min_sqft=parsed("min_sqft", "min sq ft", _pos_number, "not a size above 0"),
        min_floor=parsed("floor", "floor", _pos_int, "not a whole floor number"),
        area=args.get("area") == "1",
        suspect=args.get("suspect") == "1",
        cautioned=args.get("all") == "1",
        tagged=args.get("tagged") == "1",
        peers=args.get("peers") == "1",
        sort=sort if sort in SORTS else DEFAULT_SORT,
        page=parsed("page", "page", _pos_int, "not a page number") or 1,
        ignored=ignored,
    )


def hood_summary(chosen: list[str]) -> str:
    """The Neighborhoods picker's label for the chosen areas: 'Any neighborhood',
    'All Manhattan', 'Chelsea', '3 areas' or 'All Brooklyn + 2 areas'."""
    whole = [f"All {name}" for name in chosen if name in boroughs.BOROUGHS]
    areas = [name for name in chosen if name not in boroughs.BOROUGHS]
    if not chosen:
        return "Any neighborhood"
    if len(areas) == 1 and not whole:
        return hood_label(areas[0])
    if areas:
        whole.append(f"{len(areas)} area{'' if len(areas) == 1 else 's'}")
    return " + ".join(whole)


def _matches_hood(row: dict, chosen: list[str]) -> bool:
    if not chosen:
        return True
    raw_hood = row.get("neighbourhood")
    label = row.get("hood_label") or ""
    if not raw_hood:
        return False
    borough = boroughs.BOROUGH_OF.get(label, "Other")
    for item in chosen:
        if item in boroughs.BOROUGHS and borough == item:
            return True
        if item == "Other" and borough == "Other":
            return True
        if raw_hood == item or label.lower() == item.lower():
            return True
    return False


def _matches_beds(row: dict, beds: list[str]) -> bool:
    if not beds:
        return True
    val = row.get("bedrooms")
    if val is None:
        return False
    rounded = round(val)
    for key in beds:
        if key == "4" and rounded >= 4:
            return True
        if key != "4" and rounded == int(key):
            return True
    return False


def _matches_attributes(row: dict, c: Choice) -> bool:
    if not _matches_hood(row, c.hood):
        return False
    if not _matches_beds(row, c.beds):
        return False
    if c.max_rent is not None and row["ask"] > c.max_rent:
        return False
    if c.min_sqft is not None and (
        row["square_feet"] is None or row["square_feet"] < c.min_sqft
    ):
        return False
    if c.min_floor is not None and (row["floor"] is None or row["floor"] < c.min_floor):
        return False
    return True


def choose(rows: list[dict], c: Choice | None = None, **overrides) -> list[dict]:
    """Filter and order `rows` according to `c` (and any field `overrides`)."""
    active = dataclasses.replace(c or Choice(), **overrides)
    out: list[dict] = []
    for row in rows:
        if not _matches_attributes(row, active):
            continue
        if not active.area and row["basis"] not in ("unit", "building"):
            continue
        if not active.suspect and row["suspect"]:
            continue
        if not active.cautioned and row["cautions"]:
            continue
        if not active.tagged and row.get("ruled_out"):
            continue
        if not active.peers and row.get("peer_caution"):
            continue
        out.append(row)

    if active.sort == "discount":
        out.sort(key=lambda r: (-r["gap_pct"], r["below_share"], r["listing_id"] or ""))
    elif active.sort == "new":
        out.sort(
            key=lambda r: (
                r["days_on_market"] is None,
                r["days_on_market"] if r["days_on_market"] is not None else 0.0,
                -(
                    r["cautious_saving"]
                    if r["cautious_saving"] is not None
                    else -math.inf
                ),
                r["listing_id"] or "",
            )
        )
    elif active.sort == "score":
        out.sort(key=lambda r: (r["below_share"], r["listing_id"] or ""))
    else:
        out.sort(
            key=lambda r: (
                r["cautious_saving"] is None,
                -(r["cautious_saving"] if r["cautious_saving"] is not None else 0.0),
                r["below_share"],
                r["listing_id"] or "",
            )
        )
    return out


def hidden_counts(rows: list[dict], c: Choice, shown_count: int) -> dict[str, int]:
    """How many extra matching ads each toggle adds when turned on."""
    return {
        "area": (0 if c.area else len(choose(rows, c, area=True)) - shown_count),
        "suspect": (
            0 if c.suspect else len(choose(rows, c, suspect=True)) - shown_count
        ),
        "cautioned": (
            0 if c.cautioned else len(choose(rows, c, cautioned=True)) - shown_count
        ),
        "tagged": (0 if c.tagged else len(choose(rows, c, tagged=True)) - shown_count),
        "peers": (0 if c.peers else len(choose(rows, c, peers=True)) - shown_count),
    }


def paginate(
    rows: list[dict], page: int, per_page: int = SHOWN
) -> tuple[list[dict], int, int]:
    """Slice `rows` to one page of `per_page` items, clamping `page` into `1..pages`."""
    pages = max(1, math.ceil(len(rows) / per_page))
    current_page = min(max(1, page), pages)
    start = (current_page - 1) * per_page
    return rows[start : start + per_page], current_page, pages
