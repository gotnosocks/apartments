"""Write the analysis rows of a latest-ask run as the pipeline's rows input.

The pipeline's latest-ask models read the columns of the analysis rows that
`rentfrontier.latest_ask` reads, with `ordinal` numbering the rows in its reading order. This
script loads the datasets named in a latest-ask run's provenance.json, in the order given
there, and writes those columns to Parquet. Once the event log builds the rows from API
records, the pipeline stops reading this file.

    python ops/pipeline/analysis_rows.py PROVENANCE OUT

Run it with the frontier environment, such as /data1/apartments/venvs/serve-frontier.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
from rentfrontier import data


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("provenance", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    datasets = json.loads(args.provenance.read_text())["dataset"].split(",")
    frame = pd.concat([data.load(Path(d.strip())) for d in datasets], ignore_index=True)
    out = pd.DataFrame(
        {
            "ordinal": range(len(frame)),
            "audit_id": frame.audit_id.to_numpy(),
            "source_listing_id": frame.source_listing_id.astype(str).to_numpy(),
            "price_at": frame.price_at,
            "asking_rent": frame.asking_rent.astype(float),
            "log_rent": frame.log_rent,
            "building": frame.building.astype(str),
            "bedrooms": frame.bedrooms.astype(str),
        }
    )
    out.to_parquet(args.out, index=False)
    print(f"{len(out)} rows from {len(datasets)} datasets")


if __name__ == "__main__":
    main()
