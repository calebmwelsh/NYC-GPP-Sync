import argparse
import json
import logging
import os
import sys
from typing import Dict, List

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from core.hyrax_client import HyraxClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Use .tmp/downloads for cleaner root
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, ".tmp", "downloads")

def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for filenames."""
    import re
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def get_work_metadata(client: HyraxClient, work_id: str) -> Dict:
    """Fetch full metadata for a work ID using the robust client."""
    # Try catalog JSON first for Solr fields
    catalog_url = f"catalog/{work_id}.json"
    logger.info(f"Fetching catalog metadata for {work_id}...")
    
    try:
        response = client.get(catalog_url)
        response.raise_for_status()
        data = response.json()
        # The document is often in data['response']['document']
        return data.get("response", {}).get("document", data)
    except Exception as e:
        logger.warning(f"Catalog metadata fetch failed: {e}. Falling back to concern JSON...")
        
    # Fallback to concern JSON
    concern_url = f"concern/nyc_government_publications/{work_id}.json"
    response = client.get(concern_url)
    response.raise_for_status()
    return response.json()

def download_file(client: HyraxClient, file_set_id: str, output_dir: str, work_id: str):
    """Download the actual file associated with a FileSet ID."""
    # Attempt to get filename from FileSet metadata
    fs_metadata_url = f"concern/file_sets/{file_set_id}.json"
    filename = f"{file_set_id}.pdf" # Default
    
    try:
        fs_response = client.get(fs_metadata_url)
        if fs_response.status_code == 200:
            fs_data = fs_response.json()
            filename = fs_data.get("label") or filename
    except Exception as e:
        logger.debug(f"Could not fetch FileSet metadata for {file_set_id}: {e}")

    file_path = os.path.join(output_dir, filename)
    client.download_file(file_set_id, file_path, work_id=work_id)

def download_work(client: HyraxClient, work_id: str, download_files: bool = True):
    """Download metadata and associated files for a work."""
    # 1. Get and save metadata
    try:
        metadata = get_work_metadata(client, work_id)
    except Exception as e:
        logger.error(f"Failed to fetch metadata for work {work_id}: {e}")
        return
    
    # Extract and sanitize title for the folder name
    title = "Unknown_Title"
    titles = metadata.get("title_tesim") or metadata.get("title")
    if titles and isinstance(titles, list):
        title = titles[0]
    elif titles:
        title = titles

    safe_title = sanitize_filename(title)
    output_dir = os.path.join(DOWNLOAD_DIR, f"{safe_title}_{work_id}")
    os.makedirs(output_dir, exist_ok=True)
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to {metadata_path}")
    
    # 2. Identify associated files
    if download_files:
        # Check various fields for file set IDs
        file_set_ids = (
            metadata.get("member_ids_ssim") or 
            metadata.get("file_set_ids_ssim") or 
            metadata.get("file_set_ids") or
            []
        )
        
        # Also check representative ID
        rep_id = metadata.get("representative_id") or metadata.get("representative_id_ssim")
        if rep_id:
            if isinstance(rep_id, list):
                for rid in rep_id:
                    if rid not in file_set_ids:
                        file_set_ids.append(rid)
            elif rep_id not in file_set_ids:
                file_set_ids.append(rep_id)

        if not file_set_ids:
            logger.info("No file sets found for this work.")
            return

        logger.info(f"Found {len(file_set_ids)} file set IDs: {file_set_ids}")

        # 3. Download files
        for fs_id in file_set_ids:
            try:
                download_file(client, fs_id, output_dir, work_id)
            except Exception as e:
                logger.error(f"Failed to download file {fs_id}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download GPP work metadata and files.")
    parser.add_argument("--id", nargs='+', required=True, help="Work ID(s) to download")
    parser.add_argument("--no-files", action="store_true", help="Skip file downloads")
    
    args = parser.parse_args()
    
    # Initialize one client for all downloads to reuse session/cookies
    client = HyraxClient()
    
    for rid in args.id:
        download_work(client, rid, not args.no_files)

