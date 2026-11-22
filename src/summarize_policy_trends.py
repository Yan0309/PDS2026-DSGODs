"""Summarize county-year outcomes for the Florida and Washington policy plots."""

import argparse
import csv
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

POLICY_YEARS = {"12": 2010, "53": 2012}
OUTCOMES = ("shipments_per_capita", "overdose_deaths_per_100k")
FIELDS = (
    "policy_state_fips", "outcome", "group", "year", "event_year",
    "counties_observed", "counties_in_panel", "mean", "standard_error",
)


def summarize(panel_path, treated, controls):
    policy_year = POLICY_YEARS[treated]
    selected = {treated} | set(controls)
    samples = defaultdict(list)
    seen = set()
    with panel_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"county_fips", "year", *OUTCOMES}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing panel columns: {', '.join(sorted(missing))}")

        for line, row in enumerate(reader, start=2):
            county = (row["county_fips"] or "").strip()
            if not re.fullmatch(r"[0-9]{5}", county) or county.endswith("000"):
                raise ValueError(f"Line {line}: expected five-digit county FIPS")
            state = county[:2]
            if state not in selected:
                continue
            year = int(row["year"])
            if year not in range(2006, 2016):
                continue
            key = county, year
            if key in seen:
                raise ValueError(f"Line {line}: duplicate county-year {key}")
            seen.add(key)
            group = "treated" if state == treated else "control"
            for outcome in OUTCOMES:
                values = samples[year, group, outcome]
                raw = row[outcome]
                if raw is None:
                    raise ValueError(f"Line {line}: missing field {outcome}")
                value = float(raw) if raw.strip() else None
                if value is not None and (not math.isfinite(value) or value < 0):
                    raise ValueError(f"Line {line}: invalid {outcome}")
                values.append(value)

    for year in range(2006, 2016):
        missing_states = selected - {county[:2] for county, y in seen if y == year}
        if missing_states:
            raise ValueError(f"{year}: no panel rows for states {', '.join(sorted(missing_states))}")

    for (year, group, outcome), values in sorted(samples.items()):
        observed = [value for value in values if value is not None]
        n = len(observed)
        yield {
            "policy_state_fips": treated,
            "outcome": outcome,
            "group": group,
            "year": year,
            "event_year": year - policy_year,
            "counties_observed": n,
            "counties_in_panel": len(values),
            "mean": statistics.mean(observed) if n else None,
            "standard_error": statistics.stdev(observed) / math.sqrt(n) if n > 1 else None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--treated", required=True, choices=tuple(POLICY_YEARS))
    parser.add_argument("--controls", required=True, nargs="+", metavar="STATE_FIPS")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    controls = set(args.controls)
    if len(controls) < 3 or len(controls) != len(args.controls):
        parser.error("provide at least three distinct controls")
    if any(not re.fullmatch(r"[0-9]{2}", state) for state in controls):
        parser.error("controls must be two-digit state FIPS codes")
    if controls.intersection({"02", *POLICY_YEARS}):
        parser.error("exclude Alaska and both policy states from the control pool")
    if args.panel.resolve() == args.out.resolve():
        parser.error("output must be separate from the source panel")
    try:
        results = list(summarize(args.panel, args.treated, controls))
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
