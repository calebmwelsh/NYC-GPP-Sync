---
description: Bulk download metadata and files for all items in a search result set
---

# Directive: Bulk Ingest (`bulk_ingest.py`)

## Goal
Read `.tmp/results.json` (produced by `search_data.py`) and download metadata + files for every work item in the result set, concurrently using a thread pool.

## Status
✅ **READY.** Depends on `download_data.py` which is now verified. Tested for individual items; bulk concurrency confirmed in architecture.

## Prerequisites
1. Run `search_data.py` to populate `.tmp/results.json`.
2. Verify `download_data.py` works for a single ID first.

## Script
`cli/bulk_ingest.py`

## Inputs
No CLI arguments — reads `.tmp/results.json` automatically.

Internally calls `download_work(work_id)` from `download_data.py` for each item.

## How to Run
```bash
python cli/bulk_ingest.py
```

## Configuration
Default concurrency is 4 threads (`max_workers=4`). To change, edit the `bulk_ingest()` call in the `__main__` block or refactor to accept a CLI arg.

## Outputs
For each work ID in `results.json`:
- `data/<workId>/metadata.json`
- `data/<workId>/<filename>.pdf` (or other file types)

## Pass Criteria
- All items in `results.json` have a corresponding folder in the output directory.
- Each folder contains at least `metadata.json`.
- No unhandled exceptions (individual item failures are caught and logged, not fatal).

## Known Issues / Edge Cases
- If `.tmp/results.json` is missing, the script exits with an error message — run `search_data.py` first.
- Thread pool errors per-item are caught silently — check console output for `Failed to download file` messages.
- Large result sets (1000+ items) may take a long time; consider limiting with `--rows` in the prior search step.
- Rate limiting: the GPP API does not publish rate limits, but parallel requests at `max_workers > 8` may result in 429 errors.
