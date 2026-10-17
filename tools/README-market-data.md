# Mortgage Rates data refresh

`rates.html` reads `data/market.json`. `tools/update_market_data.py` rebuilds it from
Freddie Mac's Primary Mortgage Market Survey® history file
(https://www.freddiemac.com/pmms/docs/PMMS_history.csv). Standard-library Python, no keys, ~2 s.

Shown: latest 30-year and 15-year fixed rates, the prior week, a year ago, the 5-year
range and a weekly 5-year chart. Terms (checked Oct 17, 2026): Freddie Mac information
"may be used with proper attribution"; not altered. FRED is not used (its terms limit
copyrighted series to non-commercial use).

Values are copied and range-checked only. If the fetch fails, the previous copy is kept
with its own date and marked stale.

Schedule: `.github/workflows/update-market-data.yml` runs every Friday 13:00 UTC
(9:00 AM EDT / 8:00 AM EST), after Freddie Mac's Thursday release, and commits
`data/market.json` when it changes. Run it manually from the Actions tab any time.
`market.html` redirects to `rates.html`.
