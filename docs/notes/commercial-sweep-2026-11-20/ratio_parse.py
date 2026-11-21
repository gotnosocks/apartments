"""Parse the reader replies of the ratio-row hand read into one table per pass.

Each reader wrote CSV lines `read_id,answer,"quote","why"` to `labels_r1_NN.csv` (first pass)
or `labels_r2_NN.csv` (second pass). One first-pass line (R735) wrote an inch mark as `\\"`
and was fixed by hand to `""` before parsing. The script stops unless every read id of the
draw has one line with a valid answer.
"""

import csv
import glob
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/ratio-read")
ANSWERS = {"commercial", "placeholder", "apartment", "unclear"}


def parse(pattern: str, id_col: str, ids: set[str]) -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(OUT / pattern))):
        with open(f) as fh:
            for line in csv.reader(fh):
                if line and line[0].strip():
                    assert len(line) == 4, (f, line[0])
                    rows.append([x.strip() for x in line])
    L = pd.DataFrame(rows, columns=[id_col, "answer", "quote", "why"])
    assert set(L[id_col]) == ids and not L[id_col].duplicated().any()
    assert L.answer.isin(ANSWERS).all()
    return L


if __name__ == "__main__":
    D = pd.read_parquet(OUT / "draw_r1.parquet")
    R1 = parse("labels_r1_*.csv", "read_id", set(D.read_id))
    R1.to_csv(OUT / "r1_parsed.csv", index=False)
    S = pd.read_parquet(OUT / "draw_r2.parquet")
    R2 = parse("labels_r2_*.csv", "read2_id", set(S.read2_id))
    R2.columns = ["read2_id", "answer2", "quote2", "why2"]
    R2.to_csv(OUT / "r2_parsed.csv", index=False)
    print("first pass", len(R1), R1.answer.value_counts().to_dict())
    print("second pass", len(R2), R2.answer2.value_counts().to_dict())
