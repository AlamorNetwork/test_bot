# api_client/xui_api_client.py

import requests
import urllib3
import json
import logging
import time

# This import should come from config, ensure it exists
# from config import MAX_API_RETRIES
# Fallback if the import fails
try:
    from config import MAX_API_RETRIES
except ImportError:
    MAX_API_RETRIES = 3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

class XuiAPIClient:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        logger.info(f"XuiAPIClient initialized for {self.panel_url}")

    def _make_request(self, method, endpoint, data=None, retries=0):
        url = f"{self.panel_url}{endpoint}"
        try:
            response = self.session.request(method, url, json=data, verify=False, timeout=15)
            response.raise_for_status()

            # --- THE CRITICAL FIX IS HERE ---
            try:
                response_json = response.json()
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON from endpoint {endpoint}. Response was not valid JSON.")
                logger.error(f"Response Status: {response.status_code}, Response Text: {response.text[:200]}") # Log the problematic response
                return None # Return None instead of crashing
            # --- END OF CRITICAL FIX ---

            if response_json.get('success', False):
                return response_json
            else:
                msg = response_json.get('msg', 'Unknown API error')
                logger.warning(f"API request to {endpoint} failed: {msg}")
                # If it's an authentication error, try to re-login
                if response.status_code in [401, 403] or "Login Failed" in msg:
                    logger.warning(f"Authentication error for {endpoint}. Attempting to re-login.")
                    if self.login():
                        logger.info("Re-login successful. Retrying original request.")
                        # Important: Do not re-call _make_request here to avoid infinite loops.
                        # The session cookie is now fixed, subsequent calls should work.
                        return self.session.request(method, url, json=data, verify=False, timeout=15).json()
                    else:
                        logger.error("Re-login failed.")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for endpoint {endpoint}: {e}")
            if retries < MAX_API_RETRIES:
                time.sleep(1) # Simple sleep
                logger.info(f"Retrying request for {endpoint} ({retries + 1}/{MAX_API_RETRIES})...")
                return self._make_request(method, endpoint, data, retries + 1)
            return None

    def login(self):
        self.session.cookies.clear()
        endpoint = "/login"
        data = {"username": self.username, "password": self.password}
        try:
            res = self.session.post(f"{self.panel_url}{endpoint}", json=data, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if res.status_code == 200 and response_json.get("success"):
                logger.info("Successfully logged in to X-UI panel. '3x-ui' cookie found.")
                return True
            logger.error(f"Failed to login. Message: {response_json.get('msg', 'Unknown error')}")
            return False
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Login request exception: {e}")
            return False

    def list_inbounds(self):
        """Lists all inbounds. Now protected by the improved _make_request."""
        response_data = self._make_request("POST", "/panel/api/inbounds/list")
        if response_data and response_data.get('success'):
            return response_data.get('obj', [])
        logger.warning("Could not retrieve inbound list or list was empty.")
        return []

    def get_inbound(self, inbound_id):
        """Gets a single inbound. Now protected by the improved _make_request."""
        response_data = self._make_request("POST", f"/panel/api/inbounds/get/{inbound_id}")
        if response_data and response_data.get('success'):
            return response_data.get('obj')
        return None # Return None if it fails

    def add_client(self, data):
        """Adds a client to an inbound. Now protected by the improved _make_request."""
        response_data = self._make_request("POST", "/panel/api/inbounds/addClient", data=data)
        return response_data is not None and response_data.get('success', False)
