#!/usr/bin/env python3
"""
Robust DataTrace OSINT Telegram Bot - main.py

Usage:
- Set BOT_TOKEN as an environment variable before running:
    export BOT_TOKEN="123:ABC..."
  (Do NOT hardcode tokens into files in public repos; rotate token if it was shared.)
- Install dependencies:
    pip install python-telegram-bot==20.5 aiosqlite aiohttp

This file implements:
- Safe DB initialization and migrations (adds missing columns)
- Aiohttp session created in async context (no DeprecationWarning)
- Handlers for common lookups (num, pak, upi, aadhar, aadhar2fam, ip, tguser, callhistory)
- Credits, free searches, referral handling, protected/blacklist numbers
- Group behavior: bot responds only when mentioned (or command)
- Admin panel callbacks and lightweight admin text commands
- Search/start logging to configured channels

Configure the constants below as needed.
"""

import os
import re
import logging
import asyncio
from datetime import datetime
from typing import Optional, Any, Dict, List

import aiosqlite
import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
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

# ----------------------------
# Configuration (edit safely)
# ----------------------------
DB_PATH = os.getenv("DB_PATH", "datatrace.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8219144171:AAH3HZPZvvtohlxOkTP2jJVDuEAaAllyzdU")  # must be set in environment
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable not set. Set it and re-run.")

# Logging channels (bot will try to send logs here if accessible)
LOG_START_CHANNEL = int(os.getenv("LOG_START_CHANNEL", "-1002765060940"))
LOG_SEARCH_CHANNEL = int(os.getenv("LOG_SEARCH_CHANNEL", "-1003066524164"))

# Required channels (usernames without @ or full chat IDs)
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "DataTraceUpdates,DataTraceOSINTSupport")
REQUIRED_CHANNELS = [c.strip() for c in REQUIRED_CHANNELS.split(",") if c.strip()]

OWNER_ID = int(os.getenv("OWNER_ID", "7924074157"))
SUDO_IDS = [int(x) for x in os.getenv("SUDO_IDS", "7924074157,5294360309,7905267752").split(",")]

FREE_DM_SEARCHES = int(os.getenv("FREE_DM_SEARCHES", "2"))
COST_PER_SEARCH = int(os.getenv("COST_PER_SEARCH", "1"))
COST_CALL_HISTORY = int(os.getenv("COST_CALL_HISTORY", "600"))

BRANDING_FOOTER = (
    "\n\n—\nPowered by DataTrace\nJoin: http://t.me/DataTraceUpdates\nSupport: http://t.me/DataTraceOSINTSupport\n"
    "Contact Admin: @DataTraceSupport"
)

# External API endpoints (as examples from provided earlier script)
API_UPI = "https://upi-info.vercel.app/api/upi?upi_id={upi}&key=456"
API_NUM = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={num}"
API_PAK = "https://pak-num-api.vercel.app/search?number={num}"
API_AADHAR = "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={idnum}"
API_AADHAR_FAMILY = "https://family-members-n5um.vercel.app/fetch?aadhaar={id_number}&key=paidchx"
API_IP = "https://karmali.serv00.net/ip_api.php?ip={ip}"
API_TGUSER = "https://tg-info-neon.vercel.app/user-details?user={user}"
API_CALL_HISTORY = "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"

# Regex to detect phone-like strings (loose)
PHONE_PATTERN = re.compile(r"(?:\+?)(?:91|92)?\d{7,12}")

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("datatrace_bot")

# ----------------------------
# DB: init + migrations + helpers
# ----------------------------
CREATE_TABLE_USERS = f"""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    credits INTEGER DEFAULT 0,
    free_searches INTEGER DEFAULT {FREE_DM_SEARCHES},
    referred_by INTEGER,
    joined_at TEXT,
    is_admin INTEGER DEFAULT 0,
    is_sudo INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0
);
"""

