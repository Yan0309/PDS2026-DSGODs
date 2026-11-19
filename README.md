# PDS2026-DSGODs

## Policy trend summaries

This step supports the treated-only pre/post plots and the treated-versus-control
plots for Florida (2010) and Washington state (2012). Run it after building the
harmonized county-year panel.

Provide a UTF-8 CSV with these columns and one row per county and year:

| Column | Definition |
| --- | --- |
| `county_fips` | Harmonized five-digit county FIPS, including leading zeros |
| `year` | Calendar year, 2006–2015 |
| `shipments_per_capita` | Annual shipment volume divided by county-year population |
| `overdose_deaths_per_100k` | Annual overdose deaths divided by county-year population, multiplied by 100,000 |

Use a blank value for an unobserved outcome, including a suppressed annual
mortality count. Retain the county-year row so the output can report coverage.
A recorded zero stays in the calculation. The upstream mortality cleaning step
should document the suppression strategy used for the final analysis.

Requires Python 3.10 or later. Set `CONTROL_1`, `CONTROL_2`, and `CONTROL_3` to
distinct two-digit FIPS codes for the comparison states chosen for each case.
The team should justify those choices and inspect pre-policy trends for both
outcomes. Rerun with `--treated 53` and a separate output path for Washington.

```bash
python src/summarize_policy_trends.py \
  --panel data/analysis/county_year.csv \
  --treated 12 --controls "$CONTROL_1" "$CONTROL_2" "$CONTROL_3" \
  --out data/analysis/florida_trends.csv
```

The output contains one row per outcome, year, and group. Plot `mean` against
`event_year` with bands of mean ± one `standard_error`. Each observed county has
equal weight, so larger control states contribute more counties. The standard
error is descriptive (sample SD divided by the square root of the observed
county count). Use `counties_observed` and `counties_in_panel` to check changes in
coverage. A group with fewer than two observations has a blank standard error.

Use the treated rows for the pre/post figure and both groups for the
difference-in-differences figure. Treat event year zero as the implementation
year when interpreting Florida's annual data.

Run the synthetic regression checks with `python -m unittest discover -s tests`.
