# api_client/xui_api_client.py

import requests
import urllib3
import json 
import logging 
import time 

from config import MAX_API_RETRIES # این ایمپورت باید از config بیاید

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__) 

class XuiAPIClient: 
    def __init__(self, panel_url, username, password, two_factor=None): 
        self.panel_url = panel_url.rstrip('/') 
        self.username = username
        self.password = password
        self.two_factor = two_factor
        self.session = requests.Session() # استفاده از requests.Session
        # session_token_value دیگر لازم نیست اگر کوکی 3x-ui به درستی مدیریت شود.
        logger.info(f"XuiAPIClient initialized for {self.panel_url}") 

    def _make_request(self, method, endpoint, data=None, retries=0):
        url = f"{self.panel_url}{endpoint}"
        headers = {"Content-Type": "application/json"} 
        # requests.Session() به طور خودکار کوکی‌ها را مدیریت می‌کند.
        # پس از لاگین، کوکی '3x-ui' به طور خودکار در درخواست‌های بعدی ارسال خواهد شد.

        try:
            response = self.session.request(method, url, json=data, headers=headers, verify=False, timeout=15) 
            response.raise_for_status() 

            response_json = response.json()
            if response_json.get('success', False):
                return response_json
            else:
                logger.warning(f"API request to {endpoint} failed: {response_json.get('msg', 'Unknown error')}. Full response: {response_json}")
                if response.status_code in [401, 403]: 
                    logger.warning(f"Authentication error ({response.status_code}) for {endpoint}. Attempting to re-login.")
                    self.session.cookies.clear() # Clear existing cookies
                    if self.login(): # تلاش برای لاگین مجدد
                        logger.info("Re-login successful. Retrying original request.")
                        return self._make_request(method, endpoint, data, retries) 
                    else:
                        logger.error("Re-login failed. Cannot proceed with request.")
                        return None
                return None

        except requests.exceptions.Timeout:
            logger.error(f"API request to {endpoint} timed out.")
            if retries < MAX_API_RETRIES:
                time.sleep(2 ** retries) 
                logger.info(f"Retrying {endpoint} ({retries + 1}/{MAX_API_RETRIES})...")
                return self._make_request(method, endpoint, data, retries + 1)
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API connection error to {endpoint}: {e}")
            if retries < MAX_API_RETRIES:
                time.sleep(2 ** retries) 
                logger.info(f"Retrying {endpoint} ({retries + 1}/{MAX_API_RETRIES})...")
                return self._make_request(method, endpoint, data, retries + 1)
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"An unexpected API request error occurred for {endpoint}: {e}")
            if hasattr(response, 'text'):
                logger.error(f"Response text: {response.text}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from {endpoint}. Response text: {response.text}")
            return None
    
    def login(self):
        self.session.cookies.clear()
        endpoint = "/login"
        data = {"username": self.username, "password": self.password}
        
        logger.info(f"Attempting to login to X-UI panel at {self.panel_url}...")
        try:
            res = self.session.post(f"{self.panel_url}{endpoint}", json=data, verify=False, timeout=10) 
            res.raise_for_status()
            response_json = res.json()
            if res.status_code == 200 and response_json.get("success"):
                if 'session' in self.session.cookies or '3x-ui' in self.session.cookies:
                    logger.info("Successfully logged in to X-UI panel.")
                    return True
            logger.error(f"Failed to login to X-UI panel. Message: {response_json.get('msg', 'Unknown error')}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Login request error: {e}")
            return False

    def check_login(self):
        """
        بررسی می‌کند که آیا لاگین معتبر است یا خیر.
        اگر کوکی '3x-ui' در session موجود باشد، True برمی‌گرداند.
        """
        if '3x-ui' in self.session.cookies: # <--- اینجا هم به روز شد
            return True 
        else:
            return self.login()

    def list_inbounds(self):
        endpoint = "/panel/api/inbounds/list"
        response = self.session.post(f"{self.panel_url}{endpoint}", verify=False, timeout=15)
        if response.status_code == 200 and response.json().get('success'):
            return response.json().get('obj', [])
        return []


    def get_inbound(self, inbound_id):
        """Gets the details of a specific inbound, now with robust error handling."""
        endpoint = f"/panel/api/inbounds/get/{inbound_id}"
        # This function might not be standard in all X-UI versions,
        # so we use the more general _make_request for its retry logic.
        response_data = self._make_request("POST", endpoint)

        if response_data and response_data.get('success'):
            return response_data.get('obj')

        # Fallback for older panel versions or errors
        logger.warning(f"Could not get single inbound {inbound_id}. Falling back to list.")
        try:
            all_inbounds = self.list_inbounds()
            if all_inbounds:
                for inbound in all_inbounds:
                    if inbound.get('id') == inbound_id:
                        logger.info(f"Found inbound {inbound_id} via list fallback.")
                        return inbound
        except Exception as e:
            logger.error(f"Error during get_inbound fallback: {e}")

        logger.error(f"Failed to get details for inbound {inbound_id} after all attempts.")
        return None

            
    def add_inbound(self, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot add inbound.")
            return None
        
        endpoint = "/panel/api/inbounds/add"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Inbound added: {response.get('obj')}")
            return response.get("obj")
        else:
            logger.warning(f"Failed to add inbound: {response}")
            return None

    def delete_inbound(self, inbound_id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete inbound.")
            return False
        
        endpoint = f"/panel/api/inbounds/del/{inbound_id}"
        response = self._make_request("POST", endpoint) 
        
        if response and response.get('success'):
            logger.info(f"Inbound {inbound_id} deleted successfully.")
            return True
        else:
            logger.warning(f"Failed to delete inbound {inbound_id}: {response}")
            return False

    def update_inbound(self, inbound_id, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot update inbound.")
            return False
        
        endpoint = f"/panel/api/inbounds/update/{inbound_id}"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Inbound {inbound_id} updated successfully.")
            return True
        else:
            logger.warning(f"Failed to update inbound {inbound_id}: {response}")
            return False

    def add_client(self, data):
        endpoint = "/panel/api/inbounds/addClient"
        response = self.session.post(f"{self.panel_url}{endpoint}", json=data, verify=False, timeout=15)
        return response.status_code == 200 and response.json().get('success')

    def delete_client(self, inbound_id, client_id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete client.")
            return False
        
        endpoint = f"/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
        response = self._make_request("POST", endpoint) 
        
        if response and response.get('success'):
            logger.info(f"Client {client_id} deleted from inbound ID {inbound_id}.")
            return True
        else:
            logger.warning(f"Failed to delete client {client_id} from inbound ID {inbound_id}: {response}")
            return False

    def update_client(self, client_id, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot update client.")
            return False
        
        endpoint = f"/panel/api/inbounds/updateClient/{client_id}"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Client {client_id} updated successfully.")
            return True
        else:
            logger.warning(f"Failed to update client {client_id}: {response}")
            return False

    def reset_client_traffic(self, id, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset client traffic.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/{id}/resetClientTraffic/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client traffic reset for {email} in inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to reset client traffic for {email} in inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting client traffic for {email} from {url}: {e}")
            return False

    def reset_all_traffics(self):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset all traffics.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/resetAllTraffics"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info("All traffics reset successfully.")
                return True
            else:
                logger.warning(f"Failed to reset all traffics: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting all traffics from {url}: {e}")
            return False

    def reset_all_client_traffics(self, id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset all client traffics.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/resetAllClientTraffics/{id}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"All client traffics reset for inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to reset all client traffics for inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting all client traffics for {id} from {url}: {e}")
            return False

    def del_depleted_clients(self, id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete depleted clients.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/delDepletedClients/{id}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Depleted clients deleted for inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to delete depleted clients for inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting depleted clients for {id} from {url}: {e}")
            return False

    def client_ips(self, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot get client IPs.")
            return None
        url = f"{self.panel_url}/panel/api/inbounds/clientIps/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client IPs retrieved for {email}.")
                return response_json.get("obj")
            else:
                logger.warning(f"Failed to get client IPs for {email}: {response_json.get('msg', res.text)}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting client IPs for {email} from {url}: {e}")
            return None

    def clear_client_ips(self, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot clear client IPs.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/clearClientIps/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client IPs cleared for {email}.")
                return True
            else:
                logger.warning(f"Failed to clear client IPs for {email}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error clearing client IPs for {email} from {url}: {e}")
            return False

    def get_online_users(self):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot get online users.")
            return None
        url = f"{self.panel_url}/panel/api/inbounds/onlines"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info("Successfully retrieved online users.")
                return response_json.get("obj")
            else:
                logger.warning(f"Failed to get online users: {response_json.get('msg', res.text)}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting online users from {url}: {e}")
            return None
        
        
        
        
        
        