CREATE_TABLES_OTHER = """
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
    """
    Initialize DB and run simple migrations (add missing columns).
    Safe to call on every startup.
    """
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(CREATE_TABLE_USERS)
    await db.executescript(CREATE_TABLES_OTHER)
    await db.commit()

    # check columns in users and add if missing (future-proof migration)
    async with db.execute("PRAGMA table_info(users);") as cur:
        rows = await cur.fetchall()
    existing_cols = [r[1] for r in rows]  # second field is column name

    # Define all required columns and their default values/types for migration
    required_cols = {
        "credits": "INTEGER DEFAULT 0",
        "free_searches": f"INTEGER DEFAULT {FREE_DM_SEARCHES}",
        "referred_by": "INTEGER",
        "joined_at": "TEXT",
        "is_admin": "INTEGER DEFAULT 0",
        "is_sudo": "INTEGER DEFAULT 0",
        "is_banned": "INTEGER DEFAULT 0",
    }

    migrated = False
    for col, definition in required_cols.items():
        if col not in existing_cols:
            logger.info(f"Migration: adding '{col}' column to users")
            try:
                # SQLite ALTER TABLE ADD COLUMN
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition};")
                migrated = True
            except aiosqlite.OperationalError as e:
                # Handle case where column definition might be slightly wrong for an ALTER
                logger.error(f"Failed to add column {col}: {e}")
                pass

    if migrated:
        await db.commit()

    # Ensure owner and sudo records exist (uses all expected columns including joined_at)
    async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (OWNER_ID,)) as cur:
        if not await cur.fetchone():
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, credits, free_searches, joined_at, is_admin, is_sudo) VALUES (?, ?, ?, ?, ?, ?)",
                (OWNER_ID, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat(), 0, 1),
            )
    for sid in SUDO_IDS:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, credits, free_searches, joined_at, is_admin, is_sudo) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat(), 1, 1),
        )
    await db.commit()
    await db.close()

# DB helpers (using aiosqlite connections per function for safety)
async def get_user_record(user_id: int) -> Dict[str, Any]:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO users (user_id, credits, free_searches, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, 0, FREE_DM_SEARCHES, datetime.utcnow().isoformat())
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur2:
            row = await cur2.fetchone()
    await db.close()
    return dict(row)

async def set_user_field(user_id: int, field: str, value: Any):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    await db.commit()
    await db.close()

async def update_user_credits(user_id: int, delta: int, note: str = ""):
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (delta, user_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note, at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "credit_change", delta, note, datetime.utcnow().isoformat())
    )
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
    async with db.execute("SELECT 1 FROM protected_numbers WHERE number = ?", (number,)) as cur:
        r = await cur.fetchone()
    await db.close()
    return r is not None

async def is_blacklisted_number(number: str) -> bool:
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT 1 FROM blacklist_numbers WHERE number = ?", (number,)) as cur:
        r = await cur.fetchone()
    await db.close()
    return r is not None

async def add_referral(referrer_id: int, referred_id: int):
    """Records a referral if it doesn't already exist for this referred_id."""
    db = await aiosqlite.connect(DB_PATH)
    async with db.execute("SELECT 1 FROM referrals WHERE referred = ?", (referred_id,)) as cur:
        if await cur.fetchone():
            await db.close()
            return # Already referred

    await db.execute("INSERT INTO referrals (referrer, referred, at) VALUES (?, ?, ?)",
                     (referrer_id, referred_id, datetime.utcnow().isoformat()))
    # Give the referrer a credit bonus
    await update_user_credits(referrer_id, 1, note=f"Referral bonus for {referred_id}")
    await db.commit()
    await db.close()

# ----------------------------
# API helpers
# ----------------------------
async def fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 15) -> Any:
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}"}
            # some APIs may return text; try to parse JSON safely
            text = await resp.text()
            try:
                # Use content_type=None to force JSON parsing regardless of header
                return await resp.json(content_type=None)
            except Exception:
                # fallback: provide raw text
                return {"raw": text}
    except Exception as e:
        return {"error": str(e)}

def branding_footer() -> str:
    return BRANDING_FOOTER

def format_error(msg: str) -> str:
    return f"❌ Error: {msg}\n{branding_footer()}"

