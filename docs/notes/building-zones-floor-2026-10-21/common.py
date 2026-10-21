RUNS = "/data1/apartments/frontier/runs/"
DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
FLOOR = "building-zones-floor-b0-latest-6b5a5b4a-dense-w1000"
AGE = "building-zones-age-b0-latest-f023987f-dense-w1000"
SNAP = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"


def bands(frame, elevator):
    """Each row's floor band label, by elevator group, and its flags."""
    import numpy as np, pandas as pd

    f = (
        pd.read_parquet(SNAP)
        .drop_duplicates("listing_id")
        .set_index("listing_id")
        .reindex(frame.listing_id.astype(str))
    )
    fl = f.floor.to_numpy()
    grp = np.where(elevator == 1, "elev", "walkup")
    cuts = [
        (1, 1, "1"),
        (2, 2, "2"),
        (3, 5, "3-5"),
        (6, 9, "6-9"),
        (10, 19, "10-19"),
        (20, 39, "20-39"),
        (40, 999, "40+"),
    ]
    band = np.full(len(fl), "unknown", dtype=object)
    for lo, hi, lab in cuts:
        band[(fl >= lo) & (fl <= hi)] = lab
    return pd.DataFrame(
        {
            "group": grp,
            "band": band,
            "floor": fl,
            **{
                k: f[k].fillna(0).to_numpy() == 1
                for k in ("top", "penthouse", "garden", "lower")
            },
        }
    )
