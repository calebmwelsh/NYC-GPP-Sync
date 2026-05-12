# NYC GPP Explorer

A modular, robust, and easy-to-use crawler and UI for the NYC Government Publications Portal (GPP).

![GPP Explorer UI Dashboard](assets/Readme.png)

## Features

- **Robust Akamai Bypass**: Uses `curl_cffi` to mimic browser fingerprints and handle rate limiting.
- **Modern Web UI**: A clean interface to search, filter, and download publications directly.
- **Connector System**: Save named filter presets and switch between them instantly.
- **RRULE Scheduler**: Automate recurring syncs on a daily/weekly/monthly schedule from the UI.
- **Modular Architecture**: Separate core library, CLI tools, and UI logic.
- **Portability**: Runs anywhere with relative pathing; easy to set up with `requirements.txt`.
- **Direct Download Proxy**: Stream files directly through the UI without manual navigation.

## Directory Structure

```text
NYC GPP/
├── core/               # Core logic (HyraxClient — Akamai bypass, retries, session management)
├── cli/                # CLI tools: search.py, download.py, bulk_ingest.py, schedule.py
├── ui/                 # Web interface: server.py + HTML templates
├── data/
│   ├── filters.json    # Filter options for the Explorer dropdowns (required)
│   ├── connectors.json # Saved connector profiles (auto-created on first save)
│   └── downloads/      # Downloaded files
├── directives/         # SOP documentation
├── .env/               # Environment variables (auto-managed by the UI)
├── .tmp/               # Temporary files and logs
└── start.py            # Main entry point (launches UI)
```

> **Note:** `data/filters.json` must be present. If it is missing, the Explorer filter dropdowns will be empty and a warning will appear in the UI.

## Setup & Installation

The project requires **Python 3.8+**.

1. **Clone the Repository**:
   ```bash
   git clone [repository-url]
   cd "NYC GPP"
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   > This project relies on `curl_cffi` for Akamai Bot Manager bypass, and `python-dateutil` + `pytz` for the scheduler.

3. **Run the Dashboard**:
   ```bash
   python start.py
   ```
   Then visit `http://localhost:8004` in your browser.

## The Connectors System

Connectors are named filter presets that let you save and switch between different search contexts.

- Open `http://localhost:8004/` to view your Connectors dashboard.
- In the Explorer, configure your filters and click **"Save as Connector"** to save the current state.
- Click **"Launch Explorer"** on any connector card to reload those filters instantly.
- The connector's filter values are written to `.env` on load, keeping the UI and CLI scripts in sync.

### Saved filters include
Agency, Subject, Report Type, Fiscal Year, Borough, Keyword, and Result Limit. Multiple values per filter are supported (e.g. two agencies, three years).

## Scheduling

Each connector can be configured to sync automatically via the clock icon on its card.

**Native scheduler** (runs while the UI server is active):
- Supports daily, weekly, and monthly recurrence with a live preview of upcoming runs.
- Configured through the UI — no manual cron setup needed.

**Windows Task Scheduler** (runs 24/7 even when the UI is closed):
- The schedule modal generates the exact command to paste into Task Scheduler.

## CLI Usage

### Searching
```bash
python cli/search.py --query "Veteran" --rows 10
python cli/search.py --agency "Mayor's Office (OM)" --report-type "Reports - Annual" --fiscal-year 2024
```

### Downloading a single work
```bash
python cli/download.py --id [WORK_ID]
```

### Bulk download from last search
```bash
python cli/bulk_ingest.py
```

## Technical Details

- **Layer 1 (Directive)**: SOPs in `directives/` define task goals and edge cases.
- **Layer 2 (Orchestration)**: CLI scripts and UI server handle routing and decision logic.
- **Layer 3 (Execution)**: `core/hyrax_client.py` handles deterministic network operations with retry/backoff.

The Akamai bypass works by using `curl_cffi` with `impersonate="safari"` (matching TLS fingerprint to Safari-only User-Agent strings), warming up the session with a natural navigation sequence before any download, and resetting the session on repeated 403s.

## Contributing

This project is designed to be modular. To add new search filters, update `data/filters.json` and the corresponding field mapping in `cli/search.py`. To update scraping logic, modify `core/hyrax_client.py`.

---
*Developed as a modularized automation tool for NYC Government research.*
