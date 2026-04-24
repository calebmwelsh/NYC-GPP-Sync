import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from core.hyrax_client import HyraxClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def search_gpp(client: HyraxClient, query: str, filters: Dict[str, str] = None, rows: int = 10, page: int = 1) -> Dict[str, Any]:
    """
    Search the Government Publications Portal catalog with optional filters and pagination.
    """
    url = "catalog.json"
    params = {
        "q": query,
        "rows": min(rows, 100), # API limit is 100
        "page": page
    }
    
    # Add facets if provided
    if filters:
        for key, value in filters.items():
            if value:
                # Support multi-value filtering via pipe delimiter
                values = [v.strip() for v in value.split('|') if v.strip()]
                if values:
                    # Hyrax uses f[facet_name][] for filtering
                    params[f"f[{key}][]"] = values
    
    logger.info(f"Searching for '{query}' with filters {filters} (Page {page}, Rows {rows})...")
    response = client.get(url, params=params)
    response.raise_for_status()
    
    data = response.json()
    
    # Save raw response for debugging
    tmp_dir = os.path.join(PROJECT_ROOT, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "raw_response.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    resp_data = data.get("response", {})
    docs = resp_data.get("docs", [])
    pages = resp_data.get("pages", {})
    
    results = []
    for doc in docs:
        results.append({
            "id": doc.get("id"),
            "title": doc.get("title_tesim", ["No Title"])[0],
            "agency": doc.get("agency_tesim", ["Unknown Agency"])[0],
            "date": doc.get("date_published_tesim", ["N/A"])[0],
            "type": doc.get("report_type_tesim", ["N/A"])[0]
        })
    
    # Print facets for debugging
    facets = data.get("facet_counts", {}).get("facet_fields", {})
    if facets:
        logger.info("Facet Counts:")
        for facet, values in facets.items():
            # values is a flat list [val1, count1, val2, count2, ...]
            top_values = []
            for i in range(0, min(len(values), 10), 2):
                if values[i+1] > 0:
                    top_values.append(f"{values[i]}: {values[i+1]}")
            if top_values:
                logger.info(f"  {facet}: {', '.join(top_values)}")

    return {
        "results": results,
        "total_count": pages.get("total_count", 0),
        "current_page": pages.get("current_page", 1),
        "total_pages": pages.get("total_pages", 0)
    }

def main():
    parser = argparse.ArgumentParser(description="Search NYC GPP (Hyrax)")
    parser.add_argument("--query", default=None, help="Search query")
    parser.add_argument("--rows", type=int, default=10, help="Number of rows")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--output", help="Path to save results as JSON")
    
    # Known facets for GPP
    parser.add_argument("--agency", help="Filter by Agency")
    parser.add_argument("--subject", help="Filter by Subject")
    parser.add_argument("--report-type", help="Filter by Report Type")
    parser.add_argument("--language", help="Filter by Language")
    parser.add_argument("--fiscal-year", help="Filter by Fiscal Year")
    parser.add_argument("--calendar-year", help="Filter by Calendar Year")
    parser.add_argument("--borough", help="Filter by Borough")
    parser.add_argument("--mandated-report", help="Filter by Mandated Report Name")
    
    args = parser.parse_args()
    
    client = HyraxClient()
    
    # Prioritize environment variables if arguments are empty
    q = args.query if args.query is not None else os.getenv("SEARCH_QUERY", "")
    agency = args.agency or os.getenv("SEARCH_AGENCY", "")
    subject = args.subject or os.getenv("SEARCH_SUBJECT", "")
    report_type = args.report_type or os.getenv("SEARCH_REPORT_TYPE", "")
    language = args.language or os.getenv("SEARCH_LANGUAGE", "")
    fiscal_year = args.fiscal_year or os.getenv("SEARCH_FISCAL_YEAR", "")
    calendar_year = args.calendar_year or os.getenv("SEARCH_CALENDAR_YEAR", "")
    borough = args.borough or os.getenv("SEARCH_BOROUGH", "")
    mandated_report = args.mandated_report or os.getenv("SEARCH_MANDATED_REPORT", "")
    rows = args.rows if args.rows != 10 else int(os.getenv("SEARCH_LIMIT", "10"))
    
    # Map common aliases from front-end
    FILTER_MAP = {
        'reports-annual': 'Reports - Annual',
        'annual': 'Reports - Annual',
        'dhs': 'Homeless Services, Department of (DHS)',
        'brooklyn': 'Brooklyn',
        'manhattan': 'Manhattan',
        'queens': 'Queens',
        'bronx': 'Bronx',
        'staten island': 'Staten Island'
    }
    
    def map_filter(val):
        if not val: return val
        return FILTER_MAP.get(val.lower(), val)

    agency = map_filter(agency)
    report_type = map_filter(report_type)
    borough = map_filter(borough)
    
    filters = {
        "agency_sim": agency,
        "subject_sim": subject,
        "report_type_sim": report_type,
        "language_sim": language,
        "fiscal_year_sim": fiscal_year,
        "calendar_year_sim": calendar_year,
        "borough_sim": borough,
        "required_report_name_sim": mandated_report
    }
    
    filters = {k: v for k, v in filters.items() if v}
    logger.debug(f"Filters after env check: {filters}")
    
    try:
        # Initial search to get total count
        search_data = search_gpp(client, q, filters, rows, args.page)
        total_count = search_data["total_count"]
        all_results = search_data["results"]
        
        # If user requested more than 100, we need to paginate
        if rows > 100 and total_count > 100:
            logger.info(f"Total results: {total_count}. Fetching up to {rows}...")
            to_fetch = min(rows, total_count)
            current_count = len(all_results)
            page = 2
            
            while current_count < to_fetch:
                pdata = search_gpp(client, q, filters, to_fetch - current_count, page)
                if not pdata["results"]:
                    break
                all_results.extend(pdata["results"])
                current_count = len(all_results)
                page += 1
                if page > pdata["total_pages"]:
                    break

        # Ensure .tmp exists
        tmp_dir = os.path.join(PROJECT_ROOT, ".tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        
        output_path = args.output or os.path.join(PROJECT_ROOT, "data", "results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            output_data = search_data
            output_data["results"] = all_results
            json.dump(output_data, f, indent=2)
            
        logger.info(f"Found {total_count} total results. Saved {len(all_results)} to {output_path}.")
        for r in all_results[:10]: # Show first 10
            logger.info(f"- [{r['id']}] {r['title']} ({r['agency']})")
            
    except Exception as e:
        logger.error(f"Search failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()

