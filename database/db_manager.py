import psycopg2
from psycopg2.extras import DictCursor, execute_values
import logging
from cryptography.fernet import Fernet
import os
import json

# وارد کردن متغیرهای جدید از کانفیگ
from config import (ENCRYPTION_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_name = DB_NAME
        self.db_user = DB_USER
        self.db_password = DB_PASSWORD
        self.db_host = DB_HOST
        self.db_port = DB_PORT
        self.fernet = Fernet(ENCRYPTION_KEY.encode('utf-8'))
        logger.info(f"DatabaseManager initialized for PostgreSQL DB: {self.db_name}")

    def _get_connection(self):
        """یک اتصال جدید به پایگاه داده PostgreSQL برقرار می‌کند."""
        return psycopg2.connect(
            dbname=self.db_name, user=self.db_user, password=self.db_password,
            host=self.db_host, port=self.db_port
        )

    def _encrypt(self, data: str) -> str:
        if data is None: return None
        return self.fernet.encrypt(data.encode('utf-8')).decode('utf-8')

    def _decrypt(self, encrypted_data: str) -> str:
        if encrypted_data is None: return None
        return self.fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')

    def create_tables(self):
        """Creates the necessary tables in the PostgreSQL database."""
        commands = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE NOT NULL, first_name TEXT,
                last_name TEXT, username TEXT, is_admin BOOLEAN DEFAULT FALSE,
                join_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, last_activity TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )""",
            """
            CREATE TABLE IF NOT EXISTS servers (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, panel_url TEXT NOT NULL,
                username TEXT NOT NULL, password TEXT NOT NULL, subscription_base_url TEXT NOT NULL,
                subscription_path_prefix TEXT NOT NULL, is_active BOOLEAN DEFAULT TRUE,
                last_checked TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, is_online BOOLEAN DEFAULT FALSE
            )""",
            """
            CREATE TABLE IF NOT EXISTS plans (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, plan_type TEXT NOT NULL,
                volume_gb REAL, duration_days INTEGER, price REAL, per_gb_price REAL,
                is_active BOOLEAN DEFAULT TRUE
            )""",
            """
            CREATE TABLE IF NOT EXISTS server_inbounds (
                id SERIAL PRIMARY KEY, server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                inbound_id INTEGER NOT NULL, remark TEXT, is_active BOOLEAN DEFAULT TRUE,
                UNIQUE (server_id, inbound_id)
            )""",
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                description TEXT, is_active BOOLEAN DEFAULT TRUE
            )""",
            """
            CREATE TABLE IF NOT EXISTS profile_inbounds (
                profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                server_inbound_id INTEGER NOT NULL REFERENCES server_inbounds(id) ON DELETE CASCADE,
                PRIMARY KEY (profile_id, server_inbound_id)
            )""",
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                purchase_type TEXT NOT NULL DEFAULT 'server', server_id INTEGER REFERENCES servers(id),
                profile_id INTEGER REFERENCES profiles(id), plan_id INTEGER REFERENCES plans(id),
                purchase_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, expire_date TIMESTAMPTZ,
                initial_volume_gb REAL NOT NULL, subscription_id TEXT UNIQUE, full_configs_json TEXT,
                is_active BOOLEAN DEFAULT TRUE
            )""",
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), amount REAL NOT NULL,
                payment_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, receipt_message_id BIGINT,
                is_confirmed BOOLEAN DEFAULT FALSE, admin_confirmed_by INTEGER,
                confirmation_date TIMESTAMPTZ, order_details_json TEXT,
                admin_notification_message_id BIGINT, authority TEXT, ref_id TEXT
            )""",
            """
            CREATE TABLE IF NOT EXISTS payment_gateways (
                id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
                card_number TEXT, card_holder_name TEXT, merchant_id TEXT,
                description TEXT, is_active BOOLEAN DEFAULT TRUE, priority INTEGER DEFAULT 0
            )""",
            """
            CREATE TABLE IF NOT EXISTS free_test_usage (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                usage_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )"""
        ]
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    for command in commands:
                        cursor.execute(command)
                conn.commit()
                logger.info("Database tables created/checked successfully for PostgreSQL.")
        except psycopg2.Error as e:
            logger.error(f"Error creating tables in PostgreSQL: {e}")
            raise e

    def add_or_update_user(self, telegram_id, first_name, last_name=None, username=None):
        sql = """
            INSERT INTO users (telegram_id, first_name, last_name, username, last_activity)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                username = EXCLUDED.username,
                last_activity = CURRENT_TIMESTAMP
            RETURNING id;
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (telegram_id, first_name, last_name, username))
                    user_id = cursor.fetchone()[0]
                    conn.commit()
                    return user_id
        except psycopg2.Error as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
            return None
            
    def get_all_users(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT id, telegram_id, first_name, username, join_date FROM users ORDER BY id DESC")
                    return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting all users: {e}")
            return []

    def get_user_by_telegram_id(self, telegram_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting user by telegram_id {telegram_id}: {e}")
            return None

    def get_user_by_id(self, user_db_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE id = %s", (user_db_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting user by DB ID {user_db_id}: {e}")
            return None

    # --- توابع سرورها ---
    def add_server(self, name, panel_url, username, password, sub_base_url, sub_path_prefix):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO servers (name, panel_url, username, password, subscription_base_url, subscription_path_prefix)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id;
                    """, (name, self._encrypt(panel_url), self._encrypt(username), self._encrypt(password), self._encrypt(sub_base_url), self._encrypt(sub_path_prefix)))
                    server_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Server '{name}' added successfully.")
                    return server_id
        except psycopg2.IntegrityError:
            logger.warning(f"Server with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding server '{name}': {e}")
            return None

    def get_all_servers(self, only_active=True):
        """تمام سرورها را با اطلاعات رمزگشایی شده از دیتابیس دریافت می‌کند."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = "SELECT * FROM servers"
                    if only_active:
                        query += " WHERE is_active = TRUE AND is_online = TRUE"
                    cursor.execute(query)
                    servers_data = cursor.fetchall()
                    
                    decrypted_servers = []
                    for server in servers_data:
                        server_dict = dict(server)
                        server_dict['panel_url'] = self._decrypt(server_dict['panel_url'])
                        server_dict['username'] = self._decrypt(server_dict['username'])
                        server_dict['password'] = self._decrypt(server_dict['password'])
                        server_dict['subscription_base_url'] = self._decrypt(server_dict['subscription_base_url'])
                        server_dict['subscription_path_prefix'] = self._decrypt(server_dict['subscription_path_prefix'])
                        decrypted_servers.append(server_dict)
                    return decrypted_servers
        except Exception as e:
            logger.error(f"Error getting all servers: {e}")
            return []

    def get_server_by_id(self, server_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM servers WHERE id = %s", (server_id,))
                    server = cursor.fetchone()
                    if server:
                        server_dict = dict(server)
                        server_dict['panel_url'] = self._decrypt(server_dict['panel_url'])
                        server_dict['username'] = self._decrypt(server_dict['username'])
                        server_dict['password'] = self._decrypt(server_dict['password'])
                        server_dict['subscription_base_url'] = self._decrypt(server_dict['subscription_base_url'])
                        server_dict['subscription_path_prefix'] = self._decrypt(server_dict['subscription_path_prefix'])
                        return server_dict
                    return None
        except psycopg2.Error as e:
            logger.error(f"Error getting server by ID {server_id}: {e}")
            return None

    def delete_server(self, server_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM servers WHERE id = %s", (server_id,))
                    conn.commit()
                    logger.info(f"Server with ID {server_id} has been deleted.")
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting server with ID {server_id}: {e}")
            return False

    def update_server_status(self, server_id, is_online, last_checked):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE servers SET is_online = %s, last_checked = %s WHERE id = %s
                    """, (is_online, last_checked, server_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating server status for ID {server_id}: {e}")
            return False

    # --- توابع Inboundهای سرور ---
    def get_server_inbounds(self, server_id, only_active=True):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = "SELECT * FROM server_inbounds WHERE server_id = %s"
                    params = [server_id]
                    if only_active:
                        query += " AND is_active = TRUE"
                    cursor.execute(query, params)
                    return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting inbounds for server {server_id}: {e}")
            return []

    def update_server_inbounds(self, server_id, selected_inbounds: list):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM server_inbounds WHERE server_id = %s", (server_id,))
                    if selected_inbounds:
                        inbounds_to_insert = [
                            (server_id, inbound['id'], inbound['remark'], True)
                            for inbound in selected_inbounds
                        ]
                        execute_values(cursor, """
                            INSERT INTO server_inbounds (server_id, inbound_id, remark, is_active)
                            VALUES %s
                        """, inbounds_to_insert)
                    conn.commit()
                    logger.info(f"Updated inbounds for server ID {server_id}.")
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating inbounds for server ID {server_id}: {e}")
            return False

    # --- توابع پلن‌ها ---
    def add_plan(self, name, plan_type, volume_gb, duration_days, price, per_gb_price):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO plans (name, plan_type, volume_gb, duration_days, price, per_gb_price, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                        RETURNING id;
                    """, (name, plan_type, volume_gb, duration_days, price, per_gb_price))
                    plan_id = cursor.fetchone()[0]
                    conn.commit()
                    return plan_id
        except psycopg2.IntegrityError:
            logger.warning(f"Plan with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding plan '{name}': {e}")
            return None

    def get_all_plans(self, only_active=False):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = "SELECT * FROM plans"
                    if only_active:
                        query += " WHERE is_active = TRUE"
                    query += " ORDER BY price"
                    cursor.execute(query)
                    return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting plans: {e}")
            return []
            
    def get_plan_by_id(self, plan_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM plans WHERE id = %s", (plan_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting plan by ID {plan_id}: {e}")
            return None
            
    def update_plan_status(self, plan_id, is_active):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE plans SET is_active = %s WHERE id = %s", (is_active, plan_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating plan status for ID {plan_id}: {e}")
            return False
            
    # --- توابع درگاه پرداخت ---
    def add_payment_gateway(self, name: str, gateway_type: str, card_number: str = None, card_holder_name: str = None, merchant_id: str = None, description: str = None, priority: int = 0):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    encrypted_card_number = self._encrypt(card_number) if card_number else None
                    encrypted_card_holder_name = self._encrypt(card_holder_name) if card_holder_name else None
                    encrypted_merchant_id = self._encrypt(merchant_id) if merchant_id else None
                    cursor.execute("""
                        INSERT INTO payment_gateways (name, type, card_number, card_holder_name, merchant_id, description, is_active, priority)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
                        RETURNING id;
                    """, (name, gateway_type, encrypted_card_number, encrypted_card_holder_name, encrypted_merchant_id, description, priority))
                    gateway_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Payment Gateway '{name}' ({gateway_type}) added successfully.")
                    return gateway_id
        except psycopg2.IntegrityError:
            logger.warning(f"Payment Gateway with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding payment gateway '{name}': {e}")
            return None

    def get_all_payment_gateways(self, only_active=False):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = "SELECT * FROM payment_gateways"
                    if only_active:
                        query += " WHERE is_active = TRUE"
                    query += " ORDER BY priority DESC, id"
                    cursor.execute(query)
                    gateways = cursor.fetchall()
                    decrypted_gateways = []
                    for gateway in gateways:
                        gateway_dict = dict(gateway)
                        if gateway_dict.get('card_number'):
                            gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                        if gateway_dict.get('card_holder_name'):
                            gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                        if gateway_dict.get('merchant_id'):
                            gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                        decrypted_gateways.append(gateway_dict)
                    return decrypted_gateways
        except Exception as e:
            logger.error(f"Error getting payment gateways: {e}")
            return []

    def get_payment_gateway_by_id(self, gateway_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payment_gateways WHERE id = %s", (gateway_id,))
                    gateway = cursor.fetchone()
                    if gateway:
                        gateway_dict = dict(gateway)
                        if gateway_dict.get('card_number'):
                            gateway_dict['card_number'] = self._decrypt(gateway_dict['card_number'])
                        if gateway_dict.get('card_holder_name'):
                            gateway_dict['card_holder_name'] = self._decrypt(gateway_dict['card_holder_name'])
                        if gateway_dict.get('merchant_id'):
                            gateway_dict['merchant_id'] = self._decrypt(gateway_dict['merchant_id'])
                        return gateway_dict
                    return None
        except Exception as e:
            logger.error(f"Error getting payment gateway {gateway_id}: {e}")
            return None

    def update_payment_gateway_status(self, gateway_id, is_active):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payment_gateways SET is_active = %s WHERE id = %s", (is_active, gateway_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating gateway status for ID {gateway_id}: {e}")
            return False

    # --- توابع پرداخت‌ها (Payments) ---
    def add_payment(self, user_id, amount, receipt_message_id, order_details_json):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO payments (user_id, amount, receipt_message_id, order_details_json, is_confirmed)
                        VALUES (%s, %s, %s, %s, FALSE)
                        RETURNING id;
                    """, (user_id, amount, receipt_message_id, order_details_json))
                    payment_id = cursor.fetchone()[0]
                    conn.commit()
                    return payment_id
        except psycopg2.Error as e:
            logger.error(f"Error adding payment request for user {user_id}: {e}")
            return None

    def get_payment_by_id(self, payment_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting payment {payment_id}: {e}")
            return None

    def update_payment_status(self, payment_id, is_confirmed, admin_id=None):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE payments 
                        SET is_confirmed = %s, admin_confirmed_by = %s, confirmation_date = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (is_confirmed, admin_id, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating payment status for ID {payment_id}: {e}")
            return False
            
    def update_payment_admin_notification_id(self, payment_id, message_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payments SET admin_notification_message_id = %s WHERE id = %s", (message_id, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating admin notification message ID for payment {payment_id}: {e}")
            return False

    # --- توابع خریدها (Purchases) ---
    def add_purchase(self, user_id: int, purchase_type: str, server_id: int, profile_id: int, plan_id: int, 
                    expire_date: str, initial_volume_gb: float, subscription_id: str, full_configs_json: str,
                    xui_client_uuid: str, xui_client_email: str, single_configs_json: str):
        """یک رکورد خرید جدید را با تمام اطلاعات لازم در دیتابیس ثبت می‌کند."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO purchases (user_id, purchase_type, server_id, profile_id, plan_id, expire_date, 
                                            initial_volume_gb, subscription_id, full_configs_json, 
                                            xui_client_uuid, xui_client_email, single_configs_json, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                        RETURNING id;
                    """, (user_id, purchase_type, server_id, profile_id, plan_id, expire_date, 
                        initial_volume_gb, subscription_id, full_configs_json,
                        xui_client_uuid, xui_client_email, single_configs_json))
                    purchase_id = cursor.fetchone()[0]
                    conn.commit()
                    return purchase_id
        except psycopg2.Error as e:
            logger.error(f"Error adding purchase for user {user_id}: {e}")
            return None

    def get_user_purchases(self, user_db_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("""
                        SELECT p.id, p.purchase_date, p.expire_date, p.initial_volume_gb, p.is_active, s.name as server_name, pr.name as profile_name
                        FROM purchases p
                        LEFT JOIN servers s ON p.server_id = s.id
                        LEFT JOIN profiles pr ON p.profile_id = pr.id
                        WHERE p.user_id = %s
                        ORDER BY p.id DESC
                    """, (user_db_id,))
                    return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting purchases for user DB ID {user_db_id}: {e}")
            return []
            
    def get_purchase_by_id(self, purchase_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM purchases WHERE id = %s", (purchase_id,))
                    purchase = cursor.fetchone()
                    if purchase:
                        # full_configs_json is already a string, no need to load it here
                        # if it needs to be processed as JSON, do it in the business logic layer
                        return purchase
                    return None
        except psycopg2.Error as e:
            logger.error(f"Error getting purchase by ID {purchase_id}: {e}")
            return None
            
    def check_free_test_usage(self, user_db_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM free_test_usage WHERE user_id = %s", (user_db_id,))
                    return cursor.fetchone() is not None
        except psycopg2.Error as e:
            logger.error(f"Error checking free test usage for user {user_db_id}: {e}")
            return True

    def record_free_test_usage(self, user_db_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO free_test_usage (user_id) VALUES (%s)", (user_db_id,))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error recording free test usage for user {user_db_id}: {e}")
            return False

    def reset_free_test_usage(self, user_db_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM free_test_usage WHERE user_id = %s", (user_db_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error resetting free test usage for user {user_db_id}: {e}")
            return False
        
    def get_payment_by_authority(self, authority: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM payments WHERE authority = %s", (authority,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting payment by authority {authority}: {e}")
            return None

    def confirm_online_payment(self, payment_id: int, ref_id: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE payments 
                        SET is_confirmed = TRUE, ref_id = %s, confirmation_date = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (ref_id, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error confirming online payment for ID {payment_id}: {e}")
            return False

    def add_profile(self, name, description=""):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO profiles (name, description) VALUES (%s, %s)
                        RETURNING id;
                    """, (name, description))
                    profile_id = cursor.fetchone()[0]
                    conn.commit()
                    logger.info(f"Profile '{name}' added successfully.")
                    return profile_id
        except psycopg2.IntegrityError:
            logger.warning(f"Profile with name '{name}' already exists.")
            return None
        except psycopg2.Error as e:
            logger.error(f"Error adding profile '{name}': {e}")
            return None

    def set_payment_authority(self, payment_id: int, authority: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE payments SET authority = %s WHERE id = %s", (authority, payment_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error setting authority for payment ID {payment_id}: {e}")
            return False
            
    def get_all_profiles(self, only_active=True):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = "SELECT * FROM profiles"
                    if only_active:
                        query += " WHERE is_active = TRUE"
                    cursor.execute(query)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting all profiles: {e}")
            return []
                
    def get_profile_by_id(self, profile_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting profile by ID {profile_id}: {e}")
            return None

    def delete_profile(self, profile_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))
                    conn.commit()
                    logger.info(f"Profile with ID {profile_id} has been deleted.")
                    return cursor.rowcount > 0
        except psycopg2.Error as e:
            logger.error(f"Error deleting profile with ID {profile_id}: {e}")
            return False

    def update_profile_status(self, profile_id, is_active):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE profiles SET is_active = %s WHERE id = %s", (is_active, profile_id))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating profile status for ID {profile_id}: {e}")
            return False
                
    def get_profile_inbounds(self, profile_id):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT server_inbound_id FROM profile_inbounds WHERE profile_id = %s", (profile_id,))
                    return [row['server_inbound_id'] for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Error getting inbounds for profile {profile_id}: {e}")
            return []

    def update_profile_inbounds(self, profile_id, server_inbound_ids: list):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM profile_inbounds WHERE profile_id = %s", (profile_id,))
                    if server_inbound_ids:
                        data_to_insert = [(profile_id, inbound_id) for inbound_id in server_inbound_ids]
                        execute_values(cursor, "INSERT INTO profile_inbounds (profile_id, server_inbound_id) VALUES %s", data_to_insert)
                    conn.commit()
                    logger.info(f"Updated inbounds for profile ID {profile_id}.")
                    return True
        except psycopg2.Error as e:
            logger.error(f"Error updating inbounds for profile ID {profile_id}: {e}")
            return False
                
    def get_server_inbounds_map(self, server_id):
        inbounds = self.get_server_inbounds(server_id, only_active=False)
        return {inbound['inbound_id']: inbound['id'] for inbound in inbounds}
    
    def get_purchase_by_subscription_id(self, subscription_id: str):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("SELECT * FROM purchases WHERE subscription_id = %s", (subscription_id,))
                    return cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error getting purchase by subscription ID {subscription_id}: {e}")
            return None
                
    def get_inbounds_for_profile(self, profile_id: int):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("""
                        SELECT si.*, s.name as server_name 
                        FROM profile_inbounds pi
                        JOIN server_inbounds si ON pi.server_inbound_id = si.id
                        JOIN servers s ON si.server_id = s.id
                        WHERE pi.profile_id = %s AND si.is_active = TRUE AND s.is_active = TRUE AND s.is_online = TRUE
                    """, (profile_id,))
                    return cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error getting inbounds for profile {profile_id}: {e}")
            return []