"""Held-out behaviour and field checks of the size by its source and by the fill's makeup.

Classes of a fill (`klass`):
- unit, same beds: every source ad of the piece has the ad's bedroom count;
- unit, mixed beds: some source ads have it and some have another;
- unit, other beds: every source ad has another bedroom count;
- line, other apartments: every source unit is another apartment on the line;
- line, own apartment: some source unit is another piece of the ad's own apartment.

Two field checks. `later` compares a filled ad's size with the median size its apartment
states on other ads of the same bedrooms and full baths that no fill could read. `own`
takes the ads that state a size and compares it with the fill the cascade would have made
for them from earlier ads. Errors are of log(fill / check): `big30` is a fill more than 30%
over the check, `small30` one more than 30% under (check / fill over 1.3). `rmse_fill` and
`rmse_med` are the root mean squared log errors of the fill and of the bedroom median, the
size a blanked row is given (a relative size of 0).
"""

import numpy as np
import pandas as pd

from build import OUT

L15, L30 = np.log(1.15), np.log(1.3)


def klass(d: pd.DataFrame, source) -> np.ndarray:
    """The class of each row's fill, for the layer named by `source` ("unit" or "line")."""
    u = np.where(
        d.unit_other_n == 0,
        "unit, same beds",
        np.where(d.unit_same_n == 0, "unit, other beds", "unit, mixed beds"),
    )
    ln = np.where(d.line_piece_n == 0, "line, other apartments", "line, own apartment")
    return np.where(source == "unit", u, np.where(source == "line", ln, source))


def tails(g: pd.DataFrame) -> pd.Series:
    n = len(g)
    lo, hi = (g.cdf < 0.05).mean(), (g.cdf > 0.95).mean()
    return pd.Series(
        {
            "n": n,
            "gap": g.gap.mean(),
            "low5": lo,
            "se": np.sqrt(lo * (1 - lo) / max(n, 1)),
            "high95": hi,
            "sq_gap": (g.gap**2).mean(),
        }
    )


def errors(g: pd.DataFrame) -> pd.Series:
    e = np.log(g.fill / g.check)
    m = np.log(g.bed_median / g.check)
    return pd.Series(
        {
            "n": len(g),
            "off15": (e.abs() > L15).mean(),
            "off30": (e.abs() > L30).mean(),
            "big30": (e > L30).mean(),
            "small30": (e < -L30).mean(),
            "rmse_fill": np.sqrt((e**2).mean()),
            "rmse_med": np.sqrt((m**2).mean()),
        }
    )


def show(title: str, t: pd.DataFrame) -> None:
    print("\n" + title)
    print(t.round(3).to_string())


def load() -> pd.DataFrame:
    d = pd.read_parquet(OUT / "sizes.parquet")
    d["klass"] = klass(d, d.source.to_numpy())
    # The fill the cascade would make from earlier ads, whatever the ad itself states.
    would = np.where(d.unit_n > 0, "unit", np.where(d.line_n > 0, "line", "none"))
    d["would"] = klass(d, would)
    d["would_fill"] = np.where(would == "unit", d.unit_fill, d.line_fill)
    d["ratio"] = d.sqft / d.bed_median
    return d


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    d = load()
    show(
        "rows by class",
        pd.crosstab(d.klass, d.held.map({False: "train", True: "held"})),
    )
    h = d[d.held & (d.year >= 2022)]
    for name, part in (("2022 on", h), ("2025-26", h[h.year >= 2025])):
        show(f"held-out by source, {name}", part.groupby("source").apply(tails))
        show(f"held-out by class, {name}", part.groupby("klass").apply(tails))
        show(
            f"held-out by class and half, {name}",
            part.groupby(["klass", "half"]).apply(tails),
        )

    f = d[d.source.isin(["unit", "line"]) & d.truth.notna()]
    f = f.assign(fill=f.sqft, check=f.truth)
    show("later check, filled ads, all years", f.groupby("klass").apply(errors))
    show("later check by half", f.groupby(["klass", "half"]).apply(errors))
    show("later check, held-out ads only", f[f.held].groupby("klass").apply(errors))
    o = d[d.stated.between(150, 8000) & (d.would != "none")]
    o = o.assign(fill=o.would_fill, check=o.stated)
    show(
        "own check, ads that state a size, all years", o.groupby("would").apply(errors)
    )
    show("own check, 2022 on", o[o.year >= 2022].groupby("would").apply(errors))
    show("own check by half", o.groupby(["would", "half"]).apply(errors))
    show("own check, held-out ads", o[o.held].groupby("would").apply(errors))

    # Unit fills with mixed sources: the same-bedroom sources alone against all sources.
    m = o[o.would == "unit, mixed beds"]
    for col in ("unit_fill", "unit_same_fill", "unit_other_fill"):
        show(
            f"own check, mixed beds, {col}",
            m.assign(fill=m[col]).groupby("half").apply(errors),
        )
    m = f[f.klass == "unit, mixed beds"]
    for col in ("unit_fill", "unit_same_fill", "unit_other_fill"):
        show(
            f"later check, mixed beds, {col}",
            m.assign(fill=m[col]).groupby("half").apply(errors),
        )
    # Line fills from another piece of the apartment: that piece alone, and the others alone.
    for name, t in (
        ("own", o[o.would == "line, own apartment"]),
        ("later", f[f.klass == "line, own apartment"]),
    ):
        for col in ("line_fill", "line_piece_fill", "line_else_fill"):
            t2 = t.assign(fill=t[col])
            t2 = t2[t2.fill.notna()]
            show(
                f"{name} check, line with own apartment, {col}",
                t2.groupby("half").apply(errors),
            )
