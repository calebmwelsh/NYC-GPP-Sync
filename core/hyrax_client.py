import logging
import os
import random
import time
from typing import Any, Dict, Optional

from curl_cffi import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HyraxClient:
    """
    A robust client for interacting with Samvera-Hyrax (GPP) that handles
    403 Access Denied errors and rate limiting.
    """
    
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    
    def __init__(self, base_url: Optional[str] = None):
        # Search for .env/.env starting from current file up to root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        env_path = os.path.join(project_root, '.env', '.env')
        load_dotenv(dotenv_path=env_path)
        
        self.base_url = base_url or os.getenv("GPP_BASE_URL", "https://a860-gpp.nyc.gov")
        self.session = requests.Session()
        self.impersonate = "safari" # Safari TLS fingerprint is more resilient for Akamai

        # User agents must match the impersonation target to avoid TLS/UA fingerprint mismatch
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ]

        # Base headers aligned with Safari behaviour
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        self.request_delay = float(os.getenv("GPP_REQUEST_DELAY", "1.5"))
        self.initialized = False
        self.consecutive_403s = 0
        self.requests_since_init = 0
        self.cool_down_until = 0 # Request index to cool down until

    def reset_session(self):
        """Reset the session and cookies to clear any Akamai flags."""
        logger.warning("Resetting session due to persistent 403 errors...")
        self.session = requests.Session()
        self.initialized = False
        self.consecutive_403s = 0
        self.requests_since_init = 0
        self._initialize_session()

    def _get_random_headers(self) -> Dict[str, str]:
        """Generate randomized headers to avoid fingerprinting."""
        headers = self.headers.copy()
        headers["User-Agent"] = random.choice(self.user_agents)
        
        # Randomize Accept-Language slightly
        languages = ["en-US,en;q=0.9", "en-US,en;q=0.8", "en-GB,en;q=0.9,en-US;q=0.8"]
        headers["Accept-Language"] = random.choice(languages)
        
        return headers

    def _simulate_human_navigation(self):
        """Occasionally visit the root or facets to maintain a natural traffic profile."""
        if self.requests_since_init > 0 and self.requests_since_init % 10 == 0:
            logger.info("Simulating human navigation (refreshing session footprint)...")
            try:
                self.session.get(f"{self.base_url}/", headers=self._get_random_headers(), impersonate=self.impersonate, timeout=15)
                time.sleep(random.uniform(2, 5))
            except Exception as e:
                logger.debug(f"Human navigation simulation failed: {e}")

    def _initialize_session(self):
        """Perform a 'first visit' to the home page to get cookies and establish a session footprint."""
        if self.initialized:
            return
            
        logger.info(f"Initializing Akamai session at {self.base_url}...")
        try:
            # Akamai requires a clean impersonated visit to the root
            resp = self.session.get(
                f"{self.base_url}/", 
                headers=self._get_random_headers(), 
                impersonate=self.impersonate,
                timeout=30
            )
            resp.raise_for_status()
            logger.info(f"Session initialized (Status {resp.status_code}). Cookies: {list(self.session.cookies.get_dict().keys())}")
            self.initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize session: {e}")

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Perform a request with retries and exponential backoff."""
        if not self.initialized:
            self._initialize_session()

        # Human-like break
        self._simulate_human_navigation()
        self.requests_since_init += 1

        url = f"{self.base_url}/{path.lstrip('/')}" if not path.startswith("http") else path
        
        max_retries = 3
        backoff_factor = 4
        
        for attempt in range(max_retries):
            # Dynamic headers for each attempt
            headers = self._get_random_headers()
            if "headers" in kwargs:
                headers.update(kwargs["headers"])
            
            # Jitter: base delay + random + exponential part
            current_delay = self.request_delay + random.uniform(0.5, 2.5)
            
            # Apply cool-down if recently hit 403
            if self.requests_since_init < self.cool_down_until:
                cool_down_extra = random.uniform(3, 8)
                logger.debug(f"Applying cool-down delay (+{cool_down_extra:.2f}s)...")
                current_delay += cool_down_extra

            if attempt > 0:
                current_delay += (backoff_factor ** attempt) + random.uniform(2, 5)
            
            logger.debug(f"Waiting {current_delay:.2f}s before request...")
            time.sleep(current_delay)
            
            try:
                logger.debug(f"Requesting {url} (Attempt {attempt + 1})")
                
                request_kwargs = kwargs.copy()
                if "headers" in request_kwargs:
                    del request_kwargs["headers"]

                if method.upper() == "GET":
                    response = self.session.get(url, headers=headers, impersonate=self.impersonate, **request_kwargs)
                else:
                    response = self.session.request(method, url, headers=headers, impersonate=self.impersonate, **request_kwargs)
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 15))
                    wait_time = retry_after + (backoff_factor ** attempt) + random.uniform(5, 10)
                    logger.warning(f"Rate limited (429). Waiting {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code == 403:
                    self.consecutive_403s += 1
                    logger.error(f"403 Access Denied for {url} (Consecutive: {self.consecutive_403s})")
                    
                    # Schedule cool-down for next few requests
                    self.cool_down_until = self.requests_since_init + 5
                    
                    if self.consecutive_403s >= 2:
                        self.reset_session()
                        continue

                    if attempt < max_retries - 1:
                        wait_time = (backoff_factor ** attempt) + random.uniform(3, 7)
                        logger.info(f"Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                        continue
                
                if response.status_code < 400:
                    self.consecutive_403s = 0
                    
                return response
                
            except Exception as e:
                logger.error(f"Request error for {url}: {e}")
                if attempt < max_retries - 1:
                    wait_time = (backoff_factor ** attempt) + random.uniform(2, 5)
                    time.sleep(wait_time)
                else:
                    raise

        return response

    def get(self, path: str, referer: Optional[str] = None, **kwargs) -> requests.Response:
        """Helper for GET requests with optional referer."""
        headers = kwargs.pop("headers", {})
        if referer:
            headers["Referer"] = referer
            # When referer is set, we usually want to indicate same-origin if it matches base_url
            if referer.startswith(self.base_url):
                headers["Sec-Fetch-Site"] = "same-origin"
        
        return self.request("GET", path, headers=headers, **kwargs)

    def _warmup_for_work(self, work_id: str) -> Optional[str]:
        """
        Build a natural navigation trail before downloading a work's file.
        Returns the best available referer URL, or None if warmup failed entirely.
        Sequence: Root (already done in init) -> Catalog HTML -> Concern page
        """
        # Step 1: Visit catalog search results page to look like a real user browsing
        catalog_search_url = f"{self.base_url}/catalog?search_field=all_fields&q="
        logger.info(f"Warming up session: visiting catalog search page...")
        try:
            resp = self.session.get(
                catalog_search_url,
                headers=self._get_random_headers(),
                impersonate=self.impersonate,
                timeout=20
            )
            if resp.status_code == 200:
                time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            logger.debug(f"Catalog search warmup failed: {e}")

        # Step 2: Try the concern HTML page with catalog search as referer
        concern_path = f"concern/nyc_government_publications/{work_id}"
        concern_url = f"{self.base_url}/{concern_path}"
        logger.info(f"Visiting item page {concern_path} before download...")
        resp = self.get(concern_path, referer=catalog_search_url)
        if resp.status_code == 200:
            logger.info(f"Item page visit successful.")
            return concern_url

        # Step 3: Concern page failed — use catalog item page as fallback referer
        catalog_item_url = f"{self.base_url}/catalog/{work_id}"
        logger.warning(f"Concern page returned {resp.status_code}. Falling back to catalog item as referer.")
        try:
            resp2 = self.session.get(
                catalog_item_url,
                headers=self._get_random_headers(),
                impersonate=self.impersonate,
                timeout=20
            )
            if resp2.status_code == 200:
                time.sleep(random.uniform(1.0, 2.5))
                return catalog_item_url
        except Exception as e:
            logger.debug(f"Catalog item warmup failed: {e}")

        # Return catalog item URL as best-effort referer even if it failed
        return catalog_item_url

    def download_file(self, file_id: str, output_path: str, work_id: Optional[str] = None):
        """
        Download a file with Akamai bypass logic.
        sequence: Root (init) -> Catalog Search -> Item/Concern Page -> Download
        """
        if not self.initialized:
            self._initialize_session()

        # 1. Warm up the session with a natural navigation trail
        referer_url = f"{self.base_url}/"
        if work_id:
            referer_url = self._warmup_for_work(work_id) or f"{self.base_url}/"

        # Reset counter so warmup 403s don't carry over and poison the download attempt
        self.consecutive_403s = 0

        # 2. Download the file
        logger.info(f"Downloading file {file_id} to {output_path}...")
        download_path = f"downloads/{file_id}"

        # Safari-consistent headers for the download — no Sec-Fetch-* (Safari omits them)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        res = self.get(download_path, referer=referer_url, headers=headers, stream=True, timeout=60)

        if res.status_code == 200:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"File downloaded successfully to {output_path}")
        else:
            logger.error(f"Download failed with status {res.status_code}")
            res.raise_for_status()

if __name__ == "__main__":
    # Diagnostic test
    client = HyraxClient()
    # logging.getLogger().setLevel(logging.DEBUG) # Uncomment for deep debugging
    
    print("--- Testing Metadata (Catalog JSON) ---")
    res = client.get("catalog/9880vs24b.json")
    print(f"Metadata Status: {res.status_code}")
    if res.status_code == 200:
        print("Success!")
        
    print("\n--- Testing Download ---")
    try:
        # Try to download the file we know exists: 3t945r892
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        test_out = os.path.join(project_root, '.tmp', 'test_client_dl.pdf')
        client.download_file("3t945r892", test_out, work_id="9880vs24b")
        print(f"Download Success! Check {test_out}")
    except Exception as e:
        print(f"Download Failed: {e}")

