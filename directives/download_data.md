---
description: Download metadata and associated files for a single GPP work item
---

# Directive: Download Data (`download_data.py`)

## Goal
Given a GPP work ID, fetch its full metadata and download all associated files (e.g., PDFs) from the `/downloads/:fileSetId` endpoint. Saved to the system `Downloads/GPP_Downloads` folder for storage.

## Status
✅ **VERIFIED.** Script tested and verified for work items (e.g., `9880vs24b`). Downloads land in the user's `Downloads/GPP_Downloads` folder correctly.

## When to Use
- To download a single work item for manual inspection or ingestion.
- As a dependency called by `bulk_ingest.py` per-item.

## Script
`cli/download.py`

## Inputs
| Argument     | Required | Description                                        |
| ------------ | -------- | -------------------------------------------------- |
| `--id`       | ✅        | The Work ID (Hyrax UUID) to download               |
| `--no-files` | ❌        | If set, only fetches metadata; skips file download |

Work IDs come from `results.json` (run `search_data.py` first).

## How to Run
```bash
python cli/download.py --id <work-id>
```

**Metadata only:**
```bash
python cli/download.py --id <work-id> --no-files
```

## How it Works (Endpoint Chain)
1. **GET** `/catalog/:id.json` → Solr metadata (preferred; has `member_ids_ssim`)
2. Fallback: **GET** `/concern/nyc_government_publications/:id.json`
3. Extract file set IDs from `member_ids_ssim`, `file_set_ids_ssim`, `file_set_ids`, or `representative_id`
4. For each file set ID:
   - **GET** `/concern/file_sets/:fileSetId.json` → resolve filename from `label` field
   - **GET** `/downloads/:fileSetId` → stream file bytes

## Outputs
All outputs land in `~/Downloads/GPP_Downloads/:workId/`:
- `metadata.json` — full Solr document for the work
- `<filename>.pdf` (or resolved name) — the downloaded file(s)

## Pass Criteria
- `metadata.json` is created and non-empty.
- At least one file is downloaded for works that have associated files.
- No HTTP errors (4xx, 5xx).

## Known Issues / Edge Cases
- Some works may have no file sets (`member_ids_ssim` empty) — script will print a message and exit cleanly.
- File names default to `<fileSetId>.pdf` if `label` is missing from FileSet metadata.
- The `/downloads/:id` endpoint may redirect; `requests` follows redirects automatically.
- Authentication: currently unauthenticated. If a restricted work is tested, expect a 401/403.
