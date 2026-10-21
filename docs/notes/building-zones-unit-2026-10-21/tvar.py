import pandas as pd, numpy as np

for f in ["/data1/apartments/tmp/resid/resid_attrs.parquet", "resid_unit.parquet"]:
    d = pd.read_parquet(f)
    d["T"] = d.r + d.bld + d.F
    d["T"] -= d.groupby("zone").T.transform("mean")
    Fd = d.F - d.groupby("zone").F.transform("mean")
    print(
        f.split("/")[-1],
        "T",
        round(d["T"].var(), 4),
        d.groupby("zone")["T"].var().round(4).to_dict(),
        "err",
        round(d.r.var(), 4),
        "bld",
        round(d.bld.var(), 4),
        "F",
        round(Fd.var(), 4),
        "mad",
        round(np.median(np.abs(d.r)), 4),
    )
