#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataTrace OSINT Bot - Single-file, ready-to-copy-paste.

Features:
- Free bot but referral-based credit system
- GC (DataTraceOSINTSupport) users get full free access; DM users get 2 free searches then must refer or buy credits
- APIs integrated: UPI, Number Info (IN), TG user stats, IP info, Pak CNIC, Aadhaar family/details
- Paid feature: Call History (₹600 per search) — no demo
- Buttons & callbacks: main menu, results actions, buy credits, admin panel
- Admins / SUDO: full control (add credits, ban/unban, gcast, stats)
- Protected numbers viewable only by owner
- Blacklist blocking
- Logging: start & search logs to groups
"""

import logging
import sqlite3
import json
import requests
import html
import time
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# -----------------------------
# CONFIG - Edit only if needed
# -----------------------------
TOKEN = "8219144171:AAF8_6dxvS0skpljooJey2E-TfZhfMYKgjE"
BOT_USERNAME = "@UserDeepLookupBot"

# Admins / sudo
OWNER_ID = 7924074157
SUDO_IDS = {7924074157, 5294360309, 7905267752}

# Support / groups / must-join channels
GSUPPORT = "@DataTraceSupport"
MUST_JOIN_CHANNELS = ["DataTraceUpdates", "DataTraceOSINTSupport"]
MUST_JOIN_CHANNELS_CHATNAMES = [f"@{c}" for c in MUST_JOIN_CHANNELS]

# Logging groups (as requested)
LOG_START_GROUP = -1002765060940   # when user does /start (log)
LOG_SEARCH_GROUP = -1003066524164  # when user performs a search (log)

# Blacklist & Protected numbers
BLACKLIST_NUMS = {"+917724814462"}  # never return data for these
PROTECTED_NUMBERS = set()  # can add if needed; only owner can view

# Free usage & referral settings
FREE_CREDIT_ON_JOIN = 1
REFERRAL_COMMISSION_RATIO = 0.3  # 30% of credits purchased
FREE_SEARCHES_DM = 2

# Paid constants
CALL_HISTORY_COST = 600  # credits

# Credit packages (user requested cheaper prices)
CREDIT_PACKAGES = {
    100: 50,
    200: 100,
    500: 250,
    1000: 450,
    2000: 900,
    5000: 2250,
}

# APIs (as provided)
API_UPI = "https://upi-info.vercel.app/api/upi?upi_id={upi}&key=456"
API_NUM_INFO = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={term}"
API_NUM_INFO_ID = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={term}"
API_TG_USER = "https://tg-info-neon.vercel.app/user-details?user={user}"
API_IP = "https://karmali.serv00.net/ip_api.php?ip={ip}"
API_PAK = "https://pak-num-api.vercel.app/search?number={num}"
API_AADHAR_FAMILY = "https://family-members-n5um.vercel.app/fetch?aadhaar={id}&key=paidchx"
API_CALL_HISTORY = "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"

# Database file
DB_FILE = "datatrace_bot.db"

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------
# Database (SQLite)
# -----------------------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credits INTEGER DEFAULT 0,
    referrer_id INTEGER,
    banned INTEGER DEFAULT 0,
    joined_gc INTEGER DEFAULT 0,
    free_searches_dm INTEGER DEFAULT 0,
    created_at INTEGER DEFAULT (strftime('%s','now'))
)
"""
)
c.execute(
    """
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer INTEGER,
    referee INTEGER,
    created_at INTEGER DEFAULT (strftime('%s','now'))
)
"""
)
c.execute(
    """
CREATE TABLE IF NOT EXISTS protected_numbers (
    number TEXT PRIMARY KEY,
    note TEXT
)
"""
)
conn.commit()

# Insert default protected numbers set (optional)
for pn in PROTECTED_NUMBERS:
    try:
        c.execute("INSERT OR IGNORE INTO protected_numbers (number, note) VALUES (?,?)", (pn, "protected"))
    except Exception:
        pass
conn.commit()


