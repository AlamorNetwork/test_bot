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
            'uuid': master_client_uuid,
            'email': master_client_email,
            'sub_id': master_xui_sub_id
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
            if not api_client.login(): continue
            
            # --- FIX: Get all inbound details once and store in a dictionary ---
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
                client_settings = {
                    "id": master_client_uuid, "email": master_client_email, "flow": "",
                    "totalGB": total_traffic_bytes, "expiryTime": expiry_time_ms,
                    "enable": True, "tgId": str(user_telegram_id), "subId": master_xui_sub_id,
                }
                
                add_client_payload = {"id": s_inbound['inbound_id'], "settings": json.dumps({"clients": [client_settings]})}
                
                if not api_client.add_client(add_client_payload):
                    logger.error(f"Failed to add client to inbound {s_inbound['inbound_id']} on server {server_id}.")
                    continue

                # --- FIX: Use the details from the dictionary instead of a new API call ---
                inbound_details = panel_inbounds_details.get(s_inbound['inbound_id'])
                if inbound_details:
                    single_config = self._generate_single_config_url(master_client_uuid, server_data, inbound_details)
                    if single_config:
                        all_generated_configs.append(single_config)
                else:
                    logger.warning(f"Details for inbound ID {s_inbound['inbound_id']} not found in the list from panel.")

        return (webhook_subscription_id, all_generated_configs, client_details_for_db) if all_generated_configs else (None, None, None)
