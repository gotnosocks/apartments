"""Save the unit and ad columns of the served design for every row of b9's dataset."""

import json, numpy as np
from rentfrontier import b0, drift_building_bedtext as B

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext"
d = np.load(
    "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz",
    allow_pickle=True,
)
frame = b0.load_frame(DS)
D = B.design(frame, held=d["heldout"])
names = [str(n) for n in D.names]
keep = [
    i
    for i, n in enumerate(names)
    if n.startswith(("unit:", "ad:", "bld:doorman", "bld:elevator", "bld:gym", "flag:"))
]
np.save("design_b9_x.npy", np.asarray(D.x)[:, keep].astype(np.float32))
json.dump([names[i] for i in keep], open("design_b9_names.json", "w"))
print(len(names), len(keep), np.asarray(D.x).shape)
