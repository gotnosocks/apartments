"""Print 15 sampled ads for a spot check (seed 7): the dossier entries without the readers'
codes, then, with `--codes`, the readers' codes for the same ads."""

import json
import sys

import numpy as np
import pandas as pd

from build import OUT

if __name__ == "__main__":
    s = pd.read_csv(OUT / "sample.csv", dtype={"listing_id": str})
    pick = s.iloc[np.sort(np.random.default_rng(7).permutation(len(s))[:15])]
    if "--codes" in sys.argv:
        c = pd.concat(
            [pd.read_csv(OUT / f"codes_{k}.csv", dtype=str) for k in range(8)]
        )
        c = c.set_index("ad").reindex(pick.listing_id)
        print(c.assign(stratum=pick.stratum.to_numpy()).to_string(max_colwidth=90))
    else:
        for r in pick.itertuples():
            ads = json.loads((OUT / f"dossier_{r.batch}.json").read_text())
            a = next(a for a in ads if a["ad"] == r.listing_id)
            print(json.dumps(a)[:2600], "\n")
