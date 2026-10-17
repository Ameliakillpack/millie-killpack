# Market Trends data refresh

`market.html` reads `data/market.json`. `tools/update_market_data.py` rebuilds that file
from four free public sources (standard-library Python, no API keys, ~30-90 s).

| Figure | Source | Cadence | Terms (checked Oct 17, 2026) |
|---|---|---|---|
| 30-yr and 15-yr fixed rate, week-ago, year-ago, 5-yr chart | Freddie Mac PMMS® (`PMMS_history.csv`) | Weekly, Thursdays | "Information ... may be used with proper attribution. Alteration ... is prohibited." |
| Median sale price, days on market, inventory, months of supply, homes sold, sale-to-list (Lehi = rolling 3 months; Utah County and Utah = monthly) | Redfin Data Center, Housing Market Tracker | Monthly (around the 7th–12th) | "You are welcome to use this data ... cite the source ... link to Redfin for the first reference" |
| Typical home value (ZHVI), 10-yr chart | Zillow Research | Monthly (mid-month) | Aggregate research data may be displayed with attribution to Zillow Group; no implied relationship |
| Median and average list price (Utah County and Utah) | Realtor.com® Economic Research, Inventory Core Metrics | Monthly (start of month) | Attribute to Realtor.com Economic Research and link to realtor.com/research |

FRED is not used: its terms limit copyrighted series (including Freddie Mac's) to non-commercial use.
Realtor.com ZIP data for 84043 is skipped while its `quality_flag` is set.
The UAR / ShowingTime "Local Market Update" PDFs (MLS-based, with average sale price) are
© ShowingTime Plus and have no stated reuse license, so they are not ingested.

Safety rules in the script: values are copied from the files, range-checked, and never filled in.
If a source fails, the previous copy of that source is kept with its own dates and listed
in `stale`; the page notes it. Missing metrics are hidden.

Schedule: `.github/workflows/update-market-data.yml` runs every Friday 13:00 UTC and commits
`data/market.json` only when it changed (which redeploys GitHub Pages). Run it manually from
the Actions tab any time.
