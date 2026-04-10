import json
import os
from typing import Dict

from hyrax_client import HyraxClient

# Configure base settings
BASE_URL = os.getenv("GPP_BASE_URL", "https://a860-gpp.nyc.gov")
TMP_DIR = ".tmp"
OUTPUT_FILE = os.path.join(TMP_DIR, "gpp_filters.json")

def get_all_filters():
    """
    Fetch the catalog JSON and extract all facets (filters) and their values using HyraxClient.
    """
    client = HyraxClient(base_url=BASE_URL)
    url = "catalog.json"
    # We ask for 1 row because some Hyrax instances error on 0
    params = {
        "rows": 1
    }
    
    print(f"Fetching facets from {BASE_URL}/{url}...")
    response = client.get(url, params=params)
    response.raise_for_status()
    
    data = response.json()
    facets_data = data.get("response", {}).get("facets", [])
    
    results = {}
    
    for facet in facets_data:
        name = facet.get("name")
        label = facet.get("label", name)
        items = facet.get("items", [])
        
        # Extract just the values (labels) for the UI
        values = [item.get("value") for item in items if item.get("value")]
        
        if values:
            results[name] = {
                "label": label,
                "values": sorted(values)
            }
            print(f"Found {len(values)} values for facet '{label}' ({name})")

    # Ensure .tmp exists
    os.makedirs(TMP_DIR, exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"Filter data saved to {OUTPUT_FILE}")
    return results

if __name__ == "__main__":
    try:
        get_all_filters()
    except Exception as e:
        print(f"Error fetching filters: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
