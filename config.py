# config.py

import os
import re
from pathlib import Path
from dotenv import load_dotenv

# --- Load .env file ---
env_path = Path(__file__).parent.resolve() / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# --- Bot Settings ---
BOT_TOKEN = os.getenv("BOT_TOKEN_ALAMOR")
ADMIN_IDS = [int(s) for s in re.findall(r'\d+', os.getenv("ADMIN_IDS_ALAMOR", ""))]
BOT_USERNAME_ALAMOR = os.getenv("BOT_USERNAME_ALAMOR")

# --- PostgreSQL Database Settings ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Other Critical Settings ---
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY_ALAMOR")
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")

# --- Optional Settings ---
SUPPORT_CHANNEL_LINK = os.getenv("SUPPORT_CHANNEL_LINK_ALAMOR")
REQUIRED_CHANNEL_ID_STR = os.getenv("REQUIRED_CHANNEL_ID_ALAMOR")
REQUIRED_CHANNEL_ID = int(REQUIRED_CHANNEL_ID_STR) if REQUIRED_CHANNEL_ID_STR and REQUIRED_CHANNEL_ID_STR.lstrip('-').isdigit() else None
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK_ALAMOR")


def get_bool_env(var_name, default=False):
    """یک مقدار بولی را از متغیرهای محیطی می‌خواند."""
    value = os.getenv(var_name, str(default))
    return value.lower() in ('true', '1', 't', 'y', 'yes')

# --- Feature Flags (برای فعال/غیرفعال کردن قابلیت‌ها) ---
ENABLE_SERVER_PURCHASE = get_bool_env("ENABLE_SERVER_PURCHASE", True)
ENABLE_PROFILE_PURCHASE = get_bool_env("ENABLE_PROFILE_PURCHASE", True)
ENABLE_FIXED_PLANS = get_bool_env("ENABLE_FIXED_PLANS", True)
ENABLE_GIGABYTE_PLANS = get_bool_env("ENABLE_GIGABYTE_PLANS", True)

# --- Zarinpal Settings (تنظیمات درگاه زرین‌پال) ---
ZARINPAL_SANDBOX = get_bool_env("ZARINPAL_SANDBOX", True) # برای تست روی True و برای استفاده واقعی روی False تنظیم شود
ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID")

MAX_API_RETRIES = 3