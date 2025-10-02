import logging
import sqlite3
import json
import requests
import html
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

TOKEN = "8219144171:AAF8_6dxvS0skpljooJey2E-TfZhfMYKgjE"

# Config variables extracted
OWNER_ID = 7924074157
SUDO_IDS = {7924074157, 5294360309, 7905267752}
BLACKLIST_NUMS = {"+917724814462"}
PROTECTED_ACCESS = OWNER_ID
GSUPPORT = "@DataTraceSupport"
GC_LINK = "https://t.me/DataTraceOSINTSupport"
MUST_JOIN_CHANNELS = ["DataTraceUpdates", "DataTraceOSINTSupport"]

CALL_HISTORY_COST = 600
FREE_SEARCHES_DM = 2

# Referral system
FREE_CREDIT_ON_JOIN = 1
REFERRAL_COMMISSION = 0.3  # 30%

# Credit prices (cheap)
CREDIT_PRICES = {
    100: 20,
    200: 35,
    500: 75,
    1000: 120,
    2000: 200,
    5000: 450,
}

# SQLite Database Setup
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
c = conn.cursor()
c.execute(
    """CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credits INTEGER DEFAULT 0,
    referrer_id INTEGER,
    banned INTEGER DEFAULT 0,
    joined_gc INTEGER DEFAULT 0,
    free_searches_dm INTEGER DEFAULT 0
    )"""
)
conn.commit()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# Helper functions


def is_sudo(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_IDS


def get_user(user_id: int):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()


def add_user(user_id: int, referrer_id: int = None):
    if get_user(user_id):
        return False
    c.execute(
        "INSERT INTO users (user_id, credits, referrer_id, banned, joined_gc, free_searches_dm) VALUES (?, ?, ?, 0, 0, ?)",
        (user_id, FREE_CREDIT_ON_JOIN, referrer_id, 0),
    )
    conn.commit()
    return True


def modify_credits(user_id: int, amount: int):
    user = get_user(user_id)
    if not user:
        return False
    current_credits = user[1]
    new_credits = current_credits + amount
    if new_credits < 0:
        return False
    c.execute("UPDATE users SET credits=? WHERE user_id=?", (new_credits, user_id))
    conn.commit()
    return True


def is_banned(user_id: int):
    user = get_user(user_id)
    return user and user[3] == 1


def ban_user(user_id: int):
    c.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()


def unban_user(user_id: int):
    c.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()


def increment_free_searches_dm(user_id: int):
    user = get_user(user_id)
    if not user:
        return False
    count = user[5] + 1
    c.execute("UPDATE users SET free_searches_dm=? WHERE user_id=?", (count, user_id))
    conn.commit()
    return count


def has_joined_must_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    for ch in MUST_JOIN_CHANNELS:
        try:
            member = context.bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True


async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if not has_joined_must_channel(context, user_id):
        await update.message.reply_text(
            f"Bot use karne ke liye aapko must join karna hoga channels:
"
            + "
".join([f"@{ch}" for ch in MUST_JOIN_CHANNELS])
            + f"

Join karne ke baad phir se try karein."
        )
        return False
    return True


# Format API responses for bot output

def format_upi_info(data):
    b = data.get("bank_details_raw", {})
    v = data.get("vpa_details", {})
    lines = [
        "🔗 UPI Search Result",
        "━━━━━━━━━━━━━━━",
        f"🏦 Bank: {b.get('BANK', 'N/A')}",
        f"🏛 Branch: {b.get('BRANCH', 'N/A')}",
        f"📍 Address: {b.get('ADDRESS', 'N/A')}",
        f"🏷 IFSC: {b.get('IFSC', 'N/A')}",
        f"🌏 City: {b.get('CITY', 'N/A')}, {b.get('STATE', 'N/A')}",
        f"✅ UPI Enabled: {b.get('UPI', 'N/A')}",
        "",
        f"👤 Name: {v.get('name', 'N/A')}",
        f"💳 VPA: {v.get('vpa', 'N/A')}",
        "━━━━━━━━━━━━━━━",
        f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


def format_ip_info(data):
    keys = {
        "IP Valid": "🗾 IP Valid",
        "Country": "🌎 Country",
        "Country Code": "💠 Country Code",
        "Region": "🥬 Region",
        "Region Name": "🗺️ Region Name",
        "City": "🏠 City",
        "Zip": "✉️ Zip",
        "Latitude": "🦠 Latitude",
        "Longitude": "⭐ Longitude",
        "Timezone": "🕢 Timezone",
        "ISP": "🗼 ISP",
        "Organization": "🔥 Organization",
        "AS": "🌾 AS",
        "IP": "🛰 IP",
    }
    lines = []
    for k, v in keys.items():
        vl = data.get(k.replace(" ", "_"), data.get(k))
        if vl is None:
            vl = "N/A"
        lines.append(f"{v}: {vl}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}")
    return "
".join(lines)


def format_num_info(data):
    if "data" not in data or len(data["data"]) == 0:
        return "Number info not found."
    d = data["data"][0]
    lines = [
        "📱 Number Info (India)",
        "━━━━━━━━━━━━━━━",
        f"📞 Mobile: {d.get('mobile', 'N/A')}",
        f"👤 Name: {d.get('name', 'N/A')}",
        f"👥 Father/Alt: {d.get('fname', 'N/A')}",
        f"🏠 Address: {d.get('address', 'N/A').replace('!', ', ')}",
        f"📲 Alternate: {d.get('alt', 'N/A')}",
        f"📡 Circle: {d.get('circle', 'N/A')}",
        f"🪪 ID: {d.get('id', 'N/A')}",
        "━━━━━━━━━━━━━━━",
        f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


def format_pak_num_info(data):
    if "results" not in data or len(data["results"]) == 0:
        return "Pakistan number info not found."
    lines = ["🇵🇰 Pakistan Number Info", "━━━━━━━━━━━━━━━"]
    for record in data["results"]:
        lines.append(f"👤 Name: {record.get('Name', 'N/A')}")
        lines.append(f"🆔 CNIC: {record.get('CNIC', 'N/A')}")
        addr = record.get("Address", "N/A")
        lines.append(f"📍 Address: {addr if addr else 'N/A'}")
        lines.append(f"📞 Number: {record.get('Mobile', 'N/A')}")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}")
    return "
".join(lines)


def format_aadhar_family_info(data):
    lines = [
        "🪪 Aadhaar → Family Info",
        "━━━━━━━━━━━━━━━",
        f"🏠 Address: {data.get('address', 'N/A')}",
        f"📍 District: {data.get('homeDistName', 'N/A')}, {data.get('homeStateName', 'N/A')}",
        f"Scheme: {data.get('schemeName', 'N/A')} (Scheme ID: {data.get('schemeId', 'N/A')})",
        "",
        "👨‍👩‍👧 Members:",
    ]
    members = data.get("memberDetailsList", [])
    for idx, m in enumerate(members, 1):
        lines.append(f"{idx}. {m.get('memberName', 'N/A')} ({m.get('releationship_name', 'N/A')})")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}")
    return "
".join(lines)


def format_tg_user_stats(data):
    d = data.get("data", {})
    if not d:
        return "User stats not found."
    lines = [
        "👤 Telegram User Stats",
        "━━━━━━━━━━━━━━━",
        f"🆔 ID: {d.get('id', 'N/A')}",
        f"📛 Name: {d.get('first_name', '')} {d.get('last_name', '')}",
        f"📬 Active: {'✅' if d.get('is_active') else '❌'}",
        f"🤖 Bot: {'✅' if d.get('is_bot') else '❌'}",
        f"📅 First Seen: {d.get('first_msg_date', '')[:10]}",
        f"🕒 Last Seen: {d.get('last_msg_date', '')[:10]}",
        "",
        f"📊 Messages in Groups: {d.get('msg_in_groups_count', 0)}",
        f"💬 Total Messages: {d.get('total_msg_count', 0)}",
        f"👥 Groups Joined: {d.get('total_groups', 0)}",
        f"🧩 Total Usernames: {d.get('usernames_count', 0)}",
        f"🧩 Total Names: {d.get('names_count', 0)}",
        "━━━━━━━━━━━━━━━",
        f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}",
    ]
    return "
