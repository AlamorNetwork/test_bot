# migrate_db.py

import sqlite3
import psycopg2
import logging
import json
import os
from cryptography.fernet import Fernet

# تنظیمات اولیه برای اجرای مستقل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# این اسکریپت باید بتواند ماژول‌های دیگر را پیدا کند
try:
    from config import (ENCRYPTION_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
except ImportError:
    print("خطا: لطفاً ابتدا فایل .env را با اطلاعات دیتابیس PostgreSQL بسازید.")
    exit(1)

# مسیر دیتابیس قدیمی SQLite
OLD_SQLITE_DB_PATH = 'database/alamor_vpn.db'

def migrate_data():
    """اطلاعات را از دیتابیس SQLite به PostgreSQL منتقل می‌کند."""
    
    # --- مرحله ۱: بررسی وجود دیتابیس قدیمی ---
    if not os.path.exists(OLD_SQLITE_DB_PATH):
        logger.error(f"فایل دیتابیس SQLite در مسیر '{OLD_SQLITE_DB_PATH}' یافت نشد. مهاجرت لغو شد.")
        return

    logger.info("شروع فرآیند مهاجرت از SQLite به PostgreSQL...")

    try:
        # --- مرحله ۲: اتصال به هر دو دیتابیس ---
        sqlite_conn = sqlite3.connect(OLD_SQLITE_DB_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        logger.info("✅ با موفقیت به دیتابیس SQLite متصل شد.")

        pg_conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            host=DB_HOST, port=DB_PORT
        )
        pg_cursor = pg_conn.cursor()
        logger.info("✅ با موفقیت به دیتابیس PostgreSQL متصل شد.")

        # --- مرحله ۳: انتقال داده‌ها جدول به جدول ---
        
        # دیکشنری برای نگاشت نام جداول و ستون‌ها
        table_map = {
            'users': ['id', 'telegram_id', 'first_name', 'last_name', 'username', 'is_admin', 'join_date', 'last_activity'],
            'servers': ['id', 'name', 'panel_url', 'username', 'password', 'subscription_base_url', 'subscription_path_prefix', 'is_active', 'last_checked', 'is_online'],
            'plans': ['id', 'name', 'plan_type', 'volume_gb', 'duration_days', 'price', 'per_gb_price', 'is_active'],
            'server_inbounds': ['id', 'server_id', 'inbound_id', 'remark', 'is_active'],
            'profiles': ['id', 'name', 'description', 'is_active'],
            'profile_inbounds': ['profile_id', 'server_inbound_id'],
            'purchases': ['id', 'user_id', 'purchase_type', 'server_id', 'profile_id', 'plan_id', 'purchase_date', 'expire_date', 'initial_volume_gb', 'subscription_id', 'full_configs_json', 'is_active'],
            'payments': ['id', 'user_id', 'amount', 'payment_date', 'receipt_message_id', 'is_confirmed', 'admin_confirmed_by', 'confirmation_date', 'order_details_json', 'admin_notification_message_id', 'authority', 'ref_id'],
            'payment_gateways': ['id', 'name', 'type', 'card_number', 'card_holder_name', 'merchant_id', 'description', 'is_active', 'priority'],
            'free_test_usage': ['user_id', 'usage_timestamp']
        }

        for table_name, columns in table_map.items():
            logger.info(f"در حال انتقال اطلاعات جدول: {table_name}...")
            
            # خواندن تمام اطلاعات از جدول SQLite
            sqlite_cursor.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
            rows = sqlite_cursor.fetchall()

            if not rows:
                logger.info(f"جدول {table_name} خالی است. عبور می‌کنیم.")
                continue

            # آماده‌سازی دستور INSERT برای PostgreSQL
            placeholders = ', '.join(['%s'] * len(columns))
            insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
            
            # تبدیل ردیف‌ها به لیست تا بتوانیم آن‌ها را به PostgreSQL بفرستیم
            data_to_insert = [tuple(row) for row in rows]
            
            # وارد کردن تمام اطلاعات به جدول PostgreSQL
            pg_cursor.executemany(insert_query, data_to_insert)
            logger.info(f"✅ {len(data_to_insert)} رکورد با موفقیت به جدول {table_name} در PostgreSQL منتقل شد.")

        # --- مرحله ۴: نهایی‌سازی و بستن اتصالات ---
        pg_conn.commit()
        logger.info("تمام تغییرات در دیتابیس PostgreSQL ذخیره شد.")

    except sqlite3.Error as e:
        logger.error(f"خطا در دیتابیس SQLite: {e}")
    except psycopg2.Error as e:
        logger.error(f"خطا در دیتابیس PostgreSQL: {e}")
        if 'pg_conn' in locals():
            pg_conn.rollback()
    except Exception as e:
        logger.error(f"یک خطای پیش‌بینی نشده رخ داد: {e}")
    finally:
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        if 'pg_conn' in locals():
            pg_conn.close()
        logger.info("اتصالات دیتابیس بسته شد.")

if __name__ == '__main__':
    print("این اسکریپت اطلاعات را از دیتابیس SQLite به PostgreSQL منتقل می‌کند.")
    user_confirm = input("آیا از انجام این کار مطمئن هستید؟ (این عمل غیرقابل بازگشت است) (yes/no): ")
    if user_confirm.lower() == 'yes':
        migrate_data()
        print("مهاجرت اطلاعات به پایان رسید.")
    else:
        print("عملیات لغو شد.")