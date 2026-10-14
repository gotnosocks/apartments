"""Price screen behind quarantine-v13. It prices every NB8 row at its latest
ask (`latest-ask-v2`) after the current rules, then measures how far each ask
sits from two medians of log ask, each leaving the row itself out:

1. the unit's other rows with the same bedroom count;
2. the building's other rows with the same bedroom count.

A row's factor is the smaller of the two distances, so a row gets flagged only
when it disagrees with both. A row alone in its unit or building group gets no
factor. Rows over a factor of 2.5 go to OUT.jsonl, highest first, with their ad
text for reading.

The medians take in the unit's later listings as well as its earlier ones. A
quarantine of rows read by hand can use that; a model feature could not.

Usage: price_mismatch_screen.py OUT.jsonl
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import data, descriptions, features

RULES = (
    "baths-ad-v3",
    "bedrooms-ad-v3",
    "fields-review-v3",
    "latest-ask-v2",
    "quarantine-v12",
    "unit-labels-v15",
    "unit-reviews-v1",
    "unit-splits-v4",
)
READ_OVER = 2.5


def _loo_median(values: np.ndarray, key: pd.Series) -> np.ndarray:
    out = np.full(len(values), np.nan)
    for idx in key.groupby(key).indices.values():
        if len(idx) < 2:
            continue
        v = values[idx]
        for j, i in enumerate(idx):
            out[i] = np.median(np.delete(v, j))
    return out


def factors(frame: pd.DataFrame) -> np.ndarray:
    beds = frame.bedrooms.astype(str)
    lp = frame.log_rent.to_numpy(float)
    unit = lp - _loo_median(lp, frame.unit_id.astype(str) + "|" + beds)
    building = lp - _loo_median(lp, frame.building.astype(str) + "|" + beds)
    return np.exp(np.minimum(np.abs(unit), np.abs(building)))


def main(out_path: str):
    frame, _ = data.split_and_rules(data.load(data.DATASET_NB8), "latest", RULES)
    k = factors(frame)
    hits = frame.assign(k=k)[k > READ_OVER].sort_values("k", ascending=False)
    descriptions.SOURCES.set(
        tuple(
            Path(p)
            for p in features.description_files("nb8-nostuy-petsfill-v1").values()
        )
    )
    text = descriptions.attach(hits)
    with open(out_path, "w") as f:
        for (_, r), t in zip(hits.iterrows(), text):
            f.write(
                json.dumps(
                    {
                        "audit_id": r.audit_id,
                        "building": r.building,
                        "unit_id": r.unit_id,
                        "price_at": str(r.price_at)[:10],
                        "bedrooms": r.bedrooms,
                        "asking_rent": float(r.asking_rent),
                        "factor": round(float(r.k), 3),
                        "description": t,
                    }
                )
                + "\n"
            )
    for over in (2.5, 3, 4):
        print(f"factor over {over}: {int((k > over).sum())}")


if __name__ == "__main__":
    main(sys.argv[1])
