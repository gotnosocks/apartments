"""Loft buildings, by rule: the flag `features.loft_v1` (nb3-loft-v1) adds to
the rent model.

A building counts as a loft building at a listing's date when MapPLUTO
classes it D5 (an elevator building converted from commercial use, as at 110
W 26th St), or when at least half of its earlier ads with text call the
apartment a loft, and there are at least `MIN_ADS` of them. Earlier means
captured strictly before the row, so a row reads no later ad and not its own
ad. MapPLUTO has no L (loft) class among the buildings in Chelsea and the
Villages.

Loft buildings list more space per bedroom count (median 1,015 sq ft for a
1-bedroom against 700 elsewhere) and relist the same apartment with a
different bedroom count twice as often (25% against 12.5%; sizing,
2026-10-07). Reads no rents.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import descriptions

MIN_ADS = 3
SHARE = 0.5
LOFT_CLASSES = frozenset({"D5"})
# A loft apartment, not a bed or storage platform inside one.
LOFT_TEXT = re.compile(r"\bloft\b")
NOT_LOFT = re.compile(r"sleeping loft|loft bed|storage loft|lofted bed")


def says_loft(text: str) -> bool:
    """Whether a (lower-cased) ad calls the apartment a loft."""
    return bool(LOFT_TEXT.search(text)) and not NOT_LOFT.search(text)


def prior_text_share(frame: pd.DataFrame, text: pd.Series) -> pd.Series:
    """Per row: the share of its building's ads with text, captured strictly
    before the row, that call the apartment a loft (NaN with fewer than
    `MIN_ADS` such ads)."""
    has = text.ne("").to_numpy()
    hit = text.map(says_loft).to_numpy() & has
    when = pd.to_datetime(frame.price_at, utc=True)
    if when.isna().any():
        raise ValueError("loft text share needs a capture time on every row")
    when = when.astype("int64").to_numpy()
    out = np.full(len(frame), np.nan)
    for _, idx in frame.groupby("building", sort=False).indices.items():
        idx = idx[np.argsort(when[idx], kind="stable")]
        t = when[idx]
        # ads strictly earlier: everything before the first row sharing t
        start = np.searchsorted(t, t, side="left")
        n = np.concatenate([[0], np.cumsum(has[idx])])[start]
        k = np.concatenate([[0], np.cumsum(hit[idx])])[start]
        out[idx] = np.where(n >= MIN_ADS, k / np.maximum(n, 1), np.nan)
    return pd.Series(out, index=frame.index)


def loft_flags(frame: pd.DataFrame, building_class: pd.Series) -> pd.DataFrame:
    """Per row: `class_loft` (MapPLUTO D5), `text_loft` (earlier ads) and
    `loft` (either)."""
    share = prior_text_share(frame, descriptions.attach(frame))
    by_class = building_class.reset_index(drop=True).isin(LOFT_CLASSES).to_numpy()
    by_text = share.ge(SHARE).to_numpy()
    return pd.DataFrame(
        {"class_loft": by_class, "text_loft": by_text, "loft": by_class | by_text},
        index=frame.index,
    )
