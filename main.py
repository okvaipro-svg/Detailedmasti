"""
DataTraceOSINT Telegram Bot
Full-featured bot implementing:
- Multiple OSINT lookups via external APIs
- Referral & credits system
- Admin panel (sudo list, add credits, ban/unban, confirm purchases)
- Group behavior: replies only when mentioned, command given, or number posted and bot mentioned
- Join-to-use verification for required channels
- Logging of /start and every search to configured channels
- Protected and blacklisted numbers handling
- Inline buttons, callbacks, and purchase workflow (admin-confirmed)

Requirements:
- Python 3.10+
- python-telegram-bot v20+ (async)
- aiosqlite
- aiohttp
Install:
pip install python-telegram-bot==20.5 aiosqlite aiohttp

Configuration:
Set the following environment variables or fill DEFAULTS below:
- BOT_TOKEN
- LOG_START_CHANNEL (e.g. -1002765060940)
- LOG_SEARCH_CHANNEL (e.g. -1003066524164)
- REQUIRED_CHANNELS (comma-separated channel usernames or IDs)
- OWNER_ID (owner telegram numeric id)
- SUDO_IDS (comma-separated numeric IDs)
"""

import os
import re
import json
import logging
import asyncio
from typing import Optional, Tuple

import aiohttp
import aiosqlite
from datetime import datetime

from telegram import (
    __version__ as ptb_version,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    MessageEntity,
    ChatMember,
    ChatMemberUpdated,
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

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8219144171:AAH3HZPZvvtohlxOkTP2jJVDuEAaAllyzdU")
DB_PATH = os.getenv("DB_PATH", "datatrace.db")

# Logging channels
LOG_START_CHANNEL = int(os.getenv("LOG_START_CHANNEL", "-1002765060940"))
LOG_SEARCH_CHANNEL = int(os.getenv("LOG_SEARCH_CHANNEL", "-1003066524164"))

# Required channels to join (user must be a member), can be ids or @usernames (without @)
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "DataTraceUpdates,DataTraceOSINTSupport")
REQUIRED_CHANNELS = [c.strip() for c in REQUIRED_CHANNELS.split(",") if c.strip()]

# Admins and owner
OWNER_ID = int(os.getenv("OWNER_ID", "7924074157"))
SUDO_IDS = [int(x) for x in os.getenv("SUDO_IDS", "7924074157,5294360309,7905267752").split(",")]

# Protected and blacklisted numbers (can be prefilled here or managed via admin panel)
DEFAULT_PROTECTED = {"+919876543210"}  # sample placeholder (owner-only visible)
DEFAULT_BLACKLIST = {"+917724814462"}

# Costs
COST_PER_SEARCH = 1  # credits per regular search
COST_CALL_HISTORY = 600  # credits for call history paid API
FREE_DM_SEARCHES = 2  # in private, first N searches free before requiring refer/buy

# Branding & Admin contact
BRANDING_FOOTER = (
    "\n\n—\nPowered by DataTrace\nJoin: http://t.me/DataTraceUpdates\nSupport: http://t.me/DataTraceOSINTSupport\n"
    "Contact Admin: @DataTraceSupport"
)

# APIs
API_UPI = "https://upi-info.vercel.app/api/upi?upi_id={upi}&key=456"
API_NUM = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={num}"
API_PAK = "https://pak-num-api.vercel.app/search?number={num}"
API_AADHAR = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={idnum}"
API_AADHAR_FAMILY = "https://family-members-n5um.vercel.app/fetch?aadhaar={id_number}&key=paidchx"
API_IP = "https://karmali.serv00.net/ip_api.php?ip={ip}"
API_TGUSER = "https://tg-info-neon.vercel.app/user-details?user={user}"
API_CALL_HISTORY = "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
PHONE_PATTERN = re.compile(r"(?:\+?)(?:91|92)?\d{7,12}")  # loose phone detection

def fmt_dt(ts: Optional[str]) -> str:
    if not ts:
        return "(Not Available)"
    try:
        # Try parse iso
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts

def format_error(msg: str) -> str:
    return f"❌ Error: {msg}\n{BRANDING_FOOTER}"

