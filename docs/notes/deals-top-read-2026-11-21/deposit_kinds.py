"""Sort the uncoded deposit-over-price ads of deposit.csv into kinds, using no model output.

- "deposit=first ask (cut)": the deposit equals the ad's first ask, so the landlord cut the
  price and left the deposit at the old one.
- "net fit": deposit * (L - m) / L matches the page price within max($2, 0.2%) for some
  months free m in 0.5..3 and lease length L in 12..24, so the page shows a net rent of a
  gross rent equal to the deposit.
- "other": neither.

Writes deposit_kinds.csv to scratch and a coded copy without prices to the note's folder,
and prints counts by place in the default Deals view."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.site import deals

S = Path(sys.argv[1])
NOTE = Path(__file__).resolve().parent
rows = pd.DataFrame(deals.load(Path("/data1/apartments/site"))["rows"])
df = pd.read_csv(S / "deposit.csv", dtype={"listing_id": str})
df = df[df.over & ~(df.months_free.fillna(0) > 0)].merge(
    rows[["listing_id", "first_ask", "ask", "page_price", "building", "cautions"]],
    on="listing_id",
    how="left",
)
df["dep_is_first"] = np.isclose(df.deposit, df.first_ask)


def fit(dep: float, price: float) -> str | None:
    for m in np.arange(0.5, 3.01, 0.5):
        for L in range(12, 25):
            if abs(dep * (L - m) / L - price) <= max(2, 0.002 * price):
                return f"{m:g}/{L}"
    return None


df["fit"] = [fit(d, p) for d, p in zip(df.deposit, df.price)]
df["kind"] = np.where(
    df.dep_is_first,
    "deposit=first ask (cut)",
    np.where(df.fit.notna(), "net fit", "other"),
)
df.to_csv(S / "deposit_kinds.csv", index=False)
df[["listing_id", "building", "place", "ratio", "fit", "kind"]].round(4).to_csv(
    NOTE / "deposit_kinds.csv", index=False
)
print(df.kind.value_counts().to_string())
for lo, hi in [(1, 60), (1, 300), (301, 2000), (2001, 4067)]:
    s = df[(df.place >= lo) & (df.place <= hi)]
    print(f"places {lo}-{hi}:", s.kind.value_counts().to_dict())
print(df[df.kind == "net fit"].building.value_counts().head(8).to_string())
