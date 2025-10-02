import logging
import sqlite3
import json
import requests
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

OWNER_ID = 7924074157
SUDO_IDS = {7924074157, 5294360309, 7905267752}
BLACKLIST_NUMS = {"+917724814462"}
PROTECTED_ACCESS = OWNER_ID
GSUPPORT = "@DataTraceSupport"
GC_LINK = "https://t.me/DataTraceOSINTSupport"
MUST_JOIN_CHANNELS = ["DataTraceUpdates", "DataTraceOSINTSupport"]

CALL_HISTORY_COST = 600
FREE_SEARCHES_DM = 2

FREE_CREDIT_ON_JOIN = 1
REFERRAL_COMMISSION = 0.3

CREDIT_PRICES = {
    100: 20,
    200: 35,
    500: 75,
    1000: 120,
    2000: 200,
    5000: 450,
}


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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


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


def create_buttons():
    buttons = [
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
        [
            InlineKeyboardButton("💰 Add Credits", callback_data="addcredits"),
            InlineKeyboardButton("🛒 Buy DB/API", callback_data="buydbapi"),
        ],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{GSUPPORT.lstrip('@')}")],
    ]
    return InlineKeyboardMarkup(buttons)


# Format API responses (same as original) but updated join lines below omitted here to save space
# Use 
 joins and proper Unicode emojis as original

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


# Other format functions similar with "
".join, including format_ip_info, format_num_info, format_pak_num_info, format_aadhar_family_info, and format_tg_user_stats here exactly as previous.

# I will reuse your existing functions here for brevity - replace them in actual code with your formatting functions


def fetch_api(url):
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"API error: {str(e)}")
    return None


def is_blacklisted(number: str) -> bool:
    n = number.replace(" ", "")
    return n in BLACKLIST_NUMS or n.lstrip("+") in BLACKLIST_NUMS


def referral_link(user_id):
    return f"https://t.me/YourBotUsername?start=ref_{user_id}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

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
        if ref_id and get_user(ref_id):
            commission = int(FREE_CREDIT_ON_JOIN * REFERRAL_COMMISSION)
            modify_credits(ref_id, commission)

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
".join([f"@{ch}" for ch in MUST_JOIN_CHANNELS]) + "

"
        f"Contact Admin: {GSUPPORT}",
        parse_mode=ParseMode.HTML,
        reply_markup=create_buttons()
    )


# Reuse your other commands: help_command, stats_command, sudo_command, addcredits_command, ban_command, unban_command, gcast_command (same code), add reply_markup=create_buttons() where user replies are appropriate

# Here is handle_search with buttons added to primary responses


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        await update.message.reply_text("You are banned from using this bot.", reply_markup=create_buttons())
        return

    if not await check_join(update, context):
        return

    txt = update.message.text.strip()
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    if txt.startswith("+") or txt.isdigit():
        if is_blacklisted(txt):
            await update.message.reply_text("This number is blacklisted. No data available.", reply_markup=create_buttons())
            return

    cmd, *args = txt.split(maxsplit=1)
    param = args[0] if args else None

    if chat_type == "private" and user_id not in SUDO_IDS:
        user = get_user(user_id)
        free_used = user[5] if user else 0
        if free_used >= FREE_SEARCHES_DM:
            if user and user[1] <= 0:
                await update.message.reply_text(
                    "Aapke paas credits khatam ho gaye hain, referral se credits kamao ya buy karo.",
                    reply_markup=create_buttons()
                )
                return
        else:
            increment_free_searches_dm(user_id)

    def deduct_credits(user_id, amount):
        if is_sudo(user_id):
            return True
        user = get_user(user_id)
        if user and user[1] >= amount:
            modify_credits(user_id, -amount)
            return True
        return False

    if cmd.startswith("/"):
        command = cmd[1:].lower()
        if command == "upi" and param:
            url = f"https://upi-info.vercel.app/api/upi?upi_id={param}&key=456"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_upi_info(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "ip" and param:
            url = f"https://karmali.serv00.net/ip_api.php?ip={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_ip_info(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "num" and param:
            url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_num_info(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "tg" and param:
            url = f"https://tg-info-neon.vercel.app/user-details?user={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_tg_user_stats(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "pak" and param:
            url = f"https://pak-num-api.vercel.app/search?number={param}"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_pak_num_info(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "aadhar" and param:
            url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={param}&key=paidchx"
            data = fetch_api(url)
            if not data:
                await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                return
            msg = format_aadhar_family_info(data)
            await update.message.reply_text(msg, reply_markup=create_buttons())
            return

        if command == "callhistory" and param:
            number = param
            if is_blacklisted(number):
                await update.message.reply_text("This number is blacklisted.", reply_markup=create_buttons())
                return
            if deduct_credits(user_id, CALL_HISTORY_COST):
                url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
                data = fetch_api(url)
                if not data:
                    await update.message.reply_text("API error or no data found.", reply_markup=create_buttons())
                    return
                pretty_json = "📝 Call History Result:

" + json.dumps(data, indent=2)
                await update.message.reply_text(
                    pretty_json + f"

Credits deducted: {CALL_HISTORY_COST}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=create_buttons()
                )
            else:
                await update.message.reply_text(
                    f"Insufficient credits. Call History costs ₹{CALL_HISTORY_COST} per search.",
                    reply_markup=create_buttons()
                )
            return
        # Admin commands redirect to existing handlers (already have buttons in replies)
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
                f"To buy DB/API, contact admin: {GSUPPORT}", reply_markup=create_buttons()
            )
            return
        await update.message.reply_text("Unknown command or missing parameter.", reply_markup=create_buttons())
        return

    # No command, treat as number guess
    text = txt.replace(" ", "")
    if text.startswith("+92"):
        url = f"https://pak-num-api.vercel.app/search?number={text}"
        data = fetch_api(url)
        if not data:
            await update.message.reply_text("Pakistan Number API error or no data.", reply_markup=create_buttons())
            return
        msg = format_pak_num_info(data)
        await update.message.reply_text(msg, reply_markup=create_buttons())
        return
    elif text.startswith("+91") or text.isdigit():
        url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={text}"
        data = fetch_api(url)
        if not data:
            await update.message.reply_text("Number API error or no data.", reply_markup=create_buttons())
            return
        msg = format_num_info(data)
        await update.message.reply_text(msg, reply_markup=create_buttons())
        return

    await update.message.reply_text(
        "Invalid input or command. Type /help for usage instructions.", reply_markup=create_buttons()
    )


# Callback query handler for buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back":
        await query.edit_message_text(
            text="Main Menu. Use commands or send numbers to search info.",
            reply_markup=create_buttons()
        )
    elif data == "addcredits":
        text = "To add credits:

Refer friends using your referral link or buy cheap credits.

" \
               "Credits Price:
"
        for k, v in CREDIT_PRICES.items():
            text += f"{k} Credits - ₹{v}
"
        text += f"
Contact admin for buy: {GSUPPORT}"
        await query.edit_message_text(text=text, reply_markup=create_buttons())
    elif data == "buydbapi":
        await query.edit_message_text(
            text=f"To buy DB/API, contact admin: {GSUPPORT}",
            reply_markup=create_buttons()
        )
    else:
        await query.edit_message_text(
            text="Unknown button clicked.",
            reply_markup=create_buttons()
        )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help for instructions.", reply_markup=create_buttons())


def main():
    app = ApplicationBuilder().token(TOKEN).build()

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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