def branding_footer() -> str:
    return BRANDING_FOOTER

# ---------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    credits INTEGER DEFAULT 0,
    free_searches INTEGER DEFAULT ?,
    referred_by INTEGER,
    joined_at TEXT,
    is_admin INTEGER DEFAULT 0,
    is_sudo INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer INTEGER,
    referred INTEGER,
    at TEXT
);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    query TEXT,
    api_used TEXT,
    cost INTEGER,
    at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount INTEGER,
    note TEXT,
    at TEXT
);

CREATE TABLE IF NOT EXISTS protected_numbers (
    number TEXT PRIMARY KEY,
    added_by INTEGER,
    at TEXT
);

CREATE TABLE IF NOT EXISTS blacklist_numbers (
    number TEXT PRIMARY KEY,
    added_by INTEGER,
    at TEXT
);
"""

async def init_db():
    db = await aiosqlite.connect(DB_PATH)
    # Parameterize free search default
    await db.executescript(CREATE_TABLES_SQL.replace("?", str(FREE_DM_SEARCHES)))
    await db.commit()

    # Ensure owner & sudos exist
    async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (OWNER_ID,)) as cur:
        r = await cur.fetchone()
    if not r:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, credits, free_searches, joined_at, is_admin, is_sudo) VALUES (?, ?, ?, ?, ?, ?)",
            (OWNER_ID, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat(), 0, 1),
        )
    for sid in SUDO_IDS:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, credits, free_searches, joined_at, is_admin, is_sudo) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat(), 1 if sid != OWNER_ID else 1, 1),
        )
    await db.commit()
    await db.close()

# DB helper functions
async def get_user_record(user_id: int) -> dict:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        # create default
        await db.execute(
            "INSERT INTO users (user_id, credits, free_searches, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat()),
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur2:
            row = await cur2.fetchone()
    await db.close()
    return dict(row)

async def update_user_credits(user_id: int, delta: int, note: str = ""):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (delta, user_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note, at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "credit_change", delta, note, datetime.utcnow().isoformat())
    )
    await db.commit()
    await db.close()

async def set_user_field(user_id: int, field: str, value):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    await db.commit()
    await db.close()

async def add_referral(referrer: int, referred: int):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("INSERT INTO referrals (referrer, referred, at) VALUES (?, ?, ?)",
                     (referrer, referred, datetime.utcnow().isoformat()))
    await db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer, referred))
    await db.commit()
    await db.close()

async def record_search(user_id: int, query: str, api_used: str, cost: int):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("INSERT INTO searches (user_id, query, api_used, cost, at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, query, api_used, cost, datetime.utcnow().isoformat()))
    await db.commit()
    await db.close()

async def add_protected_number(number: str, added_by: int):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("INSERT OR IGNORE INTO protected_numbers (number, added_by, at) VALUES (?, ?, ?)",
                     (number, added_by, datetime.utcnow().isoformat()))
    await db.commit()
    await db.close()

async def add_blacklist_number(number: str, added_by: int):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("INSERT OR IGNORE INTO blacklist_numbers (number, added_by, at) VALUES (?, ?, ?)",
                     (number, added_by, datetime.utcnow().isoformat()))
    await db.commit()
    await db.close()

async def is_protected_number(number: str) -> bool:
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT number FROM protected_numbers WHERE number = ?", (number,)) as cur:
        r = await cur.fetchone()
    await db.close()
    return r is not None

async def is_blacklisted_number(number: str) -> bool:
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT number FROM blacklist_numbers WHERE number = ?", (number,)) as cur:
        r = await cur.fetchone()
    await db.close()
    return r is not None

# ---------------------------------------------------------------------
# API wrappers & formatters
# ---------------------------------------------------------------------
async def fetch_json(session: aiohttp.ClientSession, url: str, timeout=15):
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}"}
            data = await resp.json(content_type=None)
            return data
    except Exception as e:
        return {"error": str(e)}

async def api_upi_lookup(session, upi_id: str) -> str:
    url = API_UPI.format(upi=upi_id)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"UPI API error: {data['error']}")
    # Example formatting based on provided example
    bank_raw = data.get("bank_details_raw", {})
    vpa = data.get("vpa_details", {})
    lines = ["🏦 *BANK DETAILS*"]
    for k in ["ADDRESS", "BANK", "BANKCODE", "BRANCH", "CENTRE", "CITY", "DISTRICT", "STATE", "IFSC", "MICR"]:
        if bank_raw.get(k):
            lines.append(f"*{k.title()}:* {bank_raw.get(k)}")
    for k in ["IMPS", "NEFT", "RTGS", "UPI"]:
        if bank_raw.get(k) is True:
            lines.append(f"*{k}:* ✅")
        elif bank_raw.get(k) is False:
            lines.append(f"*{k}:* ❌")
    lines.append("\n👤 *ACCOUNT HOLDER*")
    lines.append(f"*NAME:* {vpa.get('name','(Not Available)')}")
    lines.append(f"*VPA:* {vpa.get('vpa','(Not Available)')}")
    lines.append(f"{branding_footer()}")
    return "\n".join(lines)

async def api_ip_lookup(session, ip: str) -> str:
    url = API_IP.format(ip=ip)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"IP API error: {data['error']}")
    # expect keys per example
    lines = ["🗾 *IP INFO*"]
    for k_label, key in [
        ("IP", "ip"), ("Country", "country"), ("Country Code", "countryCode"),
        ("Region", "region"), ("Region Name", "regionName"), ("City", "city"),
        ("Zip", "zip"), ("Latitude", "lat"), ("Longitude", "lon"),
        ("Timezone", "timezone"), ("ISP", "isp"), ("Organization", "org"), ("AS", "as")
    ]:
        if key in data:
            lines.append(f"*{k_label}:* {data.get(key)}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_num_lookup(session, num: str) -> str:
    url = API_NUM.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Number API error: {data['error']}")
    # Data given as {"data":[{...}]}
    arr = data.get("data") or []
    if not arr:
        return format_error("No information found for the number.")
    d = arr[0]
    lines = ["📱 *NUMBER DETAILS*"]
    mapping = [
        ("MOBILE", "mobile"), ("ALT MOBILE", "alt"), ("NAME", "name"),
        ("FULL NAME", "fname"), ("ADDRESS", "address"), ("CIRCLE", "circle"), ("ID", "id")
    ]
    for label, key in mapping:
        val = d.get(key, "(Not Available)")
        if val:
            val = val.replace("!", ",") if isinstance(val, str) else val
        lines.append(f"*{label}:* {val}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_pak_lookup(session, num: str) -> str:
    url = API_PAK.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Pakistan API error: {data['error']}")
    results = data.get("results") or []
    if not results:
        return format_error("No Pakistan info found.")
    lines = ["🇵🇰 *PAKISTAN INFO*"]
    for idx, r in enumerate(results, start=1):
        lines.append(f"{idx}️⃣")
        lines.append(f"*NAME:* {r.get('Name','(Not Available)')}")
        lines.append(f"*CNIC:* {r.get('CNIC','(Not Available)')}")
        lines.append(f"*MOBILE:* {r.get('Mobile','(Not Available)')}")
        addr = r.get('Address') or "(Not Available)"
        lines.append(f"*ADDRESS:* {addr}")
        lines.append("---")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_aadhar_lookup(session, idnum: str) -> str:
    url = API_AADHAR.format(idnum=idnum)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Aadhar API error: {data['error']}")
    arr = data if isinstance(data, list) else (data.get("data") or [])
    if not arr:
        return format_error("No Aadhar info found.")
    # reuse formatting like number
    lines = ["🆔 *AADHAR INFO*"]
    for d in arr:
        lines.append(f"*NAME:* {d.get('name','(Not Available)')}")
        lines.append(f"*MOBILE:* {d.get('mobile','(Not Available)')}")
        lines.append(f"*FATHER:* {d.get('father_name','(Not Available)')}")
        addr = d.get('address','(Not Available)').replace("!", ",")
        lines.append(f"*ADDRESS:* {addr}")
        lines.append("---")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_aadhar_family(session, idnum: str) -> str:
    url = API_AADHAR_FAMILY.format(id_number=idnum)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Aadhar family API error: {data['error']}")
    mdlist = data.get("memberDetailsList") or []
    if not mdlist:
        return format_error("No family info found.")
    lines = ["🆔 *AADHAR FAMILY INFO*"]
    lines.append(f"*RC ID:* {data.get('rcId', '(Not Available)')}")
    lines.append(f"*SCHEME:* {data.get('schemeId', '(Not Available)')} ({data.get('schemeName','')})")
    lines.append(f"*DISTRICT:* {data.get('homeDistName','(Not Available)')}")
    lines.append(f"*STATE:* {data.get('homeStateName','(Not Available)')}")
    lines.append("\n👨‍👩‍👧 *FAMILY MEMBERS:*")
    for idx, m in enumerate(mdlist, start=1):
        lines.append(f"{idx}️⃣ {m.get('memberName','(Not Available)')} — {m.get('releationship_name','(Not Available)')}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_tguser_lookup(session, username_or_id: str) -> str:
    url = API_TGUSER.format(user=username_or_id)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"TG user API error: {data['error']}")
    d = data.get("data") or {}
    if not d:
        return format_error("No Telegram user data found.")
    lines = ["👤 *TELEGRAM USER STATS*"]
    lines.append(f"*NAME:* {d.get('first_name','')}{' ' + (d.get('last_name') or '')}")
    lines.append(f"*USER ID:* {d.get('id','(Not Available)')}")
    lines.append(f"*IS BOT:* {'✅' if d.get('is_bot') else '❌'}")
    lines.append(f"*ACTIVE:* {'✅' if d.get('is_active') else '❌'}")
    lines.append("\n📊 *STATS*")
    lines.append(f"*TOTAL GROUPS:* {d.get('total_groups','0')}")
    lines.append(f"*ADMIN IN GROUPS:* {d.get('adm_in_groups','0')}")
    lines.append(f"*TOTAL MESSAGES:* {d.get('total_msg_count','0')}")
    lines.append(f"*MESSAGES IN GROUPS:* {d.get('msg_in_groups_count','0')}")
    lines.append(f"*FIRST MSG DATE:* {fmt_dt(d.get('first_msg_date'))}")
    lines.append(f"*LAST MSG DATE:* {fmt_dt(d.get('last_msg_date'))}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_call_history(session, num: str) -> str:
    url = API_CALL_HISTORY.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Call history API error: {data['error']}")
    # No example given; print something generic
    lines = ["📞 *CALL HISTORY*"]
    lines.append(f"Results for: {num}")
    # If data contains list of calls
    calls = data.get("calls") if isinstance(data, dict) else None
    if calls:
        for c in calls:
            lines.append(f"- {c.get('date','?')} | {c.get('direction','?')} | {c.get('duration','?')}s")
    else:
        # fallback stringify keys
        lines.append("*Raw Result Summary:*")
        lines.append(" (Data fetched from API)")
    lines.append(branding_footer())
    return "\n".join(lines)

# ---------------------------------------------------------------------
# Bot behaviors & command handlers
# ---------------------------------------------------------------------
class DataTraceBot:
    def __init__(self, token: str):
        self.app = ApplicationBuilder().token(token).build()
        # register handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CommandHandler("buycredits", self.buycredits_cmd))
        self.app.add_handler(CommandHandler("stats", self.stats_cmd))
        self.app.add_handler(CommandHandler("admin", self.admin_cmd))
        # API commands
        self.app.add_handler(CommandHandler("num", self.cmd_num))
        self.app.add_handler(CommandHandler("pak", self.cmd_pak))
        self.app.add_handler(CommandHandler("upi", self.cmd_upi))
        self.app.add_handler(CommandHandler("aadhar", self.cmd_aadhar))
        self.app.add_handler(CommandHandler("aadhar2fam", self.cmd_aadhar_fam))
        self.app.add_handler(CommandHandler("ip", self.cmd_ip))
        self.app.add_handler(CommandHandler("tguser", self.cmd_tguser))
        self.app.add_handler(CommandHandler("callhistory", self.cmd_callhistory))
        self.app.add_handler(CallbackQueryHandler(self.cb_handler))
        # Messages
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.message_handler))
        # to ensure bot only replies in groups when mentioned, we'll have logic in message_handler
        # start-up tasks
        self.session = aiohttp.ClientSession()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        args = context.args or []
        payload = args[0] if args else None
        await init_db()  # ensure DB ready
        # Log start
        try:
            await self.app.bot.send_message(LOG_START_CHANNEL, f"/start by {user.id} @{user.username or ''} ({user.full_name})")
        except Exception:
            pass

        # create user record / update names
        db_user = await get_user_record(user.id)
        # update names
        if user.username or user.first_name:
            await set_user_field(user.id, "username", user.username or "")
            await set_user_field(user.id, "first_name", user.first_name or "")

        # check required channels membership
        not_member = []
        for ch in REQUIRED_CHANNELS:
            try:
                chat_id = ch if ch.startswith("-100") or ch.startswith("@") else ("@" + ch if not ch.startswith("@") else ch)
                member = await self.app.bot.get_chat_member(chat_id, user.id)
                if member.status in ("left", "kicked"):
                    not_member.append(ch)
            except Exception:
                not_member.append(ch)
        if not_member:
            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Join Updates", url="http://t.me/DataTraceUpdates"),
                     InlineKeyboardButton("Join Support", url="http://t.me/DataTraceOSINTSupport")],
                    [InlineKeyboardButton("I Joined ✅", callback_data="verify_join")]
                ]
            )
            await update.message.reply_text(
                "Welcome!\nBefore you can use the bot, please join the required channels:\n\n"
                "• http://t.me/DataTraceUpdates\n• http://t.me/DataTraceOSINTSupport\n\n"
                "Press 'I Joined' after joining.",
                reply_markup=keyboard
            )
            return

        # handle referral payload
        if payload:
            # expecting numeric referrer id
            try:
                ref_id = int(payload)
                if ref_id != user.id:
                    # grant 1 free credit to the referred user
                    # and record referral
                    await update_user_credits(user.id, 1, note="Referral join bonus")
                    await add_referral(ref_id, user.id)
                    await update.message.reply_text("✅ You received 1 free credit for joining via referral!\nUse /help to see commands.")
                    # notify referrer
                    try:
                        await self.app.bot.send_message(ref_id, f"🎉 Your referral @{user.username or user.id} joined. You will receive 30% credits when they buy.")
                    except Exception:
                        pass
                else:
                    await update.message.reply_text("Welcome! Use /help to see commands.")
            except Exception:
                await update.message.reply_text("Welcome! Use /help to see commands.")
        else:
            await update.message.reply_text("Welcome! Use /help to see commands.")

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        text = (
            "*Main Commands*\n"
            "/num <number or +91...> - Lookup Indian number\n"
            "/pak <number or +92...> - Pakistan number\n"
            "/upi <vpa@bank> - UPI info\n"
            "/aadhar <id> - Aadhar lookup\n"
            "/aadhar2fam <id> - Aadhar family lookup\n"
            "/ip <ip> - IP lookup\n"
            "/tguser <username_or_id> - Telegram user stats\n"
            "/callhistory <number> - Paid: call history (600 credits)\n"
            "/buycredits - Buy credits (admin will confirm)\n"
            "/stats - (sudos only) bot stats\n\n"
            "Bot replies in groups only when mentioned, or when you use a command, or when you mention a number while tagging the bot.\n\n"
            f"{branding_footer()}"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Main Commands", callback_data="show_commands")],
                [InlineKeyboardButton("Buy Credits", callback_data="buy_credits_cb"),
                 InlineKeyboardButton("Contact Admin", url="http://t.me/DataTraceSupport")]
            ]
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    async def buycredits_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("100 — ₹50", callback_data="buy_100"),
                 InlineKeyboardButton("200 — ₹100", callback_data="buy_200")],
                [InlineKeyboardButton("500 — ₹250", callback_data="buy_500"),
                 InlineKeyboardButton("1000 — ₹450", callback_data="buy_1000")],
                [InlineKeyboardButton("Contact Admin", url="http://t.me/DataTraceSupport")]
            ]
        )
        await update.message.reply_text("Choose a pack. After payment, press 'I Paid' -> admin will confirm and credits will be added.", reply_markup=kb)

    async def stats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in SUDO_IDS:
            await update.message.reply_text("Unauthorized.")
            return
        # return summary stats
        db = await aiosqlite.connect(DB_PATH)
        async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
            r = await cur.fetchone()
        total_users = r[0] if r else 0
        async with db.execute("SELECT COUNT(*) as c FROM searches") as cur:
            r2 = await cur.fetchone()
        total_searches = r2[0] if r2 else 0
        await db.close()
        await update.message.reply_text(f"Users: {total_users}\nTotal searches: {total_searches}")

    async def admin_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in SUDO_IDS:
            await update.message.reply_text("You are not an admin.")
            return
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Add Credits", callback_data="admin_add_credits")],
                [InlineKeyboardButton("Ban User", callback_data="admin_ban_user"),
                 InlineKeyboardButton("Unban User", callback_data="admin_unban_user")],
                [InlineKeyboardButton("Add Protected Number", callback_data="admin_add_prot"),
                 InlineKeyboardButton("Add Blacklist Number", callback_data="admin_add_black")]
            ]
        )
        await update.message.reply_text("Admin panel:", reply_markup=kb)

    # Command handlers mapping to central lookup
    async def cmd_num(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "num")

    async def cmd_pak(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "pak")

    async def cmd_upi(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "upi")

    async def cmd_aadhar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "aadhar")

    async def cmd_aadhar_fam(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "aadhar2fam")

    async def cmd_ip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "ip")

    async def cmd_tguser(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "tguser")

    async def cmd_callhistory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.handle_lookup_command(update, context, "callhistory")

    async def handle_lookup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, lookup_type: str):
        user = update.effective_user
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: /{cmd} <query>".format(cmd=lookup_type))
            return
        query = " ".join(args).strip()
        # handle numbers with/without +91 etc.
        await self.process_lookup_request(user.id, query, lookup_type, update)

    # Central lookup processing with credits and checks
    async def process_lookup_request(self, user_id: int, query: str, lookup_type: str, update_obj):
        # ensure DB init
        await init_db()
        userrec = await get_user_record(user_id)
        # check ban
        if userrec.get("is_banned"):
            await update_obj.message.reply_text("You are banned from using this bot.")
            return
        # check joins
        not_member = []
        for ch in REQUIRED_CHANNELS:
            try:
                chat_id = ch if ch.startswith("-100") or ch.startswith("@") else ("@" + ch)
                mem = await self.app.bot.get_chat_member(chat_id, user_id)
                if mem.status in ("left", "kicked"):
                    not_member.append(ch)
            except Exception:
                not_member.append(ch)
        if not_member:
            await update_obj.message.reply_text(
                "You must join required channels first:\nhttp://t.me/DataTraceUpdates\nhttp://t.me/DataTraceOSINTSupport")
            return

        # Determine cost
        cost = COST_CALL_HISTORY if lookup_type == "callhistory" else COST_PER_SEARCH

        # Protected / blacklist checks for number-based lookups
        target_number = None
        if lookup_type in ("num", "pak", "callhistory"):
            # normalize number
            target_number = re.sub(r"[^\d+]", "", query)
            if not target_number.startswith("+"):
                # try to normalize to +91 or leave as-is based on prefix
                if target_number.startswith("91") or len(target_number) == 10:
                    target_number = "+" + target_number if not target_number.startswith("+") else target_number
            # check blacklist
            if await is_blacklisted_number(target_number):
                await update_obj.message.reply_text("No results found.")  # silently return per requirement
                return
            # check protected
            if await is_protected_number(target_number):
                if user_id != OWNER_ID:
                    await update_obj.message.reply_text("No results found.")  # hide existence
                    return

        # Check credits or free searches
        if userrec["credits"] < cost:
            # If in private chat, they have free searches
            if update_obj.effective_chat.type == "private" and userrec["free_searches"] > 0:
                # allow, decrement free_searches
                await set_user_field(user_id, "free_searches", userrec["free_searches"] - 1)
                cost_to_deduct = 0
            else:
                # Not enough credits: force refer or buy
                kb = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Refer & Get 1 Credit", url=f"https://t.me/{(await self.app.bot.get_me()).username}?start={user_id}")],
                        [InlineKeyboardButton("Buy Credits", callback_data="buy_credits_cb")]
                    ]
                )
                await update_obj.message.reply_text(
                    "You don't have enough credits.\nYou can get credits by referring friends or buying credits.",
                    reply_markup=kb
                )
                return
        else:
            cost_to_deduct = cost

        # Run the actual api lookup
        result_text = None
        async with aiohttp.ClientSession() as session:
            try:
                if lookup_type == "num":
                    result_text = await api_num_lookup(session, query)
                elif lookup_type == "pak":
                    result_text = await api_pak_lookup(session, query)
                elif lookup_type == "upi":
                    result_text = await api_upi_lookup(session, query)
                elif lookup_type == "aadhar":
                    result_text = await api_aadhar_lookup(session, query)
                elif lookup_type == "aadhar2fam":
                    result_text = await api_aadhar_family(session, query)
                elif lookup_type == "ip":
                    result_text = await api_ip_lookup(session, query)
                elif lookup_type == "tguser":
                    result_text = await api_tguser_lookup(session, query)
                elif lookup_type == "callhistory":
                    result_text = await api_call_history(session, query)
                else:
                    result_text = format_error("Unknown lookup type.")
            except Exception as e:
                logger.exception("API lookup failed")
                result_text = format_error(str(e))

        # Deduct credits if applicable
        if cost_to_deduct:
            await update_user_credits(user_id, -cost_to_deduct, note=f"Lookup {lookup_type} {query}")
        # record search log
        await record_search(user_id, query, lookup_type, cost_to_deduct or 0)
        # send result, with branding and contact
        header = f"🔎 *Result — {lookup_type.upper()}*\n"
        footer = f"\n\nContact Admin: @DataTraceSupport"
        try:
            await update_obj.message.reply_text(header + "\n" + result_text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # fallback plain
            await update_obj.message.reply_text(header + "\n" + (result_text if result_text else "No result"))

        # Log to search channel
        try:
            await self.app.bot.send_message(LOG_SEARCH_CHANNEL,
                                            f"Search by {user_id} — {lookup_type} — {query} — cost {cost_to_deduct or 0}")
        except Exception:
            pass

    # Message handler for group behavior & direct lookups
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        text = msg.text or ""

        # groups: respond only when mentioned, or command, or if bot username in entities, or number present and bot mentioned
        if chat.type in ("group", "supergroup"):
            bot_username = (await self.app.bot.get_me()).username
            bot_mentioned = False
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == MessageEntity.MENTION:
                        ent_text = msg.text[ent.offset: ent.offset + ent.length]
                        if ent_text.lower().lstrip("@") == bot_username.lower():
                            bot_mentioned = True
            if not bot_mentioned:
                # If it's a command, bot will get it via CommandHandler already. For safety return.
                return

        # If contains phone-like pattern -> attempt number lookup
        phone_match = PHONE_PATTERN.search(text)
        if phone_match:
            num = phone_match.group(0)
            # decide pak or ind
            # if starts with 92 or +92 -> pak else num
            if num.startswith("+92") or num.startswith("92"):
                await self.process_lookup_request(user.id, num, "pak", update)
            else:
                # treat as Indian
                await self.process_lookup_request(user.id, num, "num", update)
            return

        # If text is a raw username/id with @ or digits and no command, maybe tguser lookup when private
        if chat.type == "private" and text.startswith("@"):
            await self.process_lookup_request(user.id, text.lstrip("@"), "tguser", update)
            return

    # CallbackQuery handler for inline buttons and admin actions
    async def cb_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user = query.from_user

        if data == "verify_join":
            # Re-check membership
            not_member = []
            for ch in REQUIRED_CHANNELS:
                try:
                    chat_id = ch if ch.startswith("-100") or ch.startswith("@") else ("@" + ch)
                    member = await self.app.bot.get_chat_member(chat_id, user.id)
                    if member.status in ("left", "kicked"):
                        not_member.append(ch)
                except Exception:
                    not_member.append(ch)
            if not_member:
                await query.edit_message_text("You still haven't joined all required channels.")
            else:
                await query.edit_message_text("Thank you! You can now use the bot.")
        elif data == "show_commands":
            # Show brief commands list
            await query.edit_message_text("See /help for all commands.")
        elif data.startswith("buy_"):
            pack = data.split("_")[1]
            mapping = {
                "100": (100, 50),
                "200": (200, 100),
                "500": (500, 250),
                "1000": (1000, 450)
            }
            if pack in mapping:
                credits, price = mapping[pack]
                # Create a pending purchase message to admins
                await self.app.bot.send_message(
                    LOG_SEARCH_CHANNEL,
                    f"Purchase request by {user.id} @{user.username or ''}: {credits} credits for ₹{price}. Confirm with /admin panel."
                )
                await query.message.reply_text(
                    f"Payment instructions:\nSend ₹{price} to UPI: example@upi\nAfter payment, press 'I Paid' (admin will confirm)."
                )
        elif data == "buy_credits_cb":
            await query.edit_message_text("Use /buycredits to view packs and instructions.")
        elif data == "admin_add_credits":
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            await query.edit_message_text("To add credits, reply to this message with: add <user_id> <amount>")
        elif data == "admin_ban_user":
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            await query.edit_message_text("Reply with: ban <user_id>")
        elif data == "admin_unban_user":
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            await query.edit_message_text("Reply with: unban <user_id>")
        elif data == "admin_add_prot":
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            await query.edit_message_text("Reply with: addprot <number>")
        elif data == "admin_add_black":
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            await query.edit_message_text("Reply with: addblack <number>")
        else:
            await query.edit_message_text("Unknown action.")

    async def run(self):
        logger.info("Starting bot...")
        await init_db()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("Bot started. Press Ctrl+C to stop.")
        await self.app.updater.idle()
        await self.session.close()


# ---------------------------------------------------------------------
# Entrypoint & basic admin text reply handling
# ---------------------------------------------------------------------
async def admin_text_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler listens for admin replies to perform add/ban actions
    user = update.effective_user
    text = update.effective_message.text or ""
    if user.id not in SUDO_IDS:
        return
    # commands: add <user_id> <amount>
    m = re.match(r"add\s+(\d+)\s+(\d+)", text, re.I)
    if m:
        uid = int(m.group(1)); amt = int(m.group(2))
        await update.message.reply_text(f"Adding {amt} credits to {uid}...")
        await update_user_credits(uid, amt, note=f"Admin manual add by {user.id}")
        await update.message.reply_text("Done.")
        return
    m = re.match(r"ban\s+(\d+)", text, re.I)
    if m:
        uid = int(m.group(1))
        await set_user_field(uid, "is_banned", 1)
        await update.message.reply_text(f"Banned {uid}.")
        return
    m = re.match(r"unban\s+(\d+)", text, re.I)
    if m:
        uid = int(m.group(1))
        await set_user_field(uid, "is_banned", 0)
        await update.message.reply_text(f"Unbanned {uid}.")
        return
    m = re.match(r"addprot\s+(\+?\d+)", text, re.I)
    if m:
        num = m.group(1)
        await add_protected_number(num, user.id)
        await update.message.reply_text(f"Added protected number {num}.")
        return
    m = re.match(r"addblack\s+(\+?\d+)", text, re.I)
    if m:
        num = m.group(1)
        await add_blacklist_number(num, user.id)
        await update.message.reply_text(f"Added blacklist number {num}.")
        return

def main():
    bot = DataTraceBot(BOT_TOKEN)
    # register admin_text_listener to application (low priority)
    bot.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), admin_text_listener))
    # run
    asyncio.run(bot.run())

if __name__ == "__main__":
    main()
