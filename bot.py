import asyncio
import html
import json
import logging
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, ContentType, ReplyParameters,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")
ADMIN_IDS = [12345678]
DB_PATH = "bot_database.db"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

media_group_cache = {}
media_group_lock = asyncio.Lock()

class xv_fsm(StatesGroup):
    xv_state_search_user = State()
    xv_state_custom_ban_reason = State()
    xv_state_change_text = State()
    xv_state_waiting_broadcast_text = State()
    xv_state_lottery_target = State()
    xv_state_lottery_count = State()
    xv_state_waiting_broadcast_target = State()
    xv_state_waiting_broadcast_mode = State()
    xv_state_admin_reply = State()
    xv_state_add_channel = State()
    xv_state_edit_channel = State()

async def xv_db_exec(sql, params=None, fetch=False, fetchone=False, commit=False, row_factory=False):
    db = await aiosqlite.connect(DB_PATH)
    try:
        if row_factory:
            db.row_factory = aiosqlite.Row
        if params:
            cursor = await db.execute(sql, params)
        else:
            cursor = await db.execute(sql)
        if commit:
            await db.commit()
        if fetchone:
            return await cursor.fetchone()
        if fetch:
            return await cursor.fetchall()
        return cursor.lastrowid if cursor.lastrowid else None
    finally:
        await db.close()

async def xv_db_init():
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xv_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xv_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_msg_id INTEGER,
                admin_msg_id INTEGER,
                admin_chat_id INTEGER,
                reply_msg_id INTEGER,
                status_msg_id INTEGER,
                status TEXT DEFAULT 'sent',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("ALTER TABLE xv_messages ADD COLUMN status_msg_id INTEGER")
        except Exception:
            logger.debug("status_msg_id column already exists")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xv_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        defaults = {
            'maintenance': '0',
            'forced_join': '0',
            'channels': json.dumps([]),
            'start_text': 'به ربات پیام‌رسان خوش آمدید!\nهر پیامی که ارسال کنید مستقیماً به ادمین ارسال می‌شود.',
            'ban_text': 'شما توسط مدیریت مسدود شده‌اید.',
            'welcome_text': 'به ربات خوش آمدید! لطفاً پیام خود را ارسال کنید.',
            'maintenance_text': 'ربات در حال بروزرسانی است. لطفاً بعداً مراجعه کنید.',
            'admin_ids': json.dumps(ADMIN_IDS)
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO xv_settings (key, value) VALUES (?, ?)", (k, v))
        await db.commit()
    finally:
        await db.close()

async def xv_db_get(key):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT value FROM xv_settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row['value'] if row else None
    finally:
        await db.close()

async def xv_db_set(key, value):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("INSERT OR REPLACE INTO xv_settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()
    finally:
        await db.close()

async def xv_db_delete(key):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("DELETE FROM xv_settings WHERE key = ?", (key,))
        await db.commit()
    finally:
        await db.close()

async def xv_db_add_user(user_id, username, first_name):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute(
            "INSERT OR IGNORE INTO xv_users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, username, first_name)
        )
        await db.commit()
    finally:
        await db.close()

async def xv_db_update_user(user_id, username=None, first_name=None):
    db = await aiosqlite.connect(DB_PATH)
    try:
        if username is not None:
            await db.execute("UPDATE xv_users SET username = ? WHERE user_id = ?", (username, user_id))
        if first_name is not None:
            await db.execute("UPDATE xv_users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
        await db.commit()
    finally:
        await db.close()

async def xv_db_get_user(user_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM xv_users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_ban_user(user_id, reason):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("UPDATE xv_users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
        await db.commit()
    finally:
        await db.close()

async def xv_db_unban_user(user_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("UPDATE xv_users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
        await db.commit()
    finally:
        await db.close()

async def xv_db_get_banned_users(offset=0, limit=50):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM xv_users WHERE is_banned = 1 ORDER BY first_name LIMIT ? OFFSET ?", (limit, offset))
        return await cursor.fetchall()
    finally:
        await db.close()

async def xv_db_count_banned_users():
    db = await aiosqlite.connect(DB_PATH)
    try:
        cursor = await db.execute("SELECT COUNT(*) as c FROM xv_users WHERE is_banned = 1")
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()

async def xv_db_count_users(since=None):
    db = await aiosqlite.connect(DB_PATH)
    try:
        if since:
            cursor = await db.execute("SELECT COUNT(*) as c FROM xv_users WHERE joined_at >= ?", (since,))
        else:
            cursor = await db.execute("SELECT COUNT(*) as c FROM xv_users")
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()

async def xv_db_count_messages(since=None, unreplied=False):
    db = await aiosqlite.connect(DB_PATH)
    try:
        if unreplied:
            cursor = await db.execute("SELECT COUNT(*) as c FROM xv_messages WHERE status != 'replied'")
        elif since:
            cursor = await db.execute("SELECT COUNT(*) as c FROM xv_messages WHERE created_at >= ?", (since,))
        else:
            cursor = await db.execute("SELECT COUNT(*) as c FROM xv_messages")
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()

async def xv_db_count_user_messages(user_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        cursor = await db.execute("SELECT COUNT(*) as c FROM xv_messages WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()

async def xv_db_get_active_users():
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT DISTINCT u.* FROM xv_users u INNER JOIN xv_messages m ON u.user_id = m.user_id WHERE u.is_banned = 0"
        )
        return await cursor.fetchall()
    finally:
        await db.close()

async def xv_db_get_all_users(banned_included=False):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        if banned_included:
            cursor = await db.execute("SELECT * FROM xv_users ORDER BY joined_at DESC")
        else:
            cursor = await db.execute("SELECT * FROM xv_users WHERE is_banned = 0 ORDER BY joined_at DESC")
        return await cursor.fetchall()
    finally:
        await db.close()

async def xv_db_save_message(user_id, user_msg_id, admin_msg_id, admin_chat_id, status_msg_id=None):
    db = await aiosqlite.connect(DB_PATH)
    try:
        cursor = await db.execute(
            "INSERT INTO xv_messages (user_id, user_msg_id, admin_msg_id, admin_chat_id, status_msg_id, status) VALUES (?, ?, ?, ?, ?, 'sent')",
            (user_id, user_msg_id, admin_msg_id, admin_chat_id, status_msg_id)
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()

async def xv_db_mark_replied(msg_id, reply_msg_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("UPDATE xv_messages SET status = 'replied', reply_msg_id = ? WHERE id = ?", (reply_msg_id, msg_id))
        await db.commit()
    finally:
        await db.close()

async def xv_db_get_by_admin_msg(admin_msg_id, admin_chat_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM xv_messages WHERE admin_msg_id = ? AND admin_chat_id = ?",
            (admin_msg_id, admin_chat_id)
        )
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_get_by_reply_msg(reply_msg_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM xv_messages WHERE reply_msg_id = ?", (reply_msg_id,))
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_get_by_id(record_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM xv_messages WHERE id = ?", (record_id,))
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_get_last_user_msg(user_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM xv_messages WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_get_by_user_msg(user_msg_id):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM xv_messages WHERE user_msg_id = ? ORDER BY id DESC LIMIT 1", (user_msg_id,))
        return await cursor.fetchone()
    finally:
        await db.close()

async def xv_db_search_user(query):
    db = await aiosqlite.connect(DB_PATH)
    try:
        db.row_factory = aiosqlite.Row
        try:
            uid = int(query)
            cursor = await db.execute("SELECT * FROM xv_users WHERE user_id = ?", (uid,))
        except ValueError:
            q = f"%{query.replace('@', '')}%"
            cursor = await db.execute(
                "SELECT * FROM xv_users WHERE username LIKE ? OR first_name LIKE ? LIMIT 20",
                (q, q)
            )
        rows = await cursor.fetchall()
        return rows if isinstance(rows, list) else [rows] if rows else []
    finally:
        await db.close()

def vx_status_kb(status, user_msg_id):
    status_map = {
        'sent': ('🔴 ارسال شد به ادمین', 'xv_status_sent'),
        'read': ('👀 خوانده شد', 'xv_status_read'),
        'replied': ('💬 پاسخ داده شد', 'xv_status_replied')
    }
    text, cbd = status_map.get(status, status_map['sent'])
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=f"{cbd}:{user_msg_id}")]])

def vx_user_menu_kb(is_admin=False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 پروفایل من", callback_data="xv_profile")]
    ])
    if is_admin:
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔧 پنل مدیریت", callback_data="xv_admin_panel")])
    return kb

def vx_join_channels_kb(channels):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for ch in channels:
        if 'link' in ch and ch['link']:
            kb.inline_keyboard.append([
                InlineKeyboardButton(text=f"🔗 {ch.get('title', 'ورود به کانال')}", url=ch['link'])
            ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="✅ عضو شدم", callback_data="xv_verify_join")
    ])
    return kb

def vx_user_tabs_kb(user_id, active_tab):
    tabs = {
        'info': ('📋', 'اطلاعات'),
        'msgs': ('💬', 'پیام‌ها'),
        'ban': ('🚫', 'مسدودسازی'),
    }
    row = []
    for key, (icon, label) in tabs.items():
        display = f"✅ {label}" if key == active_tab else f"{icon} {label}"
        row.append(InlineKeyboardButton(text=display, callback_data=f"xv_user_tab:{user_id}:{key}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        row,
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_admin_actions_kb(user_id, admin_msg_id=None):
    reply_cb = f"xv_reply:{user_id}" if admin_msg_id is None else f"xv_reply:{user_id}:{admin_msg_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 پاسخ دادن", callback_data=reply_cb),
            InlineKeyboardButton(text="🚫 مسدودسازی", callback_data=f"xv_ban:{user_id}")
        ],
        [
            InlineKeyboardButton(text="📋 پروفایل کاربر", callback_data=f"xv_profile_admin:{user_id}")
        ]
    ])

def vx_ban_reasons_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛑 اسپم", callback_data=f"xv_ban_reason:{user_id}:spam"),
            InlineKeyboardButton(text="🛑 مزاحمت", callback_data=f"xv_ban_reason:{user_id}:harassment")
        ],
        [
            InlineKeyboardButton(text="✍️ علت دلخواه", callback_data=f"xv_ban_reason:{user_id}:custom"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"xv_ban_cancel:{user_id}")
        ]
    ])

def vx_unban_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 آزادسازی", callback_data=f"xv_unban:{user_id}")]
    ])

