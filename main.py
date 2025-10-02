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
TOKEN = "8219144171:AAEKPgaq7P9-KSvq92YRm8xwJq7H9sxh42s"
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
    return "\n".join(lines) 


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
        help_txt = """ℹ️ *DataTrace OSINT Bot - Help*

• Send phone numbers, UPI, Aadhaar, IP, or Telegram usernames directly in DM.
• Use commands in groups to search:
   /num <number> - Number lookup
   /upi <vpa> - UPI lookup
   /aadhar <id> - Aadhaar info
   /ip <ip> - IP lookup
   /tg <username> - Telegram user stats
   /pak <number> - Pakistan CNIC lookup
• Use /credits to check credits.
• Referral system rewards you credits.

For support, contact admin.
"""
        await query.edit_message_text(
            help_txt,
            reply_markup=InlineKeyboardMarkup(back_and_support()),
            parse_mode=ParseMode.MARKDOWN
        )
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
                f"""Package: {amt} credits → ₹{price}
Contact admin {GSUPPORT} after payment. Admin will add credits and commission to referrer.""",
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
        await query.edit_message_text(
    f"""Your referral link:
{link}

Share to earn credits!""",
    reply_markup=kb
        )
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
        await query.edit_message_text(
    f"""Total users: {total_users()}
Total credits: {total_credits()}""",
    reply_markup=admin_panel_kb(True)
        )

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
            await query.edit_message_text("Unauthorized", reply_markup=InlineKeyboardMarkup(back_and_support()))
            return
        await query.edit_message_text("Usage: /ban <user_id>", reply_markup=admin_panel_kb(True))
        return

    if data == "admin_unban":
        if not is_sudo(uid):
            await query.edit_message_text("Unauthorized", reply_markup=InlineKeyboardMarkup(back_and_support()))
            return
        await query.edit_message_text("Usage: /unban <user_id>", reply_markup=admin_panel_kb(True))
        return

    if data == "admin_protected":
        if uid != OWNER_ID:
            await query.edit_message_text("Only owner can view protected numbers.", reply_markup=admin_panel_kb(is_sudo(uid)))
            return
        rows = list_protected()
        if not rows:
            await query.edit_message_text("No protected numbers stored.", reply_markup=admin_panel_kb(True))
            return
        txt = "Protected numbers:\n" + "\n".join([f"{r[0]} — {r[1]}" for r in rows])
        await query.edit_message_text(txt, reply_markup=admin_panel_kb(True))
        return

    # buy_callhistory via button - instruct user to run /callhistory
    if data == "buy_callhistory":
        await query.edit_message_text(f"Call History costs {CALL_HISTORY_COST} credits. Use command: /callhistory <number>", reply_markup=InlineKeyboardMarkup(back_and_support("main_menu")))
        return

    # fallback - unknown
    await query.edit_message_text("Option expired or unknown. Returning to main menu.", reply_markup=main_menu_kb())


# -------------------------
# Commands & message handling
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    start_text = f"""👋 **Welcome {user.first_name} to DataTrace OSINT Bot**

This bot helps you search and trace details from our private OSINT database.

⚡ What you can do here:
 • Search phone numbers, UPI IDs, Aadhaar, IPs, Telegram IDs, CNIC (PK)
 • Use quick auto-search in DM
 • Get credit balance & referral rewards

🛠 How to Use
 • In Private Chat → just send any number, email, UPI, Aadhaar, or IP
 • In Groups → use commands like /num 9876543210

💡 No credits are deducted if result = Not Found."""
    await update.message.reply_text(start_text, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)

    # log start
    uid = user.id
    text = update.message.text or ""
    ref_id = None
    if text.startswith("/start") and "ref_" in text:
        try:
            rid = int(text.split("ref_")[1])
            if rid != uid:
                ref_id = rid
        except Exception:
            ref_id = None

    existed = get_user(uid)
    if not existed:
        create_user(uid, referrer_id=ref_id)
        # give referrer 1 credit on join
        if ref_id and get_user(ref_id):
            modify_credits(ref_id, FREE_CREDIT_ON_JOIN)

    # Check must-join channels
    def check_joined(user_id: int):
        for ch in MUST_JOIN_CHANNELS:
            try:
                mem = context.bot.get_chat_member(chat_id=f"@{ch}", user_id=user_id)
                if mem.status in ("left", "kicked"):
                    return False
            except Exception:
                return False
        return True

    joined = check_joined(uid)
    if joined:
        set_joined(uid, 1)
    else:
        set_joined(uid, 0)

    # Optionally, you can send join channel buttons here if not joined, but per spec it's omitted now

    try:
        context.bot.send_message(LOG_START_GROUP, f"/start by {uid} joined={joined} ref={ref_id}")
    except Exception:
        pass


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """ℹ️ *DataTrace OSINT Bot - Help*

• Send phone numbers, UPI, Aadhaar, IP, or Telegram usernames directly in DM.
• Use commands in groups to search:
   /num <number> - Number lookup
   /upi <vpa> - UPI lookup
   /aadhar <id> - Aadhaar info
   /ip <ip> - IP lookup
   /tg <username> - Telegram user stats
   /pak <number> - Pakistan CNIC lookup
• Use /credits to check credits.
• Referral system rewards you credits.

For support, contact admin.
"""
    await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(back_and_support()), parse_mode=ParseMode.MARKDOWN)

