import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from core.hyrax_client import HyraxClient
from cli.download import download_work

RESULTS_PATH = os.path.join(PROJECT_ROOT, ".tmp", "results.json")

def process_item(work_id):
    """Helper for ThreadPoolExecutor with shared client."""
    # We create a new client per thread to be safe, 
    # or pass a shared one. curl_cffi sessions are generally thread-safe
    # but separate clients ensure no cookie/impersonate collisions.
    client = HyraxClient()
    download_work(client, work_id)

def bulk_ingest(max_workers: int = 4):
    """
    Reads the latest search results and downloads metadata/files for all items.
    """
    if not os.path.exists(RESULTS_PATH):
        print(f"Error: {RESULTS_PATH} not found. Perform a search first.")
        return

    try:
        with open(RESULTS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        results = data.get("results", [])
        if not results:
            print("No items found in results.json.")
            return

        print(f"Starting bulk ingest for {len(results)} items (sequential mode)...")
        
        # Use a single client for all downloads to maintain session
        client = HyraxClient()
        
        for i, item in enumerate(results):
            work_id = item['id']
            print(f"[{i+1}/{len(results)}] Processing {work_id}...")
            try:
                download_work(client, work_id)
            except Exception as e:
                print(f"Error processing {work_id}: {e}")
            
            # Additional small delay between items beyond client's internal delay
            if i < len(results) - 1:
                delay = 2 + random.uniform(0, 2)
                # print(f"Waiting {delay:.1f}s before next item...")
                time.sleep(delay)
            
        print(f"\nBulk ingest completed for {len(results)} items.")

    except Exception as e:
        print(f"Critical error during bulk ingest: {e}")

if __name__ == "__main__":
    bulk_ingest()

