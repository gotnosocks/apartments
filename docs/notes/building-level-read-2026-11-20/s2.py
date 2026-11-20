import pandas as pd, numpy as np

pd.set_option("display.width", 250, "display.max_rows", 500, "display.max_colwidth", 40)
L = pd.concat([pd.read_parquet(f"levels_{t}.parquet") for t in ("live", "back")])
bad = L[L.rhat > 1.05]
u = bad.building.unique()
print("union", len(u), "both", bad.building.duplicated().sum())
w = L[L.building.isin(u)].pivot(
    index="building",
    columns="run",
    values=["rhat", "c0", "c1", "n_train", "n_held", "level"],
)
w["mx"] = w["rhat"].max(axis=1)
w = w.sort_values("mx", ascending=False)
print(w.round(2).to_string())
for t in ("live", "back"):
    x = L[(L.run == t) & (L.n_held > 0)]
    print(
        t,
        "quantiles of level among bld with held ads",
        x.level.quantile([0, 0.001, 0.01, 0.5, 0.99, 0.999, 1]).round(3).tolist(),
    )
    print(
        x[x.level < -0.3][
            ["building", "zone", "level", "level_sd", "rhat", "n_train", "n_held"]
        ]
        .round(3)
        .to_string()
    )
    print(
        x[x.level > 0.5][
            [
                "building",
                "zone",
                "level",
                "level_sd",
                "rhat",
                "c0",
                "c1",
                "n_train",
                "n_held",
            ]
        ]
        .round(3)
        .to_string()
    )
