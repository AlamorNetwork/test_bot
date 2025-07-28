# api_client/xui_api_client.py (نسخه جدید بر اساس مستندات Postman)

import requests
import json
import logging

# غیرفعال کردن هشدارهای مربوط به SSL
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

class XuiAPIClient:
    """
    یک کلاینت API قوی و بازنویسی شده برای پنل‌های 3X-UI
    که بر اساس مستندات رسمی Postman ساخته شده است.
    """
    def __init__(self, panel_url, username, password):
        self.base_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
        self.is_logged_in = False
        logger.info(f"XuiAPIClient initialized for {self.base_url}")

    def _request(self, method, path, **kwargs):
        """یک متد مرکزی و قوی برای ارسال تمام درخواست‌ها."""
        if not path.startswith('/'):
            path = '/' + path
        
        # اگر لاگین نکرده بودیم (به جز برای خود api لاگین)، ابتدا لاگین کن
        if not self.is_logged_in and path != '/login':
            if not self.login():
                return None # اگر لاگین ناموفق بود، درخواست را ادامه نده

        url = self.base_url + path
        try:
            response = self.session.request(method, url, verify=False, timeout=20, **kwargs)

            # اگر با خطای عدم دسترسی مواجه شدیم، یک بار دیگر برای لاگین تلاش می‌کنیم
            if response.status_code in [401, 403]:
                logger.warning("Authentication error (401/403). Attempting to re-login...")
                if not self.login():
                    return None
                # درخواست اصلی را دوباره تکرار کن
                response = self.session.request(method, url, verify=False, timeout=20, **kwargs)

            response.raise_for_status() # بررسی خطاهای HTTP مثل 500

            # مدیریت پاسخ‌های خالی که باعث کرش می‌شدند
            if not response.text:
                logger.warning(f"Received empty response from {path}")
                return None
            
            return response.json()

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from {path}. Response: {response.text[:200]}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {path}: {e}")
            return None

    def login(self):
        """لاگین به پنل و ذخیره کوکی نشست (session)."""
        self.is_logged_in = False
        payload = {'username': self.username, 'password': self.password}
        response_data = self._request('post', '/login', data=payload)
        
        if response_data and response_data.get('success'):
            logger.info(f"Successfully logged in to {self.base_url}")
            self.is_logged_in = True
            return True
        else:
            msg = response_data.get('msg', 'Unknown login error') if response_data else "No response from server"
            logger.error(f"Login failed for {self.base_url}: {msg}")
            return False

    def list_inbounds(self):
        """
        لیست تمام اینباندها را با جزئیات کامل برمی‌گرداند.
        مسیر API بر اساس مستندات: /panel/api/inbounds/list
        """
        logger.info("Attempting to get inbound list...")
        # متد درخواست GET است، نه POST
        response_data = self._request('get', '/panel/api/inbounds/list')
        
        if response_data and response_data.get('success'):
            return response_data.get('obj', [])
        
        logger.warning(f"Could not get inbounds. Response: {response_data}")
        return []

    def add_client(self, inbound_id, client_settings_json):
        """
        یک کلاینت جدید به یک اینباند مشخص اضافه می‌کند.
        مسیر API بر اساس مستندات: /panel/api/inbounds/addClient
        """
        logger.info(f"Adding client to inbound {inbound_id}...")
        payload = {
            "id": inbound_id,
            "settings": client_settings_json # این باید یک رشته JSON باشد
        }
        # متد درخواست POST است
        response_data = self._request('post', '/panel/api/inbounds/addClient', json=payload)
        
        if response_data and response_data.get('success'):
            logger.info("Client added successfully.")
            return True
        
        logger.error(f"Failed to add client. Response: {response_data}")
        return False