def vx_admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="xv_admin_users"),
            InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="xv_admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="🎁 قرعه‌کشی", callback_data="xv_admin_lottery"),
            InlineKeyboardButton(text="📊 آمار ربات", callback_data="xv_admin_stats")
        ],
        [
            InlineKeyboardButton(text="⚙️ تنظیمات عمومی", callback_data="xv_admin_settings")
        ]
    ])

def vx_admin_users_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="xv_admin_search_user")],
        [InlineKeyboardButton(text="🚫 لیست مسدودشدگان", callback_data="xv_admin_banned_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_admin_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 جوین اجباری", callback_data="xv_setting_join")],
        [InlineKeyboardButton(text="🔧 حالت تعمیر", callback_data="xv_setting_maintenance")],
        [InlineKeyboardButton(text="📝 متن خوش‌آمدید", callback_data="xv_setting_welcome")],
        [InlineKeyboardButton(text="📝 متن جوین اجباری", callback_data="xv_setting_start")],
        [InlineKeyboardButton(text="🚫 متن بن", callback_data="xv_setting_ban_text")],
        [InlineKeyboardButton(text="📝 متن تعمیر", callback_data="xv_setting_maint_text")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_back_kb(cbd="xv_admin_back"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cbd)]
    ])

def vx_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="xv_cancel_action")]
    ])

