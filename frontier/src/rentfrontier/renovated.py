"""Renovations from ad text, by rule: the terms `features.renovated_v1`
(nb3-renov-v1) adds to the rent model.

An ad says the apartment is renovated when its text calls it newly, freshly,
just, recently, completely, fully, totally or gut renovated, brand-new
renovated, or a new renovation. The apartment counts as renovated since its
last ad when its own ad says so and the unit's previous ad (its latest
listing first captured strictly before this one) has text that does not.
Rows read their own ad and earlier ads only, never a rent, so the term is the
leak-free form of a renovation split: the 2026-10-07 sizing found 4,032 such
ads, whose rent rose a median 2.4% more than other relists after market
drift, while a split gated on the price jump would read the row's own rent.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import descriptions

RENOVATED_TEXT = re.compile(
    r"\b(?:newly|freshly|just|recently|completely|fully|totally|gut|brand[- ]new)"
    r"[- ]+(?:gut[- ]+)?renovat|\bgut[- ]renovat|\bnew(?:ly)? renovation"
)


def says_renovated(text: str) -> bool:
    """Whether a (lower-cased) ad says the apartment is newly renovated."""
    return bool(RENOVATED_TEXT.search(text))


def flags(frame: pd.DataFrame, text: pd.Series | None = None) -> pd.DataFrame:
    """Per row: `renovated` (its own ad says so) and `since_last_ad` (it does,
    and the unit's previous ad has text that does not)."""
    if text is None:
        text = descriptions.attach(frame)
    text = text.fillna("").str.lower()
    ads = pd.DataFrame(
        {
            "unit_id": frame.unit_id.to_numpy(),
            "listing": frame.source_listing_id.astype(str).to_numpy(),
            "at": pd.to_datetime(frame.price_at, utc=True).to_numpy(),
            "has": text.ne("").to_numpy(),
            "hit": text.map(says_renovated).to_numpy(),
        }
    )
    per_ad = (
        ads.groupby(["unit_id", "listing"], sort=False)
        .agg(at=("at", "min"), has=("has", "any"), hit=("hit", "any"))
        .reset_index()
        .sort_values(["unit_id", "at", "listing"], kind="stable")
    )
    g = per_ad.groupby("unit_id", sort=False)
    prev_has = g.has.shift(fill_value=False).astype(bool)
    prev_hit = g.hit.shift(fill_value=False).astype(bool)
    # an ad first captured at the same moment as the previous one is not later
    same_time = g["at"].shift().eq(per_ad["at"])
    per_ad["since"] = per_ad.hit & prev_has & ~prev_hit & ~same_time
    since = ads.merge(
        per_ad[["unit_id", "listing", "since"]], on=["unit_id", "listing"], how="left"
    ).since.to_numpy()
    return pd.DataFrame(
        {"renovated": ads.hit.to_numpy(), "since_last_ad": since.astype(bool)},
        index=frame.index,
    )
