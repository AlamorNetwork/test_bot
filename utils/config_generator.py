# utils/config_generator.py

import json
import logging
import uuid
import datetime
from urllib.parse import quote
import base64

from utils.helpers import generate_random_string

logger = logging.getLogger(__name__)

class ConfigGenerator:
    def __init__(self, xui_api_client, db_manager):
        self.xui_api = xui_api_client
        self.db_manager = db_manager
        logger.info("ConfigGenerator initialized.")

    def create_subscription_for_server(self, user_telegram_id: int, server_id: int, total_gb: float, duration_days: int):
        inbounds_list = self.db_manager.get_server_inbounds(server_id, only_active=True)
        return self._build_configs(user_telegram_id, inbounds_list, total_gb, duration_days)

    def create_subscription_for_profile(self, user_telegram_id: int, profile_id: int, total_gb: float, duration_days: int):
        inbounds_list = self.db_manager.get_inbounds_for_profile(profile_id)
        return self._build_configs(user_telegram_id, inbounds_list, total_gb, duration_days)

    def _build_configs(self, user_telegram_id: int, inbounds_list: list, total_gb: float, duration_days: int):
        all_generated_configs = []
        
        webhook_subscription_id = generate_random_string(16)
        master_client_uuid = str(uuid.uuid4())
        master_client_email = f"u{user_telegram_id}.{generate_random_string(6)}"
        master_xui_sub_id = generate_random_string(12)
        
        client_details_for_db = {
            'uuid': master_client_uuid, 'email': master_client_email, 'sub_id': master_xui_sub_id
        }

        inbounds_by_server = {}
        for inbound_info in inbounds_list:
            server_id = inbound_info['server_id']
            if server_id not in inbounds_by_server:
                inbounds_by_server[server_id] = []
            inbounds_by_server[server_id].append(inbound_info)

        for server_id, inbounds in inbounds_by_server.items():
            server_data = self.db_manager.get_server_by_id(server_id)
            if not server_data: continue

            api_client = self.xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
            
            panel_inbounds_details = {i['id']: i for i in api_client.list_inbounds()}
            if not panel_inbounds_details:
                logger.error(f"Could not retrieve any inbound details from server {server_id}.")
                continue

            expiry_time_ms = 0
            if duration_days and duration_days > 0:
                expire_date = datetime.datetime.now() + datetime.timedelta(days=duration_days)
                expiry_time_ms = int(expire_date.timestamp() * 1000)
            
            total_traffic_bytes = int(total_gb * (1024**3)) if total_gb and total_gb > 0 else 0

            for s_inbound in inbounds:
                # ساخت JSON برای تنظیمات کلاینت
                client_settings = {
                    "id": master_client_uuid, "email": master_client_email, "flow": "",
                    "totalGB": total_traffic_bytes, "expiryTime": expiry_time_ms,
                    "enable": True, "tgId": str(user_telegram_id), "subId": master_xui_sub_id,
                }
                
                # تبدیل دیکشنری به یک رشته JSON
                client_settings_string = json.dumps({"clients": [client_settings]})
                
                # --- FIX: فراخوانی صحیح تابع جدید ---
                if not api_client.add_client(s_inbound['inbound_id'], client_settings_string):
                    logger.error(f"Failed to add client to inbound {s_inbound['inbound_id']} on server {server_id}.")
                    continue

                inbound_details = panel_inbounds_details.get(s_inbound['inbound_id'])
                if inbound_details:
                    single_config = self._generate_single_config_url(master_client_uuid, server_data, inbound_details)
                    if single_config:
                        all_generated_configs.append(single_config)
                else:
                    logger.warning(f"Details for inbound ID {s_inbound['inbound_id']} not found.")

        return (webhook_subscription_id, all_generated_configs, client_details_for_db) if all_generated_configs else (None, None, None)
    
    
    def _generate_single_config_url(self, client_uuid: str, server_data: dict, inbound_details: dict) -> dict or None:
        """This function now correctly handles various VLESS configurations."""
        try:
            protocol = inbound_details.get('protocol')
            remark = inbound_details.get('remark', f"Alamor-{server_data['name']}")
            # آدرس را از subscription_base_url استخراج می‌کنیم
            address = server_data['subscription_base_url'].split('//')[1].split(':')[0].split('/')[0]
            port = inbound_details.get('port')
            
            stream_settings = json.loads(inbound_details.get('streamSettings', '{}'))
            network = stream_settings.get('network', 'tcp')
            security = stream_settings.get('security', 'none')
            config_url = ""

            if protocol == 'vless':
                params = {'type': network}
                
                if security in ['tls', 'xtls', 'reality']:
                    params['security'] = security
                
                if security == 'reality':
                    reality_settings = stream_settings.get('realitySettings', {})
                    params['fp'] = reality_settings.get('fingerprint', '')
                    params['pbk'] = reality_settings.get('publicKey', '')
                    params['sid'] = reality_settings.get('shortId', '')
                    params['sni'] = reality_settings.get('serverNames', [''])[0]
                
                if security == 'tls':
                    tls_settings = stream_settings.get('tlsSettings', {})
                    params['sni'] = tls_settings.get('serverName', address)

                if network == 'ws':
                    ws_settings = stream_settings.get('wsSettings', {})
                    params['path'] = ws_settings.get('path', '/')
                    params['host'] = ws_settings.get('headers', {}).get('Host', address)
                    if security == 'tls':
                        params['sni'] = params['host']

                if security == 'xtls':
                    xtls_settings = stream_settings.get('xtlsSettings', {})
                    params['flow'] = xtls_settings.get('flow', 'xtls-rprx-direct')

                query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in params.items() if v])
                config_url = f"vless://{client_uuid}@{address}:{port}?{query_string}#{quote(remark)}"
            
            if config_url:
                return {"remark": remark, "url": config_url}
        except Exception as e:
            logger.error(f"Error in _generate_single_config_url: {e}")
        return None