async def api_num_lookup(session: aiohttp.ClientSession, num: str) -> str:
    url = API_NUM.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Number API error: {data['error']}")
    arr = data.get("data") if isinstance(data, dict) else None
    if not arr:
        return format_error("No information found for the number.")
    d = arr[0] if isinstance(arr, list) and arr else arr
    lines = ["📱 *NUMBER DETAILS*"]
    mapping = [
        ("MOBILE", "mobile"), ("ALT MOBILE", "alt"), ("NAME", "name"),
        ("FULL NAME", "fname"), ("ADDRESS", "address"), ("CIRCLE", "circle"), ("ID", "id")
    ]
    for label, key in mapping:
        val = d.get(key) if isinstance(d, dict) else None
        if not val:
            val = "(Not Available)"
        lines.append(f"*{label}:* {val}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_pak_lookup(session: aiohttp.ClientSession, num: str) -> str:
    url = API_PAK.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Pakistan API error: {data['error']}")
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return format_error("No Pakistan info found.")
    lines = ["🇵🇰 *PAKISTAN INFO*"]
    for idx, r in enumerate(results, start=1):
        lines.append(f"{idx}️⃣")
        lines.append(f"*NAME:* {r.get('Name','(Not Available)')}")
        lines.append(f"*CNIC:* {r.get('CNIC','(Not Available)')}")
        lines.append(f"*MOBILE:* {r.get('Mobile','(Not Available)')}")
        lines.append(f"*ADDRESS:* {r.get('Address','(Not Available)')}")
        lines.append("---")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_upi_lookup(session: aiohttp.ClientSession, upi_id: str) -> str:
    url = API_UPI.format(upi=upi_id)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"UPI API error: {data['error']}")
    bank_raw = data.get("bank_details_raw", {}) if isinstance(data, dict) else {}
    vpa = data.get("vpa_details", {}) if isinstance(data, dict) else {}
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
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_aadhar_lookup(session: aiohttp.ClientSession, idnum: str) -> str:
    url = API_AADHAR.format(idnum=idnum)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Aadhar API error: {data['error']}")
    arr = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None)
    if not arr:
        return format_error("No Aadhar info found.")
    lines = ["🆔 *AADHAR INFO*"]
    for d in arr:
        lines.append(f"*NAME:* {d.get('name','(Not Available)')}")
        lines.append(f"*MOBILE:* {d.get('mobile','(Not Available)')}")
        lines.append(f"*FATHER:* {d.get('father_name','(Not Available)')}")
        lines.append(f"*ADDRESS:* {d.get('address','(Not Available)')}")
        lines.append("---")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_aadhar_family(session: aiohttp.ClientSession, idnum: str) -> str:
    url = API_AADHAR_FAMILY.format(id_number=idnum)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Aadhar family API error: {data['error']}")
    mdlist = data.get("memberDetailsList") if isinstance(data, dict) else None
    if not mdlist:
        return format_error("No family info found.")
    lines = ["🆔 *AADHAR FAMILY INFO*"]
    lines.append(f"*RC ID:* {data.get('rcId', '(Not Available)')}")
    lines.append(f"*SCHEME:* {data.get('schemeId', '(Not Available)')}")
    lines.append("\n👨‍👩‍👧 *FAMILY MEMBERS:*")
    for idx, m in enumerate(mdlist, start=1):
        lines.append(f"{idx}️⃣ {m.get('memberName','(Not Available)')} — {m.get('releationship_name','(Not Available)')}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_ip_lookup(session: aiohttp.ClientSession, ip: str) -> str:
    url = API_IP.format(ip=ip)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"IP API error: {data['error']}")
    lines = ["🗾 *IP INFO*"]
    for k_label, key in [
        ("IP", "ip"), ("Country", "country"), ("Region", "region"), ("City", "city"),
        ("Zip", "zip"), ("Latitude", "lat"), ("Longitude", "lon"), ("Timezone", "timezone"),
        ("ISP", "isp"), ("Organization", "org"), ("AS", "as")
    ]:
        if isinstance(data, dict) and data.get(key) is not None:
            lines.append(f"*{k_label}:* {data.get(key)}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_tguser_lookup(session: aiohttp.ClientSession, username_or_id: str) -> str:
    url = API_TGUSER.format(user=username_or_id)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"TG user API error: {data['error']}")
    d = data.get("data") if isinstance(data, dict) else None
    if not d:
        return format_error("No Telegram user data found.")
    lines = ["👤 *TELEGRAM USER STATS*"]
    lines.append(f"*NAME:* {d.get('first_name','')}{' ' + (d.get('last_name') or '') if d.get('last_name') else ''}")
    lines.append(f"*USER ID:* {d.get('id','(Not Available)')}")
    lines.append(f"*IS BOT:* {'✅' if d.get('is_bot') else '❌'}")
    lines.append(f"*ACTIVE:* {'✅' if d.get('is_active') else '❌'}")
    lines.append(branding_footer())
    return "\n".join(lines)

