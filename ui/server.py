import http.server
import json
import logging
import os
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from dateutil import rrule
from dateutil.parser import parse as parse_date
import pytz
from curl_cffi import requests
from urllib.parse import parse_qs, urlparse

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.append(PROJECT_ROOT)

from core.hyrax_client import HyraxClient

# Configuration
PORT = 8004
ENV_PATH = os.path.join(PROJECT_ROOT, '.env', '.env')
FILTERS_JSON_PATH = os.path.join(PROJECT_ROOT, '.tmp', 'gpp_filters.json')
CONNECTORS_PATH = os.path.join(PROJECT_ROOT, 'config', 'connectors.json')
DOWNLOAD_SCRIPT_PATH = os.path.join(PROJECT_ROOT, 'cli', 'download.py')
SEARCH_SCRIPT_PATH = os.path.join(PROJECT_ROOT, 'cli', 'search.py')
BULK_SCRIPT_PATH = os.path.join(PROJECT_ROOT, 'cli', 'bulk_ingest.py')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Configure logging
LOG_FILE = os.path.join(PROJECT_ROOT, '.tmp', 'ui_server.log')
os.makedirs(os.path.join(PROJECT_ROOT, '.tmp'), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global process handle and log storage
current_process = None
server_logs = []
log_lock = threading.Lock()

def read_process_output(process):
    """Background thread function to read stdout/stderr."""
    global server_logs
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            with log_lock:
                server_logs.append(line.strip())
                if len(server_logs) > 2000:
                    server_logs.pop(0)
    except Exception as e:
        with log_lock:
            server_logs.append(f"[Server Error reading process logs]: {e}")
    finally:
        process.stdout.close()

def calculate_next_run(schedule, base_time):
    rrule_str = schedule.get("rrule", "FREQ=DAILY;INTERVAL=1")
    tz_name = schedule.get("timezone", "UTC")
    
    try:
        tz = pytz.timezone(tz_name)
        # Ensure base_time is aware
        if base_time.tzinfo is None:
            base_time = tz.localize(base_time)
        else:
            base_time = base_time.astimezone(tz)
            
        rule = rrule.rrulestr(rrule_str, dtstart=base_time)
        next_run = rule.after(base_time)
        
        if next_run:
            schedule["next_run"] = next_run.isoformat()
        else:
            schedule["next_run"] = None
    except Exception as e:
        logger.error(f"Error calculating next run for RRULE '{rrule_str}': {e}")
        schedule["next_run"] = None

class NativeScheduler:
    """Background engine that triggers scheduled syncs."""
    def __init__(self, connectors_path, schedule_script_path):
        self.connectors_path = connectors_path
        self.schedule_script_path = schedule_script_path
        self.running = True

    def run(self):
        logger.info("Native Scheduler Engine started.")
        while self.running:
            try:
                self.check_and_run()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            time.sleep(60) # Check every minute

    def check_and_run(self):
        if not os.path.exists(self.connectors_path):
            return

        with open(self.connectors_path, 'r', encoding='utf-8') as f:
            connectors = json.load(f)

        updated = False
        now = datetime.now()

        for c_id, config in connectors.items():
            schedule = config.get("schedule")
            if not schedule or not schedule.get("enabled"):
                continue

            next_run_str = schedule.get("next_run")
            if not next_run_str:
                # Initialize next run if missing
                calculate_next_run(schedule, datetime.now())
                updated = True
                continue

            next_run = datetime.fromisoformat(next_run_str)
            
            # Use the connector's timezone for comparison
            tz_name = schedule.get("timezone", "UTC")
            tz = pytz.timezone(tz_name)
            now = datetime.now(tz)
            
            if now >= next_run:
                logger.info(f"[Scheduler] Triggering sync for connector: {config.get('name')} ({c_id})")
                
                # Spawn schedule.py as a background process
                cmd = [sys.executable, self.schedule_script_path, "--connector", c_id]
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                
                # Update last and next run
                schedule["last_run"] = now.isoformat()
                calculate_next_run(schedule, now)
                updated = True

        if updated:
            with open(self.connectors_path, 'w', encoding='utf-8') as f:
                json.dump(connectors, f, indent=2)

class GPPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/' or parsed_url.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            template_path = os.path.join(TEMPLATE_DIR, 'connectors.html')
            if os.path.exists(template_path):
                with open(template_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"<h1>Template Not Found</h1>")
            return
            
        if parsed_url.path == '/explorer':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            template_path = os.path.join(TEMPLATE_DIR, 'explorer.html')
            if os.path.exists(template_path):
                with open(template_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"<h1>Template Not Found</h1>")
            return
            
        if parsed_url.path == '/api/connectors':
            self.handle_get_connectors()
            return
            
        if parsed_url.path == '/api/config':
            self.handle_get_config()
            return
            
        if parsed_url.path == '/api/status':
            self.handle_get_status()
            return
            
        if parsed_url.path == '/api/logs':
            self.handle_get_logs()
            return

        if parsed_url.path == '/api/download':
            query = parse_qs(parsed_url.query)
            work_id = query.get('id', [None])[0]
            if work_id:
                self.handle_api_download(work_id)
                return
            else:
                self.send_error(400, "Missing id parameter")
                return

        return super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        data = {}
        if post_data:
            try:
                data = json.loads(post_data.decode('utf-8'))
            except Exception as e:
                logger.error(f"Error parsing POST data: {e}")

        if path == '/api/save':
            self.handle_save_config(data)
        elif path == '/api/connectors/save':
            self.handle_save_connector(data)
        elif path == '/api/connectors/delete':
            self.handle_delete_connector(data)
        elif path == '/api/connectors/load':
            self.handle_load_connector(data)
        elif path == '/api/scheduler/preview':
            self.handle_scheduler_preview(data)
        elif path == '/api/connectors/schedule':
            self.handle_save_schedule(data)
        elif path == '/api/run':
            self.handle_run_download(data.get("id"))
        elif path == '/api/search':
            self.handle_search(data)
        else:
            self.send_error(404, "Not Found")

    def read_connectors(self):
        if not os.path.exists(CONNECTORS_PATH):
            return {}
        try:
            with open(CONNECTORS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading connectors: {e}")
            return {}

    def write_connectors(self, data):
        try:
            os.makedirs(os.path.dirname(CONNECTORS_PATH), exist_ok=True)
            with open(CONNECTORS_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error writing connectors: {e}")
            return False

    def handle_get_connectors(self):
        data = self.read_connectors()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def handle_save_connector(self, data):
        c_id = data.get("id", uuid.uuid4().hex)
        name = data.get("name", "Untitled")
        description = data.get("description", "")
        filters = data.get("filters", {})
        
        connectors = self.read_connectors()
        connectors[c_id] = {
            "name": name,
            "description": description,
            "filters": filters
        }
        
        if self.write_connectors(connectors):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "saved", "id": c_id}).encode('utf-8'))
        else:
            self.send_error(500, "Failed to save connector")

    def handle_save_schedule(self, data):
        c_id = data.get("id")
        enabled = data.get("enabled", False)
        rrule_str = data.get("rrule", "FREQ=DAILY;INTERVAL=1")
        timezone = data.get("timezone", "UTC")
        
        connectors = self.read_connectors()
        if c_id not in connectors:
            self.send_error(404, "Connector not found")
            return
            
        schedule = connectors[c_id].get("schedule", {})
        schedule["enabled"] = enabled
        schedule["rrule"] = rrule_str
        schedule["timezone"] = timezone
        
        if enabled:
            calculate_next_run(schedule, datetime.now())
        else:
            schedule["next_run"] = None
            
        connectors[c_id]["schedule"] = schedule
        if self.write_connectors(connectors):
            self.send_json({"status": "success", "next_run": schedule.get("next_run")})
        else:
            self.send_error(500, "Failed to save schedule")

    def handle_scheduler_preview(self, data):
        rrule_str = data.get("rrule")
        tz_name = data.get("timezone", "UTC")
        count = data.get("count", 5)
        
        try:
            tz = pytz.timezone(tz_name)
            now = datetime.now(tz)
            # Use rrulestr to parse the iCal string
            rule = rrule.rrulestr(rrule_str, dtstart=now)
            # Get next N occurrences
            upcoming = []
            curr = now
            for _ in range(count):
                nxt = rule.after(curr)
                if nxt:
                    upcoming.append(nxt.isoformat())
                    curr = nxt
                else:
                    break
            
            self.send_json({
                "status": "success",
                "upcoming": upcoming
            })
        except Exception as e:
            logger.error(f"Preview error: {e}")
            self.send_json({"status": "error", "message": str(e)}, 400)

    def handle_delete_connector(self, data):
        c_id = data.get("id")
        connectors = self.read_connectors()
        
        if c_id in connectors:
            del connectors[c_id]
            if self.write_connectors(connectors):
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "deleted"}).encode('utf-8'))
                return
        
        self.send_error(500, "Failed to delete connector")

    def handle_load_connector(self, data):
        c_id = data.get("id")
        connectors = self.read_connectors()
        
        if c_id in connectors:
            filters = connectors[c_id].get("filters", {})
            success, msg = self._save_config_internal(filters)
            if success:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "loaded"}).encode('utf-8'))
                return
            else:
                self.send_error(500, f"Error writing .env: {msg}")
                return
                
        self.send_error(404, "Connector not found")

    def handle_get_config(self):
        filters_data = {}
        if os.path.exists(FILTERS_JSON_PATH):
            try:
                with open(FILTERS_JSON_PATH, 'r', encoding='utf-8') as f:
                    filters_data = json.load(f)
            except Exception as e:
                logger.error(f"Error reading filters json: {e}")
        
        current_env = {}
        if os.path.exists(ENV_PATH):
            try:
                with open(ENV_PATH, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        if '=' in line:
                            key, val = line.split('=', 1)
                            current_env[key.strip()] = val.strip()
            except Exception as e:
                logger.error(f"Error reading env file: {e}")

        response = {
            "filters": filters_data,
            "current_env": {
                "SEARCH_QUERY": current_env.get("SEARCH_QUERY", ""),
                "SEARCH_AGENCY": current_env.get("SEARCH_AGENCY", ""),
                "SEARCH_SUBJECT": current_env.get("SEARCH_SUBJECT", ""),
                "SEARCH_REPORT_TYPE": current_env.get("SEARCH_REPORT_TYPE", ""),
                "SEARCH_LANGUAGE": current_env.get("SEARCH_LANGUAGE", ""),
                "SEARCH_FISCAL_YEAR": current_env.get("SEARCH_FISCAL_YEAR", ""),
                "SEARCH_CALENDAR_YEAR": current_env.get("SEARCH_CALENDAR_YEAR", ""),
                "SEARCH_BOROUGH": current_env.get("SEARCH_BOROUGH", ""),
                "SEARCH_MANDATED_REPORT": current_env.get("SEARCH_MANDATED_REPORT", ""),
                "SEARCH_LIMIT": current_env.get("SEARCH_LIMIT", "10"),
            }
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def _save_config_internal(self, data):
        lines = []
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        updates = {
            "SEARCH_QUERY": data.get("SEARCH_QUERY", ""),
            "SEARCH_AGENCY": data.get("SEARCH_AGENCY", ""),
            "SEARCH_SUBJECT": data.get("SEARCH_SUBJECT", ""),
            "SEARCH_REPORT_TYPE": data.get("SEARCH_REPORT_TYPE", ""),
            "SEARCH_LANGUAGE": data.get("SEARCH_LANGUAGE", ""),
            "SEARCH_FISCAL_YEAR": data.get("SEARCH_FISCAL_YEAR", ""),
            "SEARCH_CALENDAR_YEAR": data.get("SEARCH_CALENDAR_YEAR", ""),
            "SEARCH_BOROUGH": data.get("SEARCH_BOROUGH", ""),
            "SEARCH_MANDATED_REPORT": data.get("SEARCH_MANDATED_REPORT", ""),
            "SEARCH_LIMIT": str(data.get("SEARCH_LIMIT", "10")),
        }
        
        new_lines = []
        processed_keys = set()
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                new_lines.append(line)
                continue
            
            parts = stripped.split('=', 1)
            key = parts[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                processed_keys.add(key)
            else:
                new_lines.append(line)
        
        for key, val in updates.items():
            if key not in processed_keys:
                new_lines.append(f"{key}={val}\n")
                
        try:
            os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
            with open(ENV_PATH, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True, "saved"
        except Exception as e:
            return False, str(e)

    def handle_save_config(self, data):
        success, msg = self._save_config_internal(data)
        if success:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "saved"}).encode('utf-8'))
        else:
            self.send_error(500, f"Error writing .env: {msg}")

    def handle_run_download(self, work_id):
        global current_process, server_logs
        if current_process and current_process.poll() is None:
            self.send_response(409)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "already_running"}).encode('utf-8'))
            return

        with log_lock:
            server_logs = []

        try:
            if work_id:
                cmd = [sys.executable, '-u', DOWNLOAD_SCRIPT_PATH, "--id", work_id]
            else:
                cmd = [sys.executable, '-u', BULK_SCRIPT_PATH]
                
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace',
                **kwargs
            )
            
            t = threading.Thread(target=read_process_output, args=(current_process,), daemon=True)
            t.start()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_get_status(self):
        global current_process
        status = "idle"
        if current_process:
            ret = current_process.poll()
            if ret is None:
                status = "running"
            else:
                status = "completed"
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": status}).encode('utf-8'))

    def handle_search(self, data):
        try:
            success, msg = self._save_config_internal(data)
            if not success:
                self.send_error(500, f"Failed to save config: {msg}")
                return

            temp_file = f"search_results_{uuid.uuid4().hex}.json"
            temp_path = os.path.join(PROJECT_ROOT, '.tmp', temp_file)

            cmd = [sys.executable, SEARCH_SCRIPT_PATH, "--output", temp_path]
            # Mapping env keys to script args
            if data.get("SEARCH_QUERY"): cmd.extend(["--query", data["SEARCH_QUERY"]])
            if data.get("SEARCH_AGENCY"): cmd.extend(["--agency", data["SEARCH_AGENCY"]])
            if data.get("SEARCH_SUBJECT"): cmd.extend(["--subject", data["SEARCH_SUBJECT"]])
            if data.get("SEARCH_REPORT_TYPE"): cmd.extend(["--report-type", data["SEARCH_REPORT_TYPE"]])
            if data.get("SEARCH_FISCAL_YEAR"): cmd.extend(["--fiscal-year", data["SEARCH_FISCAL_YEAR"]])
            if data.get("SEARCH_CALENDAR_YEAR"): cmd.extend(["--calendar-year", data["SEARCH_CALENDAR_YEAR"]])
            if data.get("SEARCH_BOROUGH"): cmd.extend(["--borough", data["SEARCH_BOROUGH"]])
            if data.get("SEARCH_MANDATED_REPORT"): cmd.extend(["--mandated-report", data["SEARCH_MANDATED_REPORT"]])
            if data.get("SEARCH_LIMIT"): cmd.extend(["--rows", data["SEARCH_LIMIT"]])
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode != 0:
                self.send_error(500, f"Search failed: {result.stderr}")
                return
            
            if os.path.exists(temp_path):
                with open(temp_path, 'r', encoding='utf-8') as f:
                    search_data = json.load(f)
                
                # Save to results.json for bulk_ingest.py
                results_path = os.path.join(PROJECT_ROOT, '.tmp', 'results.json')
                with open(results_path, 'w', encoding='utf-8') as f:
                    json.dump(search_data, f)
                    
                os.remove(temp_path)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(search_data).encode('utf-8'))
            else:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"results": [], "total_count": 0}).encode('utf-8'))

        except Exception as e:
            self.send_error(500, str(e))

    def handle_get_logs(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        with log_lock:
            self.wfile.write(json.dumps({"logs": server_logs}).encode('utf-8'))

    def resolve_file_id(self, client, work_id):
        """Resolves a Work ID to its first or representative FileSet ID."""
        logger.info(f"Resolving FileSet ID for Work: {work_id}...")
        try:
            catalog_path = f"catalog/{work_id}.json"
            res = client.get(catalog_path)
            if res.status_code == 200:
                doc = res.json().get('response', {}).get('document', {})
                file_id = doc.get('representative_id_ssi') or doc.get('representative_id')
                if file_id:
                    return file_id
                members = doc.get('member_ids_ssim') or doc.get('file_set_ids_ssim')
                if members and len(members) > 0:
                    return members[0]
        except Exception as e:
            logger.error(f"Error resolving FileSet ID: {e}")
        return None

    def handle_api_download(self, work_id):
        """Streams the file from GPP to the browser using HyraxClient."""
        logger.info(f"Starting direct download proxy for {work_id}...")
        client = HyraxClient()
        
        try:
            file_id = self.resolve_file_id(client, work_id)
            if not file_id:
                file_id = work_id

            item_path = f"concern/nyc_government_publications/{work_id}"
            item_url = f"{client.base_url}/{item_path}"
            download_path = f"downloads/{file_id}"
            
            # Use client.get to ensure Akamai session and robust retries
            client.get(item_path, referer=f"{client.base_url}/")
            
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1"
            }

            # Use client.get for the actual download as well to get retry logic
            r = client.get(download_path, referer=item_url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            
            content_length = r.headers.get('Content-Length')
            content_type = r.headers.get('Content-Type', 'application/pdf')
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{work_id}.pdf"')
            if content_length:
                self.send_header('Content-Length', content_length)
            self.end_headers()

            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    self.wfile.write(chunk)
            logger.info(f"Download complete for {work_id}.")
        except Exception as e:
            logger.error(f"Direct download error for {work_id}: {e}")
            self.send_error(500, f"Download failed: {str(e)}")

if __name__ == "__main__":
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, '.env'), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, '.tmp'), exist_ok=True)
    
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.write("# Environment Variables for GPP\n")

    # Start Native Scheduler
    schedule_script = os.path.join(PROJECT_ROOT, 'cli', 'schedule.py')
    scheduler = NativeScheduler(CONNECTORS_PATH, schedule_script)
    sched_thread = threading.Thread(target=scheduler.run, daemon=True)
    sched_thread.start()

    logger.info(f"Starting server at http://localhost:{PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), GPPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()
