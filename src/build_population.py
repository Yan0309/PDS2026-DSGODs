"""
Step: build the county-year population table (2006-2015).

Inputs (Census Bureau county population estimates, July 1 of each year):
  - co-est00int-tot.csv     2000-2010 intercensal estimates -> used for 2006-2009
  - co-est2019-alldata.csv  Vintage 2019 estimates           -> used for 2010-2015

Output:
  - population_county_year.parquet
        county_fips (str, 5 digits), state_fips (str, 2 digits),
        state_name, county_name, year (int), population (int), pop_source
  - population_checks.txt          human-readable report of every check
  - population_2010_comparison.csv  2010 value from both files, per county

Decisions (documented so reviewers and the final report can cite them):
  1. 2006-2009 come from the intercensal file and 2010-2015 from Vintage 2019, so
     every post-2010 year uses one consistent series.
  2. County geography is harmonized to the Vintage 2019 (current) codes:
       46113 Shannon County, SD  -> 46102 Oglala Lakota County (renamed 2015, same area)
       51515 Bedford city, VA    -> merged into 51019 Bedford County (merged 2013)
     The mortality and ARCOS tables must apply the same mapping; import
     `harmonize_fips` from this module so all steps share one definition.
  3. Alaska (state FIPS 02) is dropped because its borough/census-area boundaries
     changed during the study period (per the project outline).

Usage:
  python build_population.py --intercensal path/to/co-est00int-tot.csv \
      --vintage2019 path/to/co-est2019-alldata.csv --outdir data/intermediate
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

YEARS_INTERCENSAL = list(range(2006, 2010))  # 2006-2009
YEARS_V2019 = list(range(2010, 2016))  # 2010-2015
ALL_YEARS = YEARS_INTERCENSAL + YEARS_V2019

DROP_STATES = {"02"}  # Alaska

# old code -> current code. Applied to every source table before merging.
FIPS_HARMONIZATION = {
    "46113": "46102",  # Shannon County, SD -> Oglala Lakota County, SD
    "51515": "51019",  # Bedford city, VA -> Bedford County, VA
}

# Census files are Latin-1 encoded (e.g. "Doña Ana County"); UTF-8 fails.
CENSUS_ENCODING = "latin-1"


def harmonize_fips(fips: pd.Series) -> pd.Series:
    """Map outdated county FIPS codes to the codes used in Vintage 2019."""
    return fips.replace(FIPS_HARMONIZATION)


def make_fips(state: pd.Series, county: pd.Series) -> pd.Series:
    """Build zero-padded 5-digit FIPS strings, e.g. 1, 1 -> '01001'."""
    return state.astype(int).map("{:02d}".format) + county.astype(int).map("{:03d}".format)


def read_census(path: Path, years: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read one Census file. Return (county rows, state-total rows), wide format."""
    keep = ["SUMLEV", "STATE", "COUNTY", "STNAME", "CTYNAME"] + [f"POPESTIMATE{y}" for y in years]
    df = pd.read_csv(path, encoding=CENSUS_ENCODING, usecols=keep)
    df["state_fips"] = df["STATE"].astype(int).map("{:02d}".format)
    df["county_fips"] = make_fips(df["STATE"], df["COUNTY"])

    counties = df[df["SUMLEV"] == 50].copy()  # 50 = county
    states = df[df["SUMLEV"] == 40].copy()  # 40 = state total
    return counties, states


def check_state_totals(counties: pd.DataFrame, states: pd.DataFrame, years: list[int]) -> list[str]:
    """Counties must add up exactly to each state's total row."""
    problems = []
    for y in years:
        col = f"POPESTIMATE{y}"
        county_sum = counties.groupby("state_fips")[col].sum()
        state_tot = states.set_index("state_fips")[col]
        diff = (county_sum - state_tot).dropna()
        bad = diff[diff != 0]
        if len(bad):
            problems.append(f"{y}: county sums differ from state totals in {bad.to_dict()}")
    return problems


def to_long(counties: pd.DataFrame, years: list[int], source: str) -> pd.DataFrame:
    """Harmonize FIPS, sum counties that now share a code, reshape wide years to long.

    Returns county_fips, year, population, pop_source (names are attached later
    from the Vintage 2019 file so every year carries the current county name).
    """
    df = counties.assign(county_fips=harmonize_fips(counties["county_fips"]))
    pop_cols = [f"POPESTIMATE{y}" for y in years]
    wide = df.groupby("county_fips")[pop_cols].sum()  # Bedford city + Bedford County -> one row
    long = wide.reset_index().melt(id_vars="county_fips", var_name="year", value_name="population")
    long["year"] = long["year"].str.replace("POPESTIMATE", "", regex=False).astype(int)
    long["pop_source"] = source
    return long


