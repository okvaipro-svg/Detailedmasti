# DataTrace OSINT Bot - enhanced with inline buttons & callbacks
# FULL ready-to-copy-paste file. Keeps all original behavior and adds beautiful inline keyboards and callback handlers.
# NOTE: You already included a TOKEN in your original file; this file uses that same token variable.

import logging
import sqlite3
import json
import requests
import html
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
    # If we can't check (exceptions), treat as not joined
    if not has_joined_must_channel(context, user_id):
        await update.message.reply_text(
            f"Bot use karne ke liye aapko must join karna hoga channels:\n"
            + "\n".join([f"@{ch}" for ch in MUST_JOIN_CHANNELS])
            + f"\n\nJoin karne ke baad phir se try karein."
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
    return "\n".join(lines)


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
    # API returns keys differently sometimes; attempt both.
    for k, v in keys.items():
        vl = data.get(k.replace(" ", "_"), data.get(k))
        if vl is None:
            vl = "N/A"
        lines.append(f"{v}: {vl}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"📢 Join @DataTraceUpdates | Support: {GSUPPORT}")
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return "\n".join(lines)


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
    return f"https://t.me/YourBotUsername?start=ref_{user_id}"


# -----------------------
# NEW: Inline keyboard builders & callback handlers
# -----------------------

def main_menu_keyboard():
    kb = [
        [InlineKeyboardButton("🔎 Search Number", switch_inline_query_current_chat="+91 ")],
        [
            InlineKeyboardButton("🖇 UPI Lookup", callback_data="menu_upi"),
            InlineKeyboardButton("🌐 IP Lookup", callback_data="menu_ip"),
        ],
        [
            InlineKeyboardButton("👤 TG Lookup", callback_data="menu_tg"),
            InlineKeyboardButton("🪪 Aadhaar Family", callback_data="menu_aadhar"),
        ],
        [
            InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits"),
            InlineKeyboardButton("🎁 Referral", callback_data="referral"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="menu_help"),
            InlineKeyboardButton("🆘 Support", url=f"https://t.me/{GSUPPORT.lstrip('@')}"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


def result_action_keyboard(can_call_history=False, message_id=None):
    kb = []
    kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    # If call history feature is available for the result, show purchase button
    if can_call_history:
        kb.append([InlineKeyboardButton(f"📞 Call History (₹{CALL_HISTORY_COST})", callback_data="buy_callhistory")])
    # Buy credits quick button
    # A URL button to group/contact support for buying
    kb.append(
        [
            InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits"),
            InlineKeyboardButton("🔁 Share", switch_inline_query="Check this result from DataTrace OSINT Bot"),
        ]
    )
    return InlineKeyboardMarkup(kb)


def buy_credits_keyboard():
    kb = []
    for amount, price in sorted(CREDIT_PRICES.items()):
        kb.append([InlineKeyboardButton(f"{amount} credits → ₹{price}", callback_data=f"buypkg|{amount}")])
    kb.append([InlineKeyboardButton("Contact Admin / Pay", url=f"https://t.me/{GSUPPORT.lstrip('@')}")])
    kb.append([InlineKeyboardButton("◀️ Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(kb)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback query handler for inline buttons."""
    query = update.callback_query
    await query.answer()  # let the client know we received the callback
    data = query.data or ""

    user_id = query.from_user.id

    # MAIN MENU
    if data == "main_menu":
        await query.edit_message_text(
            "✨ Main Menu — DataTrace OSINT\nChoose an action:",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "menu_help":
        await query.edit_message_text(
            "Commands:\n"
            "/start - Start bot\n"
            "/help - This message\n"
            "/stats - Get user bot stats\n"
            "/addcredits <user_id> <amount> - Add credits (sudo only)\n"
            "/ban <user_id> - Ban user (sudo only)\n"
            "/unban <user_id> - Unban user (sudo only)\n"
            "/sudo - List sudo IDs\n"
            "/gcast <msg> - Global broadcast (sudo only)\n\n"
            "Search by commands or direct message:\n"
            "- Send number to get info\n"
            "- /num <number>, /upi <id>, /ip <ip>, /tg <user_id>, /pak <number>, /aadhar <id>\n"
            "- Call history is paid feature (₹600/search)\n\nEnsure you have joined must join channels.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # MENU shortcuts that open input hints for the user
    if data == "menu_upi":
        # We can't open a keyboard with a prefilled /upi command. Use switch_inline_query_current_chat for number search,
        # but for other commands we show example usage and a back button.
        await query.edit_message_text(
            "UPI Lookup\nUsage: /upi example@bank\nSend /upi <vpa> in chat or click Main Menu.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "menu_ip":
        await query.edit_message_text(
            "IP Lookup\nUsage: /ip 8.8.8.8\nSend /ip <ip> in chat or click Main Menu.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "menu_tg":
        await query.edit_message_text(
            "TG Lookup\nUsage: /tg username_or_id\nSend /tg <user> in chat or click Main Menu.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "menu_aadhar":
        await query.edit_message_text(
            "Aadhaar Family Lookup\nUsage: /aadhar <aadhaar_number>\nSend /aadhar <id> in chat or click Main Menu.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Referral
    if data == "referral":
        link = referral_link(user_id)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔗 Copy Referral Link", callback_data="main_menu")],
                [InlineKeyboardButton("Share Link", switch_inline_query=link)],
                [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
                [InlineKeyboardButton("◀️ Back", callback_data="main_menu")],
            ]
        )
        await query.edit_message_text(
            f"Your referral link:\n{link}\n\nShare this with friends to earn credits!",
            reply_markup=kb,
        )
        return

    # Buy credits
    if data == "buy_credits":
        await query.edit_message_text(
            "Choose a credit package to buy (offline/manual):",
            reply_markup=buy_credits_keyboard(),
        )
        return

    # Buying specific package selected
    if data.startswith("buypkg|"):
        parts = data.split("|", 1)
        if len(parts) == 2:
            try:
                amt = int(parts[1])
            except Exception:
                amt = None
            if amt and amt in CREDIT_PRICES:
                price = CREDIT_PRICES[amt]
                # We don't implement payment flow — instruct user to contact admin & present quick contact
                await query.edit_message_text(
                    f"Package: {amt} credits → ₹{price}\n\nTo purchase, contact admin: {GSUPPORT}\n\nAfter payment, admin will add credits.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
                            [InlineKeyboardButton("◀️ Back", callback_data="buy_credits")],
                        ]
                    ),
                )
                return

    # Call history purchase via button
    if data == "buy_callhistory":
        # We'll attempt to deduct credits and fetch call history in this callback.
        user = get_user(user_id)
        if is_sudo(user_id):
            # For sudo, free access — just show usage hint
            await query.edit_message_text("Sudo user: You can use /callhistory <number> directly.")
            return
        if not user or user[1] < CALL_HISTORY_COST:
            # Not enough credits
            await query.edit_message_text(
                f"Insufficient credits. Call History costs ₹{CALL_HISTORY_COST}. Buy credits or contact admin.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
                        [InlineKeyboardButton("Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
                        [InlineKeyboardButton("◀️ Back", callback_data="main_menu")],
                    ]
                ),
            )
            return
        # Ask user to send the number now in chat to fetch (since we don't have the number context in callback)
        await query.edit_message_text(
            f"Credits available. Please send the number you want call history for in chat now. ₹{CALL_HISTORY_COST} will be deducted once you send /callhistory <number>.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="main_menu")]]),
        )
        return

    # Unknown callback - fallback to main menu
    await query.edit_message_text("Option expired or unknown. Returning to Main Menu.", reply_markup=main_menu_keyboard())


# -----------------------
# HANDLER FUNCTIONS (commands, message handling)
# -----------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Try to check join; if not joined, check_join sends message and returns False.
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

    text = (
        "Welcome to DataTrace OSINT Bot!\n\n"
        "Get started by searching any info. Use the menu below for quick actions."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Show help but with keyboard
    text = (
        "Commands:\n"
        "/start - Start bot\n"
        "/help - This message\n"
        "/stats - Get user bot stats\n"
        "/addcredits <user_id> <amount> - Add credits (sudo only)\n"
        "/ban <user_id> - Ban user (sudo only)\n"
        "/unban <user_id> - Unban user (sudo only)\n"
        "/sudo - List sudo IDs\n"
        "/gcast <msg> - Global broadcast (sudo only)\n\n"
        "Search by commands or direct message:\n"
        "- Send number to get info\n"
        "- /num <number>, /upi <id>, /ip <ip>, /tg <user_id>, /pak <number>, /aadhar <id>\n"
        "- Call history is paid feature (₹600/search)\n\nEnsure you have joined must join channels."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("You are not authorized to use this command.", reply_markup=main_menu_keyboard())
        return

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(credits) FROM users")
    total_credits = c.fetchone()[0] or 0
    await update.message.reply_text(
        f"Bot Stats:\nTotal Users: {total_users}\nTotal Credits in system: {total_credits}",
        reply_markup=main_menu_keyboard(),
    )


async def sudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    sudo_list = "\n".join(str(x) for x in SUDO_IDS)
    await update.message.reply_text(f"Sudo IDs:\n{sudo_list}", reply_markup=main_menu_keyboard())


async def addcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        _, target_id_str, amount_str = update.message.text.split()
        target_id = int(target_id_str)
        amount = int(amount_str)
    except Exception:
        await update.message.reply_text("Usage: /addcredits <user_id> <amount>", reply_markup=main_menu_keyboard())
        return
    if modify_credits(target_id, amount):
        await update.message.reply_text(f"Added {amount} credits to {target_id}.", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("Failed to add credits (maybe user does not exist).", reply_markup=main_menu_keyboard())


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        _, target_id_str = update.message.text.split()
        target_id = int(target_id_str)
    except Exception:
        await update.message.reply_text("Usage: /ban <user_id>", reply_markup=main_menu_keyboard())
        return
    ban_user(target_id)
    await update.message.reply_text(f"Banned user {target_id}.", reply_markup=main_menu_keyboard())


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        _, target_id_str = update.message.text.split()
        target_id = int(target_id_str)
    except Exception:
        await update.message.reply_text("Usage: /unban <user_id>", reply_markup=main_menu_keyboard())
        return
    unban_user(target_id)
    await update.message.reply_text(f"Unbanned user {target_id}.", reply_markup=main_menu_keyboard())


async def gcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        await update.message.reply_text("Unauthorized.", reply_markup=main_menu_keyboard())
        return
    try:
        msg = update.message.text.split(" ", 1)[1]
    except IndexError:
        await update.message.reply_text("Usage: /gcast <message>", reply_markup=main_menu_keyboard())
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
    await update.message.reply_text(f"Sent broadcast to {count} users.", reply_markup=main_menu_keyboard())


# Keep the behavior of handle_search but attach result keyboards to replies
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        await update.message.reply_text("You are banned from using this bot.", reply_markup=main_menu_keyboard())
        return

    if not await check_join(update, context):
        return

    txt = update.message.text.strip()
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # Blacklist check if input looks like number
    if txt.startswith("+") or txt.isdigit():
        if is_blacklisted(txt):
            await update.message.reply_text("This number is blacklisted. No data available.", reply_markup=main_menu_keyboard())
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
                    "Aapke paas credits khatam ho gaye hain, referral se credits kamao ya buy karo.",
                    reply_markup=main_menu_keyboard(),
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

    # If command
    if cmd.startswith("/"):
        command = cmd[1:].lower()
        if command == "upi" and param:
            url = f"https://upi-info.vercel.app/api/upi?upi_id={param}&key=456"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_upi_info(data)
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=False))
            return

        if command == "ip" and param:
            url = f"https://karmali.serv00.net/ip_api.php?ip={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_ip_info(data)
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=False))
            return

        if command == "num" and param:
            url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_num_info(data)
            # include callhistory purchase option for numbers
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=True))
            return

        if command == "tg" and param:
            url = f"https://tg-info-neon.vercel.app/user-details?user={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_tg_user_stats(data)
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=False))
            return

        if command == "pak" and param:
            url = f"https://pak-num-api.vercel.app/search?number={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_pak_num_info(data)
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=True))
            return

        if command == "aadhar" and param:
            url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={param}&key=paidchx"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                return
            msg = format_aadhar_family_info(data)
            await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=False))
            return

        if command == "callhistory" and param:
            # Paid feature - deduct CALL_HISTORY_COST credits
            number = param
            if is_blacklisted(number):
                await update.message.reply_text("This number is blacklisted.", reply_markup=main_menu_keyboard())
                return
            if deduct_credits(user_id, CALL_HISTORY_COST):
                url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
                data = fetch_api(url)
                if not data:
                    await update.message.reply_text("API error or no data found.", reply_markup=main_menu_keyboard())
                    return
                pretty_json = "📝 Call History Result:\n\n" + json.dumps(data, indent=2)
                await update.message.reply_text(
                    pretty_json + f"\n\nCredits deducted: {CALL_HISTORY_COST}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=main_menu_keyboard(),
                )
            else:
                await update.message.reply_text(
                    f"Insufficient credits. Call History costs ₹{CALL_HISTORY_COST} per search.",
                    reply_markup=main_menu_keyboard(),
                )
            return

        # Admin commands pass through to their handlers to maintain logic
        if command == "addcredits":
            await addcredits_command(update, context)
            return

        if command == "ban":
            await ban_command(update, context)
            return

        if command == "unban":
            await unban_command(update, context)
            return

        if command == "sudo":
            await sudo_command(update, context)
            return

        if command == "stats":
            await stats_command(update, context)
            return

        if command == "gcast":
            await gcast_command(update, context)
            return

        if command == "buydb" or command == "buyapi":
            await update.message.reply_text(
                f"To buy DB/API, contact admin: {GSUPPORT}",
                reply_markup=main_menu_keyboard(),
            )
            return

        await update.message.reply_text("Unknown command or missing parameter.", reply_markup=main_menu_keyboard())
        return

    # If no command, treat as a guessed number or generic input
    text = txt.replace(" ", "")
    if text.startswith("+92"):
        url = f"https://pak-num-api.vercel.app/search?number={text}"
        data = fetch_api(url)
        if not data:
            await update.message.reply_text("Pakistan Number API error or no data.", reply_markup=main_menu_keyboard())
            return
        msg = format_pak_num_info(data)
        await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=True))
        return
    elif text.startswith("+91") or text.isdigit():
        url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={text}"
        data = fetch_api(url)
        if not data:
            await update.message.reply_text("Number API error or no data.", reply_markup=main_menu_keyboard())
            return
        msg = format_num_info(data)
        await update.message.reply_text(msg, reply_markup=result_action_keyboard(can_call_history=True))
        return

    await update.message.reply_text(
        "Invalid input or command. Type /help for usage instructions.",
        reply_markup=main_menu_keyboard(),
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help for instructions.", reply_markup=main_menu_keyboard())


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("sudo", sudo_command))
    app.add_handler(CommandHandler("addcredits", addcredits_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("gcast", gcast_command))
    app.add_handler(CommandHandler("buydb", handle_search))
    app.add_handler(CommandHandler("buyapi", handle_search))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # CallbackQuery handler for inline button presses
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