# -----------------------------
# DB Helpers
# -----------------------------
def get_user(user_id: int):
    c.execute("SELECT user_id, credits, referrer_id, banned, joined_gc, free_searches_dm FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row


def add_user(user_id: int, referrer_id: Optional[int] = None):
    if get_user(user_id):
        return False
    c.execute("INSERT INTO users (user_id, credits, referrer_id, banned, joined_gc, free_searches_dm) VALUES (?,?,?,?,?,?)",
              (user_id, FREE_CREDIT_ON_JOIN if referrer_id is None else FREE_CREDIT_ON_JOIN, referrer_id, 0, 0, 0))
    conn.commit()
    if referrer_id:
        c.execute("INSERT INTO referrals (referrer, referee) VALUES (?,?)", (referrer_id, user_id))
        conn.commit()
    return True


def modify_credits(user_id: int, amount: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    new_amount = user[1] + amount
    if new_amount < 0:
        return False
    c.execute("UPDATE users SET credits=? WHERE user_id=?", (new_amount, user_id))
    conn.commit()
    return True


def set_joined_gc(user_id: int, val: int = 1):
    c.execute("UPDATE users SET joined_gc=? WHERE user_id=?", (val, user_id))
    conn.commit()


def increment_free_searches(user_id: int):
    user = get_user(user_id)
    if not user:
        return False
    new_val = user[5] + 1
    c.execute("UPDATE users SET free_searches_dm=? WHERE user_id=?", (new_val, user_id))
    conn.commit()
    return new_val


def ban_user_db(user_id: int):
    c.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()


def unban_user_db(user_id: int):
    c.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()


def total_users_count():
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]


def total_credits_sum():
    c.execute("SELECT SUM(credits) FROM users")
    val = c.fetchone()[0]
    return val if val else 0


def add_protected_number(number: str, note: str = ""):
    c.execute("INSERT OR REPLACE INTO protected_numbers (number, note) VALUES (?,?)", (number, note))
    conn.commit()


def is_protected(number: str) -> bool:
    c.execute("SELECT number FROM protected_numbers WHERE number=?", (number,))
    return bool(c.fetchone())


def is_blacklisted(number: str) -> bool:
    n = number.replace(" ", "")
    return n in BLACKLIST_NUMS or n.lstrip("+") in BLACKLIST_NUMS


# -----------------------------
# Utilities
# -----------------------------
def is_sudo(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_IDS


def normalize_number(num: str) -> str:
    return num.strip().replace(" ", "")


# API fetcher
def fetch_api(url: str, timeout: int = 12):
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                # sometimes API returns plain text - return text
                return resp.text
    except Exception as e:
        logger.error("API fetch error: %s", e)
    return None


# -----------------------------
# Formatters (per user request)
# -----------------------------
def format_upi_info(data) -> str:
    if not data:
        return "No UPI info found."
    b = data.get("bank_details_raw", {}) if isinstance(data, dict) else {}
    v = data.get("vpa_details", {}) if isinstance(data, dict) else {}
    lines = []
    lines.append("🔗 UPI Info Result")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🏦 Bank: {b.get('BANK', 'N/A')}")
    lines.append(f"🏢 Branch: {b.get('BRANCH', 'N/A')}")
    lines.append(f"📍 Address: {b.get('ADDRESS', 'N/A')}")
    lines.append(f"🧾 IFSC: {b.get('IFSC', 'N/A')}")
    lines.append(f"📌 MICR: {b.get('MICR', 'N/A')}")
    lines.append(f"🌏 City: {b.get('CITY', 'N/A')}, {b.get('STATE', 'N/A')}")
    lines.append(f"✔ NEFT: {b.get('NEFT', 'N/A')} | RTGS: {b.get('RTGS', 'N/A')} | IMPS: {b.get('IMPS', 'N/A')} | UPI: {b.get('UPI', 'N/A')}")
    lines.append("")
    lines.append(f"👤 Name: {v.get('name', 'N/A')}")
    lines.append(f"💳 VPA: {v.get('vpa', 'N/A')}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


def format_ip_info(data) -> str:
    # Keep formatting as user asked (emoji + labels)
    if not data or not isinstance(data, dict):
        return "No IP data."
    # these APIs sometimes return keys in different case; attempt both
    def get(d, k):
        return d.get(k) or d.get(k.lower()) or d.get(k.upper()) or "N/A"

    lines = []
    lines.append("🌐 IP Lookup Result")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🗾 IP Valid: {get(data, 'IP Valid')}")
    lines.append(f"🌎 Country: {get(data, 'Country')}")
    lines.append(f"💠 Country Code: {get(data, 'Country Code')}")
    lines.append(f"🥬 Region: {get(data, 'Region')}")
    lines.append(f"🗺️ Region Name: {get(data, 'Region Name')}")
    lines.append(f"🏠 City: {get(data, 'City')}")
    lines.append(f"✉️ Zip: {get(data, 'Zip')}")
    lines.append(f"🦠 Latitude: {get(data, 'Latitude')}")
    lines.append(f"⭐ Longitude: {get(data, 'Longitude')}")
    lines.append(f"🕢 Timezone: {get(data, 'Timezone')}")
    lines.append(f"🗼 ISP: {get(data, 'ISP')}")
    lines.append(f"🔥 Organization: {get(data, 'Organization')}")
    lines.append(f"🌾 AS: {get(data, 'AS')}")
    lines.append(f"🛰 IP: {get(data, 'IP')}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


def format_num_info(data) -> str:
    if not data or "data" not in data or len(data["data"]) == 0:
        return "Number info not found."
    d = data["data"][0]
    # address replacement as requested: '!' => ', '
    addr = d.get("address", "N/A")
    try:
        addr = addr.replace("!", ", ")
    except Exception:
        pass
    lines = []
    lines.append("📱 Number Info (India)")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📞 Mobile: {d.get('mobile', 'N/A')}")
    lines.append(f"👤 Name: {d.get('name', 'N/A')}")
    lines.append(f"👥 Father/Alt: {d.get('fname', 'N/A')}")
    lines.append(f"🏠 Address: {addr}")
    lines.append(f"📲 Alternate: {d.get('alt', 'N/A')}")
    lines.append(f"📡 Circle: {d.get('circle', 'N/A')}")
    lines.append(f"🪪 ID: {d.get('id', 'N/A')}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


def format_pak_info(data) -> str:
    if not data or "results" not in data or len(data["results"]) == 0:
        return "Pakistan number info not found."
    lines = []
    lines.append("🇵🇰 Pakistan Number Info")
    lines.append("━━━━━━━━━━━━━━━")
    for rec in data["results"]:
        lines.append(f"👤 Name: {rec.get('Name','N/A')}")
        lines.append(f"🆔 CNIC: {rec.get('CNIC','N/A')}")
        addr = rec.get("Address", "N/A")
        lines.append(f"📍 Address: {addr if addr else 'N/A'}")
        lines.append(f"📞 Number: {rec.get('Mobile','N/A')}")
        lines.append("-----")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


def format_aadhar_family(data) -> str:
    if not data:
        return "Aadhaar family info not found."
    lines = []
    lines.append("🪪 Aadhaar -> Family Info")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🏠 Address: {data.get('address', 'N/A')}")
    lines.append(f"📍 District: {data.get('homeDistName', 'N/A')}, {data.get('homeStateName', 'N/A')}")
    lines.append(f"Scheme: {data.get('schemeName', 'N/A')} (Scheme ID: {data.get('schemeId','N/A')})")
    lines.append("")
    lines.append("👨‍👩‍👧 Members:")
    members = data.get("memberDetailsList", [])
    for idx, m in enumerate(members, 1):
        lines.append(f"{idx}. {m.get('memberName','N/A')} ({m.get('releationship_name','N/A')})")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


def format_tg_user_stats(data) -> str:
    d = data.get("data", {}) if isinstance(data, dict) else {}
    if not d:
        return "TG user stats not found."
    lines = []
    lines.append("👤 Telegram User Stats")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🆔 ID: {d.get('id', 'N/A')}")
    lines.append(f"📛 Name: {d.get('first_name', '')} {d.get('last_name', '')}")
    lines.append(f"📬 Active: {'✅' if d.get('is_active') else '❌'}")
    lines.append(f"🤖 Bot: {'✅' if d.get('is_bot') else '❌'}")
    lines.append(f"📅 First Seen: {d.get('first_msg_date', '')[:10]}")
    lines.append(f"🕒 Last Seen: {d.get('last_msg_date', '')[:10]}")
    lines.append("")
    lines.append(f"📊 Messages in Groups: {d.get('msg_in_groups_count', 0)}")
    lines.append(f"💬 Total Messages: {d.get('total_msg_count', 0)}")
    lines.append(f"👥 Groups Joined: {d.get('total_groups', 0)}")
    lines.append(f"🧩 Total Usernames: {d.get('usernames_count', 0)}")
    lines.append(f"🧩 Total Names: {d.get('names_count', 0)}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 {MUST_JOIN_CHANNELS_CHATNAMES[0]} | Support: {GSUPPORT}")
    return "\n".join(lines)


# -----------------------------
# Keyboards & UI
# -----------------------------
def main_menu_keyboard():
    kb = [
        [InlineKeyboardButton("🔎 Number (auto)", switch_inline_query_current_chat="+91 ")],
        [InlineKeyboardButton("🔍 UPI Lookup", callback_data="ui_upi"),
         InlineKeyboardButton("🌐 IP Lookup", callback_data="ui_ip")],
        [InlineKeyboardButton("🇵🇰 Pakistan CNIC", callback_data="ui_pak"),
         InlineKeyboardButton("🪪 Aadhaar (Family)", callback_data="ui_aadhar")],
        [InlineKeyboardButton("👤 TG User Stats", callback_data="ui_tg"),
         InlineKeyboardButton("📞 Call History (Paid)", callback_data="ui_callhistory")],
        [InlineKeyboardButton("🎁 Referral", callback_data="ui_referral"),
         InlineKeyboardButton("💳 Buy Credits", callback_data="ui_buycredits")],
        [InlineKeyboardButton("🆘 Support", url=f"https://t.me/{GSUPPORT.lstrip('@')}"),
         InlineKeyboardButton("ℹ️ Help", callback_data="ui_help")],
    ]
    return InlineKeyboardMarkup(kb)


def result_action_keyboard(number_based=False):
    kb = [
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu"),
         InlineKeyboardButton("◀️ Back", callback_data="main_menu")]
    ]
    if number_based:
        kb.insert(0, [InlineKeyboardButton(f"📞 Call History (₹{CALL_HISTORY_COST})", callback_data="buy_callhistory")])
    return InlineKeyboardMarkup(kb)


def buy_credits_keyboard():
    kb = []
    for credits, price in sorted(CREDIT_PACKAGES.items()):
        kb.append([InlineKeyboardButton(f"{credits} credits → ₹{price}", callback_data=f"buy_pkg|{credits}")])
    kb.append([InlineKeyboardButton("Contact Admin / Pay", url=f"https://t.me/{GSUPPORT.lstrip('@')}")])
    kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)


def admin_panel_keyboard():
    kb = [
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
         InlineKeyboardButton("📢 GCast", callback_data="admin_gcast")],
        [InlineKeyboardButton("➕ Add Credits", callback_data="admin_addcredits"),
         InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban"),
         InlineKeyboardButton("🛡 Protected Numbers", callback_data="admin_protected")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(kb)


# -----------------------------
# Callbacks
# -----------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    # Basic menu navigation
    if data == "main_menu":
        await query.edit_message_text("✨ DataTrace OSINT — Main Menu", reply_markup=main_menu_keyboard())
        return

    if data == "ui_help":
        help_text = (
            "Commands:\n"
            "/start - Start bot\n"
            "/help - This message\n"
            "/stats - Admin stats\n\n"
            "Search examples:\n"
            "/upi <vpa>\n"
            "/num <number>\n"
            "/ip <ip>\n"
            "/pak <number>\n"
            "/aadhar <id>\n"
            "/tg <username_or_id>\n"
            "/callhistory <number>  (paid: ₹600/search)\n\n"
            "Direct number in DM or groups also works.\n"
            f"Support: {GSUPPORT}"
        )
        await query.edit_message_text(help_text, reply_markup=main_menu_keyboard())
        return

    if data == "ui_referral":
        link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{uid}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Copy Link", callback_data="main_menu")],
            [InlineKeyboardButton("Share Link", switch_inline_query=link)],
            [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        await query.edit_message_text(f"Your referral link:\n{link}\n\nShare it to earn credits!", reply_markup=kb)
        return

    if data == "ui_buycredits":
        await query.edit_message_text("Choose a credit package:", reply_markup=buy_credits_keyboard())
        return

    if data.startswith("buy_pkg|"):
        parts = data.split("|", 1)
        try:
            amt = int(parts[1])
        except Exception:
            amt = None
        if amt and amt in CREDIT_PACKAGES:
            price = CREDIT_PACKAGES[amt]
            await query.edit_message_text(
                f"Package: {amt} credits → ₹{price}\n\nTo purchase, contact admin: {GSUPPORT}\nAfter payment, admin will add credits.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
                ])
            )
            return

    # Call history purchase flow (button)
    if data == "buy_callhistory":
        # We'll ask user to send the number in chat with /callhistory <number> (deduction occurs there)
        await query.edit_message_text(f"Call History is paid: ₹{CALL_HISTORY_COST} credits per search.\nSend /callhistory <number> in chat. Credits will be deducted when you run the command.", reply_markup=main_menu_keyboard())
        return

    # Admin Panel
    if data == "admin_panel":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("🔐 Admin Panel", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_stats":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text(f"Total users: {total_users_count()}\nTotal credits in system: {total_credits_sum()}", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_gcast":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("Send /gcast <message> in chat to broadcast to all users.", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_addcredits":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("Usage: /addcredits <user_id> <amount>", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_ban":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("Usage: /ban <user_id>", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_unban":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("Usage: /unban <user_id>", reply_markup=admin_panel_keyboard())
        return

    if data == "admin_protected":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.", reply_markup=admin_panel_keyboard())
            return
        # List protected numbers
        c.execute("SELECT number, note FROM protected_numbers")
        rows = c.fetchall()
        if not rows:
            await query.edit_message_text("No protected numbers configured.", reply_markup=admin_panel_keyboard())
            return
        txt = "Protected numbers:\n" + "\n".join([f"{r[0]} - {r[1]}" for r in rows])
        await query.edit_message_text(txt, reply_markup=admin_panel_keyboard())
        return

    # Fallback
    await query.edit_message_text("Option expired or unknown. Returning to main menu.", reply_markup=main_menu_keyboard())


# -----------------------------
# Command Handlers
# -----------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    text = update.message.text or ""
    # Check mandatory channel join
    # We'll attempt to verify membership in required channels; if fails, ask to join
    def check_joined(user_id: int):
        for ch in MUST_JOIN_CHANNELS:
            try:
                mem = context.bot.get_chat_member(chat_id=ch, user_id=user_id)
                # mem.status can be 'left' 'kicked' 'member' 'administrator' 'creator'
                if mem.status in ("left", "kicked"):
                    return False
            except Exception:
                # Can't check or bot isn't admin; safer to require join explicitly
                return False
        return True

    joined = check_joined(uid)

    # If /start has referral token
    ref_id = None
    if text.startswith("/start") and "ref_" in text:
        try:
            ref_id = int(text.split("ref_")[1])
            if ref_id == uid:
                ref_id = None
        except Exception:
            ref_id = None

    # Create user if not exists
    existed = get_user(uid)
    if not existed:
        add_user(uid, referrer_id=ref_id)
        # referral commission on join: give referrer 1 credit (or specified)
        if ref_id and get_user(ref_id):
            # give 1 free credit to referrer
            modify_credits(ref_id, FREE_CREDIT_ON_JOIN)
            # Log referral already inserted into referrals table by add_user
    # If user joined required channels, set flag
    if joined:
        set_joined_gc(uid, 1)

    # Send start message
    if not joined:
        msg = (
            f"👋 Hello {user.first_name}!\n\n"
            "To use this bot, you MUST join the following channels first:\n"
            + "\n".join(MUST_JOIN_CHANNELS_CHATNAMES)
            + f"\n\nAfter joining, press /start again.\n\nSupport: {GSUPPORT}"
        )
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("I Joined ✅ (Press after joining)", callback_data="main_menu")],
            [InlineKeyboardButton("Contact Support", url=f"https://t.me/{GSUPPORT.lstrip('@')}")]
        ]))
    else:
        # Good, allow access
        start_text = (
            f"👋 Welcome to DataTrace OSINT Bot — Free-access via group or referrals!\n\n"
            f"Use the menu below. You have {FREE_SEARCHES_DM} free searches in DM before needing to refer/buy credits.\n\n"
            f"Referral: open the menu → Referral to share your link and earn credits.\n\nSupport: {GSUPPORT}"
        )
        await update.message.reply_text(start_text, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)

    # Log start to group
    try:
        context.bot.send_message(LOG_START_GROUP, f"User /start: {uid} — joined_required_channels={joined} — ref={ref_id}")
    except Exception as e:
        logger.warning("Failed to log start: %s", e)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use the main menu or send commands. Type /start to open menu.", reply_markup=main_menu_keyboard())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    await update.message.reply_text(f"Total users: {total_users_count()}\nTotal credits in system: {total_credits_sum()}", reply_markup=main_menu_keyboard())


async def sudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    await update.message.reply_text("Sudo IDs:\n" + "\n".join(str(x) for x in SUDO_IDS), reply_markup=main_menu_keyboard())


async def addcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        parts = update.message.text.split()
        if len(parts) != 3:
            raise ValueError
        target = int(parts[1])
        amount = int(parts[2])
    except Exception:
        await update.message.reply_text("Usage: /addcredits <user_id> <amount>", reply_markup=main_menu_keyboard())
        return
    if not get_user(target):
        await update.message.reply_text("User not found in database. They must /start first.", reply_markup=main_menu_keyboard())
        return
    modify_credits(target, amount)
    await update.message.reply_text(f"Added {amount} credits to {target}.", reply_markup=main_menu_keyboard())


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        parts = update.message.text.split()
        target = int(parts[1])
    except Exception:
        await update.message.reply_text("Usage: /ban <user_id>", reply_markup=main_menu_keyboard())
        return
    ban_user_db(target)
    await update.message.reply_text(f"Banned {target}.", reply_markup=main_menu_keyboard())


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        parts = update.message.text.split()
        target = int(parts[1])
    except Exception:
        await update.message.reply_text("Usage: /unban <user_id>", reply_markup=main_menu_keyboard())
        return
    unban_user_db(target)
    await update.message.reply_text(f"Unbanned {target}.", reply_markup=main_menu_keyboard())


async def gcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        msg = update.message.text.split(" ", 1)[1]
    except Exception:
        await update.message.reply_text("Usage: /gcast <message>", reply_markup=main_menu_keyboard())
        return
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    sent = 0
    for r in rows:
        try:
            await context.bot.send_message(r[0], msg)
            sent += 1
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast sent to {sent} users.", reply_markup=main_menu_keyboard())


# Call history command (paid)
async def callhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_blacklisted((update.message.text.split()[-1]) if update.message.text else ""):
        await update.message.reply_text("This number is blacklisted.", reply_markup=main_menu_keyboard())
        return
    try:
        parts = update.message.text.split()
        num = parts[1]
    except Exception:
        await update.message.reply_text("Usage: /callhistory <number>", reply_markup=main_menu_keyboard())
        return

    # Deduct credits
    user = get_user(uid)
    if not is_sudo(uid):
        if not user or user[1] < CALL_HISTORY_COST:
            await update.message.reply_text(f"Insufficient credits. Call History costs {CALL_HISTORY_COST} credits.", reply_markup=main_menu_keyboard())
            return
        else:
            modify_credits(uid, -CALL_HISTORY_COST)
    # Call API
    api = API_CALL_HISTORY.format(num=num)
    data = fetch_api(api)
    if not data:
        await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
        return
    pretty = "📝 Call History Result:\n\n" + json.dumps(data, indent=2)
    await update.message.reply_text(pretty, parse_mode=ParseMode.MARKDOWN)
    # Log
    try:
        context.bot.send_message(LOG_SEARCH_GROUP, f"User {uid} requested callhistory for {num}")
    except Exception:
        pass


# Generic search handler - both commands and direct inputs
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    text = msg.text.strip() if msg.text else ""
    chat_type = msg.chat.type

    # enforce user not banned
    user = get_user(uid)
    if user and user[3] == 1:
        await msg.reply_text("You are banned from using this bot.", reply_markup=main_menu_keyboard())
        return

    # must join channels
    def check_joined(user_id: int):
        for ch in MUST_JOIN_CHANNELS:
            try:
                mem = context.bot.get_chat_member(chat_id=ch, user_id=user_id)
                if mem.status in ("left", "kicked"):
                    return False
            except Exception:
                return False
        return True

    joined = check_joined(uid)
    if not joined:
        await msg.reply_text("You must join the required channels first.", reply_markup=main_menu_keyboard())
        return

    # If DM and free searches left
    if chat_type == "private" and not is_sudo(uid):
        u = get_user(uid)
        free_used = u[5] if u else 0
        if free_used < FREE_SEARCHES_DM:
            increment_free_searches(uid)
            # allow free
        else:
            # if user has credits allow, else ask to refer/buy
            if not u or u[1] <= 0:
                await msg.reply_text("Aapke paas free searches khatam ho gaye hain. Refer karo ya credits kharido.", reply_markup=main_menu_keyboard())
                return

    # If user simply sends command style, let individual command handlers handle them
    if text.startswith("/"):
        # Let dispatcher handle specific commands (we already have handlers registered)
        return

    # If text looks like number
    t = normalize_number(text)
    # blacklist check
    if is_blacklisted(t):
        await msg.reply_text("This number is blacklisted. No data available.", reply_markup=main_menu_keyboard())
        return

    # Decide which API to call:
    # if startswith +92 -> Pakistan API
    # if startswith +91 or all digits -> India number API
    if t.startswith("+92") or (t.startswith("92") and len(t) >= 11):
        # Pak API
        api = API_PAK.format(num=t)
        data = fetch_api(api)
        out = format_pak_info(data)
        await msg.reply_text("🇵🇰 Pakistan Number Search Result\n\n" + out, reply_markup=result_action_keyboard(number_based=True))
        # log
        try:
            context.bot.send_message(LOG_SEARCH_GROUP, f"Search by {uid}: PAK number {t}")
        except Exception:
            pass
        return
    elif t.startswith("+91") or (t.isdigit() and (len(t) >= 10)):
        api = API_NUM_INFO.format(term=t)
        data = fetch_api(api)
        out = format_num_info(data if data else {})
        await msg.reply_text("📱 Number Search Result\n\n" + out, reply_markup=result_action_keyboard(number_based=True))
        try:
            context.bot.send_message(LOG_SEARCH_GROUP, f"Search by {uid}: IN number {t}")
        except Exception:
            pass
        return
    else:
        # Unknown free text - tell user to use commands or menu
        await msg.reply_text("Invalid input. Use /help or the menu. For number lookups send +91... or +92... or use /num <number>.", reply_markup=main_menu_keyboard())


# Command wrappers for specific APIs
async def upi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        upi = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /upi <vpa>", reply_markup=main_menu_keyboard())
        return
    if not upi:
        await update.message.reply_text("Usage: /upi <vpa>", reply_markup=main_menu_keyboard())
        return
    api = API_UPI.format(upi=upi)
    data = fetch_api(api)
    out = format_upi_info(data if data else {})
    await update.message.reply_text("🔗 UPI Lookup Result\n\n" + out, reply_markup=result_action_keyboard())


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ip = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /ip <ip>", reply_markup=main_menu_keyboard())
        return
    api = API_IP.format(ip=ip)
    data = fetch_api(api)
    out = format_ip_info(data if data else {})
    await update.message.reply_text(out, reply_markup=result_action_keyboard())


async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /num <number>", reply_markup=main_menu_keyboard())
        return
    if is_blacklisted(num):
        await update.message.reply_text("Blacklisted number.", reply_markup=main_menu_keyboard())
        return
    api = API_NUM_INFO.format(term=num)
    data = fetch_api(api)
    out = format_num_info(data if data else {})
    await update.message.reply_text("📱 Number Lookup Result\n\n" + out, reply_markup=result_action_keyboard(number_based=True))


async def pak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /pak <number>", reply_markup=main_menu_keyboard())
        return
    if is_blacklisted(num):
        await update.message.reply_text("Blacklisted number.", reply_markup=main_menu_keyboard())
        return
    api = API_PAK.format(num=num)
    data = fetch_api(api)
    out = format_pak_info(data if data else {})
    await update.message.reply_text(out, reply_markup=result_action_keyboard(number_based=True))


async def aadhar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        aid = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /aadhar <aadhaar_number>", reply_markup=main_menu_keyboard())
        return
    api = API_AADHAR_FAMILY.format(id=aid)
    data = fetch_api(api)
    out = format_aadhar_family(data if data else {})
    await update.message.reply_text(out, reply_markup=result_action_keyboard())


async def tg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /tg <username_or_id>", reply_markup=main_menu_keyboard())
        return
    api = API_TG_USER.format(user=user)
    data = fetch_api(api)
    out = format_tg_user_stats(data if data else {})
    await update.message.reply_text(out, reply_markup=result_action_keyboard())


# Unknown commands handler
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help", reply_markup=main_menu_keyboard())


# -----------------------------
# Startup & main
# -----------------------------
def run():
    app = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("sudo", sudo_command))
    app.add_handler(CommandHandler("addcredits", addcredits_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("gcast", gcast_command))
    app.add_handler(CommandHandler("callhistory", callhistory_command))
    app.add_handler(CommandHandler("upi", upi_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("num", num_command))
    app.add_handler(CommandHandler("pak", pak_command))
    app.add_handler(CommandHandler("aadhar", aadhar_command))
    app.add_handler(CommandHandler("tg", tg_command))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    run()
