import csv
import tempfile
import unittest
from pathlib import Path

from src.summarize_policy_trends import OUTCOMES, summarize


class PolicyTrendsTest(unittest.TestCase):
    def test_event_years_and_suppressed_mortality(self):
        with tempfile.TemporaryDirectory() as folder:
            panel = Path(folder) / "panel.csv"
            with panel.open("w", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["county_fips", "year", *OUTCOMES])
                for year in range(2006, 2016):
                    writer.writerows([
                        ["12001", year, 2, ""],
                        ["12003", year, 4, 20],
                        ["53001", year, 10, 30],
                        ["01001", year, 1, 0],
                        ["13001", year, 2, ""],
                        ["37001", year, 3, 10],
                    ])
            for state, policy_year in [("12", 2010), ("53", 2012)]:
                with self.subTest(state=state):
                    rows = list(summarize(panel, state, {"01", "13", "37"}))
                    self.assertEqual(len(rows), 40)
                    indexed = {
                        (r["group"], r["outcome"]): r
                        for r in rows if r["year"] == policy_year
                    }
                    mortality = indexed["control", "overdose_deaths_per_100k"]
                    self.assertEqual(mortality["event_year"], 0)
                    self.assertEqual(mortality["counties_observed"], 2)
                    self.assertEqual(mortality["counties_in_panel"], 3)
                    self.assertEqual(mortality["mean"], 5)
                    self.assertAlmostEqual(mortality["standard_error"], 5)
                    treated = indexed["treated", "shipments_per_capita"]
                    if state == "12":
                        self.assertEqual(treated["mean"], 3)
                        self.assertAlmostEqual(treated["standard_error"], 1)
                    else:
                        self.assertEqual(treated["mean"], 10)
                        self.assertIsNone(treated["standard_error"])

    def test_duplicate_county_year_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            panel = Path(folder) / "panel.csv"
            panel.write_text(
                f"county_fips,year,{','.join(OUTCOMES)}\n"
                "12001,2010,2,20\n12001,2010,2,20\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate county-year"):
                list(summarize(panel, "12", {"01", "13", "37"}))