def compare_2010(int_counties: pd.DataFrame, v19_counties: pd.DataFrame) -> pd.DataFrame:
    """2010 July 1 estimate from both files, after harmonization, per county."""
    def one(df: pd.DataFrame, label: str) -> pd.Series:
        d = df.assign(county_fips=harmonize_fips(df["county_fips"]))
        return d.groupby("county_fips")["POPESTIMATE2010"].sum().rename(label)

    out = pd.concat([one(int_counties, "pop2010_intercensal"), one(v19_counties, "pop2010_v2019")], axis=1)
    out["pct_diff"] = (out["pop2010_v2019"] / out["pop2010_intercensal"] - 1) * 100
    return out.reset_index()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--intercensal", required=True, type=Path, help="co-est00int-tot.csv")
    p.add_argument("--vintage2019", required=True, type=Path, help="co-est2019-alldata.csv")
    p.add_argument("--outdir", default=Path("."), type=Path)
    args = p.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    report: list[str] = []
    log = report.append

    # --- read (2010 is read from both files only for the comparison) ---
    int_c, int_s = read_census(args.intercensal, YEARS_INTERCENSAL + [2010])
    v19_c, v19_s = read_census(args.vintage2019, YEARS_V2019)
    log(f"Intercensal file: {len(int_c)} counties, {len(int_s)} state rows")
    log(f"Vintage 2019 file: {len(v19_c)} counties, {len(v19_s)} state rows")

    # --- check 1: counties add up to state totals (before any changes) ---
    problems = check_state_totals(int_c, int_s, YEARS_INTERCENSAL) + check_state_totals(v19_c, v19_s, YEARS_V2019)
    log("Check county sums = state totals: " + ("PASS" if not problems else "FAIL\n  " + "\n  ".join(problems)))

    # --- 2010 comparison between the two sources (before dropping Alaska) ---
    cmp2010 = compare_2010(int_c, v19_c)
    cmp2010 = cmp2010[~cmp2010["county_fips"].str[:2].isin(DROP_STATES)]
    cmp2010.to_csv(args.outdir / "population_2010_comparison.csv", index=False)
    big = cmp2010[cmp2010["pct_diff"].abs() > 2].sort_values("pct_diff")
    log(
        "2010 estimate, Vintage 2019 vs intercensal (Alaska excluded): "
        f"median |diff| {cmp2010['pct_diff'].abs().median():.3f}%, "
        f"{(cmp2010['pct_diff'].abs() > 1).sum()} counties >1%, {len(big)} counties >2%"
    )
    if len(big):
        log("  Counties with |diff| > 2% (possible level break between 2009 and 2010):")
        for r in big.itertuples():
            log(f"    {r.county_fips}: {r.pct_diff:+.2f}%")

    # --- build long table ---
    int_long = to_long(int_c, YEARS_INTERCENSAL, "census_intercensal_2000_2010")
    v19_long = to_long(v19_c, YEARS_V2019, "census_vintage_2019")
    pop = pd.concat([int_long, v19_long], ignore_index=True)

    n_before = pop["county_fips"].nunique()
    pop = pop[~pop["county_fips"].str[:2].isin(DROP_STATES)]
    log(f"Dropped Alaska: {n_before - pop['county_fips'].nunique()} county codes removed")

    # Current names from Vintage 2019 for every year.
    names = v19_c[["county_fips", "state_fips", "STNAME", "CTYNAME"]].rename(
        columns={"STNAME": "state_name", "CTYNAME": "county_name"}
    )
    pop = pop.merge(names, on="county_fips", how="left", validate="many_to_one")

    # --- check 2: same county list in both periods after harmonization ---
    kept = lambda s: {f for f in s if f[:2] not in DROP_STATES}  # noqa: E731
    a, b = kept(int_long["county_fips"]), kept(v19_long["county_fips"])
    only_a, only_b = sorted(a - b), sorted(b - a)
    log(
        "Check same counties in both files: "
        + ("PASS" if not (only_a or only_b) else f"FAIL only-intercensal={only_a} only-v2019={only_b}")
    )

    # --- check 3: exactly one row per county-year, every year present ---
    dup = pop.duplicated(["county_fips", "year"]).sum()
    per_county = pop.groupby("county_fips")["year"].nunique()
    incomplete = per_county[per_county != len(ALL_YEARS)]
    log(f"Check no duplicate county-years: {'PASS' if dup == 0 else f'FAIL ({dup})'}")
    log(
        f"Check every county has all {len(ALL_YEARS)} years: "
        + ("PASS" if incomplete.empty else f"FAIL {incomplete.to_dict()}")
    )

    # --- check 4: no missing or non-positive population ---
    bad = pop[pop["population"].isna() | (pop["population"] <= 0)]
    log(f"Check population present and > 0: {'PASS' if bad.empty else f'FAIL ({len(bad)} rows)'}")

    # --- check 5: no implausible year-to-year jumps (flag only) ---
    pop = pop.sort_values(["county_fips", "year"])
    pop["pct_change"] = pop.groupby("county_fips")["population"].pct_change() * 100
    jumps = pop[pop["pct_change"].abs() > 10]
    log(f"Year-over-year changes > 10% (review, not an error): {len(jumps)}")
    for r in jumps.itertuples():
        log(f"    {r.county_fips} {r.county_name}, {r.state_name}: {r.year} {r.pct_change:+.1f}%")
    pop = pop.drop(columns="pct_change")

    log(
        f"Final table: {len(pop)} rows, {pop['county_fips'].nunique()} counties, "
        f"{pop['state_fips'].nunique()} states (incl. DC), years {pop['year'].min()}-{pop['year'].max()}"
    )

    pop["population"] = pop["population"].astype("int64")
    cols = ["county_fips", "state_fips", "state_name", "county_name", "year", "population", "pop_source"]
    pop[cols].to_parquet(args.outdir / "population_county_year.parquet", index=False)
    (args.outdir / "population_checks.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))

    failed = [line for line in report if "FAIL" in line]
    if failed:
        raise SystemExit("One or more checks failed; see population_checks.txt")


if __name__ == "__main__":
    main()