".join(lines)


# Fetch API helper
def fetch_api(url):
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"API error: {str(e)}")
    return None


# Format and check number for blacklist
def is_blacklisted(number: str) -> bool:
    # Normalize
    n = number.replace(" ", "")
    return n in BLACKLIST_NUMS or n.lstrip("+") in BLACKLIST_NUMS


# Generate referral link
def referral_link(user_id):
    return f"https://t.me/UserDeepLookupBot?start=ref_{user_id}"


# HANDLER FUNCTIONS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if user joined must join channels
    if not await check_join(update, context):
        return

    msg = update.message.text or ""
    ref_id = None
    if msg.startswith("/start") and "ref_" in msg:
        try:
            ref_id = int(msg.split("ref_")[1])
            if ref_id == user_id:
                ref_id = None
        except Exception:
            ref_id = None

    exists = get_user(user_id)
    if not exists:
        add_user(user_id, ref_id)
        # Add commission to referrer
        if ref_id and get_user(ref_id):
            commission = int(FREE_CREDIT_ON_JOIN * REFERRAL_COMMISSION)
            modify_credits(ref_id, commission)  # Commission on join credit 1

    await update.message.reply_text(
        f"Welcome to DataTrace OSINT Bot!

"
        f"Get started by searching any info.
"
        f"Refer friends via your referral link to earn credits:
"
        f"{referral_link(user_id)}

"
        f"You get {FREE_CREDIT_ON_JOIN} free credits on join.

"
        f"Must join channels:
" + "
".join([f"@{ch}" for ch in MUST_JOIN_CHANNELS])
        + f"

Contact Admin: {GSUPPORT}",
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Commands:
"
        "/start - Start bot
"
        "/help - This message
"
        "/stats - Get user bot stats
"
        "/addcredits <user_id> <amount> - Add credits (sudo only)
"
        "/ban <user_id> - Ban user (sudo only)
"
        "/unban <user_id> - Unban user (sudo only)
"
        "/sudo - List sudo IDs
"
        "/gcast <msg> - Global broadcast (sudo only)
"
        "
Search by commands or direct message:
"
        "- Send number to get info
"
        "- /num <number>, /upi <id>, /ip <ip>, /tg <user_id>, /pak <number>, /aadhar <id>
"
        "- Call history is paid feature (₹600/search)
"
        "
Ensure you have joined must join channels."
    )
    await update.message.reply_text(text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(credits) FROM users")
    total_credits = c.fetchone()[0] or 0
    await update.message.reply_text(
        f"Bot Stats:
Total Users: {total_users}
Total Credits in system: {total_credits}"
    )


async def sudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    sudo_list = "
".join(str(x) for x in SUDO_IDS)
    await update.message.reply_text(f"Sudo IDs:
{sudo_list}")


async def addcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    try:
        _, target_id_str, amount_str = update.message.text.split()
        target_id = int(target_id_str)
        amount = int(amount_str)
    except Exception:
        await update.message.reply_text("Usage: /addcredits <user_id> <amount>")
        return
    if modify_credits(target_id, amount):
        await update.message.reply_text(f"Added {amount} credits to {target_id}.")
    else:
        await update.message.reply_text("Failed to add credits (maybe user does not exist).")


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    try:
        _, target_id_str = update.message.text.split()
        target_id = int(target_id_str)
    except Exception:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    ban_user(target_id)
    await update.message.reply_text(f"Banned user {target_id}.")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    try:
        _, target_id_str = update.message.text.split()
        target_id = int(target_id_str)
    except Exception:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    unban_user(target_id)
    await update.message.reply_text(f"Unbanned user {target_id}.")


async def gcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    try:
        msg = update.message.text.split(" ", 1)[1]
    except IndexError:
        await update.message.reply_text("Usage: /gcast <message>")
        return
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    count = 0
    for u in users:
        try:
            await context.bot.send_message(u[0], msg)
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"Sent broadcast to {count} users.")


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        await update.message.reply_text("You are banned from using this bot.")
        return

    if not await check_join(update, context):
        return

    txt = update.message.text.strip()
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # Blacklist check if input looks like number
    if txt.startswith("+") or txt.isdigit():
        if is_blacklisted(txt):
            await update.message.reply_text("This number is blacklisted. No data available.")
            return

    # Determine API called based on input/command
    # Check if command or direct input
    cmd, *args = txt.split(maxsplit=1)
    param = args[0] if args else None

    # Free search limit check in DM
    if chat_type == "private" and user_id not in SUDO_IDS:
        user = get_user(user_id)
        free_used = user[5] if user else 0
        if free_used >= FREE_SEARCHES_DM:  # Need referral or credits
            if user and user[1] <= 0:
                await update.message.reply_text(
                    "Aapke paas credits khatam ho gaye hain, referral se credits kamao ya buy karo."
                )
                return
        else:
            increment_free_searches_dm(user_id)

    # Helper to deduct credits - used only for paid features
    def deduct_credits(user_id, amount):
        if is_sudo(user_id):
            return True
        user = get_user(user_id)
        if user and user[1] >= amount:
            modify_credits(user_id, -amount)
            return True
        return False

    # Commands and API mapping
    if cmd.startswith("/"):
        command = cmd[1:].lower()
        if command == "upi" and param:
            url = f"https://upi-info.vercel.app/api/upi?upi_id={param}&key=456"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_upi_info(data)
            await update.message.reply_text(msg)
            return

        if command == "ip" and param:
            url = f"https://karmali.serv00.net/ip_api.php?ip={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_ip_info(data)
            await update.message.reply_text(msg)
            return

        if command == "num" and param:
            url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_num_info(data)
            await update.message.reply_text(msg)
            return

        if command == "tg" and param:
            url = f"https://tg-info-neon.vercel.app/user-details?user={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_tg_user_stats(data)
            await update.message.reply_text(msg)
            return

        if command == "pak" and param:
            url = f"https://pak-num-api.vercel.app/search?number={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_pak_num_info(data)
            await update.message.reply_text(msg)
            return

        if command == "aadhar" and param:
            url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={param}&key=paidchx"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.")
                return
            msg = format_aadhar_family_info(data)
            await update.message.reply_text(msg)
            return

        if command == "callhistory" and param:
            # Paid feature - deduct 600 credits
            number = param
            if is_blacklisted(number):
                await update.message.reply_text("This number is blacklisted.")
                return
            if deduct_credits(user_id, CALL_HISTORY_COST):
                url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
                data = fetch_api(url)
                if not data:
                    await update.message.reply_text("API error or no data found.")
                    return
                # Format response as JSON string or basic format here
                pretty_json = "📝 Call History Result:

" + json.dumps(data, indent=2)
                await update.message.reply_text(
                    pretty_json + f"

Credits deducted: {CALL_HISTORY_COST}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await update.message.reply_text(
                    f"Insufficient credits. Call History costs ₹{CALL_HISTORY_COST} per search."
                )
            return

        # Admin commands
        if command == "addcredits":
            await addcredits_command(update, context)
            return

        if command == "ban":
            await ban_command(update, context)
            return

        if command ==
