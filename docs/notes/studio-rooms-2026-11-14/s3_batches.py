"""S17, part 3: three reading batches of 10 dossiers, and the frozen evidence's SHA-256s.

I shuffle the 30 row ids with the draw's seed so each batch mixes room counts and held-out
with training rows, write `batches/batch_K.txt` with the dossier paths, and record the
SHA-256 of every dossier, plan image and evidence table in `evidence.json`. Row 8's stored
plan was a .webp, which I converted to .png with Pillow and added to its dossier before this
step."""

import glob
import hashlib
import json
import os

import numpy as np

OUT = "/data1/apartments/tmp/studio-rooms-2026-11-14/"
SEED, N_BATCH = 20261114, 3

rows = np.random.default_rng(SEED).permutation(30)
os.makedirs(OUT + "batches", exist_ok=True)
for k, part in enumerate(np.array_split(rows, N_BATCH)):
    with open(OUT + f"batches/batch_{k}.txt", "w") as fh:
        for r in part:
            fh.write(OUT + f"dossiers/row_{r:02d}.md\n")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


files = sorted(
    glob.glob(OUT + "dossiers/*.md")
    + glob.glob(OUT + "plans/*")
    + glob.glob(OUT + "batches/*.txt")
    + [
        OUT + f"{n}.parquet"
        for n in ["sample", "pool", "row_ads", "unit_ads", "line_ads"]
    ]
)
json.dump(
    {os.path.relpath(p, OUT): sha(p) for p in files},
    open(OUT + "evidence.json", "w"),
    indent=1,
)
print(len(files), [sorted(int(r) for r in p) for p in np.array_split(rows, N_BATCH)])
