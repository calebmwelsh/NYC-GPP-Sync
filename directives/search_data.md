---
description: Search the GPP catalog with optional keyword queries and facet filters
---

# Directive: Search Data (`search_data.py`)

## Goal
Query the GPP Hyrax catalog API with a keyword query and/or any combination of facet filters. Saves paginated results to `.tmp/results.json` for downstream use (e.g., bulk ingest).

## When to Use
- Before running `bulk_ingest.py` — search first to populate `.tmp/results.json`.
- For filter parity testing (compare result counts against the live portal UI).
- For any exploratory querying of the GPP catalog.

## Script
`execution/search_data.py`

## Environment Variables (`.env/.env`)
| Variable                 | Description                                      |
| ------------------------ | ------------------------------------------------ |
| `GPP_BASE_URL`           | Base URL, defaults to `https://a860-gpp.nyc.gov` |
| `SEARCH_QUERY`           | Fallback keyword query                           |
| `SEARCH_AGENCY`          | Fallback agency filter                           |
| `SEARCH_SUBJECT`         | Fallback subject filter                          |
| `SEARCH_REPORT_TYPE`     | Fallback report type filter                      |
| `SEARCH_LANGUAGE`        | Fallback language filter                         |
| `SEARCH_FISCAL_YEAR`     | Fallback fiscal year filter                      |
| `SEARCH_CALENDAR_YEAR`   | Fallback calendar year filter                    |
| `SEARCH_BOROUGH`         | Fallback borough filter                          |
| `SEARCH_MANDATED_REPORT` | Fallback mandated report name filter             |
| `SEARCH_LIMIT`           | Fallback row limit (default 10)                  |

CLI args override env variables.

## How to Run

**Basic keyword search:**
```bash
python search_data.py --query "budget" --rows 20
```

**With filters:**
```bash
python search_data.py --agency "City Planning, Department of (DCP)" --fiscal-year "2024" --rows 50
```

**Fetch all results (auto-paginates):**
```bash
python search_data.py --rows 9999
```

**Save to custom path:**
```bash
python search_data.py --query "housing" --output .tmp/housing_results.json
```

## Outputs
- `.tmp/results.json` (default) with structure:
  ```json
  {
    "results": [{ "id": "...", "title": "...", "agency": "...", "date": "...", "type": "..." }],
    "total_count": 123,
    "current_page": 1,
    "total_pages": 7
  }
  ```

## Pass Criteria
- `total_count` is non-zero for non-empty searches.
- Result count matches (within ~5%) of what the portal UI shows.

## Known Issues / Edge Cases
- API hard cap: 100 rows per request. The script auto-paginates when `--rows > 100`.
- Multi-value filtering: use pipe delimiter, e.g., `--borough "Brooklyn|Manhattan"`.
- Facet field names must use `_sim` suffix (indexed). Wrong suffix → 0 results silently.
- Debug lines (`DEBUG: SEARCH_SUBJECT env`) are intentional for filter verification — do not remove.
