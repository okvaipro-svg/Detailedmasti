#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataTrace OSINT Bot - Single-file ready to run.
Features implemented per user's spec with refined UI as requested:
- Free bot (group members free). DM: 2 free searches then referral/credits.
- Referral system: 1 credit on join, 30% commission on admin-added purchases.
- APIs integrated: UPI, IN Number, TG user stats, IP, Pak CNIC, Aadhaar family/details.
- Paid feature: Call History (600 credits) - deducts credits on /callhistory.
- Blacklist + protected numbers table (only OWNER can view).
- Dynamic UI with context-aware buttons, only Back + Contact Admin buttons everywhere except main menu.
- Admin panel for SUDO IDs: addcredits, ban, unban, gcast, stats.
- Logging to groups for /start and searches.
"""

import logging
import sqlite3
import json
import requests
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

# -------------------------
# CONFIG - Edit if needed
# -------------------------
TOKEN = "8219144171:AAF8_6dxvS0skpljooJey2E-TfZhfMYKgjE"
BOT_USERNAME = "@UserDeepLookupBot"

OWNER_ID = 7924074157
SUDO_IDS = {7924074157, 5294360309, 7905267752}

GSUPPORT = "@DataTraceSupport"
MUST_JOIN_CHANNELS = ["DataTraceUpdates", "DataTraceOSINTSupport"]  # without '@'
MUST_JOIN_CHANNELS_AT = [f"@{c}" for c in MUST_JOIN_CHANNELS]

LOG_START_GROUP = -1002765060940
LOG_SEARCH_GROUP = -1003066524164

BLACKLIST_NUMS = {"+917724814462"}
# Protected numbers stored in DB table; only OWNER_ID can view via admin panel.

FREE_CREDIT_ON_JOIN = 1
REFERRAL_COMMISSION_RATIO = 0.3  # 30%
FREE_SEARCHES_DM = 2

CALL_HISTORY_COST = 600  # credits

CREDIT_PACKAGES = {
    100: 50,
    200: 100,
    500: 250,
    1000: 450,
    2000: 900,
    5000: 2250,
}

# APIs (user-provided)
API_UPI = "https://upi-info.vercel.app/api/upi?upi_id={upi}&key=456"
API_NUM_INFO = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={term}"
API_NUM_INFO_ID = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={term}"
API_TG_USER = "https://tg-info-neon.vercel.app/user-details?user={user}"
API_IP = "https://karmali.serv00.net/ip_api.php?ip={ip}"
API_PAK = "https://pak-num-api.vercel.app/search?number={num}"
API_AADHAR_FAMILY = "https://family-members-n5um.vercel.app/fetch?aadhaar={id}&key=paidchx"
API_CALL_HISTORY = "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"

DB_FILE = "datatrace_bot.db"

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------
# DB Setup
# -------------------------
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

# -------------------------
# DB helpers
# -------------------------
def get_user(user_id: int):
    c.execute(
        "SELECT user_id, credits, referrer_id, banned, joined_gc, free_searches_dm FROM users WHERE user_id=?",
        (user_id,),
    )
    return c.fetchone()


def create_user(user_id: int, referrer_id: Optional[int] = None):
    if get_user(user_id):
        return False
    c.execute(
        "INSERT INTO users (user_id, credits, referrer_id, banned, joined_gc, free_searches_dm) VALUES (?,?,?,?,?,?)",
        (user_id, FREE_CREDIT_ON_JOIN, referrer_id, 0, 0, 0),
    )
    conn.commit()
    if referrer_id:
        c.execute("INSERT INTO referrals (referrer, referee) VALUES (?,?)", (referrer_id, user_id))
        conn.commit()
    return True


def modify_credits(user_id: int, amount: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    new_val = user[1] + amount
    if new_val < 0:
        return False
    c.execute("UPDATE users SET credits=? WHERE user_id=?", (new_val, user_id))
    conn.commit()
    return True


def set_joined(user_id: int, val: int = 1):
    c.execute("UPDATE users SET joined_gc=? WHERE user_id=?", (val, user_id))
    conn.commit()


def increment_free_searches(user_id: int) -> int:
    u = get_user(user_id)
    if not u:
        return 0
    newv = u[5] + 1
    c.execute("UPDATE users SET free_searches_dm=? WHERE user_id=?", (newv, user_id))
    conn.commit()
    return newv


def ban_user(user_id: int):
    c.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()


def unban_user(user_id: int):
    c.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()


def add_protected(number: str, note: str = ""):
    c.execute("INSERT OR REPLACE INTO protected_numbers (number, note) VALUES (?,?)", (number, note))
    conn.commit()


def list_protected():
    c.execute("SELECT number, note FROM protected_numbers")
    return c.fetchall()


def is_protected(number: str) -> bool:
    c.execute("SELECT number FROM protected_numbers WHERE number=?", (number,))
    return bool(c.fetchone())


def total_users():
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]


def total_credits():
    c.execute("SELECT SUM(credits) FROM users")
    s = c.fetchone()[0]
    return s if s else 0


# -------------------------
# Utils
# -------------------------
def is_sudo(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_IDS


def normalize(num: str) -> str:
    return (num or "").strip().replace(" ", "")


def is_blacklisted(num: str) -> bool:
    n = normalize(num)
    return n in BLACKLIST_NUMS or n.lstrip("+") in BLACKLIST_NUMS


def fetch_api(url: str, timeout: int = 12):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return r.text
    except Exception as e:
        logger.warning("API fetch error: %s", e)
    return None


# -------------------------
# Formatters - keep styling consistent
# -------------------------
def fmt_upi(d) -> str:
    if not d:
        return "No UPI info found."
    b = d.get("bank_details_raw", {}) if isinstance(d, dict) else {}
    v = d.get("vpa_details", {}) if isinstance(d, dict) else {}
    lines = [
        "🔗 UPI Lookup Result",
        "━━━━━━━━━━━━━━━",
        f"🏦 Bank: {b.get('BANK', 'N/A')}",
        f"🏢 Branch: {b.get('BRANCH', 'N/A')}",
        f"📍 Address: {b.get('ADDRESS', 'N/A')}",
        f"🧾 IFSC: {b.get('IFSC', 'N/A')}",
        f"📌 MICR: {b.get('MICR', 'N/A')}",
        f"🌏 City: {b.get('CITY', 'N/A')}, {b.get('STATE', 'N/A')}",
        f"✔ UPI: {b.get('UPI', 'N/A')} | NEFT: {b.get('NEFT', 'N/A')} | RTGS: {b.get('RTGS', 'N/A')}",
        "",
        f"👤 Name: {v.get('name', 'N/A')}",
        f"💳 VPA: {v.get('vpa', 'N/A')}",
        "━━━━━━━━━━━━━━━",
        f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


def fmt_ip(d) -> str:
    if not d or not isinstance(d, dict):
        return "No IP data."
    def G(k): return d.get(k) or d.get(k.lower()) or d.get(k.upper()) or "N/A"
    lines = [
        "🌐 IP Lookup Result",
        "━━━━━━━━━━━━━━━",
        f"🗾 IP Valid: {G('IP Valid')}",
        f"🌎 Country: {G('Country')}",
        f"💠 Country Code: {G('Country Code')}",
        f"🥬 Region: {G('Region')}",
        f"🗺️ Region Name: {G('Region Name')}",
        f"🏠 City: {G('City')}",
        f"✉️ Zip: {G('Zip')}",
        f"🦠 Latitude: {G('Latitude')}",
        f"⭐ Longitude: {G('Longitude')}",
        f"🕢 Timezone: {G('Timezone')}",
        f"🗼 ISP: {G('ISP')}",
        f"🔥 Organization: {G('Organization')}",
        f"🌾 AS: {G('AS')}",
        f"🛰 IP: {G('IP')}",
        "━━━━━━━━━━━━━━━",
        f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


def fmt_num(d) -> str:
    if not d or "data" not in d or not d["data"]:
        return "Number info not found."
    r = d["data"][0]
    addr = r.get("address", "N/A")
    try:
        addr = addr.replace("!", ", ")
    except Exception:
        pass
    lines = [
        "📱 Number Info (India)",
        "━━━━━━━━━━━━━━━",
        f"📞 Mobile: {r.get('mobile', 'N/A')}",
        f"👤 Name: {r.get('name', 'N/A')}",
        f"👥 Father/Alt: {r.get('fname', 'N/A')}",
        f"🏠 Address: {addr}",
        f"📲 Alternate: {r.get('alt', 'N/A')}",
        f"📡 Circle: {r.get('circle', 'N/A')}",
        f"🪪 ID: {r.get('id', 'N/A')}",
        "━━━━━━━━━━━━━━━",
        f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


def fmt_pak(d) -> str:
    if not d or "results" not in d or not d["results"]:
        return "Pakistan number info not found."
    lines = ["🇵🇰 Pakistan Number Info", "━━━━━━━━━━━━━━━"]
    for rec in d["results"]:
        lines += [
            f"👤 Name: {rec.get('Name','N/A')}",
            f"🆔 CNIC: {rec.get('CNIC','N/A')}",
            f"📍 Address: {rec.get('Address','N/A') or 'N/A'}",
            f"📞 Number: {rec.get('Mobile','N/A')}",
            "-----",
        ]
    lines += ["━━━━━━━━━━━━━━━", f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}"]
    return "
".join(lines)


def fmt_aadhar_family(d) -> str:
    if not d:
        return "Aadhaar family info not found."
    lines = [
        "🪪 Aadhaar → Family Info",
        "━━━━━━━━━━━━━━━",
        f"🏠 Address: {d.get('address','N/A')}",
        f"📍 District: {d.get('homeDistName','N/A')}, {d.get('homeStateName','N/A')}",
        f"Scheme: {d.get('schemeName','N/A')} (Scheme ID: {d.get('schemeId','N/A')})",
        "",
        "👨‍👩‍👧 Members:",
    ]
    for idx, m in enumerate(d.get("memberDetailsList", []) or [], 1):
        lines.append(f"{idx}. {m.get('memberName','N/A')} ({m.get('releationship_name','N/A')})")
    lines += ["━━━━━━━━━━━━━━━", f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}"]
    return "
".join(lines)


def fmt_tg_user(d) -> str:
    if not d or "data" not in d:
        return "TG user stats not found."
    u = d["data"]
    lines = [
        "👤 Telegram User Stats",
        "━━━━━━━━━━━━━━━",
        f"🆔 ID: {u.get('id','N/A')}",
        f"📛 Name: {u.get('first_name','')} {u.get('last_name','')}",
        f"📬 Active: {'✅' if u.get('is_active') else '❌'}",
        f"🤖 Bot: {'✅' if u.get('is_bot') else '❌'}",
        f"📅 First Seen: {u.get('first_msg_date','')[:10]}",
        f"🕒 Last Seen: {u.get('last_msg_date','')[:10]}",
        "",
        f"📊 Messages in Groups: {u.get('msg_in_groups_count',0)}",
        f"💬 Total Messages: {u.get('total_msg_count',0)}",
        f"👥 Groups Joined: {u.get('total_groups',0)}",
        f"🧩 Total Usernames: {u.get('usernames_count',0)}",
        f"🧩 Total Names: {u.get('names_count',0)}",
        "━━━━━━━━━━━━━━━",
        f"📢 {MUST_JOIN_CHANNELS_AT[0]} | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


# -------------------------
# UI: dynamic keyboards
# -------------------------
def back_and_support(cb: str = "main_menu"):
    return [
        [InlineKeyboardButton("🔙 Back", callback_data=cb)],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")]
    ]


def main_menu_kb():
    kb = [
        [InlineKeyboardButton("🔎 Quick Search", switch_inline_query_current_chat="+91 ")],
        [
            InlineKeyboardButton("📱 Number Lookup", callback_data="menu_search_numbers"),
            InlineKeyboardButton("💳 UPI Lookup", callback_data="menu_upi"),
        ],
        [
            InlineKeyboardButton("🆔 Aadhaar", callback_data="menu_aadhar"),
            InlineKeyboardButton("🌍 IP Lookup", callback_data="menu_ip"),
        ],
        [
            InlineKeyboardButton("👤 TG Stats", callback_data="menu_tg"),
            InlineKeyboardButton("🇵🇰 Pak CNIC", callback_data="menu_pak"),
        ],
        [
            InlineKeyboardButton("🎁 Referral", callback_data="menu_referral"),
            InlineKeyboardButton("💰 Buy Credits", callback_data="menu_buycredits"),
        ],
        [
            InlineKeyboardButton("🔐 Admin Panel", callback_data="menu_admin"),
            InlineKeyboardButton("ℹ️ Help", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def search_numbers_kb():
    kb = [
        [InlineKeyboardButton("🇮🇳 India (+91) Lookup", callback_data="search_num_in")],
        [InlineKeyboardButton("🇵🇰 Pakistan (+92) Lookup", callback_data="search_num_pk")],
    ] + back_and_support("main_menu")
    return InlineKeyboardMarkup(kb)


def buycredits_kb():
    kb = [[InlineKeyboardButton(f"{amt} credits → ₹{price}", callback_data=f"buy_pkg|{amt}") ] for amt, price in sorted(CREDIT_PACKAGES.items())]
    kb += back_and_support("main_menu")
    return InlineKeyboardMarkup(kb)


def admin_panel_kb(is_sudo_user: bool):
    if not is_sudo_user:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Unauthorized", callback_data="main_menu")]])
    kb = [
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("📢 GCast", callback_data="admin_gcast")
        ],
        [
            InlineKeyboardButton("➕ Add Credits", callback_data="admin_addcredits"),
            InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")
        ],
        [
            InlineKeyboardButton("✅ Unban User", callback_data="admin_unban"),
            InlineKeyboardButton("🛡 Protected Numbers", callback_data="admin_protected")
        ]
    ] + back_and_support("main_menu")
    return InlineKeyboardMarkup(kb)


# -------------------------
# Callback handler (central)
# -------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    # MAIN MENU
    if data == "main_menu":
        await query.edit_message_text("✨ DataTrace OSINT — Main Menu", reply_markup=main_menu_kb())
        return

    if data == "menu_help":
        help_txt = (
            "ℹ️ *DataTrace OSINT Bot - Help*

"
            "• Send phone numbers, UPI, Aadhaar, IP, or Telegram usernames directly in DM.
"
            "• Use commands in groups to search:
"
            "   /num <number> - Number lookup
"
            "   /upi <vpa> - UPI lookup
"
            "   /aadhar <id> - Aadhaar info
"
            "   /ip <ip> - IP lookup
"
            "   /tg <username> - Telegram user stats
"
            "   /pak <number> - Pakistan CNIC lookup
"
            "• Use /credits to check credits.
"
            "• Referral system rewards you credits.

"
            "For support, contact admin."
        )
        await query.edit_message_text(help_txt, reply_markup=InlineKeyboardMarkup(back_and_support()), parse_mode=ParseMode.MARKDOWN)
        return

    # Search menus
    if data == "menu_search_numbers":
        await query.edit_message_text("Choose number lookup type:", reply_markup=search_numbers_kb())
        return

    if data == "search_num_in":
        await query.edit_message_text("Send the Indian number (+91 or plain 10 digits) in chat or use /num <number>.", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "search_num_pk":
        await query.edit_message_text("Send Pakistan number (+92...) or use /pak <number>.", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "menu_upi":
        await query.edit_message_text("Send /upi <vpa> or type vpa in chat (example: example@upi).", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "menu_ip":
        await query.edit_message_text("Send /ip <ip-address> or type ip in chat (example: 8.8.8.8).", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "menu_pak":
        await query.edit_message_text("Pakistan CNIC/number lookup — use /pak <number> or send +92 number.", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "menu_aadhar":
        await query.edit_message_text("Aadhaar family/details — use /aadhar <id>.", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    if data == "menu_tg":
        await query.edit_message_text("Telegram user stats — use /tg <username_or_id>.", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    # Buy credits
    if data == "menu_buycredits":
        await query.edit_message_text("Choose a package (contact admin to pay):", reply_markup=buycredits_kb())
        return

    if data and data.startswith("buy_pkg|"):
        parts = data.split("|", 1)
        try:
            amt = int(parts[1])
        except:
            amt = None
        if amt and amt in CREDIT_PACKAGES:
            price = CREDIT_PACKAGES[amt]
            await query.edit_message_text(
                f"Package: {amt} credits → ₹{price}
Contact admin {GSUPPORT} after payment. Admin will add credits and commission to referrer.",
                reply_markup=InlineKeyboardMarkup(back_and_support("main_menu"))
            )
            return

    # Referral
    if data == "menu_referral":
        link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{uid}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Copy Link", callback_data="main_menu")],
            [InlineKeyboardButton("Share Link", switch_inline_query=link)],
            [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ])
        await query.edit_message_text(f"Your referral link:
{link}

Share to earn credits!", reply_markup=kb)
        return

    # Admin panel
    if data == "menu_admin":
        await query.edit_message_text("Admin Panel", reply_markup=admin_panel_kb(is_sudo(uid)))
        return

    # Admin callbacks
    if data == "admin_stats":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized", reply_markup=InlineKeyboardMarkup(back_and_support()))
            return
        await query.edit_message_text(f"Total users: {total_users()}
Total credits: {total_credits()}", reply_markup=admin_panel_kb(True))
        return

    if data == "admin_gcast":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized", reply_markup=InlineKeyboardMarkup(back_and_support()))
            return
        await query.edit_message_text("Send /gcast <message> to broadcast to all users.", reply_markup=admin_panel_kb(True))
        return

    if data == "admin_addcredits":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized", reply_markup=InlineKeyboardMarkup(back_and_support()))
            return
        await query.edit_message_text("Usage: /addcredits <user_id> <amount> (admins should verify payment first)", reply_markup=admin_panel_kb(True))
        return

    if data == "admin_ban":
        if not is_sudo(uid):
    
