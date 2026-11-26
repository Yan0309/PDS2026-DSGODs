"""Step 1b: filter the aggregated ARCOS table and sum it to state x county name x year.

Input:  data/intermediate/arcos_aggregated.parquet (from src/arcos_chunks.py)
Output: data/intermediate/arcos_county_year.parquet with
          buyer_state, buyer_county, year,
          mme_mg            main measure (see filters below)
          mme_mg_with_hosp  robustness: also counts hospitals/clinics
          mme_mg_with_bupe  robustness: also counts buprenorphine
          n_transactions    transactions in the main measure
County names are still ARCOS names; FIPS codes are added in the crosswalk step.

Filters (see PR description for the evidence behind each one):
  - sales only (TRANSACTION_CODE == "S")
  - buyers: chain/retail pharmacies and practitioners; no supply-chain buyers,
    mail-order or central-fill pharmacies, or opioid treatment programs
  - drugs: no buprenorphine in the main measure
  - years 2006-2019, 50 states + DC, Alaska dropped, rows with no county dropped
"""
import pandas as pd

SRC = "data/intermediate/arcos_aggregated.parquet"
OUT = "data/intermediate/arcos_county_year.parquet"

PHARMACIES = {"CHAIN PHARMACY", "RETAIL PHARMACY"}
HOSPITALS = {"HOSPITAL/CLINIC", "HOSP/CLINIC-VA", "HOSP/CLINIC- MIL", "HOSP/CLINIC FED",
             "CHAIN HOSP/CLINIC", "HOSP/CLINIC NG"}
STATES = set(
    "AL AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
    "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)  # 50 states + DC, without Alaska

d = pd.read_parquet(SRC)
buyer = d["BUYER_BUS_ACT"].fillna("")
practitioner = buyer.str.contains("PRACTITIONER") | buyer.str.startswith("MLP-PHYSICIAN ASSISTANT")

base = (
    (d["TRANSACTION_CODE"] == "S")
    & d["year"].between(2006, 2019)
    & d["BUYER_STATE"].isin(STATES)
    & d["BUYER_COUNTY"].notna()
)
retail = buyer.isin(PHARMACIES) | practitioner
bupe = d["DRUG_NAME"] == "BUPRENORPHINE"

d["mme_mg"] = d["MME"].where(base & retail & ~bupe, 0)
d["mme_mg_with_hosp"] = d["MME"].where(base & (retail | buyer.isin(HOSPITALS)) & ~bupe, 0)
d["mme_mg_with_bupe"] = d["MME"].where(base & retail, 0)
d["n_tx_main"] = d["n_transactions"].where(base & retail & ~bupe, 0)

keep = d[base & (retail | buyer.isin(HOSPITALS))]
out = (
    keep.groupby(["BUYER_STATE", "BUYER_COUNTY", "year"])[["mme_mg", "mme_mg_with_hosp", "mme_mg_with_bupe", "n_tx_main"]]
    .sum()
    .reset_index()
    .rename(columns={"BUYER_STATE": "buyer_state", "BUYER_COUNTY": "buyer_county", "n_tx_main": "n_transactions"})
)
out["year"] = out["year"].astype(int)
out.to_parquet(OUT, index=False)

print(f"Wrote {OUT}: {len(out):,} rows, {out[['buyer_state', 'buyer_county']].drop_duplicates().shape[0]:,} "
      f"state-county names, {out['buyer_state'].nunique()} states, years {out['year'].min()}-{out['year'].max()}")
print("\nNational totals by year, billion mg (main | with hospitals | with buprenorphine):")
print((out.groupby("year")[["mme_mg", "mme_mg_with_hosp", "mme_mg_with_bupe"]].sum() / 1e9).round(1).to_string())
print("\nFlorida and Washington, main measure, billion mg:")
print((out[out["buyer_state"].isin(["FL", "WA"])].pivot_table(index="year", columns="buyer_state", values="mme_mg", aggfunc="sum") / 1e9).round(2).to_string())
