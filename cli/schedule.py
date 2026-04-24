import json
import os
import subprocess
import sys
import argparse
import logging

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, ".tmp", "schedule.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CONNECTORS_PATH = os.path.join(PROJECT_ROOT, "data", "connectors.json")
SEARCH_SCRIPT = os.path.join(PROJECT_ROOT, "cli", "search.py")
BULK_SCRIPT = os.path.join(PROJECT_ROOT, "cli", "bulk_ingest.py")

def load_connector(target):
    if not os.path.exists(CONNECTORS_PATH):
        logger.error(f"Connectors file not found: {CONNECTORS_PATH}")
        return None

    with open(CONNECTORS_PATH, 'r', encoding='utf-8') as f:
        connectors = json.load(f)

    # Try ID first
    if target in connectors:
        return connectors[target]

    # Try Name
    for c_id, data in connectors.items():
        if data.get("name") == target:
            return data

    logger.error(f"Connector '{target}' not found.")
    return None

def run_schedule(connector_target, rows=None):
    connector = load_connector(connector_target)
    if not connector:
        return

    logger.info(f"Running scheduled sync for connector: {connector.get('name')} ({connector_target})")
    filters = connector.get("filters", {})
    
    # 1. Prepare search command
    cmd_search = [sys.executable, SEARCH_SCRIPT]
    
    # Map filters to CLI args
    if filters.get("SEARCH_QUERY"): cmd_search.extend(["--query", filters["SEARCH_QUERY"]])
    if filters.get("SEARCH_AGENCY"): cmd_search.extend(["--agency", filters["SEARCH_AGENCY"]])
    if filters.get("SEARCH_SUBJECT"): cmd_search.extend(["--subject", filters["SEARCH_SUBJECT"]])
    if filters.get("SEARCH_REPORT_TYPE"): cmd_search.extend(["--report-type", filters["SEARCH_REPORT_TYPE"]])
    if filters.get("SEARCH_FISCAL_YEAR"): cmd_search.extend(["--fiscal-year", filters["SEARCH_FISCAL_YEAR"]])
    if filters.get("SEARCH_CALENDAR_YEAR"): cmd_search.extend(["--calendar-year", filters["SEARCH_CALENDAR_YEAR"]])
    if filters.get("SEARCH_BOROUGH"): cmd_search.extend(["--borough", filters["SEARCH_BOROUGH"]])
    
    limit = rows or filters.get("SEARCH_LIMIT", "10")
    cmd_search.extend(["--rows", str(limit)])

    # 2. Execute search
    logger.info(f"Step 1/2: Searching with command: {' '.join(cmd_search)}")
    result = subprocess.run(cmd_search, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Search failed: {result.stderr}")
        return
    logger.info("Search completed successfully.")

    # 3. Execute bulk ingest
    logger.info("Step 2/2: Starting bulk download...")
    cmd_bulk = [sys.executable, BULK_SCRIPT]
    result = subprocess.run(cmd_bulk, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Bulk ingest failed: {result.stderr}")
        return
    
    logger.info("Scheduled sync completed successfully.")
    logger.info(result.stdout)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schedule a GPP report sync using a saved connector.")
    parser.add_argument("--connector", required=True, help="ID or Name of the saved connector")
    parser.add_argument("--rows", type=int, help="Override result limit")
    
    args = parser.parse_args()
    
    try:
        run_schedule(args.connector, args.rows)
    except Exception as e:
        logger.critical(f"Scheduler crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
