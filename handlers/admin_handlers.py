# handlers/admin_handlers.py (نسخه نهایی، کامل و حرفه‌ای)

import telebot
from telebot import types
import logging
import datetime
import json
import os
import zipfile
from config import ADMIN_IDS, SUPPORT_CHANNEL_LINK , WEBHOOK_DOMAIN
from database.db_manager import DatabaseManager
from api_client.xui_api_client import XuiAPIClient
from utils import messages, helpers
from keyboards import inline_keyboards
from utils.config_generator import ConfigGenerator
from utils.bot_helpers import send_subscription_info # این ایمپورت جدید است
logger = logging.getLogger(__name__)

# ماژول‌های سراسری
_bot: telebot.TeleBot = None
_db_manager: DatabaseManager = None
_xui_api: XuiAPIClient = None
_config_generator: ConfigGenerator = None
_admin_states = {}

def register_admin_handlers(bot_instance, db_manager_instance, xui_api_instance):
    global _bot, _db_manager, _xui_api, _config_generator
    _bot = bot_instance
    _db_manager = db_manager_instance
    _xui_api = xui_api_instance
    _config_generator = ConfigGenerator(xui_api_instance, db_manager_instance)

    # =============================================================================
    # SECTION: Helper and Menu Functions
    # =============================================================================

    def _clear_admin_state(admin_id):
        """وضعیت ادمین را فقط از دیکشنری پاک می‌کند."""
        if admin_id in _admin_states:
            del _admin_states[admin_id]

    def _show_menu(user_id, text, markup, message=None):
        try:
            if message:
                return _bot.edit_message_text(text, user_id, message.message_id, reply_markup=markup, parse_mode='Markdown')
            else:
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if 'message to edit not found' in e.description:
                return _bot.send_message(user_id, text, reply_markup=markup, parse_mode='Markdown')
            elif 'message is not modified' not in e.description:
                logger.warning(f"Error handling menu for {user_id}: {e}")
        return message

    def _show_admin_main_menu(admin_id, message=None): _show_menu(admin_id, messages.ADMIN_WELCOME, inline_keyboards.get_admin_main_inline_menu(), message)
    def _show_server_management_menu(admin_id, message=None): _show_menu(admin_id, messages.SERVER_MGMT_MENU_TEXT, inline_keyboards.get_server_management_inline_menu(), message)
    def _show_plan_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PLAN_MGMT_MENU_TEXT, inline_keyboards.get_plan_management_inline_menu(), message)
    def _show_payment_gateway_management_menu(admin_id, message=None): _show_menu(admin_id, messages.PAYMENT_GATEWAY_MGMT_MENU_TEXT, inline_keyboards.get_payment_gateway_management_inline_menu(), message)
    def _show_user_management_menu(admin_id, message=None): _show_menu(admin_id, messages.USER_MGMT_MENU_TEXT, inline_keyboards.get_user_management_inline_menu(), message)
    def _show_profile_management_menu(admin_id, message=None):
        _show_menu(admin_id, "🧬 **مدیریت پروفایل‌ها**\n\nاز این بخش می‌توانید پروفایل‌های ترکیبی را تعریف و مدیریت کنید.", inline_keyboards.get_profile_management_menu(), message)

    # =============================================================================
    # SECTION: Single-Action Functions (Listing, Testing)
    # =============================================================================

    def list_all_servers(admin_id, message):
        _bot.edit_message_text(_generate_server_list_text(), admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_server_management"))

    # در فایل handlers/admin_handlers.py

    def list_all_plans(admin_id, message, return_text=False):
        plans = _db_manager.get_all_plans()
        if not plans: 
            text = messages.NO_PLANS_FOUND
        else:
            text = messages.LIST_PLANS_HEADER
            for p in plans:
                status = "✅ فعال" if p['is_active'] else "❌ غیرفعال"
                if p['plan_type'] == 'fixed_monthly':
                    details = f"حجم: {p['volume_gb']}GB | مدت: {p['duration_days']} روز | قیمت: {p['price']:,.0f} تومان"
                else:
                    # --- بخش اصلاح شده ---
                    duration_days = p.get('duration_days') # مقدار ممکن است None باشد
                    if duration_days and duration_days > 0:
                        duration_text = f"{duration_days} روز"
                    else:
                        duration_text = "نامحدود"
                    # --- پایان بخش اصلاح شده ---
                    details = f"قیمت هر گیگ: {p['per_gb_price']:,.0f} تومان | مدت: {duration_text}"
                text += f"**ID: `{p['id']}`** - {helpers.escape_markdown_v1(p['name'])}\n_({details})_ - {status}\n---\n"
        
        if return_text:
            return text
        _bot.edit_message_text(text, admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_plan_management"))
    def list_all_gateways(admin_id, message, return_text=False):
        gateways = _db_manager.get_all_payment_gateways()
        if not gateways:
            text = messages.NO_GATEWAYS_FOUND
        else:
            text = messages.LIST_GATEWAYS_HEADER
            for g in gateways:
                status = "✅ فعال" if g['is_active'] else "❌ غیرفعال"
                text += f"**ID: `{g['id']}`** - {helpers.escape_markdown_v1(g['name'])}\n`{g.get('card_number', 'N/A')}` - {status}\n---\n"
        
        if return_text:
            return text
        _bot.edit_message_text(text, admin_id, message.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_payment_management"))


    def list_all_users(admin_id, message):
        users = _db_manager.get_all_users()
        if not users:
            text = messages.NO_USERS_FOUND
        else:
            text = messages.LIST_USERS_HEADER
            for user in users:
                # --- بخش اصلاح شده ---
                # نام کاربری نیز escape می‌شود تا از خطا جلوگیری شود
                username = helpers.escape_markdown_v1(user.get('username', 'N/A'))
                first_name = helpers.escape_markdown_v1(user.get('first_name', ''))
                text += f"👤 `ID: {user['id']}` - **{first_name}** (@{username})\n"
                # --- پایان بخش اصلاح شده ---
        
        _show_menu(admin_id, text, inline_keyboards.get_back_button("admin_user_management"), message)

    def test_all_servers(admin_id, message):
        _bot.edit_message_text(messages.TESTING_ALL_SERVERS, admin_id, message.message_id, reply_markup=None)
        servers = _db_manager.get_all_servers()
        if not servers:
            _bot.send_message(admin_id, messages.NO_SERVERS_FOUND); _show_server_management_menu(admin_id); return
        results = []
        for s in servers:
            temp_xui_client = _xui_api(panel_url=s['panel_url'], username=s['username'], password=s['password'])
            is_online = temp_xui_client.login()
            _db_manager.update_server_status(s['id'], is_online, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            results.append(f"{'✅' if is_online else '❌'} {helpers.escape_markdown_v1(s['name'])}")
        _bot.send_message(admin_id, messages.TEST_RESULTS_HEADER + "\n".join(results), parse_mode='Markdown')
        _show_server_management_menu(admin_id)

    # =============================================================================
    # SECTION: Stateful Process Handlers
    # =============================================================================

    def _handle_stateful_message(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        state = state_info.get("state")
        prompt_id = state_info.get("prompt_message_id")
        data = state_info.get("data", {})
        text = message.text
        

        # --- Server Flows ---
        if state == 'waiting_for_server_name':
            data['name'] = text; state_info['state'] = 'waiting_for_server_url'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_URL, admin_id, prompt_id)
        elif state == 'waiting_for_server_url':
            data['url'] = text; state_info['state'] = 'waiting_for_server_username'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_USERNAME, admin_id, prompt_id)
        elif state == 'waiting_for_server_username':
            data['username'] = text; state_info['state'] = 'waiting_for_server_password'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_PASSWORD, admin_id, prompt_id)
        elif state == 'waiting_for_server_password':
            data['password'] = text; state_info['state'] = 'waiting_for_sub_base_url'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_BASE_URL, admin_id, prompt_id)
        elif state == 'waiting_for_sub_base_url':
            data['sub_base_url'] = text; state_info['state'] = 'waiting_for_sub_path_prefix'
            _bot.edit_message_text(messages.ADD_SERVER_PROMPT_SUB_PATH_PREFIX, admin_id, prompt_id)
        elif state == 'waiting_for_sub_path_prefix':
            data['sub_path_prefix'] = text; execute_add_server(admin_id, data)
        elif state == 'waiting_for_server_id_to_delete':
            if not text.isdigit() or not (server := _db_manager.get_server_by_id(int(text))):
                _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.DELETE_SERVER_PROMPT}", admin_id, prompt_id); return
            confirm_text = messages.DELETE_SERVER_CONFIRM.format(server_name=server['name'], server_id=server['id'])
            markup = inline_keyboards.get_confirmation_menu(f"confirm_delete_server_{server['id']}", "admin_server_management")
            _bot.edit_message_text(confirm_text, admin_id, prompt_id, reply_markup=markup)

        # --- Plan Flows ---
        elif state == 'waiting_for_plan_name':
            data['name'] = text; state_info['state'] = 'waiting_for_plan_type'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_plan_type_selection_menu_admin())
        elif state == 'waiting_for_plan_volume':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_VOLUME}", admin_id, prompt_id); return
            data['volume_gb'] = float(text); state_info['state'] = 'waiting_for_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION, admin_id, prompt_id)
        elif state == 'waiting_for_plan_duration':
            if not text.isdigit(): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION}", admin_id, prompt_id); return
            data['duration_days'] = int(text); state_info['state'] = 'waiting_for_plan_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PRICE, admin_id, prompt_id)
        elif state == 'waiting_for_plan_price':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PRICE}", admin_id, prompt_id); return
            data['price'] = float(text); execute_add_plan(admin_id, data)
        elif state == 'waiting_for_per_gb_price':
            if not helpers.is_float_or_int(text): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_PER_GB_PRICE}", admin_id, prompt_id); return
            data['per_gb_price'] = float(text); state_info['state'] = 'waiting_for_gb_plan_duration'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_DURATION_GB, admin_id, prompt_id)
        elif state == 'waiting_for_gb_plan_duration':
            if not text.isdigit(): _bot.edit_message_text(f"{messages.INVALID_NUMBER_INPUT}\n\n{messages.ADD_PLAN_PROMPT_DURATION_GB}", admin_id, prompt_id); return
            data['duration_days'] = int(text); execute_add_plan(admin_id, data)
        elif state == 'waiting_for_plan_id_to_toggle':
            execute_toggle_plan_status(admin_id, text)

        # --- Gateway Flows ---
        if state == 'waiting_for_gateway_name':
            data['name'] = text
            state_info['state'] = 'waiting_for_gateway_type'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_TYPE, admin_id, prompt_id, reply_markup=inline_keyboards.get_gateway_type_selection_menu())
        elif state == 'waiting_for_merchant_id':
            data['merchant_id'] = text
            state_info['state'] = 'waiting_for_gateway_description'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_DESCRIPTION, admin_id, prompt_id)

        elif state == 'waiting_for_card_number':
            if not text.isdigit() or len(text) not in [16]:
                _bot.edit_message_text(f"شماره کارت نامعتبر است.\n\n{messages.ADD_GATEWAY_PROMPT_CARD_NUMBER}", admin_id, prompt_id)
                return
            data['card_number'] = text
            state_info['state'] = 'waiting_for_card_holder_name'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_CARD_HOLDER_NAME, admin_id, prompt_id)
        elif state == 'waiting_for_card_holder_name':
            data['card_holder_name'] = text
            state_info['state'] = 'waiting_for_gateway_description'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_DESCRIPTION, admin_id, prompt_id)

        elif state == 'waiting_for_gateway_description':
            data['description'] = None if text.lower() == 'skip' else text
            execute_add_gateway(admin_id, data)
        elif state == 'waiting_for_gateway_id_to_toggle':
            execute_toggle_gateway_status(admin_id, text)
            
        elif state == 'waiting_for_gateway_id_to_toggle':
            execute_toggle_gateway_status(admin_id, text)
            
        # --- شرط جدید ---
        elif state == 'waiting_for_profile_name':
            profile_name = text.strip()
            profile_id = _db_manager.add_profile(profile_name)
            if profile_id:
                _bot.edit_message_text(f"✅ پروفایل **{profile_name}** با موفقیت ایجاد شد.", admin_id, prompt_id, parse_mode='Markdown')
                _clear_admin_state(admin_id)
                _show_profile_management_menu(admin_id)
            else:
                _bot.edit_message_text(f"⚠️ خطایی رخ داد! پروفایلی با نام **{profile_name}** از قبل وجود دارد. لطفاً نام دیگری انتخاب کنید.", admin_id, prompt_id, parse_mode='Markdown')
        # ------------------
            
        # --- Inbound Flow ---
        elif state == 'waiting_for_server_id_for_inbounds':
            process_manage_inbounds_flow(admin_id, message)

        
    # =============================================================================
    # SECTION: Process Starters and Callback Handlers
    # =============================================================================
    def start_add_server_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_server_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_SERVER_PROMPT_NAME, admin_id, message.message_id)

    def start_delete_server_flow(admin_id, message):
        _clear_admin_state(admin_id)
        list_text = _generate_server_list_text()
        if list_text == messages.NO_SERVERS_FOUND:
            _bot.edit_message_text(list_text, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management")); return
        _admin_states[admin_id] = {'state': 'waiting_for_server_id_to_delete', 'prompt_message_id': message.message_id}
        prompt_text = f"{list_text}\n\n{messages.DELETE_SERVER_PROMPT}"
        _bot.edit_message_text(prompt_text, admin_id, message.message_id, parse_mode='Markdown')

    def start_add_plan_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_plan_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_PLAN_PROMPT_NAME, admin_id, message.message_id)
        
    def start_toggle_plan_status_flow(admin_id, message):
        _clear_admin_state(admin_id)
        # --- بخش اصلاح شده ---
        # اکنون پارامترهای لازم به تابع پاس داده می‌شوند
        plans_text = list_all_plans(admin_id, message, return_text=True)
        _bot.edit_message_text(f"{plans_text}\n\n{messages.TOGGLE_PLAN_STATUS_PROMPT}", admin_id, message.message_id, parse_mode='Markdown')
        _admin_states[admin_id] = {'state': 'waiting_for_plan_id_to_toggle', 'prompt_message_id': message.message_id}
        
    def start_add_gateway_flow(admin_id, message):
        _clear_admin_state(admin_id)
        _admin_states[admin_id] = {'state': 'waiting_for_gateway_name', 'data': {}, 'prompt_message_id': message.message_id}
        _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_NAME, admin_id, message.message_id)
        
    def start_toggle_gateway_status_flow(admin_id, message):
        _clear_admin_state(admin_id)
        # --- بخش اصلاح شده ---
        # اکنون پارامترهای لازم به تابع پاس داده می‌شوند
        gateways_text = list_all_gateways(admin_id, message, return_text=True)
        _bot.edit_message_text(f"{gateways_text}\n\n{messages.TOGGLE_GATEWAY_STATUS_PROMPT}", admin_id, message.message_id, parse_mode='Markdown')
        _admin_states[admin_id] = {'state': 'waiting_for_gateway_id_to_toggle', 'prompt_message_id': message.message_id}

    def get_plan_details_from_callback(admin_id, message, plan_type):
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_plan_type': return
        state_info['data']['plan_type'] = plan_type
        if plan_type == 'fixed_monthly':
            state_info['state'] = 'waiting_for_plan_volume'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_VOLUME, admin_id, message.message_id)
        elif plan_type == 'gigabyte_based':
            state_info['state'] = 'waiting_for_per_gb_price'
            _bot.edit_message_text(messages.ADD_PLAN_PROMPT_PER_GB_PRICE, admin_id, message.message_id)
        state_info['prompt_message_id'] = message.message_id

    # ... other functions remain the same ...

    # =============================================================================
    # SECTION: Main Bot Handlers
    # =============================================================================

    @_bot.message_handler(commands=['admin'])
    def handle_admin_command(message):
        if not helpers.is_admin(message.from_user.id):
            _bot.reply_to(message, messages.NOT_ADMIN_ACCESS); return
        try: _bot.delete_message(message.chat.id, message.message_id)
        except Exception: pass
        _clear_admin_state(message.from_user.id)
        _show_admin_main_menu(message.from_user.id)

    @_bot.callback_query_handler(func=lambda call: helpers.is_admin(call.from_user.id))
    def handle_admin_callbacks(call):
        """این هندلر تمام کلیک‌های ادمین را به صورت یکپارچه مدیریت می‌کند."""
        _bot.answer_callback_query(call.id)
        admin_id, message, data = call.from_user.id, call.message, call.data

        # --- بخش اصلاح شده ---
        # تعریف توابع داخلی برای خوانایی بهتر
        def list_plans_action(a_id, msg):
            # پاس دادن صحیح پارامترها به تابع اصلی
            text = list_all_plans(a_id, msg, return_text=True)
            _bot.edit_message_text(text, a_id, msg.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_plan_management"))

        def list_gateways_action(a_id, msg):
            # پاس دادن صحیح پارامترها به تابع اصلی
            text = list_all_gateways(a_id, msg, return_text=True)
            _bot.edit_message_text(text, a_id, msg.message_id, parse_mode='Markdown', reply_markup=inline_keyboards.get_back_button("admin_payment_management"))
        # --- پایان بخش اصلاح شده ---

        actions = {
            "admin_main_menu": _show_admin_main_menu,
            "admin_server_management": _show_server_management_menu,
            "admin_plan_management": _show_plan_management_menu,
            "admin_payment_management": _show_payment_gateway_management_menu,
            "admin_user_management": _show_user_management_menu,
            "admin_profile_management": _show_profile_management_menu, # <-- اضافه شده
            "admin_add_server": start_add_server_flow,
            "admin_delete_server": start_delete_server_flow,
            "admin_add_plan": start_add_plan_flow,
            "admin_toggle_plan_status": start_toggle_plan_status_flow,
            "admin_add_gateway": start_add_gateway_flow,
            "admin_toggle_gateway_status": start_toggle_gateway_status_flow,
            "admin_list_servers": list_all_servers,
            "admin_test_all_servers": test_all_servers,
            "admin_list_plans": list_plans_action,
            "admin_list_gateways": list_gateways_action,
            "admin_list_users": list_all_users,
            "admin_manage_inbounds": start_manage_inbounds_flow,
            "admin_create_backup": create_backup,
            "admin_add_profile": start_add_profile_flow, # <-- اضافه شده
            "admin_list_profiles": list_profiles_for_management, # <-- اضافه شده
        }
        
        if data in actions:
            actions[data](admin_id, message); return


        # --- هندل کردن موارد پیچیده‌تر ---
        if data.startswith("plan_type_"): get_plan_details_from_callback(admin_id, message, data.replace('plan_type_', ''))
        elif data.startswith("gateway_type_"): handle_gateway_type_selection(admin_id, message, data.replace('gateway_type_', ''))
        elif data.startswith("confirm_delete_server_"): execute_delete_server(admin_id, message, int(data.split('_')[-1]))
        elif data.startswith("inbound_"): handle_inbound_selection(admin_id, call)
        elif data.startswith("admin_approve_payment_"): process_payment_approval(admin_id, int(data.split('_')[-1]), message)
        elif data.startswith("admin_reject_payment_"): process_payment_rejection(admin_id, int(data.split('_')[-1]), message)
        # --- هندلرهای جدید برای پروفایل ---
        elif data.startswith("admin_view_profile_"): view_single_profile_menu(admin_id, message, int(data.split('_')[-1]))
        elif data.startswith("admin_delete_profile_"): confirm_delete_profile(call, int(data.split('_')[-1]))
        elif data.startswith("admin_toggle_profile_status_"): toggle_profile_status(call, int(data.split('_')[-1]))
        elif data.startswith("admin_manage_profile_inbounds_"): start_manage_profile_inbounds_flow(call, int(data.split('_')[-1]))
        elif data.startswith("admin_profile_inbounds_select_server_"):
            parts = data.split('_'); profile_id, server_id = int(parts[-2]), int(parts[-1])
            show_profile_inbounds_for_server(call, profile_id, server_id)
        elif data.startswith("admin_profile_toggle_inbound_"):
            parts = data.split('_'); profile_id, db_inbound_id = int(parts[-2]), int(parts[-1])
            handle_toggle_profile_inbound(call, profile_id, db_inbound_id)
        elif data.startswith("admin_profile_save_inbounds_"): save_profile_inbounds(call, int(data.split('_')[-1]))
        else: _bot.edit_message_text(messages.UNDER_CONSTRUCTION, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_main_menu"))
    @_bot.message_handler(func=lambda msg: helpers.is_admin(msg.from_user.id) and _admin_states.get(msg.from_user.id))
    def handle_admin_stateful_messages(message):
        _handle_stateful_message(message.from_user.id, message)
        
        


    # =============================================================================
# SECTION: Final Execution Functions
# =============================================================================

    def execute_add_server(admin_id, data):
        _clear_admin_state(admin_id)
        msg = _bot.send_message(admin_id, messages.ADD_SERVER_TESTING)
        temp_xui_client = _xui_api(panel_url=data['url'], username=data['username'], password=data['password'])
        if temp_xui_client.login():
            server_id = _db_manager.add_server(data['name'], data['url'], data['username'], data['password'], data['sub_base_url'], data['sub_path_prefix'])
            if server_id:
                _db_manager.update_server_status(server_id, True, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                _bot.edit_message_text(messages.ADD_SERVER_SUCCESS.format(server_name=data['name']), admin_id, msg.message_id)
            else:
                _bot.edit_message_text(messages.ADD_SERVER_DB_ERROR.format(server_name=data['name']), admin_id, msg.message_id)
        else:
            _bot.edit_message_text(messages.ADD_SERVER_LOGIN_FAILED.format(server_name=data['name']), admin_id, msg.message_id)
        _show_server_management_menu(admin_id)

    def execute_delete_server(admin_id, message, server_id):
        # پاک کردن وضعیت در ابتدای اجرای عملیات نهایی
        _clear_admin_state(admin_id)
        
        server = _db_manager.get_server_by_id(server_id)
        if server and _db_manager.delete_server(server_id):
            _bot.edit_message_text(messages.SERVER_DELETED_SUCCESS.format(server_name=server['name']), admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
        else:
            _bot.edit_message_text(messages.SERVER_DELETED_ERROR, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))

    def execute_add_plan(admin_id, data):
        _clear_admin_state(admin_id)
        plan_id = _db_manager.add_plan(
            name=data.get('name'), plan_type=data.get('plan_type'),
            volume_gb=data.get('volume_gb'), duration_days=data.get('duration_days'),
            price=data.get('price'), per_gb_price=data.get('per_gb_price')
        )
        msg_to_send = messages.ADD_PLAN_SUCCESS if plan_id else messages.ADD_PLAN_DB_ERROR
        _bot.send_message(admin_id, msg_to_send.format(plan_name=data['name']))
        _show_plan_management_menu(admin_id)
        
    def execute_add_gateway(admin_id, data):
        _clear_admin_state(admin_id)
        gateway_id = _db_manager.add_payment_gateway(
            name=data.get('name'),
            gateway_type=data.get('gateway_type'),  # <-- اصلاح شد
            card_number=data.get('card_number'),
            card_holder_name=data.get('card_holder_name'),
            merchant_id=data.get('merchant_id'),    # <-- اضافه شد
            description=data.get('description'),
            priority=0
        )
        
        msg_to_send = messages.ADD_GATEWAY_SUCCESS if gateway_id else messages.ADD_GATEWAY_DB_ERROR
        _bot.send_message(admin_id, msg_to_send.format(gateway_name=data['name']))
        _show_payment_gateway_management_menu(admin_id)

    def execute_toggle_plan_status(admin_id, plan_id_str: str): # ورودی به text تغییر کرد
        _clear_admin_state(admin_id)
        if not plan_id_str.isdigit() or not (plan := _db_manager.get_plan_by_id(int(plan_id_str))):
            _bot.send_message(admin_id, messages.PLAN_NOT_FOUND)
            _show_plan_management_menu(admin_id)
            return
        new_status = not plan['is_active']
        if _db_manager.update_plan_status(plan['id'], new_status):
            _bot.send_message(admin_id, messages.PLAN_STATUS_TOGGLED_SUCCESS.format(plan_name=plan['name'], new_status="فعال" if new_status else "غیرفعال"))
        else:
            _bot.send_message(admin_id, messages.PLAN_STATUS_TOGGLED_ERROR.format(plan_name=plan['name']))
        _show_plan_management_menu(admin_id)
        
    def execute_toggle_gateway_status(admin_id, gateway_id_str: str): # ورودی به text تغییر کرد
        _clear_admin_state(admin_id)
        if not gateway_id_str.isdigit() or not (gateway := _db_manager.get_payment_gateway_by_id(int(gateway_id_str))):
            _bot.send_message(admin_id, messages.GATEWAY_NOT_FOUND)
            _show_payment_gateway_management_menu(admin_id)
            return
        new_status = not gateway['is_active']
        if _db_manager.update_payment_gateway_status(gateway['id'], new_status):
            _bot.send_message(admin_id, messages.GATEWAY_STATUS_TOGGLED_SUCCESS.format(gateway_name=gateway['name'], new_status="فعال" if new_status else "غیرفعال"))
        else:
            _bot.send_message(admin_id, messages.GATEWAY_STATUS_TOGGLED_ERROR.format(gateway_name=gateway['name']))
        _show_payment_gateway_management_menu(admin_id)
        # =============================================================================
    # SECTION: Process-Specific Helper Functions
    # =============================================================================

    def _generate_server_list_text():
        servers = _db_manager.get_all_servers()
        if not servers: return messages.NO_SERVERS_FOUND
        response_text = messages.LIST_SERVERS_HEADER
        for s in servers:
            status = "✅ آنلاین" if s['is_online'] else "❌ آفلاین"
            is_active_emoji = "✅" if s['is_active'] else "❌"
            sub_link = f"{s['subscription_base_url'].rstrip('/')}/{s['subscription_path_prefix'].strip('/')}/<SUB_ID>"
            response_text += messages.SERVER_DETAIL_TEMPLATE.format(
                name=helpers.escape_markdown_v1(s['name']), id=s['id'], status=status, is_active_emoji=is_active_emoji, sub_link=helpers.escape_markdown_v1(sub_link)
            )
        return response_text

    def process_manage_inbounds_flow(admin_id, message):
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_server_id_for_inbounds': return
        server_id_str = message.text.strip()
        prompt_id = state_info.get('prompt_message_id')
        try: _bot.delete_message(admin_id, message.message_id)
        except Exception: pass
        if not server_id_str.isdigit() or not (server_data := _db_manager.get_server_by_id(int(server_id_str))):
            _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}", admin_id, prompt_id, parse_mode='Markdown'); return
        server_id = int(server_id_str)
        _bot.edit_message_text(messages.FETCHING_INBOUNDS, admin_id, prompt_id)
        temp_xui_client = _xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
        panel_inbounds = temp_xui_client.list_inbounds()
        if not panel_inbounds:
            _bot.edit_message_text(messages.NO_INBOUNDS_FOUND_ON_PANEL, admin_id, prompt_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            _clear_admin_state(admin_id); return
        active_db_inbound_ids = [i['inbound_id'] for i in _db_manager.get_server_inbounds(server_id, only_active=True)]
        state_info['state'] = f'selecting_inbounds_for_{server_id}'
        state_info['data'] = {'panel_inbounds': panel_inbounds, 'selected_inbound_ids': active_db_inbound_ids}
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, active_db_inbound_ids)
        _bot.edit_message_text(messages.SELECT_INBOUNDS_TO_ACTIVATE.format(server_name=server_data['name']), admin_id, prompt_id, reply_markup=markup, parse_mode='Markdown')

    def handle_inbound_selection(admin_id, call):
        """کلیک روی دکمه‌های کیبورد انتخاب اینباند را به درستی مدیریت می‌کند."""
        data = call.data
        parts = data.split('_')
        action = parts[1]

        state_info = _admin_states.get(admin_id)
        if not state_info: return

        server_id = None
        
        # استخراج server_id بر اساس نوع اکشن
        if action == 'toggle':
            # فرمت: inbound_toggle_{server_id}_{inbound_id}
            if len(parts) == 4:
                server_id = int(parts[2])
        else: # برای select, deselect, save
            # فرمت: inbound_select_all_{server_id}
            server_id = int(parts[-1])

        if server_id is None or state_info.get('state') != f'selecting_inbounds_for_{server_id}':
            return

        # دریافت اطلاعات لازم از state
        selected_ids = state_info['data'].get('selected_inbound_ids', [])
        panel_inbounds = state_info['data'].get('panel_inbounds', [])

        # انجام عملیات بر اساس اکشن
        if action == 'toggle':
            inbound_id_to_toggle = int(parts[3])
            if inbound_id_to_toggle in selected_ids:
                selected_ids.remove(inbound_id_to_toggle)
            else:
                selected_ids.append(inbound_id_to_toggle)
        
        elif action == 'select' and parts[2] == 'all':
            panel_ids = {p['id'] for p in panel_inbounds}
            selected_ids.extend([pid for pid in panel_ids if pid not in selected_ids])
            selected_ids = list(set(selected_ids)) # حذف موارد تکراری
        
        elif action == 'deselect' and parts[2] == 'all':
            selected_ids.clear()
            
        elif action == 'save':
            save_inbound_changes(admin_id, call.message, server_id, selected_ids)
            return
        
        # به‌روزرسانی state و کیبورد
        state_info['data']['selected_inbound_ids'] = selected_ids
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, selected_ids)
        
        try:
            _bot.edit_message_reply_markup(chat_id=admin_id, message_id=call.message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.warning(f"Error updating inbound selection keyboard: {e}")

    def process_payment_approval(admin_id, payment_id, message):
        _bot.edit_message_caption("⏳ در حال ساخت و فعال‌سازی سرویس...", message.chat.id, message.message_id)
        payment = _db_manager.get_payment_by_id(payment_id)
        if not payment or payment['is_confirmed']:
            _bot.answer_callback_query(message.id, "این پرداخت قبلاً پردازش شده است.", show_alert=True)
            return

        order_details = json.loads(payment['order_details_json'])
        user_telegram_id = order_details['user_telegram_id']
        user_db_info = _db_manager.get_user_by_id(payment['user_id'])
        
        purchase_type = order_details.get('purchase_type')
        plan_type = order_details.get('plan_type')

        # Determine plan specs
        if plan_type == 'fixed_monthly':
            plan = order_details.get('plan_details')
            total_gb, duration_days = (plan.get('volume_gb'), plan.get('duration_days')) if plan else (0, 0)
        else: # gigabyte_based
            gb_plan = order_details.get('gb_plan_details')
            total_gb, duration_days = (order_details.get('requested_gb'), gb_plan.get('duration_days', 0)) if gb_plan else (0, 0)
        
        # Get plan_id safely
        plan_id = (order_details.get('plan_details') or {}).get('id') or (order_details.get('gb_plan_details') or {}).get('id')

        # Create configs based on purchase type
        subscription_id, full_configs = None, None
        server_id, profile_id = None, None

        if purchase_type == 'profile':
            profile_id = order_details.get('profile_id')
            if profile_id:
                subscription_id, full_configs = _config_generator.create_subscription_for_profile(user_telegram_id, profile_id, total_gb, duration_days)
        else: # Default to 'server'
            server_id = order_details.get('server_id')
            if server_id:
                subscription_id, full_configs = _config_generator.create_subscription_for_server(user_telegram_id, server_id, total_gb, duration_days)

        if not subscription_id or not full_configs:
            _bot.edit_message_caption("❌ خطا در ساخت کانفیگ‌ها در پنل X-UI.", message.chat.id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_main_menu"))
            return
        
        expire_date = (datetime.datetime.now() + datetime.timedelta(days=duration_days)) if duration_days and duration_days > 0 else None
        
        purchase_id = _db_manager.add_purchase(
            user_id=user_db_info['id'], 
            purchase_type=purchase_type, 
            server_id=server_id,
            profile_id=profile_id, 
            plan_id=plan_id,
            expire_date=expire_date.strftime("%Y-%m-%d %H:%M:%S") if expire_date else None,
            initial_volume_gb=total_gb, 
            subscription_id=subscription_id,
            full_configs_json=json.dumps(full_configs)
        )

        if not purchase_id:
            _bot.edit_message_caption("❌ خطا در ذخیره خرید در دیتابیس.", message.chat.id, message.message_id)
            return
            
        _db_manager.update_payment_status(payment_id, True, admin_id)
        
        final_sub_link = f"https://{WEBHOOK_DOMAIN}/sub/{subscription_id}"
        
        # --- CORRECTED LINE ---
        admin_user = _bot.get_chat_member(admin_id, admin_id).user
        admin_username_display = f"@{admin_user.username}" if admin_user.username else admin_user.first_name
        new_caption = message.caption + "\n\n" + messages.ADMIN_PAYMENT_CONFIRMED_DISPLAY.format(admin_username=admin_username_display)
        # --- END OF CORRECTION ---
        
        _bot.edit_message_caption(new_caption, message.chat.id, message.message_id, parse_mode='Markdown')
        _bot.send_message(user_telegram_id, "✅ پرداخت شما با موفقیت تایید و سرویس شما فعال گردید.")
        send_subscription_info(_bot, user_telegram_id, final_sub_link)

    def process_payment_rejection(admin_id, payment_id, message):
        payment = _db_manager.get_payment_by_id(payment_id)
        if not payment or payment['is_confirmed']:
            _bot.answer_callback_query(message.id, "این پرداخت قبلاً پردازش شده است.", show_alert=True); return
        _db_manager.update_payment_status(payment_id, False, admin_id)
        admin_user = _bot.get_chat_member(admin_id, admin_id).user
        new_caption = message.caption + "\n\n" + messages.ADMIN_PAYMENT_REJECTED_DISPLAY.format(admin_username=f"@{admin_user.username}" if admin_user.username else admin_user.first_name)
        _bot.edit_message_caption(new_caption, message.chat.id, message.message_id, parse_mode='Markdown')
        order_details = json.loads(payment['order_details_json'])
        _bot.send_message(order_details['user_telegram_id'], messages.PAYMENT_REJECTED_USER.format(support_link=SUPPORT_CHANNEL_LINK))
        
        
    def save_inbound_changes(admin_id, message, server_id, selected_ids):
        """تغییرات انتخاب اینباندها را در دیتابیس ذخیره کرده و به کاربر بازخورد می‌دهد."""
        server_data = _db_manager.get_server_by_id(server_id)
        panel_inbounds = _admin_states.get(admin_id, {}).get('data', {}).get('panel_inbounds', [])
        
        inbounds_to_save = [
            {'id': p_in['id'], 'remark': p_in.get('remark', '')}
            for p_in in panel_inbounds if p_in['id'] in selected_ids
        ]
        
        # ابتدا اطلاعات در دیتابیس ذخیره می‌شود
        if _db_manager.update_server_inbounds(server_id, inbounds_to_save):
            msg = messages.INBOUND_CONFIG_SUCCESS
        else:
            msg = messages.INBOUND_CONFIG_FAILED

        # سپس پیام فعلی ویرایش شده و دکمه بازگشت نمایش داده می‌شود
        _bot.edit_message_text(
            msg.format(server_name=server_data['name']),
            admin_id,
            message.message_id,
            reply_markup=inline_keyboards.get_back_button("admin_server_management")
        )
        
        # در نهایت، وضعیت ادمین پاک می‌شود
        _clear_admin_state(admin_id)
    def start_manage_inbounds_flow(admin_id, message):
            """فرآیند مدیریت اینباند را با نمایش لیست سرورها آغاز می‌کند."""
            _clear_admin_state(admin_id)
            list_text = _generate_server_list_text()
            if list_text == messages.NO_SERVERS_FOUND:
                _bot.edit_message_text(list_text, admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
                return
            
            _admin_states[admin_id] = {'state': 'waiting_for_server_id_for_inbounds', 'prompt_message_id': message.message_id}
            prompt_text = f"{list_text}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}"
            _bot.edit_message_text(prompt_text, admin_id, message.message_id, parse_mode='Markdown')


    def process_manage_inbounds_flow(admin_id, message):
        """
        پس از دریافت ID سرور از ادمین، لیست اینباندهای آن را از پنل X-UI گرفته و نمایش می‌دهد.
        """
        state_info = _admin_states.get(admin_id, {})
        if state_info.get('state') != 'waiting_for_server_id_for_inbounds': return

        server_id_str = message.text.strip()
        prompt_id = state_info.get('prompt_message_id')
        try: _bot.delete_message(admin_id, message.message_id)
        except Exception: pass
        
        if not server_id_str.isdigit() or not (server_data := _db_manager.get_server_by_id(int(server_id_str))):
            _bot.edit_message_text(f"{messages.SERVER_NOT_FOUND}\n\n{messages.SELECT_SERVER_FOR_INBOUNDS_PROMPT}", admin_id, prompt_id, parse_mode='Markdown')
            return

        server_id = int(server_id_str)
        _bot.edit_message_text(messages.FETCHING_INBOUNDS, admin_id, prompt_id)
        
        temp_xui_client = _xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
        panel_inbounds = temp_xui_client.list_inbounds()

        if not panel_inbounds:
            _bot.edit_message_text(messages.NO_INBOUNDS_FOUND_ON_PANEL, admin_id, prompt_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            _clear_admin_state(admin_id)
            return

        active_db_inbound_ids = [i['inbound_id'] for i in _db_manager.get_server_inbounds(server_id, only_active=True)]
        
        state_info['state'] = f'selecting_inbounds_for_{server_id}'
        state_info['data'] = {'panel_inbounds': panel_inbounds, 'selected_inbound_ids': active_db_inbound_ids}
        
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, active_db_inbound_ids)
        _bot.edit_message_text(messages.SELECT_INBOUNDS_TO_ACTIVATE.format(server_name=server_data['name']), admin_id, prompt_id, reply_markup=markup, parse_mode='Markdown')


    def save_inbound_changes(admin_id, message, server_id, selected_ids):
        """تغییرات انتخاب اینباندها را در دیتابیس ذخیره می‌کند."""
        server_data = _db_manager.get_server_by_id(server_id)
        panel_inbounds = _admin_states.get(admin_id, {}).get('data', {}).get('panel_inbounds', [])
        inbounds_to_save = [{'id': p_in['id'], 'remark': p_in.get('remark', '')} for p_in in panel_inbounds if p_in['id'] in selected_ids]
        
        msg = messages.INBOUND_CONFIG_SUCCESS if _db_manager.update_server_inbounds(server_id, inbounds_to_save) else messages.INBOUND_CONFIG_FAILED
        _bot.edit_message_text(msg.format(server_name=server_data['name']), admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_server_management"))
            
        _clear_admin_state(admin_id)

    def handle_inbound_selection(admin_id, call):
        """با منطق جدید برای خواندن callback_data اصلاح شده است."""
        data = call.data
        parts = data.split('_')
        action = parts[1]

        state_info = _admin_states.get(admin_id)
        if not state_info: return

        # استخراج server_id با روشی که برای همه اکشن‌ها کار کند
        server_id = int(parts[2]) if action == 'toggle' else int(parts[-1])
            
        if state_info.get('state') != f'selecting_inbounds_for_{server_id}': return

        selected_ids = state_info['data'].get('selected_inbound_ids', [])
        panel_inbounds = state_info['data'].get('panel_inbounds', [])

        if action == 'toggle':
            inbound_id_to_toggle = int(parts[3]) # آیدی اینباند همیشه پارامتر چهارم است
            if inbound_id_to_toggle in selected_ids:
                selected_ids.remove(inbound_id_to_toggle)
            else:
                selected_ids.append(inbound_id_to_toggle)
        
        elif action == 'select' and parts[2] == 'all':
            panel_ids = {p['id'] for p in panel_inbounds}
            selected_ids.extend([pid for pid in panel_ids if pid not in selected_ids])
        
        elif action == 'deselect' and parts[2] == 'all':
            selected_ids.clear()
            
        elif action == 'save':
            save_inbound_changes(admin_id, call.message, server_id, selected_ids)
            return
        
        state_info['data']['selected_inbound_ids'] = list(set(selected_ids))
        markup = inline_keyboards.get_inbound_selection_menu(server_id, panel_inbounds, selected_ids)
        
        try:
            _bot.edit_message_reply_markup(chat_id=admin_id, message_id=call.message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.warning(f"Error updating inbound selection keyboard: {e}")
                
                
    def create_backup(admin_id, message):
        """از فایل‌های حیاتی ربات (دیتابیس و .env) بکاپ گرفته و برای ادمین ارسال می‌کند."""
        _bot.edit_message_text("⏳ در حال ساخت فایل پشتیبان...", admin_id, message.message_id)
        
        backup_filename = f"alamor_backup_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        
        files_to_backup = [
            os.path.join(os.getcwd(), '.env'),
            _db_manager.db_path
        ]
        
        try:
            with zipfile.ZipFile(backup_filename, 'w') as zipf:
                for file_path in files_to_backup:
                    if os.path.exists(file_path):
                        zipf.write(file_path, os.path.basename(file_path))
                    else:
                        logger.warning(f"فایل بکاپ یافت نشد: {file_path}")

            with open(backup_filename, 'rb') as backup_file:
                _bot.send_document(admin_id, backup_file, caption="✅ فایل پشتیبان شما آماده است.")
            
            _bot.delete_message(admin_id, message.message_id)
            _show_admin_main_menu(admin_id)

        except Exception as e:
            logger.error(f"خطا در ساخت بکاپ: {e}")
            _bot.edit_message_text("❌ در ساخت فایل پشتیبان خطایی رخ داد.", admin_id, message.message_id)
        finally:
            # پاک کردن فایل زیپ پس از ارسال
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
                
    def handle_gateway_type_selection(admin_id, message, gateway_type):
        state_info = _admin_states.get(admin_id)
        if not state_info or state_info.get('state') != 'waiting_for_gateway_type': return
        
        state_info['data']['gateway_type'] = gateway_type
        
        if gateway_type == 'zarinpal':
            state_info['state'] = 'waiting_for_merchant_id'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_MERCHANT_ID, admin_id, message.message_id)
        elif gateway_type == 'card_to_card':
            state_info['state'] = 'waiting_for_card_number'
            _bot.edit_message_text(messages.ADD_GATEWAY_PROMPT_CARD_NUMBER, admin_id, message.message_id)
            
            
            
            
            
    def _show_profile_management_menu(admin_id, message=None):
        """منوی اصلی بخش مدیریت پروفایل‌ها را نمایش می‌دهد."""
        _show_menu(admin_id, "🧬 **مدیریت پروفایل‌ها**\n\nاز این بخش می‌توانید پروفایل‌های ترکیبی را تعریف و مدیریت کنید.", inline_keyboards.get_profile_management_menu(), message)

    def start_add_profile_flow(admin_id, message):
        """فرآیند افزودن یک پروفایل جدید را آغاز می‌کند."""
        _clear_admin_state(admin_id)
        prompt = _bot.edit_message_text("لطفاً یک نام برای پروفایل جدید وارد کنید:", admin_id, message.message_id)
        _admin_states[admin_id] = {'state': 'waiting_for_profile_name', 'prompt_message_id': prompt.message_id, 'data': {}}

    def list_profiles_for_management(admin_id, message):
        """Shows a list of profiles for the admin to manage."""
        profiles = _db_manager.get_all_profiles(only_active=False)
        if not profiles:
            _bot.edit_message_text("هیچ پروفایلی یافت نشد. لطفاً ابتدا یک پروفایل بسازید.", admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button("admin_profile_management"))
            return
        
        # FIX: Corrected message.message_id
        _bot.edit_message_text(
            "کدام پروفایل را می‌خواهید مدیریت کنید؟",
            admin_id,
            message.message_id,
            reply_markup=inline_keyboards.get_profiles_list_menu(profiles, "admin_view_profile")
        )
    def view_single_profile_menu(admin_id, message, profile_id):
        """منوی مدیریت برای یک پروفایل خاص را نمایش می‌دهد."""
        profile = _db_manager.get_profile_by_id(profile_id)
        if not profile:
            _bot.answer_callback_query(message.id, "خطا: پروفایل یافت نشد.", show_alert=True)
            list_profiles_for_management(admin_id, message)
            return
        status = "✅ فعال" if profile['is_active'] else "❌ غیرفعال"
        text = f"🧬 **مدیریت پروفایل: {helpers.escape_markdown_v1(profile['name'])}**\n\n**وضعیت:** {status}"
        _show_menu(admin_id, text, inline_keyboards.get_single_profile_management_menu(profile_id, profile['is_active']), message)

    def confirm_delete_profile(call, profile_id):
        """حذف یک پروفایل را مدیریت می‌کند."""
        if _db_manager.delete_profile(profile_id):
            _bot.answer_callback_query(call.id, "پروفایل با موفقیت حذف شد.")
            list_profiles_for_management(call.from_user.id, call.message)
        else:
            _bot.answer_callback_query(call.id, "خطا در حذف پروفایل!", show_alert=True)

    def toggle_profile_status(call, profile_id):
        """وضعیت فعال/غیرفعال بودن پروفایل را تغییر می‌دهد."""
        profile = _db_manager.get_profile_by_id(profile_id)
        if not profile: return
        new_status = not profile['is_active']
        if _db_manager.update_profile_status(profile_id, new_status):
            _bot.answer_callback_query(call.id, "وضعیت پروفایل تغییر کرد.")
            view_single_profile_menu(call.from_user.id, call.message, profile_id)
        else:
            _bot.answer_callback_query(call.id, "خطا در تغییر وضعیت!", show_alert=True)

    def start_manage_profile_inbounds_flow(call, profile_id):
        """فرآیند انتخاب سرور برای مدیریت اینباندهای پروفایل را آغاز می‌کند."""
        servers = _db_manager.get_all_servers()
        if not servers:
            _bot.answer_callback_query(call.id, "ابتدا باید حداقل یک سرور اضافه کنید.", show_alert=True)
            return
        text = "لطفاً سروری که می‌خواهید اینباندهای آن را به پروفایل اضافه/حذف کنید، انتخاب نمایید:"
        keyboard = inline_keyboards.get_server_selection_for_profile_menu(profile_id, servers)
        _show_menu(call.from_user.id, text, keyboard, call.message)

    def show_profile_inbounds_for_server(call, profile_id, server_id):
        """منوی چندانتخابی اینباندها را برای یک پروفایل و سرور خاص نمایش می‌دهد."""
        admin_id, message = call.from_user.id, call.message
        server_data = _db_manager.get_server_by_id(server_id)
        if not server_data:
            _bot.answer_callback_query(call.id, "خطا: سرور یافت نشد.", show_alert=True)
            return

        _bot.edit_message_text("⏳ در حال دریافت لیست اینباندها از پنل...", admin_id, message.message_id)
        
        api_client = _xui_api(panel_url=server_data['panel_url'], username=server_data['username'], password=server_data['password'])
        if not api_client.login():
            _bot.edit_message_text("❌ اتصال به پنل سرور ناموفق بود.", admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"admin_manage_profile_inbounds_{profile_id}"))
            return
        
        panel_inbounds = api_client.list_inbounds()
        if not panel_inbounds:
            _bot.edit_message_text("هیچ اینباندی در پنل این سرور یافت نشد.", admin_id, message.message_id, reply_markup=inline_keyboards.get_back_button(f"admin_manage_profile_inbounds_{profile_id}"))
            return

        # دریافت اینباندهایی که از قبل برای این پروفایل انتخاب شده‌اند
        selected_db_ids = set(_db_manager.get_profile_inbounds(profile_id))
        
        # ساخت یک نقشه برای تبدیل ID اینباند پنل به ID دیتابیس (server_inbounds)
        inbound_map = _db_manager.get_server_inbounds_map(server_id)
        
        # --- بخش اصلاح شده و حیاتی ---
        # ذخیره تمام اطلاعات لازم در وضعیت (state) برای استفاده در مراحل بعدی
        _admin_states[admin_id] = {
            'state': 'selecting_profile_inbounds',
            'profile_id': profile_id,
            'server_id': server_id,
            'selected_ids': selected_db_ids,
            'inbound_map': inbound_map,
            'panel_inbounds': panel_inbounds  # <-- این خط تضمین می‌کند که لیست کامل ذخیره شود
        }
        # --- پایان بخش اصلاح شده ---
        
        profile = _db_manager.get_profile_by_id(profile_id)
        text = f"🧬 **پروفایل:** {profile['name']}\n**سرور:** {server_data['name']}\n\nلطفاً اینباندهای مورد نظر را انتخاب کنید:"
        
        keyboard = inline_keyboards.get_profile_inbound_selection_menu(profile_id, server_id, panel_inbounds, list(selected_db_ids), inbound_map)
        _bot.edit_message_text(text, admin_id, message.message_id, reply_markup=keyboard, parse_mode='Markdown')

    def handle_toggle_profile_inbound(call, profile_id, db_inbound_id):
        """وضعیت تیک خوردن یک اینباند را در حافظه موقت تغییر داده و فقط کیبورد را به‌روز می‌کند."""
        admin_id = call.from_user.id
        state_data = _admin_states.get(admin_id)

        # بررسی صحت وضعیت فعلی
        if not state_data or state_data.get('state') != 'selecting_profile_inbounds' or state_data.get('profile_id') != profile_id:
            _bot.answer_callback_query(call.id, "خطا: لطفاً فرآیند را مجدداً شروع کنید.", show_alert=True)
            return
            
        selected_ids = state_data['selected_ids']
        
        # تغییر وضعیت تیک در حافظه
        if db_inbound_id in selected_ids:
            selected_ids.remove(db_inbound_id)
        else:
            selected_ids.add(db_inbound_id)
            
        # --- بخش اصلاح شده و حیاتی ---
        # بازخوانی اطلاعات لازم از حافظه موقت (state)
        panel_inbounds = state_data.get('panel_inbounds', [])
        inbound_map = state_data.get('inbound_map', {})
        server_id = state_data.get('server_id')

        # اگر به هر دلیلی لیست اینباندها در حافظه نبود، از ادامه کار جلوگیری کن
        if not panel_inbounds:
            _bot.answer_callback_query(call.id, "خطا در بازخوانی لیست اینباندها.", show_alert=True)
            return

        # ساخت کیبورد جدید با وضعیت به‌روز شده
        new_keyboard = inline_keyboards.get_profile_inbound_selection_menu(
            profile_id,
            server_id,
            panel_inbounds,
            list(selected_ids), # تبدیل set به list برای تابع کیبورد
            inbound_map
        )
        
        # فقط کیبورد پیام را ویرایش می‌کنیم
        try:
            _bot.edit_message_reply_markup(
                chat_id=admin_id,
                message_id=call.message.message_id,
                reply_markup=new_keyboard
            )
            _bot.answer_callback_query(call.id)
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is not modified' not in e.description:
                logger.error(f"Error updating profile inbound keyboard: {e}")
                _bot.answer_callback_query(call.id, "خطا در به‌روزرسانی کیبورد.")
        # --- پایان بخش اصلاح شده ---
    def save_profile_inbounds(call, profile_id):
        admin_id = call.from_user.id
        state_data = _admin_states.get(admin_id)
        if not state_data or state_data.get('state') != 'selecting_profile_inbounds' or state_data.get('profile_id') != profile_id:
            _bot.answer_callback_query(call.id, "خطا: اطلاعاتی برای ذخیره یافت نشد.", show_alert=True); return

        final_selected_ids = list(state_data['selected_ids'])
        if _db_manager.update_profile_inbounds(profile_id, final_selected_ids):
            _bot.answer_callback_query(call.id, "✅ تغییرات با موفقیت ذخیره شد.")
            _clear_admin_state(admin_id)
            view_single_profile_menu(admin_id, call.message, profile_id)
        else:
            _bot.answer_callback_query(call.id, "❌ خطا در ذخیره تغییرات!", show_alert=True)