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