def vx_broadcast_mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ ارسال به صورت فوروارد", callback_data="xv_bc_mode:forward")],
        [InlineKeyboardButton(text="🆔 ارسال به صورت کپی", callback_data="xv_bc_mode:copy")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_broadcast_target_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 همه کاربران", callback_data="xv_bc_target:all")],
        [InlineKeyboardButton(text="🟢 فقط کاربران فعال", callback_data="xv_bc_target:active")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_lottery_target_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 کل کاربران", callback_data="xv_lottery_target:all")],
        [InlineKeyboardButton(text="💬 کاربران فعال", callback_data="xv_lottery_target:active")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_lottery_count_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1", callback_data="xv_lottery_count:1")],
        [InlineKeyboardButton(text="3", callback_data="xv_lottery_count:3")],
        [InlineKeyboardButton(text="5", callback_data="xv_lottery_count:5")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_join_settings_kb(is_active=False):
    btn = [InlineKeyboardButton(text="❌ غیرفعال کردن", callback_data="xv_join_off")] if is_active else [InlineKeyboardButton(text="✅ فعال کردن", callback_data="xv_join_on")]
    return InlineKeyboardMarkup(inline_keyboard=[
        btn,
        [InlineKeyboardButton(text="📝 تغییر کانال‌ها", callback_data="xv_join_channels")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_maintenance_kb(is_active=False):
    btn = [InlineKeyboardButton(text="❌ غیرفعال کردن", callback_data="xv_maint_off")] if is_active else [InlineKeyboardButton(text="✅ فعال کردن", callback_data="xv_maint_on")]
    return InlineKeyboardMarkup(inline_keyboard=[
        btn,
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")]
    ])

def vx_channel_mgmt_kb(channels):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, ch in enumerate(channels):
        title = ch.get('title', ch['id'])
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ حذف {title[:20]}", callback_data=f"xv_ch_del:{i}"),
            InlineKeyboardButton(text=f"✏️ ویرایش {title[:15]}", callback_data=f"xv_ch_edit:{i}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ افزودن کانال جدید", callback_data="xv_ch_add")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_setting_join")])
    return kb

_admin_ids_cache = None

async def vx_is_admin(user_id):
    global _admin_ids_cache
    if _admin_ids_cache is None:
        _admin_ids_cache = await vx_get_admins()
    return user_id in _admin_ids_cache

async def vx_get_admins():
    admin_ids_str = await xv_db_get('admin_ids')
    if not admin_ids_str:
        return []
    try:
        return json.loads(admin_ids_str)
    except Exception:
        return []

async def vx_invalidate_admin_cache():
    global _admin_ids_cache
    _admin_ids_cache = None

async def vx_check_forced_join(user_id, bot_instance):
    forced_join = await xv_db_get('forced_join')
    if forced_join != '1':
        return True
    channels_str = await xv_db_get('channels')
    if not channels_str:
        return True
    try:
        channels = json.loads(channels_str)
    except Exception:
        return True
    if not channels:
        return True
    for ch in channels:
        try:
            chat_id = ch.get('id', '')
            if not chat_id:
                continue
            member = await bot_instance.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ('left', 'kicked', 'banned'):
                return False
        except Exception as e:
            logger.warning(f"get_chat_member failed for {ch.get('id', '?')}: {e}")
            continue
    return True

async def vx_forward_to_admin(message, user_id):
    admins = await vx_get_admins()
    if not admins:
        return None, None
    admin_chat_id = admins[0]

    user_info = f"👤 {html.escape(message.from_user.full_name)}"
    if message.from_user.username:
        user_info += f" (@{html.escape(message.from_user.username)})"
    user_info += f"\n🆔 {message.from_user.id}"

    try:
        if message.content_type == ContentType.TEXT:
            sent = await bot.send_message(
                admin_chat_id,
                f"{user_info}\n\n{html.escape(message.text)}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.PHOTO:
            sent = await bot.send_photo(
                admin_chat_id,
                message.photo[-1].file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.VIDEO:
            sent = await bot.send_video(
                admin_chat_id,
                message.video.file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.DOCUMENT:
            sent = await bot.send_document(
                admin_chat_id,
                message.document.file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.STICKER:
            sent = await bot.send_sticker(
                admin_chat_id,
                message.sticker.file_id,
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.VOICE:
            sent = await bot.send_voice(
                admin_chat_id,
                message.voice.file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.VIDEO_NOTE:
            sent = await bot.send_video_note(
                admin_chat_id,
                message.video_note.file_id,
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.ANIMATION:
            sent = await bot.send_animation(
                admin_chat_id,
                message.animation.file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.AUDIO:
            sent = await bot.send_audio(
                admin_chat_id,
                message.audio.file_id,
                caption=f"{user_info}\n\n{html.escape(message.caption or '')}",
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.LOCATION:
            loc = message.location
            sent = await bot.send_location(
                admin_chat_id,
                loc.latitude,
                loc.longitude,
                reply_markup=vx_admin_actions_kb(user_id)
            )
        elif message.content_type == ContentType.CONTACT:
            cnt = message.contact
            sent = await bot.send_contact(
                admin_chat_id,
                cnt.phone_number,
                cnt.first_name,
                last_name=cnt.last_name,
                reply_markup=vx_admin_actions_kb(user_id)
            )
        else:
            sent = await message.forward(admin_chat_id)
            await bot.send_message(
                admin_chat_id,
                user_info,
                reply_markup=vx_admin_actions_kb(user_id)
            )
            sent = None

        if sent:
            for admin_id in admins[1:]:
                try:
                    await bot.copy_message(admin_id, admin_chat_id, sent.message_id)
                except Exception as e:
                    logger.debug(f"copy to secondary admin {admin_id} failed: {e}")
            return sent.message_id, admin_chat_id

        return None, admin_chat_id
    except Exception as e:
        logging.error(f"xv_forward_to_admin error: {e}")
        return None, None

async def vx_process_admin_reply(message):
    if not message.reply_to_message:
        return
    if not await vx_is_admin(message.from_user.id):
        return

    admin_chat_id = message.chat.id
    replied_msg_id = message.reply_to_message.message_id

    msg_record = await xv_db_get_by_admin_msg(replied_msg_id, admin_chat_id)
    if not msg_record:
        msg_record = await xv_db_get_by_reply_msg(replied_msg_id)

    if not msg_record:
        return

    user_id = msg_record['user_id']
    original_user_msg_id = msg_record['user_msg_id']

    try:
        if message.content_type == ContentType.TEXT:
            sent = await bot.send_message(
                user_id,
                message.text,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.PHOTO:
            sent = await bot.send_photo(
                user_id,
                message.photo[-1].file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.VIDEO:
            sent = await bot.send_video(
                user_id,
                message.video.file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.DOCUMENT:
            sent = await bot.send_document(
                user_id,
                message.document.file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.STICKER:
            sent = await bot.send_sticker(
                user_id,
                message.sticker.file_id,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.VOICE:
            sent = await bot.send_voice(
                user_id,
                message.voice.file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.VIDEO_NOTE:
            sent = await bot.send_video_note(
                user_id,
                message.video_note.file_id,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.ANIMATION:
            sent = await bot.send_animation(
                user_id,
                message.animation.file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.AUDIO:
            sent = await bot.send_audio(
                user_id,
                message.audio.file_id,
                caption=message.caption or '',
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.LOCATION:
            loc = message.location
            sent = await bot.send_location(
                user_id,
                loc.latitude,
                loc.longitude,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        elif message.content_type == ContentType.CONTACT:
            cnt = message.contact
            sent = await bot.send_contact(
                user_id,
                cnt.phone_number,
                cnt.first_name,
                last_name=cnt.last_name,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )
        else:
            sent = await bot.copy_message(
                user_id,
                admin_chat_id,
                message.message_id,
                reply_parameters=ReplyParameters(message_id=original_user_msg_id)
            )

        if sent:
            await xv_db_mark_replied(msg_record['id'], sent.message_id)
            status_msg_id = msg_record['status_msg_id']
            if status_msg_id:
                try:
                    kb_replied = vx_status_kb('replied', original_user_msg_id)
                    await bot.edit_message_reply_markup(
                        chat_id=user_id,
                        message_id=status_msg_id,
                        reply_markup=kb_replied
                    )
                except Exception as e:
                    logger.debug(f"status edit failed: {e}")
            else:
                try:
                    kb_replied = vx_status_kb('replied', original_user_msg_id)
                    for mid in [original_user_msg_id + 1, original_user_msg_id]:
                        try:
                            await bot.edit_message_reply_markup(
                                chat_id=user_id,
                                message_id=mid,
                                reply_markup=kb_replied
                            )
                        except Exception as e:
                            logger.debug(f"status fallback edit failed: {e}")
                except Exception as e:
                    logger.debug(f"status fallback outer failed: {e}")
    except Exception as e:
        logging.error(f"xv_process_admin_reply error: {e}")

async def vx_handle_media_group(message):
    if not message.media_group_id:
        return

    async with media_group_lock:
        if message.media_group_id not in media_group_cache:
            media_group_cache[message.media_group_id] = {
                'messages': [],
                'timer': None,
                'user_id': message.from_user.id
            }
        media_group_cache[message.media_group_id]['messages'].append(message)

        async def xv_send_media_group(mgid):
            try:
                await asyncio.sleep(0.5)
                async with media_group_lock:
                    data = media_group_cache.pop(mgid, None)
                if not data:
                    return
                msgs = data['messages']
                uid = data['user_id']
                if not msgs:
                    return
                admins = await vx_get_admins()
                if not admins:
                    return
                admin_chat_id = admins[0]

                media_group = []
                for m in msgs:
                    if m.content_type == ContentType.PHOTO:
                        media_group.append(InputMediaPhoto(
                            media=m.photo[-1].file_id,
                            caption=m.caption or ''
                        ))
                    elif m.content_type == ContentType.VIDEO:
                        media_group.append(InputMediaVideo(
                            media=m.video.file_id,
                            caption=m.caption or ''
                        ))
                    elif m.content_type == ContentType.DOCUMENT:
                        media_group.append(InputMediaDocument(
                            media=m.document.file_id,
                            caption=m.caption or ''
                        ))

                if media_group:
                    try:
                        user_info = f"👤 {html.escape(msgs[0].from_user.full_name)}"
                        if msgs[0].from_user.username:
                            user_info += f" (@{html.escape(msgs[0].from_user.username)})"
                        user_info += f"\n🆔 {msgs[0].from_user.id}"

                        await bot.send_message(admin_chat_id, user_info)
                        sent_msgs = await bot.send_media_group(admin_chat_id, media_group)
                        if sent_msgs:
                            for idx, s in enumerate(sent_msgs):
                                orig_msg = msgs[idx] if idx < len(msgs) else msgs[0]
                                await xv_db_save_message(uid, orig_msg.message_id, s.message_id, admin_chat_id)
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="🚫 مسدودسازی", callback_data=f"xv_ban:{uid}")]
                                ])
                                try:
                                    await bot.edit_message_reply_markup(
                                        chat_id=admin_chat_id,
                                        message_id=s.message_id,
                                        reply_markup=kb
                                    )
                                except Exception:
                                    logger.debug("media_group edit_reply_markup failed")

                            for admin_id in admins[1:]:
                                try:
                                    await bot.send_message(admin_id, user_info)
                                    await bot.send_media_group(admin_id, media_group)
                                except Exception:
                                    logger.debug("media_group forward to secondary admin failed")

                        status_kb = vx_status_kb('read', msgs[0].message_id)
                        await bot.send_message(uid, "پیام شما به ادمین ارسال شد.", reply_markup=status_kb)
                    except Exception as e:
                        logging.error(f"xv_send_media_group error: {e}")
            except Exception as e:
                logging.error(f"xv_send_media_group outer error: {e}")
                async with media_group_lock:
                    media_group_cache.pop(mgid, None)

        if media_group_cache[message.media_group_id]['timer'] is None:
            media_group_cache[message.media_group_id]['timer'] = asyncio.create_task(
                xv_send_media_group(message.media_group_id)
            )

@dp.message(lambda msg: msg.text and msg.text.startswith('/start'))
async def vx_start_handler(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    await xv_db_add_user(user_id, username, first_name)
    await xv_db_update_user(user_id, username, first_name)

    user_data = await xv_db_get_user(user_id)
    if user_data and user_data['is_banned']:
        if await vx_is_admin(user_id):
            await xv_db_unban_user(user_id)
        else:
            ban_text = await xv_db_get('ban_text')
            await message.answer(ban_text or 'شما توسط مدیریت مسدود شده‌اید.')
            return

    maintenance = await xv_db_get('maintenance')
    if maintenance == '1' and not await vx_is_admin(user_id):
        maint_text = await xv_db_get('maintenance_text')
        await message.answer(maint_text or 'ربات در حال بروزرسانی است. لطفاً بعداً مراجعه کنید.')
        return

    forced_join = await xv_db_get('forced_join')
    if forced_join == '1':
        if not await vx_check_forced_join(user_id, bot):
            channels_str = await xv_db_get('channels')
            try:
                channels = json.loads(channels_str) if channels_str else []
            except Exception:
                channels = []
            kb = vx_join_channels_kb(channels)
            start_text = await xv_db_get('start_text')
            await message.answer(
                start_text or 'لطفاً ابتدا در کانال‌های زیر عضو شوید:',
                reply_markup=kb
            )
            return

    welcome_text = await xv_db_get('welcome_text')
    kb = vx_user_menu_kb(await vx_is_admin(user_id))
    await message.answer(welcome_text or 'به ربات خوش آمدید! لطفاً پیام خود را ارسال کنید.', reply_markup=kb)

@dp.callback_query(F.data == "xv_cancel_action")
async def vx_cancel_cb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    orig_msg_id = data.get('xv_orig_msg_id')
    orig_chat_id = data.get('xv_orig_chat_id')
    orig_user_id = data.get('xv_orig_user_id')
    ban_msg_id = data.get('xv_ban_msg_id')
    ban_chat_id = data.get('xv_ban_chat_id')
    ch_msg_id = data.get('xv_ch_msg_id')
    ch_chat_id = data.get('xv_ch_chat_id')
    await state.clear()
    if orig_msg_id and orig_chat_id and orig_user_id:
        if data.get('xv_reply_user_msg_id') is None:
            try:
                pm = await bot.edit_message_text("⏳ در حال بارگذاری...", chat_id=orig_chat_id, message_id=orig_msg_id)
                await vx_show_user_tab(pm, orig_user_id, 'info')
            except:
                pass
        else:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=orig_chat_id,
                    message_id=orig_msg_id,
                    reply_markup=vx_admin_actions_kb(orig_user_id)
                )
            except:
                pass
        await callback.answer("✅ لغو شد.", show_alert=True)
    elif ch_msg_id and ch_chat_id:
        channels_str = await xv_db_get('channels')
        try:
            channels = json.loads(channels_str) if channels_str else []
        except:
            channels = []
        text = "📋 کانال‌های جوین اجباری:\n\n"
        if channels:
            for i, ch in enumerate(channels, 1):
                text += f"{i}. {ch.get('title', ch['id'])}\n   آیدی: {ch['id']}\n"
                if ch.get('link'):
                    text += f"   🔗 {ch['link']}\n"
                text += "\n"
        else:
            text += "هیچ کانالی تنظیم نشده.\n\n"
        text += "با دکمه‌های زیر می‌توانید کانال‌ها را مدیریت کنید:"
        try:
            await bot.edit_message_text(text, chat_id=ch_chat_id, message_id=ch_msg_id, reply_markup=vx_channel_mgmt_kb(channels))
        except:
            pass
        await callback.answer()
    elif ban_msg_id and ban_chat_id:
        try:
            await bot.edit_message_text("✅ عملیات لغو شد.", chat_id=ban_chat_id, message_id=ban_msg_id)
        except:
            await bot.edit_message_caption(caption="✅ عملیات لغو شد.", chat_id=ban_chat_id, message_id=ban_msg_id)
        await callback.answer()
    elif data.get('xv_text_msg_id') and data.get('xv_text_chat_id'):
        try:
            await bot.edit_message_text("🔧 تنظیمات", chat_id=data['xv_text_chat_id'], message_id=data['xv_text_msg_id'], reply_markup=vx_admin_settings_kb())
        except:
            pass
        await callback.answer()
    else:
        await callback.answer("✅ عملیات لغو شد.")
        await callback.message.delete()

@dp.callback_query(F.data == "xv_admin_panel")
async def vx_admin_panel_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    kb = vx_admin_menu_kb()
    try:
        await callback.message.edit_text("🔧 پنل مدیریت", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_verify_join")
async def vx_verify_join_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await vx_check_forced_join(user_id, bot):
        welcome_text = await xv_db_get('welcome_text')
        kb = vx_user_menu_kb(await vx_is_admin(user_id))
        try:
            await callback.message.edit_text(
                welcome_text or 'به ربات خوش آمدید!',
                reply_markup=kb
            )
        except Exception:
            pass
    else:
        await callback.answer("⚠️ شما هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)

@dp.callback_query(F.data == "xv_profile")
async def vx_profile_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = await xv_db_get_user(user_id)
    if not user_data:
        await callback.answer("کاربر یافت نشد.")
        return
    msg_count = await xv_db_count_user_messages(user_id)
    username = user_data['username'] or 'ندارد'
    joined_at = user_data['joined_at'] or 'نامشخص'
    text = (
        f"👤 پروفایل شما\n\n"
        f"🆔 آیدی: {user_id}\n"
        f"👤 نام: {user_data['first_name'] or 'ندارد'}\n"
        f"📌 یوزرنیم: @{username}\n"
        f"📅 تاریخ عضویت: {joined_at}\n"
        f"💬 تعداد پیام‌ها: {msg_count}"
    )
    try:
        await callback.message.edit_text(text, reply_markup=vx_user_menu_kb(await vx_is_admin(user_id)))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_reply:"))
async def vx_reply_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    parts = callback.data.split(":")
    user_id = int(parts[1])
    admin_msg_id = parts[2] if len(parts) > 2 else None

    msg_record = None
    if admin_msg_id:
        msg_record = await xv_db_get_by_admin_msg(int(admin_msg_id), callback.message.chat.id)
    if not msg_record:
        msg_record = await xv_db_get_last_user_msg(user_id)
    if not msg_record:
        await callback.answer("پیامی یافت نشد.", show_alert=True)
        return

    orig_kb = callback.message.reply_markup
    await state.set_state(xv_fsm.xv_state_admin_reply)
    await state.update_data(
        xv_reply_user_id=msg_record['user_id'],
        xv_reply_user_msg_id=msg_record['user_msg_id'],
        xv_reply_msg_id=msg_record['id'],
        xv_reply_chat_id=callback.message.chat.id,
        xv_orig_msg_id=callback.message.message_id,
        xv_orig_chat_id=callback.message.chat.id,
        xv_orig_user_id=msg_record['user_id']
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=vx_cancel_kb())
    except:
        pass
    await callback.answer("💬 پاسخ خود را ارسال کنید.", show_alert=False)

@dp.callback_query(F.data.startswith("xv_send:"))
async def vx_send_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    await state.set_state(xv_fsm.xv_state_admin_reply)
    await state.update_data(
        xv_reply_user_id=user_id,
        xv_reply_user_msg_id=None,
        xv_reply_msg_id=0,
        xv_reply_chat_id=callback.message.chat.id,
        xv_orig_msg_id=callback.message.message_id,
        xv_orig_chat_id=callback.message.chat.id,
        xv_orig_user_id=user_id
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=vx_cancel_kb())
    except:
        pass
    await callback.answer("💬 پیام خود را ارسال کنید.", show_alert=False)

@dp.callback_query(F.data.startswith("xv_status_"))
async def vx_status_cb(callback: CallbackQuery):
    await callback.answer("وضعیت پیام شما", show_alert=False)

@dp.callback_query(F.data.startswith("xv_ban:"))
async def vx_ban_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    if user_id == callback.from_user.id:
        await callback.answer("نمی‌توانید خودتان را مسدود کنید!", show_alert=True)
        return
    user_data = await xv_db_get_user(user_id)
    if user_data and user_data['is_banned']:
        await callback.answer("کاربر قبلاً مسدود شده است.", show_alert=True)
        return
    await vx_show_user_tab(callback.message, user_id, 'ban')
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_ban_reason:"))
async def vx_ban_reason_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    parts = callback.data.split(":")
    user_id = int(parts[1])
    reason = parts[2]

    if user_id == callback.from_user.id:
        await callback.answer("نمی‌توانید خودتان را مسدود کنید!", show_alert=True)
        return

    if reason == 'custom':
        await state.set_state(xv_fsm.xv_state_custom_ban_reason)
        await state.update_data(xv_ban_user_id=user_id, xv_ban_msg_id=callback.message.message_id, xv_ban_chat_id=callback.message.chat.id)
        try:
            await callback.message.edit_text("✍️ لطفاً علت مسدودسازی را ارسال کنید:", reply_markup=vx_cancel_kb())
        except:
            await callback.message.edit_caption(caption="✍️ لطفاً علت مسدودسازی را ارسال کنید:", reply_markup=vx_cancel_kb())
        await callback.answer()
        return

    reason_map = {'spam': 'اسپم', 'harassment': 'مزاحمت'}
    reason_text = reason_map.get(reason, reason)
    await xv_db_ban_user(user_id, reason_text)
    await vx_show_user_tab(callback.message, user_id, 'ban')
    await callback.answer("✅ کاربر مسدود شد.", show_alert=True)

    try:
        ban_text = await xv_db_get('ban_text')
        await bot.send_message(user_id, f"{ban_text}\nعلت: {reason_text}")
    except:
        pass

@dp.message(xv_fsm.xv_state_custom_ban_reason)
async def vx_custom_ban_reason_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('xv_ban_user_id')
    if not user_id:
        await state.clear()
        return
    if user_id == message.from_user.id:
        await state.clear()
        await message.answer("نمی‌توانید خودتان را مسدود کنید!")
        return
    reason = message.text
    await xv_db_ban_user(user_id, reason)
    ban_msg_id = data.get('xv_ban_msg_id')
    ban_chat_id = data.get('xv_ban_chat_id')
    await state.clear()
    if ban_msg_id and ban_chat_id:
        try:
            pm = await bot.edit_message_text("⏳ در حال بارگذاری...", chat_id=ban_chat_id, message_id=ban_msg_id)
            await vx_show_user_tab(pm, user_id, 'ban')
        except:
            try:
                pm = await bot.edit_message_caption(caption="⏳ در حال بارگذاری...", chat_id=ban_chat_id, message_id=ban_msg_id)
                await vx_show_user_tab(pm, user_id, 'ban')
            except:
                pass
    else:
        await message.answer(f"✅ کاربر {user_id} با علت «{reason}» مسدود شد.")

    try:
        ban_text = await xv_db_get('ban_text')
        await bot.send_message(user_id, f"{ban_text}\nعلت: {reason}")
    except:
        pass

    admins = await vx_get_admins()
    if admins:
        admin_chat_id = admins[0]
        try:
            await bot.send_message(admin_chat_id, f"✅ کاربر {user_id} مسدود شد.\nعلت: {reason}")
        except:
            pass

@dp.callback_query(F.data.startswith("xv_ban_cancel:"))
async def vx_ban_cancel_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    await vx_show_user_tab(callback.message, user_id, 'info')
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_unban:"))
async def vx_unban_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    await xv_db_unban_user(user_id)
    await vx_show_user_tab(callback.message, user_id, 'info')
    await callback.answer("✅ کاربر آزاد شد.", show_alert=True)

    try:
        await bot.send_message(user_id, "✅ حساب شما توسط مدیریت آزاد شد.")
    except:
        pass

@dp.callback_query(F.data.startswith("xv_profile_admin:"))
async def vx_profile_admin_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    user_id = int(callback.data.split(":")[1])
    await vx_show_user_tab(callback.message, user_id, 'info')
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_user_tab:"))
async def vx_user_tab_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    parts = callback.data.split(":")
    user_id = int(parts[1])
    tab = parts[2]
    await vx_show_user_tab(callback.message, user_id, tab)
    await callback.answer()

async def vx_show_user_tab(msg, user_id, active_tab):
    user_data = await xv_db_get_user(user_id)
    if not user_data:
        try:
            await msg.edit_text("❌ کاربر یافت نشد.")
        except:
            pass
        return
    msg_count = await xv_db_count_user_messages(user_id)
    username = user_data['username'] or 'ندارد'
    joined_at = user_data['joined_at'] or 'نامشخص'
    first_name = user_data['first_name'] or 'ندارد'
    ban_status = "🚫 مسدود" if user_data['is_banned'] else "✅ فعال"

    if active_tab == 'info':
        ban_reason = f"\nعلت بن: {user_data['ban_reason']}" if user_data['is_banned'] and user_data['ban_reason'] else ""
        body = (
            f"🆔 آیدی: {user_id}\n"
            f"👤 نام: {first_name}\n"
            f"📌 یوزرنیم: @{username}\n"
            f"📅 عضویت: {joined_at}\n"
            f"💬 پیام‌ها: {msg_count}\n"
            f"وضعیت: {ban_status}{ban_reason}"
        )
        extra = [[InlineKeyboardButton(text="💬 ارسال پیام", callback_data=f"xv_send:{user_id}")]]
        tab_kb = vx_user_tabs_kb(user_id, 'info')
        tab_kb.inline_keyboard = tab_kb.inline_keyboard[:-1] + extra + [tab_kb.inline_keyboard[-1]]
        text = f"📋 اطلاعات کاربر @{username}\n━━━━━━━━━━━━━━━━━━━\n\n{body}"

    elif active_tab == 'msgs':
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at, status FROM xv_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        rows = await cursor.fetchall()
        await db.close()
        body = ""
        if rows:
            status_map = {'sent': '🔴', 'read': '👀', 'replied': '💬'}
            for i, row in enumerate(rows, 1):
                st = status_map.get(row['status'], '❓')
                body += f"{i}. {st} {row['created_at'] or 'نامشخص'}\n"
        else:
            body = "هیچ پیامی یافت نشد."
        tab_kb = vx_user_tabs_kb(user_id, 'msgs')
        text = f"💬 پیام‌های @{username}\n━━━━━━━━━━━━━━━━━━━\n\n{body}"

    elif active_tab == 'ban':
        if user_data['is_banned']:
            reason = user_data['ban_reason'] or 'نامشخص'
            body = f"🚫 این کاربر مسدود شده است.\nعلت: {reason}"
            extra = [[InlineKeyboardButton(text="🟢 آزادسازی", callback_data=f"xv_unban:{user_id}")]]
        else:
            body = "🚫 مسدودسازی کاربر:\n\nعلت را انتخاب کنید:"
            extra = [
                [InlineKeyboardButton(text="🛑 اسپم", callback_data=f"xv_ban_reason:{user_id}:spam"),
                 InlineKeyboardButton(text="🛑 مزاحمت", callback_data=f"xv_ban_reason:{user_id}:harassment")],
                [InlineKeyboardButton(text="✍️ علت دلخواه", callback_data=f"xv_ban_reason:{user_id}:custom")]
            ]
        tab_kb = vx_user_tabs_kb(user_id, 'ban')
        tab_kb.inline_keyboard = tab_kb.inline_keyboard[:-1] + extra + [tab_kb.inline_keyboard[-1]]
        text = f"🚫 مدیریت مسدودسازی @{username}\n━━━━━━━━━━━━━━━━━━━\n\n{body}"

    try:
        await msg.edit_text(text, reply_markup=tab_kb)
    except:
        try:
            await msg.edit_caption(caption=text, reply_markup=tab_kb)
        except:
            await msg.answer(text, reply_markup=tab_kb)

@dp.callback_query(F.data == "xv_admin_back")
async def vx_admin_back_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await vx_is_admin(callback.from_user.id):
        kb = vx_admin_menu_kb()
        try:
            await callback.message.edit_text("🔧 پنل مدیریت", reply_markup=kb)
        except Exception:
            pass
    await callback.answer()

@dp.callback_query(F.data == "xv_admin_users")
async def vx_admin_users_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    kb = vx_admin_users_kb()
    try:
        await callback.message.edit_text("👥 مدیریت کاربران", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_admin_search_user")
async def vx_admin_search_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    await state.set_state(xv_fsm.xv_state_search_user)
    await state.update_data(xv_text_msg_id=callback.message.message_id, xv_text_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            "🔍 جستجوی کاربر\n\n"
            "می‌توانید با یکی از روش‌های زیر جستجو کنید:\n\n"
            "• آیدی عددی (مثال: 123456789)\n"
            "• یوزرنیم (مثال: @username)\n"
            "• نام یا قسمتی از نام\n\n"
            "لطفاً عبارت خود را ارسال کنید:",
            reply_markup=vx_back_kb("xv_admin_back")
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(xv_fsm.xv_state_search_user)
async def vx_search_user_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    query = message.text.strip()
    results = await xv_db_search_user(query)
    chat_id = data.get('xv_text_chat_id')
    msg_id = data.get('xv_text_msg_id')
    if not results:
        if chat_id and msg_id:
            try:
                await bot.edit_message_text("❌ کاربری یافت نشد.", chat_id=chat_id, message_id=msg_id, reply_markup=vx_back_kb("xv_admin_back"))
            except:
                pass
        else:
            await message.answer("❌ کاربری یافت نشد.", reply_markup=vx_back_kb("xv_admin_back"))
        await state.clear()
        await message.delete()
        return

    for i, user in enumerate(results):
        if i == 0 and chat_id and msg_id:
            try:
                prompt_msg = await bot.edit_message_text("⏳ در حال بارگذاری...", chat_id=chat_id, message_id=msg_id)
            except:
                prompt_msg = await message.answer("⏳ در حال بارگذاری...")
        else:
            prompt_msg = await message.answer("⏳ در حال بارگذاری...")
        await vx_show_user_tab(prompt_msg, user['user_id'], 'info')

    await state.clear()
    await message.delete()

@dp.callback_query(F.data.startswith("xv_admin_banned_list"))
async def vx_admin_banned_list_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0
    page_size = 15
    banned = await xv_db_get_banned_users(offset=page * page_size, limit=page_size)
    total = await xv_db_count_banned_users()
    if not banned:
        if page == 0:
            try:
                await callback.message.edit_text(
                    "✅ هیچ کاربر مسدودی وجود ندارد.",
                    reply_markup=vx_back_kb("xv_admin_back")
                )
            except Exception:
                pass
        else:
            await callback.answer("صفحه‌ای وجود ندارد.", show_alert=True)
        await callback.answer()
        return

    text = f"🚫 لیست کاربران مسدود شده (صفحه {page + 1}):\n\n"
    kb_buttons = []
    for user in banned:
        display = user['first_name'] or str(user['user_id'])
        text += f"🆔 {user['user_id']} - {display}"
        if user['ban_reason']:
            text += f" ({user['ban_reason']})"
        text += "\n"
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"🆔 {user['user_id']} - {display[:20]}",
                callback_data=f"xv_profile_admin:{user['user_id']}"
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ قبل", callback_data=f"xv_admin_banned_list:{page - 1}"))
    if (page + 1) * page_size < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"xv_admin_banned_list:{page + 1}"))
    if nav_row:
        kb_buttons.append(nav_row)
    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_users")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_admin_stats")
async def vx_admin_stats_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    total_users = await xv_db_count_users()
    today_users = await xv_db_count_users(since=today_start.strftime("%Y-%m-%d %H:%M:%S"))
    week_users = await xv_db_count_users(since=week_start.strftime("%Y-%m-%d %H:%M:%S"))
    month_users = await xv_db_count_users(since=month_start.strftime("%Y-%m-%d %H:%M:%S"))

    today_msgs = await xv_db_count_messages(since=today_start.strftime("%Y-%m-%d %H:%M:%S"))
    week_msgs = await xv_db_count_messages(since=week_start.strftime("%Y-%m-%d %H:%M:%S"))
    month_msgs = await xv_db_count_messages(since=month_start.strftime("%Y-%m-%d %H:%M:%S"))

    unreplied = await xv_db_count_messages(unreplied=True)

    def bar(val, mx):
        if mx == 0:
            return '▱' * 10
        filled = round(val / mx * 10)
        return '▰' * filled + '▱' * (10 - filled)

    max_u = max(total_users, week_users, month_users, today_users, 1)
    max_m = max(today_msgs, week_msgs, month_msgs, unreplied, 1)

    text = (
        f"📊 آمار ربات\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>کاربران</b>\n"
        f"کل　　　 {bar(total_users, max_u)} {total_users}\n"
        f"امروز　　{bar(today_users, max_u)} {today_users}\n"
        f"این هفته {bar(week_users, max_u)} {week_users}\n"
        f"این ماه　{bar(month_users, max_u)} {month_users}\n\n"
        f"💬 <b>پیام‌ها</b>\n"
        f"امروز　　{bar(today_msgs, max_m)} {today_msgs}\n"
        f"این هفته {bar(week_msgs, max_m)} {week_msgs}\n"
        f"این ماه　{bar(month_msgs, max_m)} {month_msgs}\n"
        f"بی‌پاسخ　{bar(unreplied, max_m)} {unreplied}\n\n"
        f"📌 جمع‌آوری شده از {total_users} کاربر"
    )

    try:
        await callback.message.edit_text(text, reply_markup=vx_back_kb("xv_admin_back"))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_admin_broadcast")
async def vx_admin_broadcast_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    await state.set_state(xv_fsm.xv_state_waiting_broadcast_mode)
    try:
        await callback.message.edit_text(
            "📢 ارسال همگانی\nلطفاً نوع ارسال را انتخاب کنید:",
            reply_markup=vx_broadcast_mode_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_bc_mode:"))
async def vx_bc_mode_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    mode = callback.data.split(":")[1]
    await state.update_data(xv_bc_mode=mode)
    await state.set_state(xv_fsm.xv_state_waiting_broadcast_target)
    try:
        await callback.message.edit_text(
            "📢 انتخاب هدف ارسال:",
            reply_markup=vx_broadcast_target_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_bc_target:"))
async def vx_bc_target_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    target = callback.data.split(":")[1]
    await state.update_data(xv_bc_target=target, xv_bc_msg_id=callback.message.message_id, xv_bc_chat_id=callback.message.chat.id)
    await state.set_state(xv_fsm.xv_state_waiting_broadcast_text)
    try:
        await callback.message.edit_text(
            "📢 لطفاً پیام همگانی را ارسال کنید (متن، عکس، ویدئو، فایل و ...):",
            reply_markup=vx_back_kb("xv_admin_back")
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(xv_fsm.xv_state_waiting_broadcast_text)
async def vx_broadcast_text_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get('xv_bc_mode', 'copy')
    target = data.get('xv_bc_target', 'all')
    bc_msg_id = data.get('xv_bc_msg_id')
    bc_chat_id = data.get('xv_bc_chat_id')

    try:
        await bot.edit_message_text("📤 در حال ارسال همگانی...", chat_id=bc_chat_id, message_id=bc_msg_id)
    except:
        status_msg = await message.answer("📤 در حال ارسال همگانی...")

    if target == 'all':
        users = await xv_db_get_all_users()
    else:
        users = await xv_db_get_active_users()

    success = 0
    failed = 0

    for i, user in enumerate(users):
        retries = 3
        while retries > 0:
            try:
                if mode == 'forward':
                    await message.forward(chat_id=user['user_id'])
                else:
                    if message.content_type == ContentType.TEXT:
                        await bot.send_message(user['user_id'], message.text or message.caption or '')
                    elif message.content_type == ContentType.PHOTO:
                        await bot.send_photo(user['user_id'], message.photo[-1].file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.VIDEO:
                        await bot.send_video(user['user_id'], message.video.file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.DOCUMENT:
                        await bot.send_document(user['user_id'], message.document.file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.STICKER:
                        await bot.send_sticker(user['user_id'], message.sticker.file_id)
                    elif message.content_type == ContentType.VOICE:
                        await bot.send_voice(user['user_id'], message.voice.file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.VIDEO_NOTE:
                        await bot.send_video_note(user['user_id'], message.video_note.file_id)
                    elif message.content_type == ContentType.ANIMATION:
                        await bot.send_animation(user['user_id'], message.animation.file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.AUDIO:
                        await bot.send_audio(user['user_id'], message.audio.file_id, caption=message.caption or '')
                    elif message.content_type == ContentType.CONTACT:
                        cnt = message.contact
                        await bot.send_contact(user['user_id'], cnt.phone_number, cnt.first_name, last_name=cnt.last_name)
                    elif message.content_type == ContentType.LOCATION:
                        loc = message.location
                        await bot.send_location(user['user_id'], loc.latitude, loc.longitude)
                    else:
                        await message.forward(chat_id=user['user_id'])
                success += 1
                break
            except TelegramRetryAfter as e:
                retries -= 1
                if retries > 0:
                    await asyncio.sleep(e.retry_after)
                else:
                    failed += 1
                    logging.error(f"xv_broadcast 429 for user {user['user_id']}, exhausted retries")
            except Exception as e:
                failed += 1
                logging.error(f"xv_broadcast error for user {user['user_id']}: {e}")
                break
        if i % 25 == 0:
            await asyncio.sleep(1)

    try:
        await bot.edit_message_text(
            f"📊 گزارش ارسال همگانی\n\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {failed}\n"
            f"📌 مجموع: {success + failed}",
            chat_id=bc_chat_id, message_id=bc_msg_id,
            reply_markup=vx_back_kb("xv_admin_back")
        )
    except:
        await message.answer(
            f"📊 گزارش ارسال همگانی\n\n"
            f"✅ موفق: {success}\n"
            f"❌ ناموفق: {failed}\n"
            f"📌 مجموع: {success + failed}",
            reply_markup=vx_back_kb("xv_admin_back")
        )
    await state.clear()
    await message.delete()

@dp.callback_query(F.data == "xv_admin_lottery")
async def vx_admin_lottery_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    await state.set_state(xv_fsm.xv_state_lottery_target)
    try:
        await callback.message.edit_text(
            "🎁 قرعه‌کشی\nلطفاً هدف قرعه‌کشی را انتخاب کنید:",
            reply_markup=vx_lottery_target_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_lottery_target:"))
async def vx_lottery_target_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    target = callback.data.split(":")[1]
    await state.update_data(xv_lottery_target=target)
    await state.set_state(xv_fsm.xv_state_lottery_count)
    try:
        await callback.message.edit_text(
            "🎁 تعداد برندگان را انتخاب کنید:",
            reply_markup=vx_lottery_count_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_lottery_count:"))
async def vx_lottery_count_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    count = int(callback.data.split(":")[1])
    data = await state.get_data()
    target = data.get('xv_lottery_target', 'all')

    if target == 'all':
        users = await xv_db_get_all_users()
    else:
        users = await xv_db_get_active_users()

    if not users:
        try:
            await callback.message.edit_text(
                "❌ هیچ کاربری یافت نشد!",
                reply_markup=vx_back_kb("xv_admin_back")
            )
        except Exception:
            pass
        await callback.answer()
        await state.clear()
        return

    if len(users) < count:
        count = len(users)

    winners = random.sample(users, count)

    text = "🎁 برندگان قرعه‌کشی:\n\n"
    kb_buttons = []
    for winner in winners:
        display = winner['first_name'] or str(winner['user_id'])
        username = f"@{winner['username']}" if winner['username'] else 'بدون یوزرنیم'
        text += f"🆔 {winner['user_id']} - {display} ({username})\n"
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"✉️ ارسال تبریک به {display[:15]}",
                callback_data=f"xv_congratulate:{winner['user_id']}"
            )
        ])

    kb_buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="xv_admin_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()
    await state.clear()

@dp.callback_query(F.data.startswith("xv_congratulate:"))
async def vx_congratulate_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split(":")[1])
    try:
        await bot.send_message(
            user_id,
            "🎉 تبریک! شما در قرعه‌کشی ربات برنده شده‌اید!\n"
            "برای دریافت جایزه خود با ادمین در ارتباط باشید."
        )
        await callback.answer("✅ پیام تبریک ارسال شد.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال: {e}", show_alert=True)

@dp.callback_query(F.data == "xv_admin_settings")
async def vx_admin_settings_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    await state.clear()
    kb = vx_admin_settings_kb()

    forced_join = await xv_db_get('forced_join')
    maintenance = await xv_db_get('maintenance')

    fjs = "✅ فعال" if forced_join == '1' else "❌ غیرفعال"
    mts = "✅ فعال" if maintenance == '1' else "❌ غیرفعال"

    text = (
        f"⚙️ تنظیمات عمومی\n\n"
        f"🔒 جوین اجباری: {fjs}\n"
        f"🔧 حالت تعمیر: {mts}"
    )

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_setting_join")
async def vx_setting_join_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    forced_join = await xv_db_get('forced_join')
    status = "✅ فعال" if forced_join == '1' else "❌ غیرفعال"

    channels_str = await xv_db_get('channels')
    try:
        channels = json.loads(channels_str) if channels_str else []
    except:
        channels = []

    ch_text = ""
    if channels:
        for i, ch in enumerate(channels, 1):
            ch_text += f"{i}. {ch.get('title', 'بدون نام')} - {ch.get('id', '')}\n"
    else:
        ch_text = "هیچ کانالی تنظیم نشده."

    text = f"🔒 تنظیمات جوین اجباری\nوضعیت: {status}\n\nکانال‌ها:\n{ch_text}"

    try:
        await callback.message.edit_text(text, reply_markup=vx_join_settings_kb(forced_join == '1'))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_join_on")
async def vx_join_on_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    await xv_db_set('forced_join', '1')
    await callback.answer("✅ جوین اجباری فعال شد.", show_alert=True)
    await vx_setting_join_cb(callback)

@dp.callback_query(F.data == "xv_join_off")
async def vx_join_off_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    await xv_db_set('forced_join', '0')
    await callback.answer("❌ جوین اجباری غیرفعال شد.", show_alert=True)
    await vx_setting_join_cb(callback)

@dp.callback_query(F.data == "xv_join_channels")
async def vx_join_channels_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    channels_str = await xv_db_get('channels')
    try:
        channels = json.loads(channels_str) if channels_str else []
    except:
        channels = []
    text = "📋 کانال‌های جوین اجباری:\n\n"
    if channels:
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch.get('title', ch['id'])}\n"
            text += f"   آیدی: {ch['id']}\n"
            if ch.get('link'):
                text += f"   🔗 {ch['link']}\n"
            text += "\n"
    else:
        text += "هیچ کانالی تنظیم نشده.\n\n"
    text += "با دکمه‌های زیر می‌توانید کانال‌ها را مدیریت کنید:"
    kb = vx_channel_mgmt_kb(channels)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_ch_add")
async def vx_ch_add_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    await state.set_state(xv_fsm.xv_state_add_channel)
    await state.update_data(xv_ch_msg_id=callback.message.message_id, xv_ch_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            "➕ لطفاً یوزرنیم کانال را ارسال کنید:\nمثال: @channel_username",
            reply_markup=vx_cancel_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("xv_ch_del:"))
async def vx_ch_del_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    idx = int(callback.data.split(":")[1])
    channels_str = await xv_db_get('channels')
    try:
        channels = json.loads(channels_str) if channels_str else []
    except:
        channels = []
    if 0 <= idx < len(channels):
        removed = channels.pop(idx)
        await xv_db_set('channels', json.dumps(channels, ensure_ascii=False))
    await callback.answer(f"✅ کانال {removed.get('title', removed['id'])} حذف شد.", show_alert=True)
    await vx_join_channels_cb(callback)

@dp.callback_query(F.data.startswith("xv_ch_edit:"))
async def vx_ch_edit_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    idx = int(callback.data.split(":")[1])
    await state.set_state(xv_fsm.xv_state_edit_channel)
    await state.update_data(xv_edit_ch_idx=idx, xv_ch_msg_id=callback.message.message_id, xv_ch_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            "✏️ لطفاً یوزرنیم جدید کانال را ارسال کنید:\nمثال: @new_channel",
            reply_markup=vx_cancel_kb()
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(xv_fsm.xv_state_add_channel)
async def vx_add_channel_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    ch_msg_id = data.get('xv_ch_msg_id')
    ch_chat_id = data.get('xv_ch_chat_id')
    username = message.text.strip().replace('@', '').strip()
    if not username:
        try:
            await bot.edit_message_text("❌ لطفاً یک یوزرنیم معتبر ارسال کنید.", chat_id=ch_chat_id, message_id=ch_msg_id, reply_markup=vx_cancel_kb())
        except:
            await message.answer("❌ لطفاً یک یوزرنیم معتبر ارسال کنید.", reply_markup=vx_cancel_kb())
        return
    try:
        chat = await bot.get_chat(f"@{username}")
        title = chat.title or username
    except:
        title = username
    new_ch = {'id': f"@{username}", 'link': f"https://t.me/{username}", 'title': title}
    channels_str = await xv_db_get('channels')
    try:
        channels = json.loads(channels_str) if channels_str else []
    except:
        channels = []
    channels.append(new_ch)
    await xv_db_set('channels', json.dumps(channels, ensure_ascii=False))
    await state.clear()
    text = "📋 کانال‌های جوین اجباری:\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. {ch.get('title', ch['id'])}\n   آیدی: {ch['id']}\n"
        if ch.get('link'):
            text += f"   🔗 {ch['link']}\n"
        text += "\n"
    text += "با دکمه‌های زیر می‌توانید کانال‌ها را مدیریت کنید:"
    try:
        await bot.edit_message_text(text, chat_id=ch_chat_id, message_id=ch_msg_id, reply_markup=vx_channel_mgmt_kb(channels))
    except:
        pass
    await message.delete()

@dp.message(xv_fsm.xv_state_edit_channel)
async def vx_edit_channel_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get('xv_edit_ch_idx')
    ch_msg_id = data.get('xv_ch_msg_id')
    ch_chat_id = data.get('xv_ch_chat_id')
    if idx is None:
        await state.clear()
        return
    username = message.text.strip().replace('@', '').strip()
    if not username:
        try:
            await bot.edit_message_text("❌ لطفاً یک یوزرنیم معتبر ارسال کنید.", chat_id=ch_chat_id, message_id=ch_msg_id, reply_markup=vx_cancel_kb())
        except:
            await message.answer("❌ لطفاً یک یوزرنیم معتبر ارسال کنید.", reply_markup=vx_cancel_kb())
        return
    channels_str = await xv_db_get('channels')
    try:
        channels = json.loads(channels_str) if channels_str else []
    except:
        channels = []
    if 0 <= idx < len(channels):
        try:
            chat = await bot.get_chat(f"@{username}")
            title = chat.title or username
        except:
            title = username
        channels[idx] = {'id': f"@{username}", 'link': f"https://t.me/{username}", 'title': title}
        await xv_db_set('channels', json.dumps(channels, ensure_ascii=False))
    await state.clear()
    text = "📋 کانال‌های جوین اجباری:\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. {ch.get('title', ch['id'])}\n   آیدی: {ch['id']}\n"
        if ch.get('link'):
            text += f"   🔗 {ch['link']}\n"
        text += "\n"
    text += "با دکمه‌های زیر می‌توانید کانال‌ها را مدیریت کنید:"
    try:
        await bot.edit_message_text(text, chat_id=ch_chat_id, message_id=ch_msg_id, reply_markup=vx_channel_mgmt_kb(channels))
    except:
        pass
    await message.delete()

@dp.callback_query(F.data == "xv_setting_maintenance")
async def vx_setting_maintenance_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    maintenance = await xv_db_get('maintenance')
    maint_text = await xv_db_get('maintenance_text')
    status = "✅ فعال" if maintenance == '1' else "❌ غیرفعال"
    text = f"🔧 حالت تعمیر\nوضعیت فعلی: {status}\n\nمتن فعلی:\n{maint_text}\n\nدر صورت فعال بودن، کاربران فقط متن بالا را دریافت می‌کنند."
    try:
        await callback.message.edit_text(text, reply_markup=vx_maintenance_kb(maintenance == '1'))
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_maint_on")
async def vx_maint_on_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    await xv_db_set('maintenance', '1')
    await callback.answer("✅ حالت تعمیر فعال شد.", show_alert=True)
    await vx_setting_maintenance_cb(callback)

@dp.callback_query(F.data == "xv_maint_off")
async def vx_maint_off_cb(callback: CallbackQuery):
    if not await vx_is_admin(callback.from_user.id):
        return
    await xv_db_set('maintenance', '0')
    await callback.answer("❌ حالت تعمیر غیرفعال شد.", show_alert=True)
    await vx_setting_maintenance_cb(callback)

@dp.callback_query(F.data == "xv_setting_welcome")
async def vx_setting_welcome_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    current = await xv_db_get('welcome_text')
    await state.set_state(xv_fsm.xv_state_change_text)
    await state.update_data(xv_text_key='welcome_text', xv_text_msg_id=callback.message.message_id, xv_text_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            f"📝 متن خوش‌آمدید فعلی:\n\n{current if current else '(پیش‌فرض: به ربات خوش آمدید! لطفاً پیام خود را ارسال کنید.)'}\n\n"
            "لطفاً متن جدید را ارسال کنید (برای بازگشت به پیش‌فرض، کافیست خالی بفرستید):",
            reply_markup=vx_back_kb("xv_admin_settings")
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_setting_start")
async def vx_setting_start_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    current = await xv_db_get('start_text')
    await state.set_state(xv_fsm.xv_state_change_text)
    await state.update_data(xv_text_key='start_text', xv_text_msg_id=callback.message.message_id, xv_text_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            f"📝 متن جوین اجباری فعلی:\n\n{current if current else '(پیش‌فرض: لطفاً ابتدا در کانال‌های زیر عضو شوید.)'}\n\n"
            "لطفاً متن جدید را ارسال کنید:",
            reply_markup=vx_back_kb("xv_admin_settings")
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_setting_ban_text")
async def vx_setting_ban_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    current = await xv_db_get('ban_text')
    await state.set_state(xv_fsm.xv_state_change_text)
    await state.update_data(xv_text_key='ban_text', xv_text_msg_id=callback.message.message_id, xv_text_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            f"🚫 متن بن فعلی:\n\n{current if current else '(پیش‌فرض: شما توسط مدیریت مسدود شده‌اید.)'}\n\n"
            "لطفاً متن جدید را ارسال کنید:",
            reply_markup=vx_back_kb("xv_admin_settings")
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "xv_setting_maint_text")
async def vx_setting_maint_text_cb(callback: CallbackQuery, state: FSMContext):
    if not await vx_is_admin(callback.from_user.id):
        return
    current = await xv_db_get('maintenance_text')
    await state.set_state(xv_fsm.xv_state_change_text)
    await state.update_data(xv_text_key='maintenance_text', xv_text_msg_id=callback.message.message_id, xv_text_chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(
            f"📝 متن حالت تعمیر فعلی:\n\n{current if current else '(پیش‌فرض: ربات در حال بروزرسانی است. لطفاً بعداً مراجعه کنید.)'}\n\n"
            "لطفاً متن جدید را ارسال کنید:",
            reply_markup=vx_back_kb("xv_admin_settings")
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(xv_fsm.xv_state_change_text)
async def vx_change_text_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get('xv_text_key', 'start_text')
    msg_id = data.get('xv_text_msg_id')
    chat_id = data.get('xv_text_chat_id')
    if message.text and message.text.strip():
        await xv_db_set(key, message.text)
    else:
        await xv_db_delete(key)
    labels = {'welcome_text': '📝 متن خوش‌آمدید', 'start_text': '📝 متن جوین اجباری', 'ban_text': '🚫 متن بن', 'maintenance_text': '📝 متن حالت تعمیر'}
    label = labels.get(key, key)
    try:
        await bot.edit_message_text(f"✅ {label} با موفقیت به‌روزرسانی شد.", chat_id=chat_id, message_id=msg_id, reply_markup=vx_back_kb("xv_admin_settings"))
    except:
        await message.answer("✅ متن با موفقیت به‌روزرسانی شد.")
    await state.clear()
    await message.delete()

@dp.message(xv_fsm.xv_state_admin_reply)
async def vx_admin_reply_msg_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('xv_reply_user_id')
    user_msg_id = data.get('xv_reply_user_msg_id')
    msg_record_id = data.get('xv_reply_msg_id')

    if not user_id:
        await state.clear()
        return

    rp = ReplyParameters(message_id=user_msg_id) if user_msg_id else None

    try:
        if message.content_type == ContentType.TEXT:
            sent = await bot.send_message(user_id, message.text, reply_parameters=rp)
        elif message.content_type == ContentType.PHOTO:
            sent = await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.VIDEO:
            sent = await bot.send_video(user_id, message.video.file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.DOCUMENT:
            sent = await bot.send_document(user_id, message.document.file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.STICKER:
            sent = await bot.send_sticker(user_id, message.sticker.file_id, reply_parameters=rp)
        elif message.content_type == ContentType.VOICE:
            sent = await bot.send_voice(user_id, message.voice.file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.VIDEO_NOTE:
            sent = await bot.send_video_note(user_id, message.video_note.file_id, reply_parameters=rp)
        elif message.content_type == ContentType.ANIMATION:
            sent = await bot.send_animation(user_id, message.animation.file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.AUDIO:
            sent = await bot.send_audio(user_id, message.audio.file_id, caption=message.caption or '', reply_parameters=rp)
        elif message.content_type == ContentType.LOCATION:
            loc = message.location
            sent = await bot.send_location(user_id, loc.latitude, loc.longitude, reply_parameters=rp)
        elif message.content_type == ContentType.CONTACT:
            cnt = message.contact
            sent = await bot.send_contact(user_id, cnt.phone_number, cnt.first_name, last_name=cnt.last_name, reply_parameters=rp)
        else:
            sent = await bot.copy_message(user_id, message.chat.id, message.message_id, reply_parameters=rp)

        if sent:
            if user_msg_id:
                await xv_db_mark_replied(msg_record_id, sent.message_id)
                rec = await xv_db_get_by_id(msg_record_id)
                status_msg_id = rec['status_msg_id'] if rec else None
                if status_msg_id:
                    try:
                        kb = vx_status_kb('replied', user_msg_id)
                        await bot.edit_message_reply_markup(chat_id=user_id, message_id=status_msg_id, reply_markup=kb)
                    except:
                        pass
                else:
                    try:
                        kb = vx_status_kb('replied', user_msg_id)
                        for mid in [user_msg_id + 1, user_msg_id]:
                            try:
                                await bot.edit_message_reply_markup(chat_id=user_id, message_id=mid, reply_markup=kb)
                            except:
                                pass
                    except:
                        pass
            await message.answer("✅ پیام شما ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ خطا در ارسال: {e}")

    orig_msg_id = data.get('xv_orig_msg_id')
    orig_chat_id = data.get('xv_orig_chat_id')
    orig_user_id = data.get('xv_orig_user_id')
    await state.clear()
    if orig_msg_id and orig_chat_id and orig_user_id:
        if user_msg_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=orig_chat_id,
                    message_id=orig_msg_id,
                    reply_markup=vx_admin_actions_kb(orig_user_id)
                )
            except:
                pass
        else:
            try:
                pm = await bot.edit_message_text("⏳ در حال بارگذاری...", chat_id=orig_chat_id, message_id=orig_msg_id)
                await vx_show_user_tab(pm, orig_user_id, 'info')
            except:
                pass

@dp.message()
async def vx_message_router(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    user_id = message.from_user.id

    if message.reply_to_message and await vx_is_admin(user_id):
        await vx_process_admin_reply(message)
        return

    user_data = await xv_db_get_user(user_id)
    if user_data and user_data['is_banned']:
        ban_text = await xv_db_get('ban_text')
        await message.answer(ban_text or 'شما توسط مدیریت مسدود شده‌اید.')
        return

    maintenance = await xv_db_get('maintenance')
    if maintenance == '1':
        maint_text = await xv_db_get('maintenance_text')
        await message.answer(maint_text or 'ربات در حال بروزرسانی است. لطفاً بعداً مراجعه کنید.')
        return

    forced_join = await xv_db_get('forced_join')
    if forced_join == '1':
        if not await vx_check_forced_join(user_id, bot):
            channels_str = await xv_db_get('channels')
            if channels_str:
                try:
                    channels = json.loads(channels_str)
                except:
                    channels = []
            else:
                channels = []
            kb = vx_join_channels_kb(channels)
            start_text = await xv_db_get('start_text')
            await message.answer(
                start_text or 'لطفاً ابتدا در کانال‌های زیر عضو شوید:',
                reply_markup=kb
            )
            return

    if message.media_group_id:
        await vx_handle_media_group(message)
        return

    admin_msg_id, admin_chat_id = await vx_forward_to_admin(message, user_id)
    if admin_msg_id:
        status_kb = vx_status_kb('sent', message.message_id)
        status_msg = await message.answer("پیام شما به ادمین ارسال شد.", reply_markup=status_kb)
        await xv_db_save_message(user_id, message.message_id, admin_msg_id, admin_chat_id, status_msg.message_id)
        await asyncio.sleep(0.8)
        try:
            kb_read = vx_status_kb('read', message.message_id)
            await bot.edit_message_reply_markup(chat_id=user_id, message_id=status_msg.message_id, reply_markup=kb_read)
        except:
            pass
    else:
        await message.answer("پیام شما ثبت شد.")

@dp.edited_message(F.chat.type == ChatType.PRIVATE)
async def vx_edit_sync_handler(message: Message):
    if not await vx_is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        return

    admin_chat_id = message.chat.id
    replied_msg_id = message.reply_to_message.message_id

    msg_record = await xv_db_get_by_admin_msg(replied_msg_id, admin_chat_id)
    if not msg_record:
        msg_record = await xv_db_get_by_reply_msg(replied_msg_id)

    if not msg_record:
        return

    user_id = msg_record['user_id']
    reply_msg_id = msg_record['reply_msg_id']

    if not reply_msg_id:
        return

    try:
        if message.text:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=reply_msg_id,
                text=message.text
            )
        elif message.caption:
            await bot.edit_message_caption(
                chat_id=user_id,
                message_id=reply_msg_id,
                caption=message.caption
            )
    except Exception as e:
        logging.error(f"xv_edit_sync_handler error: {e}")

async def xv_main():
    await xv_db_init()

    global ADMIN_IDS
    admin_ids_str = await xv_db_get('admin_ids')
    if admin_ids_str:
        try:
            loaded_ids = json.loads(admin_ids_str)
            if loaded_ids:
                ADMIN_IDS = loaded_ids
                _admin_ids_cache = loaded_ids
                logging.info(f"Admin IDs loaded from DB: {ADMIN_IDS}")
        except Exception as e:
            logging.error(f"Failed to load admin IDs: {e}")

    logging.info("Bot started polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(xv_main())
