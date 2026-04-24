import sys
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from core.hyrax_client import HyraxClient

# Configure logging to show debug info for testing
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_baseline(client):
    logger.info("--- TEST 1: Baseline Connectivity ---")
    resp = client.get("/")
    logger.info(f"Status: {resp.status_code}")
    assert resp.status_code == 200
    logger.info("Success!")

def test_catalog_json(client):
    logger.info("\n--- TEST 2: Deep Linking (Catalog JSON) ---")
    resp = client.get("catalog.json")
    logger.info(f"Status: {resp.status_code}")
    assert resp.status_code == 200
    logger.info("Success!")

def test_stress_requests(client, count=5):
    logger.info(f"\n--- TEST 3: Stress Requests ({count} sequentially) ---")
    successes = 0
    for i in range(count):
        logger.info(f"Request {i+1}/{count}...")
        resp = client.get("catalog.json", params={"q": f"test_{i}"})
        logger.info(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            successes += 1
        time.sleep(1) # Small delay between requests
    logger.info(f"Stress test complete: {successes}/{count} succeeded.")

def test_concurrent_requests(client, workers=3):
    logger.info(f"\n--- TEST 7: Concurrent Requests ({workers} workers) ---")
    def fetch_home():
        return client.get("/")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_home) for _ in range(workers)]
        for future in as_completed(futures):
            resp = future.result()
            logger.info(f"Thread response: {resp.status_code}")

def test_search_variety(client):
    logger.info("\n--- TEST 8: Facet Combination Variety ---")
    scenarios = [
        {"agency_sim": "City Planning, Department of (DCP)"},
        {"borough_sim": "Manhattan", "fiscal_year_sim": "2024"},
        {"report_type_sim": "Reports - Annual", "language_sim": "English"}
    ]
    for i, filters in enumerate(scenarios):
        logger.info(f"Sub-test {i+1}: filters={filters}")
        # Build params like search.py
        params = {}
        for k, v in filters.items():
            params[f"f[{k}][]"] = v
        resp = client.get("catalog.json", params=params)
        logger.info(f"Status: {resp.status_code}")
        assert resp.status_code == 200

def test_deep_pagination(client):
    logger.info("\n--- TEST 9: Deep Pagination Stress ---")
    pages = [1, 5, 10, 25] # 50/100 might be too much if results are few, but catalog.json usually has many
    for p in pages:
        logger.info(f"Requesting Page {p}...")
        resp = client.get("catalog.json", params={"page": p, "rows": 10})
        logger.info(f"Status: {resp.status_code}")
        # Note: If page exceeds total, Hyrax usually returns 200 with empty docs
        assert resp.status_code == 200

def test_special_queries(client):
    logger.info("\n--- TEST 10: Special Character Queries ---")
    queries = ["' OR 1=1", "<script>", "budget & housing", "2024/2025"]
    for q in queries:
        logger.info(f"Searching for: {q}")
        resp = client.get("catalog.json", params={"q": q})
        logger.info(f"Status: {resp.status_code}")
        # We expect 200 (search result) or 400 (if API rejects it), but not 403
        assert resp.status_code in [200, 400]

def run_all_tests():
    client = HyraxClient()
    # Reduce delay slightly for testing, but keep it safe
    client.request_delay = 1.0 
    
    try:
        test_baseline(client)
        test_catalog_json(client)
        test_search_variety(client)
        test_deep_pagination(client)
        test_special_queries(client)
        test_stress_requests(client, count=3)
        test_concurrent_requests(client, workers=2)
        logger.info("\nAll enhanced automated tests passed!")
    except Exception as e:
        logger.error(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()