async def api_call_history(session: aiohttp.ClientSession, num: str) -> str:
    url = API_CALL_HISTORY.format(num=num)
    data = await fetch_json(session, url)
    if "error" in data:
        return format_error(f"Call history API error: {data['error']}")
    lines = ["📞 *CALL HISTORY*"]
    if isinstance(data, dict) and data.get("calls"):
        for c in data.get("calls"):
            lines.append(f"- {c.get('date','?')} | {c.get('direction','?')} | {c.get('duration','?')}s")
    else:
        lines.append("*Raw result:*")
        lines.append(str(data))
    lines.append(branding_footer())
    return "\n".join(lines)

# ----------------------------
# Bot Class
# ----------------------------
class DataTraceBot:
    def __init__(self, token: str):
        self.token = token
        self.app = ApplicationBuilder().token(self.token).build()
        self.session: Optional[aiohttp.ClientSession] = None

        # Register handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CommandHandler("buycredits", self.buycredits_cmd))
        self.app.add_handler(CommandHandler("stats", self.stats_cmd))
        self.app.add_handler(CommandHandler("admin", self.admin_cmd))
        self.app.add_handler(CommandHandler("num", self.cmd_num))
        self.app.add_handler(CommandHandler("pak", self.cmd_pak))
        self.app.add_handler(CommandHandler("upi", self.cmd_upi))
        self.app.add_handler(CommandHandler("aadhar", self.cmd_aadhar))
        self.app.add_handler(CommandHandler("aadhar2fam", self.cmd_aadhar_fam))
        self.app.add_handler(CommandHandler("ip", self.cmd_ip))
        self.app.add_handler(CommandHandler("tguser", self.cmd_tguser))
        self.app.add_handler(CommandHandler("callhistory", self.cmd_callhistory))
        self.app.add_handler(CallbackQueryHandler(self.cb_handler))
        # message handlers
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.message_handler))
        # admin quick text listener
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.admin_text_listener), group=1)

    # Lifecycle helpers
    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    # Handlers
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._ensure_session()
        user = update.effective_user
        
        # --- ENHANCED DEBUG LOGGING ---
        logger.info(f"Received /start from user: {user.id} ({user.full_name}) in chat: {update.effective_chat.id}")
        # --- END ENHANCED DEBUG LOGGING ---

        args = context.args or []
        payload = args[0] if args else None
        await init_db()
        # log start (best-effort)
        try:
            await self.app.bot.send_message(LOG_START_CHANNEL, f"/start by {user.id} @{user.username or ''} ({user.full_name})")
        except Exception as e:
            logger.warning(f"Failed to log /start to channel {LOG_START_CHANNEL}: {e}")

        # create/update user
        await get_user_record(user.id)
        if payload:
            try:
                ref_id = int(payload)
                if ref_id != user.id:
                    # Note: Referral logic moved to add_referral, this only grants the joiner credit
                    await update_user_credits(user.id, 1, note="Referral join bonus")
                    # Use the robust add_referral to handle the referrer side
                    await add_referral(ref_id, user.id)
                    await update.message.reply_text("✅ You received 1 free credit for joining via referral!\nUse /help to see commands.")
                    try:
                        await self.app.bot.send_message(ref_id, f"🎉 Your referral @{user.username or user.id} joined.")
                    except Exception:
                        pass
                    return
            except Exception:
                pass
        await update.message.reply_text("Welcome! Use /help to see commands.")

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "*Main Commands*\n"
            "/num <number> - Lookup Indian number\n"
            "/pak <number> - Pakistan number\n"
            "/upi <vpa@bank> - UPI info\n"
            "/aadhar <id> - Aadhar lookup\n"
            "/aadhar2fam <id> - Aadhar family lookup\n"
            "/ip <ip> - IP lookup\n"
            "/tguser <username_or_id> - Telegram user stats\n"
            "/callhistory <number> - Paid: call history (600 credits)\n"
            "/buycredits - Buy credits\n"
            "/stats - (sudos only) bot stats\n\n"
            f"{branding_footer()}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Buy Credits", callback_data="buy_credits_cb"),
             InlineKeyboardButton("Contact Admin", url="http://t.me/DataTraceSupport")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

    async def buycredits_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("100 — ₹50", callback_data="buy_100"),
             InlineKeyboardButton("200 — ₹100", callback_data="buy_200")],
            [InlineKeyboardButton("500 — ₹250", callback_data="buy_500"),
             InlineKeyboardButton("1000 — ₹450", callback_data="buy_1000")],
            [InlineKeyboardButton("Contact Admin", url="http://t.me/DataTraceSupport")]
        ])
        await update.message.reply_text("Choose a pack. After payment, admin will confirm and add credits.", reply_markup=kb)

    async def stats_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in SUDO_IDS:
            await update.message.reply_text("Unauthorized.")
            return
        db = await aiosqlite.connect(DB_PATH)
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM searches") as cur2:
            total_searches = (await cur2.fetchone())[0]
        await db.close()
        await update.message.reply_text(f"Users: {total_users}\nTotal searches: {total_searches}")

    async def admin_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in SUDO_IDS:
            await update.message.reply_text("You are not an admin.")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Add Credits", callback_data="admin_add_credits")],
            [InlineKeyboardButton("Ban User", callback_data="admin_ban_user"),
             InlineKeyboardButton("Unban User", callback_data="admin_unban_user")],
            [InlineKeyboardButton("Add Protected Number", callback_data="admin_add_prot"),
             InlineKeyboardButton("Add Blacklist Number", callback_data="admin_add_black")]
        ])
        await update.message.reply_text("Admin panel: Reply to this message with the command (e.g., `add 123456 100`)", reply_markup=kb)

    # Command wrappers
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
        await self._ensure_session()
        user = update.effective_user
        args = context.args or []
        if not args:
            await update.message.reply_text(f"Usage: /{lookup_type} <query>")
            return
        query = " ".join(args).strip()
        await self.process_lookup_request(user.id, query, lookup_type, update)

    async def process_lookup_request(self, user_id: int, query: str, lookup_type: str, update_obj: Update):
        await self._ensure_session()
        await init_db()
        userrec = await get_user_record(user_id)
        if userrec.get("is_banned"):
            await update_obj.message.reply_text("You are banned from using this bot.")
            return

        # join checks
        not_member = []
        for ch in REQUIRED_CHANNELS:
            chat_id = ch if ch.startswith("-100") or ch.startswith("@") else ("@" + ch)
            try:
                # Check for required channel subscription
                mem = await self.app.bot.get_chat_member(chat_id, user_id)
                if mem.status in ("left", "kicked"):
                    not_member.append(ch)
            except Exception as e:
                # If bot cannot check membership, assume user needs to join
                logger.warning(f"Could not check membership for {ch}: {e}")
                not_member.append(ch)
        if not_member:
            # Create inline keyboard for easy joining
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Join @{c}", url=f"http://t.me/{c}")] for c in not_member])
            await update_obj.message.reply_text(
                "You must join required channels first:\n" + "\n".join(f"- @{c}" for c in REQUIRED_CHANNELS),
                reply_markup=kb
            )
            return

        cost = COST_CALL_HISTORY if lookup_type == "callhistory" else COST_PER_SEARCH

        # Normalize potential number target
        target_number = None
        if lookup_type in ("num", "pak", "callhistory"):
            # keep digits and plus
            target_number = re.sub(r"[^\d+]", "", query)
            # Simple attempt to add + if it looks like an Indian number without a plus
            if not target_number.startswith("+") and (len(target_number) == 10 or target_number.startswith("91")):
                target_number = "+" + target_number
            # Use normalized number for checks
            if await is_blacklisted_number(target_number):
                # silently return no results
                await update_obj.message.reply_text("No results found.")
                return
            if await is_protected_number(target_number) and user_id != OWNER_ID:
                await update_obj.message.reply_text("No results found.")
                return

        # credits handling
        cost_to_deduct = 0
        current_credits = userrec.get("credits", 0)
        current_free_searches = userrec.get("free_searches", 0)

        if current_credits >= cost:
            cost_to_deduct = cost
            # Update user credits
            await update_user_credits(user_id, -cost_to_deduct, note=f"Lookup {lookup_type} {query}")
        elif update_obj.effective_chat.type == "private" and current_free_searches > 0 and cost == COST_PER_SEARCH:
            # Allow free searches in private DMs for non-callhistory lookups
            new_free = current_free_searches - 1
            await set_user_field(user_id, "free_searches", new_free)
            cost_to_deduct = 0 # Cost is covered by free search
        else:
            # prompt user to buy or refer
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Refer & Get 1 Credit", url=f"https://t.me/{(await self.app.bot.get_me()).username}?start={user_id}")],
                [InlineKeyboardButton("Buy Credits", callback_data="buy_credits_cb")]
            ])
            await update_obj.message.reply_text("You don't have enough credits. Refer or buy credits to continue.", reply_markup=kb)
            return

        # perform API lookup
        result_text = None
        try:
            sess = self.session
            if lookup_type == "num":
                result_text = await api_num_lookup(sess, query)
            elif lookup_type == "pak":
                result_text = await api_pak_lookup(sess, query)
            elif lookup_type == "upi":
                result_text = await api_upi_lookup(sess, query)
            elif lookup_type == "aadhar":
                result_text = await api_aadhar_lookup(sess, query)
            elif lookup_type == "aadhar2fam":
                result_text = await api_aadhar_family(sess, query)
            elif lookup_type == "ip":
                result_text = await api_ip_lookup(sess, query)
            elif lookup_type == "tguser":
                result_text = await api_tguser_lookup(sess, query)
            elif lookup_type == "callhistory":
                result_text = await api_call_history(sess, query)
            else:
                result_text = format_error("Unknown lookup type.")
        except Exception as e:
            logger.exception("Lookup failed")
            result_text = format_error(str(e))

        # Record search (cost is 0 if covered by free search)
        await record_search(user_id, query, lookup_type, cost_to_deduct or 0)

        # Send result
        header = f"🔎 *Result — {lookup_type.upper()}*"
        if cost_to_deduct > 0:
            header += f" (Deducted: {cost_to_deduct} Cr)"
        elif cost_to_deduct == 0 and cost == COST_PER_SEARCH:
            header += f" (Free Search Left: {new_free})"
        
        try:
            await update_obj.message.reply_text(header + "\n" + result_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            await update_obj.message.reply_text(header + "\n" + (result_text or "No result"))

        # Log search (best-effort)
        try:
            await self.app.bot.send_message(LOG_SEARCH_CHANNEL,
                                            f"Search by {user_id} — {lookup_type} — {query} — cost {cost_to_deduct or 0}")
        except Exception:
            pass

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._ensure_session()
        msg = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        text = msg.text or ""
        
        # --- ENHANCED DEBUG LOGGING ---
        logger.debug(f"Received non-command message from {user.id} in {chat.type} chat.")
        # --- END ENHANCED DEBUG LOGGING ---

        if chat.type in ("group", "supergroup"):
            bot_username = (await self.app.bot.get_me()).username
            mentioned = False
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == MessageEntity.MENTION:
                        ent_text = msg.text[ent.offset: ent.offset + ent.length]
                        if ent_text.lower().lstrip("@") == bot_username.lower():
                            mentioned = True
            if not mentioned:
                return  # do not respond in group unless mentioned
            # Strip bot mention for processing
            if mentioned:
                text = re.sub(r"@"+re.escape(bot_username), "", text, 1).strip()
        
        phone_match = PHONE_PATTERN.search(text)
        if phone_match:
            num = phone_match.group(0)
            # Remove all non-digit characters from the start, except for '+'
            if num.startswith('+'):
                num = '+' + re.sub(r"[^\d]", "", num[1:])
            else:
                num = re.sub(r"[^\d]", "", num)

            # Check if it looks like a Pakistan number based on prefix
            is_pak = num.startswith("+92") or num.startswith("92") or (len(num) > 10 and num.startswith("03"))
            
            if is_pak:
                await self.process_lookup_request(user.id, num, "pak", update)
            else:
                # Default to Indian lookup
                await self.process_lookup_request(user.id, num, "num", update)
            return

        # in private, if user sends @username -> tguser lookup
        if chat.type == "private" and text.startswith("@"):
            await self.process_lookup_request(user.id, text.lstrip("@"), "tguser", update)
            return

    async def cb_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._ensure_session()
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data
        user = query.from_user

        if data == "verify_join":
            not_member = []
            for ch in REQUIRED_CHANNELS:
                chat_id = ch if ch.startswith("-100") or ch.startswith("@") else ("@" + ch)
                try:
                    mem = await self.app.bot.get_chat_member(chat_id, user.id)
                    if mem.status in ("left", "kicked"):
                        not_member.append(ch)
                except Exception:
                    not_member.append(ch)
            if not_member:
                await query.edit_message_text("You still haven't joined all required channels.")
            else:
                await query.edit_message_text("Thank you! You can now use the bot.")
        elif data == "show_commands":
            await query.edit_message_text("Use /help to see all commands.")
        elif data.startswith("buy_"):
            pack = data.split("_", 1)[1]
            mapping = {"100": (100, 50), "200": (200, 100), "500": (500, 250), "1000": (1000, 450)}
            if pack in mapping:
                credits, price = mapping[pack]
                # Log to admin channel for manual confirmation
                await self.app.bot.send_message(LOG_SEARCH_CHANNEL,
                                                f"💰 Purchase request by {user.id} @{user.username or ''}: {credits} credits for ₹{price}. Admin action required to provide payment details and confirm payment.")
                await query.message.reply_text(f"Payment instructions: You requested {credits} credits for ₹{price}. Please contact Admin: @DataTraceSupport for payment details and to confirm your purchase.")
        elif data == "buy_credits_cb":
            await self.buycredits_cmd(update, context) # Resend the buy menu
        elif data.startswith("admin_"):
            if user.id not in SUDO_IDS:
                await query.edit_message_text("Unauthorized.")
                return
            # guide admins how to proceed (they should reply with the proper command)
            await query.edit_message_text("Admin panel: Reply to this message with the command (e.g., `add 123456 100`, `ban 123456`, `addprot +91999`)")
        else:
            await query.edit_message_text("Unknown action.")

    async def admin_text_listener(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Group 1 handler prioritized for admin text commands
        user = update.effective_user
        text = update.effective_message.text or ""
        if user.id not in SUDO_IDS:
            return
        text = text.strip()
        # patterns: add <user_id> <amount>, ban <user_id>, unban <user_id>, addprot <number>, addblack <number>
        m = re.match(r"add\s+(\d+)\s+(\d+)", text, re.I)
        if m:
            uid = int(m.group(1)); amt = int(m.group(2))
            await update.message.reply_text(f"Adding {amt} credits to {uid}...")
            await update_user_credits(uid, amt, note=f"Admin add by {user.id}")
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
            # Normalize number: remove all non-digits except initial '+'
            num = m.group(1)
            num = '+' + re.sub(r"[^\d]", "", num[1:]) if num.startswith('+') else re.sub(r"[^\d]", "", num)
            await add_protected_number(num, user.id)
            await update.message.reply_text(f"Added protected number {num}.")
            return
        m = re.match(r"addblack\s+(\+?\d+)", text, re.I)
        if m:
            # Normalize number: remove all non-digits except initial '+'
            num = m.group(1)
            num = '+' + re.sub(r"[^\d]", "", num[1:]) if num.startswith('+') else re.sub(r"[^\d]", "", num)
            await add_blacklist_number(num, user.id)
            await update.message.reply_text(f"Added blacklist number {num}.")
            return

    # Start/stop lifecycle for the bot
    async def start_and_idle(self):
        await init_db()
        await self._ensure_session()
        # Application lifecycle: initialize -> start -> start_polling -> idle -> stop -> shutdown
        await self.app.initialize()
        await self.app.start()
        # start polling
        await self.app.updater.start_polling()
        logger.info("Bot started. Press Ctrl+C to stop.")
        await self.app.updater.idle()
        # cleanup
        await self.app.updater.stop_polling()
        await self.app.stop()
        await self.app.shutdown()
        if self.session and not self.session.closed:
            await self.session.close()

# ----------------------------
# Entrypoint
# ----------------------------
def main():
    bot = DataTraceBot(BOT_TOKEN)
    try:
        # Use asyncio.run(bot.start_and_idle()) in Python 3.7+ environments
        # If your environment is older, you might need a different setup.
        asyncio.run(bot.start_and_idle())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")

if __name__ == "__main__":
    main()
