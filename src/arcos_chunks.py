"""Step 1: read ARCOS in chunks (course big-data method) and aggregate.

Keeps only the columns we need, sums each chunk by
state x county x year x transaction code x buyer type x drug,
and throws the raw rows away. All states are kept because the
control states are not chosen yet.

Usage:
  python3 src/arcos_chunks.py ~/Downloads/arcos_all.zip data/intermediate/arcos_aggregated.parquet
  (add a third argument, e.g. 2000000, to stop after that many rows for a test)
"""
import csv
import sys
import time

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
max_rows = int(sys.argv[3]) if len(sys.argv) > 3 else None

KEYS = ["BUYER_STATE", "BUYER_COUNTY", "year", "TRANSACTION_CODE", "BUYER_BUS_ACT", "DRUG_NAME"]
TEXT = ["BUYER_STATE", "BUYER_COUNTY", "TRANSACTION_CODE", "BUYER_BUS_ACT", "DRUG_NAME", "TRANSACTION_DATE"]
NUM = ["MME", "CALC_BASE_WT_IN_GM", "MME_Conversion_Factor", "DOSAGE_UNIT"]

reader = pd.read_csv(
    src, sep="\t", usecols=TEXT + NUM, dtype={c: "string" for c in TEXT},
    quoting=csv.QUOTE_NONE, chunksize=1_000_000, on_bad_lines="skip",
)

parts, rows, start = [], 0, time.time()
for chunk in reader:
    for c in NUM:  # bad numbers become missing instead of crashing the run
        chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
    chunk["year"] = pd.to_numeric(chunk["TRANSACTION_DATE"].str[:4], errors="coerce").astype("Int64")
    chunk["mme_recomputed"] = chunk["CALC_BASE_WT_IN_GM"] * 1000 * chunk["MME_Conversion_Factor"]
    chunk["n_transactions"] = 1
    chunk["n_mme_missing"] = chunk["MME"].isna().astype(int)
    parts.append(
        chunk.groupby(KEYS, dropna=False)[["MME", "mme_recomputed", "DOSAGE_UNIT", "n_transactions", "n_mme_missing"]]
        .sum(min_count=0).reset_index()
    )
    rows += len(chunk)
    if len(parts) >= 50:  # combine partial sums now and then to keep memory small
        parts = [pd.concat(parts).groupby(KEYS, dropna=False).sum().reset_index()]
    print(f"{rows:,} rows, {(time.time() - start) / 60:.1f} min", flush=True)
    if max_rows and rows >= max_rows:
        break

result = pd.concat(parts).groupby(KEYS, dropna=False).sum().reset_index()
result.to_parquet(out, index=False)
print(f"Done: {rows:,} rows read -> {len(result):,} aggregated rows, "
      f"total MME {result['MME'].sum():,.0f} mg, missing MME {result['n_mme_missing'].sum():,}, "
      f"years {result['year'].min()}-{result['year'].max()}")
