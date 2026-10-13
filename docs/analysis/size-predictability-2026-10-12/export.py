from pathlib import Path
import pandas as pd
from rentfrontier import data, features, descriptions

CR = "baths-ad-v3,bedrooms-ad-v3,fields-review-v3,quarantine-v12,unit-labels-v15,unit-reviews-v1,unit-splits-v4".split(
    ","
)
f, h = data.split_and_rules(data.load(data.DATASET_NB8), "latest", CR)
g = features.build("nb8-nostuy-v1", f, ~h)
X = pd.DataFrame(g.values, columns=g.names)
descriptions.SOURCES.set(
    tuple(
        Path(p) for p in features.description_files("nb8-nostuy-petsfill-v1").values()
    )
)
d = descriptions.attach(f)
out = f.reset_index(drop=True).copy()
out["description"] = pd.Series(d).reset_index(drop=True).astype("string")
out["heldout"] = h
out = pd.concat([out, X.add_prefix("x::")], axis=1)
out.to_parquet("/data1/apartments/tmp/suspect/size/frame.parquet")
print(out.shape, out.description.notna().mean(), out.square_feet.notna().mean())
