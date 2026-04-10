---
description: Enumerate all available facets and their values from the GPP catalog API
---

# Directive: Get All Filters (`get_all_filters.py`)

## Goal
Pull every facet (filter category) and all of its values from the GPP Hyrax API and save them to `.tmp/gpp_filters.json`. This output is used to understand what filters are available for search testing and to build the filter parity matrix.

## When to Use
- At the start of a new test sprint to refresh the known filter set.
- Whenever a new facet might have been added to the portal.

## Script
`cli/get_filters.py`

## Inputs
Environment variable (optional):
- `GPP_BASE_URL` — defaults to `https://a860-gpp.nyc.gov`

Set in `.env/.env` if needed.

## How to Run
```bash
python cli/get_filters.py
```

## Outputs
- `.tmp/gpp_filters.json` — a dict keyed by Solr facet name, e.g.:
  ```json
  {
    "subject_sim": { "label": "Subject", "values": ["Education", "Finance", ...] },
    "agency_sim":  { "label": "Agency",  "values": ["DCP", "DCAS", ...] }
  }
  ```

## Pass Criteria
At least 5 facets returned with non-empty value lists.

## Known Issues / Edge Cases
- Script uses `rows=1` (not `rows=0`) because some Hyrax instances return an error on `rows=0`.
- Values are only the top N returned by Solr — not an exhaustive list of all possible values.
- Facet names ending in `_sim` are indexed facet fields; `_tesim` are full-text fields (not filterable this way).