async def credits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /credits command. Replies with the user's current credit balance.
    """
    uid = update.effective_user.id
    user = get_user(uid)
    credits = user[1] if user else 0

    reply_text = (
        f"Your credits: {credits}\n"
        f"Earn by referrals or contact {GSUPPORT}."
    )

    await update.message.reply_text(
        reply_text,
        reply_markup=InlineKeyboardMarkup(back_and_support())
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    await update.message.reply_text(
        f"Total users: {total_users()}\nTotal credits: {total_credits()}",
        reply_markup=InlineKeyboardMarkup(back_and_support())
    )

async def sudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "Sudo IDs:\n" + "\n".join(str(s) for s in SUDO_IDS),
        reply_markup=InlineKeyboardMarkup(back_and_support())
    )


async def addcredits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    try:
        parts = update.message.text.split()
        target = int(parts[1]); amount = int(parts[2])
    except Exception:
        await update.message.reply_text("Usage: /addcredits <user_id> <amount>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    if not get_user(target):
        await update.message.reply_text("User not found. They must /start first.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    modify_credits(target, amount)
    # commission: if target has referrer, give them 30% of amount as credits
    t = get_user(target)
    ref = t[2]
    if ref and get_user(ref):
        commission = int(amount * REFERRAL_COMMISSION_RATIO)
        if commission > 0:
            modify_credits(ref, commission)
    await update.message.reply_text(f"Added {amount} credits to {target}.", reply_markup=InlineKeyboardMarkup(back_and_support()))


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    try:
        target = int(update.message.text.split()[1])
    except Exception:
        await update.message.reply_text("Usage: /ban <user_id>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    ban_user(target)
    await update.message.reply_text(f"Banned {target}.", reply_markup=InlineKeyboardMarkup(back_and_support()))


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    try:
        target = int(update.message.text.split()[1])
    except Exception:
        await update.message.reply_text("Usage: /unban <user_id>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    unban_user(target)
    await update.message.reply_text(f"Unbanned {target}.", reply_markup=InlineKeyboardMarkup(back_and_support()))


async def gcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sudo(uid):
        await update.message.reply_text("Unauthorized.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    try:
        msg = update.message.text.split(" ", 1)[1]
    except Exception:
        await update.message.reply_text("Usage: /gcast <message>", reply_markup=InlineKeyboardMarkup(back_and_support()))
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
    await update.message.reply_text(f"Broadcast sent to {sent} users.", reply_markup=InlineKeyboardMarkup(back_and_support()))


async def callhistory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        num = normalize(context.args[0])
    except (IndexError, AttributeError):
        await update.message.reply_text("Usage: /callhistory <number>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    if is_blacklisted(num):
        await update.message.reply_text("This number is blacklisted.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # Only deduct credits if API result is successful
    user = get_user(uid)
    if not is_sudo(uid):
        if not user or user[1] < CALL_HISTORY_COST:
            await update.message.reply_text(
                f"Insufficient credits. Call History costs {CALL_HISTORY_COST} credits.",
                reply_markup=InlineKeyboardMarkup(back_and_support())
            )
            return

    api = API_CALL_HISTORY.format(num=num)
    data = fetch_api(api)
    if not data:
        await update.message.reply_text(
            "API error or no data found. Please try again later.",
            reply_markup=InlineKeyboardMarkup(back_and_support())
        )
        return

    # Only deduct credits after successful API response
    if not is_sudo(uid):
        modify_credits(uid, -CALL_HISTORY_COST)

    pretty = "📝 Call History Result:\n\n" + json.dumps(data, indent=2)
    await update.message.reply_text(pretty, reply_markup=InlineKeyboardMarkup(back_and_support()))
    try:
        context.bot.send_message(LOG_SEARCH_GROUP, f"{uid} requested callhistory for {num}")
    except Exception as e:
        logger.warning(f"Failed to log callhistory search: {e}")


# API command wrappers
async def upi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        vpa = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /upi <vpa>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_UPI.format(upi=vpa))
    out = fmt_upi(data if data else {})
    await update.message.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))


async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ip = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /ip <ip>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_IP.format(ip=ip))
    out = fmt_ip(data if data else {})
    await update.message.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))


async def num_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /num <number>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    if is_blacklisted(num):
        await update.message.reply_text("Blacklisted.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_NUM_INFO.format(term=num))
    out = fmt_num(data if data else {})
    await update.message.reply_text("📱 Number Search Result\n" + out, reply_markup=InlineKeyboardMarkup(back_and_support()))
    try:
        context.bot.send_message(LOG_SEARCH_GROUP, f"/num by {update.effective_user.id} -> {num}")
    except Exception:
        pass


async def pak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /pak <number>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    if is_blacklisted(num):
        await update.message.reply_text("Blacklisted.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_PAK.format(num=num))
    out = fmt_pak(data if data else {})
    await update.message.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))
    try:
        context.bot.send_message(LOG_SEARCH_GROUP, f"/pak by {update.effective_user.id} -> {num}")
    except Exception:
        pass


async def aadhar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        aid = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /aadhar <aadhaar>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_AADHAR_FAMILY.format(id=aid))
    out = fmt_aadhar_family(data if data else {})
    await update.message.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))


async def tg_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = context.args[0]
    except Exception:
        await update.message.reply_text("Usage: /tg <username_or_id>", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    data = fetch_api(API_TG_USER.format(user=user))
    out = fmt_tg_user(data if data else {})
    await update.message.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))


# Generic text handler (DM or group) — smart routing
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    text = (msg.text or "").strip()

    # banned?
    u = get_user(uid)
    if u and u[3] == 1:
        await msg.reply_text("You are banned.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # must-join check
    def check_joined(user_id: int):
        for ch in MUST_JOIN_CHANNELS:
            try:
                mem = context.bot.get_chat_member(chat_id=f"@{ch}", user_id=user_id)
                if mem.status in ("left", "kicked"):
                    return False
            except Exception:
                return False
        return True
    joined = check_joined(uid)
    if not joined:
        await msg.reply_text("You must join required channels first.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # DM free searches logic
    if msg.chat.type == "private" and not is_sudo(uid):
        if not u:
            create_user(uid)
            u = get_user(uid)
        if u[5] < FREE_SEARCHES_DM:
            increment_free_searches(uid)
        else:
            if u[1] <= 0:
                await msg.reply_text("Free searches exhausted. Refer or buy credits.", reply_markup=InlineKeyboardMarkup(back_and_support()))
                return

    # If looks like a number/UPI/AADHAR/IP -> attempt auto-detect
    s = normalize(text)
    # blacklist/protected check
    if is_blacklisted(s):
        await msg.reply_text("This number is blacklisted.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return
    if is_protected(s) and uid != OWNER_ID:
        await msg.reply_text("This number is protected.", reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # Detect UPI (contains '@')
    if "@" in s and not s.startswith("+"):
        data = fetch_api(API_UPI.format(upi=s))
        await msg.reply_text(fmt_upi(data if data else {}), reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # IP detection: if contains '.' and looks like ip
    if "." in s and any(c.isdigit() for c in s):
        data = fetch_api(API_IP.format(ip=s))
        await msg.reply_text(fmt_ip(data if data else {}), reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # Aadhaar/id detection: numeric and length ~12
    if s.isdigit() and len(s) >= 12:
        # try aadhaar family first
        data = fetch_api(API_AADHAR_FAMILY.format(id=s))
        out = fmt_aadhar_family(data if data else {})
        await msg.reply_text(out, reply_markup=InlineKeyboardMarkup(back_and_support()))
        return

    # Phone detection: +92 or +91 or plain 10 digits
        # Phone detection: +92 or +91 or plain 10 digits
    if s.startswith("+92") or (s.startswith("92") and len(s) >= 11):
        data = fetch_api(API_PAK.format(num=s))
        await msg.reply_text("🇵🇰 Pakistan Number Search Result\n" + (fmt_pak(data if data else {})), reply_markup=InlineKeyboardMarkup(back_and_support()))
        try:
            context.bot.send_message(LOG_SEARCH_GROUP, f"Search: {uid} PAK {s}")
        except Exception:
            pass
        return
    if s.startswith("+91") or (s.isdigit() and len(s) in (10,11)):
        data = fetch_api(API_NUM_INFO.format(term=s))
        await msg.reply_text("📱 Number Search Result\n" + (fmt_num(data if data else {})), reply_markup=InlineKeyboardMarkup(back_and_support()))
        try:
            context.bot.send_message(LOG_SEARCH_GROUP, f"Search: {uid} IN {s}")
        except Exception:
            pass
        return

    # If none matched
    await msg.reply_text("Invalid/unknown input. Use /help or menu.", reply_markup=InlineKeyboardMarkup(back_and_support()))
    

# Unknown commands
async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /help", reply_markup=InlineKeyboardMarkup(back_and_support()))


# -------------------------
# Run
# -------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("credits", credits_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("sudo", sudo_cmd))
    app.add_handler(CommandHandler("addcredits", addcredits_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("gcast", gcast_cmd))
    app.add_handler(CommandHandler("callhistory", callhistory_cmd))
    app.add_handler(CommandHandler("upi", upi_cmd))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CommandHandler("num", num_cmd))
    app.add_handler(CommandHandler("pak", pak_cmd))
    app.add_handler(CommandHandler("aadhar", aadhar_cmd))
    app.add_handler(CommandHandler("tg", tg_cmd))

    # Callbacks & messages
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))

    logger.info("Bot started")
    app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
