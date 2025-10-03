import logging
import os
import json
import requests
import sqlite3
import random
import string
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
    filters,
    ContextTypes,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = os.environ.get("TOKEN", "8219144171:AAH3HZPZvvtohlxOkTP2jJVDuEAaAllyzdU")

# Owner and sudo IDs
OWNER_ID = 7924074157
SUDO_USERS = [7924074157, 5294360309, 7905267752]

# Required channels
REQUIRED_CHANNELS = [
    {"username": "DataTraceUpdates", "id": -1001234567890},  # Replace with actual ID
    {"username": "DataTraceOSINTSupport", "id": -1001234567891}  # Replace with actual ID
]

# Log channels
START_LOG_CHANNEL = -1002765060940
SEARCH_LOG_CHANNEL = -1003066524164

# API endpoints
API_ENDPOINTS = {
    "upi_info": "https://upi-info.vercel.app/api/upi?upi_id={upi_id}&key=456",
    "num_info": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={number}",
    "tg_user_stats": "https://tg-info-neon.vercel.app/user-details?user={user_id}",
    "ip_details": "https://karmali.serv00.net/ip_api.php?ip={ip}",
    "pak_num": "https://pak-num-api.vercel.app/search?number={number}",
    "aadhar_family": "https://family-members-n5um.vercel.app/fetch?aadhaar={aadhaar}&key=paidchx",
    "aadhar_details": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={aadhaar}",
    "call_history": "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
}

# Blacklisted numbers
BLACKLISTED_NUMBERS = ["+917724814462"]

# Protected numbers (only owner can check)
PROTECTED_NUMBERS = ["+919876543210"]  # Add protected numbers here

# Credit prices
CREDIT_PRICES = {
    100: {"inr": 50, "usdt": 0.45},
    200: {"inr": 100, "usdt": 0.9},
    500: {"inr": 250, "usdt": 2.25},
    1000: {"inr": 450, "usdt": 4.0},
    2000: {"inr": 900, "usdt": 8.0},
    5000: {"inr": 2250, "usdt": 20.0}
}

# States for conversation
ADD_CREDITS, BAN_USER, PROTECT_NUMBER = range(3)

# Database setup
def init_db():
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        credits INTEGER DEFAULT 2,
        referred_by INTEGER,
        referral_code TEXT,
        is_banned INTEGER DEFAULT 0,
        join_date TEXT,
        last_used TEXT
    )
    ''')
    
    # Referrals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        credits_earned INTEGER DEFAULT 0,
        referral_date TEXT
    )
    ''')
    
    # Transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        credits INTEGER,
        status TEXT,
        transaction_date TEXT
    )
    ''')
    
    # Search logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS search_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        search_type TEXT,
        query TEXT,
        result_count INTEGER,
        search_date TEXT
    )
    ''')
    
    # Protected numbers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS protected_numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE,
        added_by INTEGER,
        added_date TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# Helper functions
def generate_referral_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ---------- REPLACE is_user_member and check_membership WITH THE FOLLOWING ----------

async def is_user_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    Returns True if the user is a member of ALL REQUIRED_CHANNELS.
    Owner and sudo users bypass the check (always allowed).
    This function treats 'member', 'creator', 'administrator' as valid statuses.
    On transient errors contacting Telegram, we log and return False (so the flow
    will prompt the user), but Owner/Sudo bypass prevents blocking them.
    """
    # Allow owner/sudo to bypass membership requirement
    try:
        if is_owner(user_id) or is_sudo(user_id):
            logger.debug(f"Membership check bypass for owner/sudo user {user_id}")
            return True
    except Exception:
        # if is_owner/is_sudo are not available for some reason, continue to checking normally
        pass

    bot = context.bot
    for channel in REQUIRED_CHANNELS:
        chat_identifier = channel.get("id") or channel.get("username")
        try:
            # get_chat_member accepts either int id or username string
            member = await bot.get_chat_member(chat_identifier, user_id)

            # Accept these statuses as being a member:
            if member.status in ("member", "creator", "administrator"):
                # good for this channel â€” continue to next
                continue
            # If user explicitly left or was kicked, not a member
            if member.status in ("left", "kicked", "restricted", "banned"):
                logger.info(f"User {user_id} is not a member of {channel.get('username') or chat_identifier}: status={member.status}")
                return False

            # If status is something else, be conservative and treat as not a member
            logger.info(f"User {user_id} membership status for {chat_identifier}: {member.status}")
            return False

        except Exception as e:
            # Log the failure â€” do not crash. Returning False will prompt user to join.
            logger.warning(f"Error checking membership for channel {channel.get('username') or chat_identifier}: {e}")
            return False

    # Passed all channel checks
    return True


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Checks membership and prompts the user to join missing channels.
    Channel posts are skipped. Owner/Sudo users bypass the check.
    """
    # Skip for channel posts (channel messages)
    if getattr(update, "channel_post", None):
        return True

    user = update.effective_user
    user_id = user.id if user else None
    if not user_id:
        return False

    # If owner/sudo, bypass
    if is_owner(user_id) or is_sudo(user_id):
        logger.debug(f"check_membership: bypassing membership for owner/sudo user {user_id}")
        return True

    is_member = await is_user_member(context, user_id)
    if not is_member:
        keyboard = []
        for channel in REQUIRED_CHANNELS:
            username = channel.get("username")
            if username:
                keyboard.append([InlineKeyboardButton(f"Join {username}", url=f"https://t.me/{username}")])
            else:
                # fallback: use channel id if username missing
                keyboard.append([InlineKeyboardButton("Open Channel", url=f"https://t.me/{channel.get('id')}")])
        keyboard.append([InlineKeyboardButton("âœ… I've joined all channels", callback_data="check_membership")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Some updates (like callback queries) don't have message; ensure we reply safely
        try:
            # prefer update.message, else send to chat_id
            if getattr(update, "message", None):
                await update.message.reply_text(
                    "ðŸš« *You must join all required channels to use this bot*\n\n"
                    "Please join the channels below and then click the button:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text="ðŸš« *You must join all required channels to use this bot*\n\n"
                                                    "Please join the channels below and then click the button:",
                                               reply_markup=reply_markup,
                                               parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to prompt user about membership: {e}")

        return False

    return True

# ----------------------------------------------------------------------------------
def get_user_credits(user_id: int) -> int:
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_credits(user_id: int, credits: int, operation: str = "set") -> bool:
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    
    if operation == "add":
        cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits, user_id))
    elif operation == "subtract":
        cursor.execute("UPDATE users SET credits = credits - ? WHERE user_id = ?", (credits, user_id))
    else:  # set
        cursor.execute("UPDATE users SET credits = ? WHERE user_id = ?", (credits, user_id))
    
    conn.commit()
    conn.close()
    return True

def log_search(user_id: int, search_type: str, query: str, result_count: int):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO search_logs (user_id, search_type, query, result_count, search_date) VALUES (?, ?, ?, ?, ?)",
        (user_id, search_type, query, result_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, channel_id: int, message: str):
    try:
        await context.bot.send_message(chat_id=channel_id, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to log to channel {channel_id}: {e}")

def is_protected_number(number: str) -> bool:
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM protected_numbers WHERE number = ?", (number,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_blacklisted_number(number: str) -> bool:
    return number in BLACKLISTED_NUMBERS

def is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Log to start channel
    log_message = f"ðŸ†• *New User Started*\n\n"
    log_message += f"ðŸ‘¤ Name: {user.first_name} {user.last_name if user.last_name else ''}\n"
    log_message += f"ðŸ”– Username: @{user.username if user.username else 'N/A'}\n"
    log_message += f"ðŸ†” User ID: {user_id}\n"
    log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    await log_to_channel(context, START_LOG_CHANNEL, log_message)
    
    # Check if user is in database
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        # Check if user was referred
        referral_code = context.args[0] if context.args else None
        referred_by = None
        
        if referral_code:
            cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
            referrer = cursor.fetchone()
            if referrer:
                referred_by = referrer[0]
                # Give 1 credit to new user
                initial_credits = 1
                # Give 1 credit to referrer
                update_user_credits(referred_by, 1, "add")
                
                # Log referral
                cursor.execute(
                    "INSERT INTO referrals (referrer_id, referred_id, credits_earned, referral_date) VALUES (?, ?, ?, ?)",
                    (referred_by, user_id, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
            else:
                initial_credits = 2  # Free credits for new users
        else:
            initial_credits = 2  # Free credits for new users
        
        # Generate referral code
        new_referral_code = generate_referral_code()
        
        # Add user to database
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, last_name, credits, referred_by, referral_code, join_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user.username, user.first_name, user.last_name, initial_credits, referred_by, new_referral_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    else:
        # Get referral code
        cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
        new_referral_code = cursor.fetchone()[0]
    
    conn.close()
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Get user credits
    credits = get_user_credits(user_id)
    
    # Create referral link
    referral_link = f"https://t.me/{context.bot.username}?start={new_referral_code}"
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("ðŸ” Search", callback_data="search_menu")],
        [InlineKeyboardButton("ðŸ’³ My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("ðŸ‘¥ Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("â„¹ï¸ Help", callback_data="help")],
        [InlineKeyboardButton("ðŸ“ž Contact Admin", url="https://t.me/DataTraceSupport")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ðŸ‘‹ *Welcome to DataTrace OSINT Bot, {user.first_name}!*\n\n"
        f"ðŸ” *Your Credits:* {credits}\n\n"
        f"ðŸ“‹ *Features:*\n"
        f"â€¢ UPI to Information\n"
        f"â€¢ Number to Information\n"
        f"â€¢ Telegram User Stats\n"
        f"â€¢ IP to Details\n"
        f"â€¢ Pakistan Number to CNIC\n"
        f"â€¢ Aadhar to Family Details\n"
        f"â€¢ Aadhar to Details\n"
        f"â€¢ Call History (Paid)\n\n"
        f"ðŸ”— *Your Referral Link:*\n{referral_link}\n\n"
        f"Share this link with friends and earn credits!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    help_text = "ðŸ“– *DataTrace OSINT Bot Help*\n\n"
    help_text += "ðŸ” *Search Commands:*\n"
    help_text += "â€¢ `/upi [UPI_ID]` - Get UPI details\n"
    help_text += "â€¢ `/num [NUMBER]` - Get number details\n"
    help_text += "â€¢ `/tg [USER_ID]` - Get Telegram user stats\n"
    help_text += "â€¢ `/ip [IP_ADDRESS]` - Get IP details\n"
    help_text += "â€¢ `/pak [NUMBER]` - Get Pakistan number to CNIC\n"
    help_text += "â€¢ `/aadhar [AADHAR_NUMBER]` - Get Aadhar details\n"
    help_text += "â€¢ `/family [AADHAR_NUMBER]` - Get Aadhar family details\n"
    help_text += "â€¢ `/call [NUMBER]` - Get call history (Paid - 600 credits)\n\n"
    
    help_text += "ðŸ’³ *Credit Commands:*\n"
    help_text += "â€¢ `/credits` - Check your credits\n"
    help_text += "â€¢ `/buy` - Buy more credits\n"
    help_text += "â€¢ `/refer` - Get your referral link\n\n"
    
    help_text += "ðŸ”§ *Other Commands:*\n"
    help_text += "â€¢ `/start` - Start the bot\n"
    help_text += "â€¢ `/help` - Show this help message\n\n"
    
    if is_sudo(user_id):
        help_text += "ðŸ› ï¸ *Admin Commands:*\n"
        help_text += "â€¢ `/admin` - Open admin panel\n"
        help_text += "â€¢ `/addcredits [USER_ID] [AMOUNT]` - Add credits to user\n"
        help_text += "â€¢ `/ban [USER_ID]` - Ban a user\n"
        help_text += "â€¢ `/unban [USER_ID]` - Unban a user\n"
        help_text += "â€¢ `/stats` - View bot statistics\n"
        help_text += "â€¢ `/gcast [MESSAGE]` - Broadcast message to all users\n"
        help_text += "â€¢ `/protect [NUMBER]` - Add a number to protected list\n"
        help_text += "â€¢ `/unprotect [NUMBER]` - Remove a number from protected list\n"
        help_text += "â€¢ `/blacklist [NUMBER]` - Add a number to blacklist\n"
        help_text += "â€¢ `/unblacklist [NUMBER]` - Remove a number from blacklist\n\n"
    
    help_text += "ðŸ“ž *Need Help?*\n"
    help_text += "Contact: @DataTraceSupport\n\n"
    help_text += "ðŸ¤ *Referral Program:*\n"
    help_text += "Share your referral link and earn 30% commission when your referrals buy credits!"
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    credits = get_user_credits(user_id)
    
    # Get referral code
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    referral_code = cursor.fetchone()[0]
    conn.close()
    
    # Create referral link
    referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"
    
    # Get referral stats
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    referral_count = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(credits_earned) FROM referrals WHERE referrer_id = ?", (user_id,))
    credits_earned = cursor.fetchone()[0] or 0
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")],
        [InlineKeyboardButton("ðŸ‘¥ Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ðŸ’³ *Your Credits: {credits}*\n\n"
        f"ðŸ‘¥ *Referral Stats:*\n"
        f"â€¢ Referrals: {referral_count}\n"
        f"â€¢ Credits Earned: {credits_earned}\n\n"
        f"ðŸ”— *Your Referral Link:*\n{referral_link}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Get referral code
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    referral_code = cursor.fetchone()[0]
    conn.close()
    
    # Create referral link
    referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"
    
    keyboard = [
        [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ðŸ¤ *Referral Program*\n\n"
        f"Share your referral link and earn rewards!\n\n"
        f"ðŸ”— *Your Referral Link:*\n{referral_link}\n\n"
        f"ðŸ“‹ *How it works:*\n"
        f"â€¢ Share your personal referral link\n"
        f"â€¢ When someone starts the bot using your link, they get 1 free credit\n"
        f"â€¢ Whenever your referral buys credits, you earn 30% commission (in credits)\n\n"
        f"ðŸ“Š *Example:*\n"
        f"â€¢ Friend joins â†’ They get 1 free credit\n"
        f"â€¢ Friend buys 1000 credits â†’ You get 300 credits commission\n"
        f"â€¢ Friend buys 5000 credits â†’ You get 1500 credits commission",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    keyboard = []
    for credits, price in CREDIT_PRICES.items():
        keyboard.append([
            InlineKeyboardButton(f"ðŸ’³ {credits} Credits - â‚¹{price['inr']} | {price['usdt']} USDT", 
                               callback_data=f"buy_{credits}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("ðŸ“ž Contact Admin for Custom Plans", url="https://t.me/DataTraceSupport")
    ])
    keyboard.append([
        InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "ðŸ’³ *Buy Credits*\n\n"
        "Choose a credit package below:\n\n"
        "ðŸ’° *Payment Methods:*\n"
        "â€¢ UPI\n"
        "â€¢ USDT (TRC20)\n\n"
        "ðŸ“ž *Need Help?*\n"
        "Contact: @DataTraceSupport",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# API handlers
async def upi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get UPI ID from command
    if context.args:
        upi_id = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide a UPI ID.\n\nUsage: `/upi example@upi`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["upi_info"].format(upi_id=upi_id))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            bank_details = data.get("bank_details_raw", {})
            vpa_details = data.get("vpa_details", {})
            
            result_text = "ðŸ¦ *UPI DETAILS*\n\n"
            result_text += "ðŸ‘¤ *ACCOUNT HOLDER*\n"
            result_text += f"NAME: {vpa_details.get('name', 'N/A')}\n"
            result_text += f"VPA: {vpa_details.get('vpa', 'N/A')}\n\n"
            
            result_text += "ðŸ¦ *BANK DETAILS*\n"
            result_text += f"BANK: {bank_details.get('BANK', 'N/A')}\n"
            result_text += f"BRANCH: {bank_details.get('BRANCH', 'N/A')}\n"
            result_text += f"CITY: {bank_details.get('CITY', 'N/A')}\n"
            result_text += f"DISTRICT: {bank_details.get('DISTRICT', 'N/A')}\n"
            result_text += f"STATE: {bank_details.get('STATE', 'N/A')}\n"
            result_text += f"ADDRESS: {bank_details.get('ADDRESS', 'N/A')}\n"
            result_text += f"IFSC: {bank_details.get('IFSC', 'N/A')}\n"
            result_text += f"MICR: {bank_details.get('MICR', 'N/A')}\n"
            result_text += f"IMPS: {'âœ…' if bank_details.get('IMPS') else 'âŒ'}\n"
            result_text += f"NEFT: {'âœ…' if bank_details.get('NEFT') else 'âŒ'}\n"
            result_text += f"RTGS: {'âœ…' if bank_details.get('RTGS') else 'âŒ'}\n"
            result_text += f"UPI: {'âœ…' if bank_details.get('UPI') else 'âŒ'}\n"
            
            # Add branding
            result_text += "\n\nðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "upi", upi_id, 1)
            
            # Log to channel
            log_message = f"ðŸ” *UPI Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {upi_id}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this UPI ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in UPI lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching UPI information. Please try again later.", parse_mode="Markdown")

async def num_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get number from command
    if context.args:
        number = context.args[0]
        # Remove +91 if present
        if number.startswith("+91"):
            number = number[3:]
        # Remove +92 if present (Pakistan)
        elif number.startswith("+92"):
            number = number[3:]
    else:
        await update.message.reply_text("âŒ Please provide a phone number.\n\nUsage: `/num 9876543210`", parse_mode="Markdown")
        return
    
    # Check if number is blacklisted
    if is_blacklisted_number(number):
        await update.message.reply_text("âŒ This number is blacklisted and cannot be searched.", parse_mode="Markdown")
        return
    
    # Check if number is protected (only owner can check)
    if is_protected_number(number) and not is_owner(user_id):
        await update.message.reply_text("âŒ This number is protected and cannot be searched.", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["num_info"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data.get("data"):
            # Format response
            result = data["data"][0]
            
            result_text = "ðŸ“± *NUMBER DETAILS*\n\n"
            result_text += f"MOBILE: {result.get('mobile', 'N/A')}\n"
            result_text += f"ALT MOBILE: {result.get('alt', 'N/A')}\n"
            result_text += f"NAME: {result.get('name', 'N/A')}\n"
            result_text += f"FULL NAME: {result.get('fname', 'N/A')}\n"
            result_text += f"ADDRESS: {result.get('address', 'N/A').replace('!', ', ')}\n"
            result_text += f"CIRCLE: {result.get('circle', 'N/A')}\n"
            result_text += f"ID: {result.get('id', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\nðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "num", number, len(data["data"]))
            
            # Log to channel
            log_message = f"ðŸ” *Number Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {number}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in number lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching number information. Please try again later.", parse_mode="Markdown")

async def tg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get user ID from command
    if context.args:
        tg_user_id = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide a Telegram user ID.\n\nUsage: `/tg 123456789`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["tg_user_stats"].format(user_id=tg_user_id))
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            # Format response
            user_data = data["data"]
            
            result_text = "ðŸ‘¤ *TELEGRAM USER STATS*\n\n"
            result_text += f"NAME: {user_data.get('first_name', 'N/A')} {user_data.get('last_name', '')}\n"
            result_text += f"USER ID: {user_data.get('id', 'N/A')}\n"
            result_text += f"IS BOT: {'âœ…' if user_data.get('is_bot') else 'âŒ'}\n"
            result_text += f"ACTIVE: {'âœ…' if user_data.get('is_active') else 'âŒ'}\n\n"
            
            result_text += "ðŸ“Š *STATS*\n"
            result_text += f"TOTAL GROUPS: {user_data.get('total_groups', 'N/A')}\n"
            result_text += f"ADMIN IN GROUPS: {user_data.get('adm_in_groups', 'N/A')}\n"
            result_text += f"TOTAL MESSAGES: {user_data.get('total_msg_count', 'N/A')}\n"
            result_text += f"MESSAGES IN GROUPS: {user_data.get('msg_in_groups_count', 'N/A')}\n\n"
            
            result_text += "ðŸ• *DATES*\n"
            result_text += f"FIRST MSG DATE: {user_data.get('first_msg_date', 'N/A')[:10]}\n"
            result_text += f"LAST MSG DATE: {user_data.get('last_msg_date', 'N/A')[:10]}\n\n"
            
            result_text += "ðŸ”„ *CHANGES*\n"
            result_text += f"NAME CHANGES: {user_data.get('names_count', 'N/A')}\n"
            result_text += f"USERNAME CHANGES: {user_data.get('usernames_count', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\nðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "tg", tg_user_id, 1)
            
            # Log to channel
            log_message = f"ðŸ” *Telegram User Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {tg_user_id}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this Telegram user.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Telegram user lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching Telegram user information. Please try again later.", parse_mode="Markdown")

async def ip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get IP from command
    if context.args:
        ip = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide an IP address.\n\nUsage: `/ip 8.8.8.8`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["ip_details"].format(ip=ip))
        data = response.text
        
        if response.status_code == 200 and data:
            # Format response (API returns formatted text)
            result_text = f"ðŸŒ *IP DETAILS*\n\n{data}\n\n"
            
            # Add branding
            result_text += "ðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "ip", ip, 1)
            
            # Log to channel
            log_message = f"ðŸ” *IP Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {ip}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this IP address.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in IP lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching IP information. Please try again later.", parse_mode="Markdown")

async def pak_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get number from command
    if context.args:
        number = context.args[0]
        # Add +92 if not present
        if not number.startswith("+92"):
            number = "+92" + number
    else:
        await update.message.reply_text("âŒ Please provide a Pakistan phone number.\n\nUsage: `/pak 3362006909`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["pak_num"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data.get("results"):
            # Format response
            results = data["results"]
            
            result_text = "ðŸ‡µðŸ‡° *PAKISTAN INFO*\n\n"
            
            for i, result in enumerate(results, 1):
                result_text += f"{i}ï¸âƒ£\n"
                result_text += f"NAME: {result.get('Name', 'N/A')}\n"
                result_text += f"CNIC: {result.get('CNIC', 'N/A')}\n"
                result_text += f"MOBILE: {result.get('Mobile', 'N/A')}\n"
                result_text += f"ADDRESS: {result.get('Address', 'Not Available')}\n\n"
            
            # Add branding
            result_text += "ðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "pak", number, len(results))
            
            # Log to channel
            log_message = f"ðŸ” *Pakistan Number Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {number}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this Pakistan number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Pakistan number lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching Pakistan number information. Please try again later.", parse_mode="Markdown")

async def aadhar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get Aadhar number from command
    if context.args:
        aadhar = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide an Aadhar number.\n\nUsage: `/aadhar 123456789012`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["aadhar_details"].format(aadhaar=aadhar))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "ðŸ†” *AADHAR DETAILS*\n\n"
            
            for i, result in enumerate(data, 1):
                result_text += f"{i}ï¸âƒ£\n"
                result_text += f"ID: {result.get('id', 'N/A')}\n"
                result_text += f"MOBILE: {result.get('mobile', 'N/A')}\n"
                result_text += f"ALT MOBILE: {result.get('alt_mobile', 'N/A')}\n"
                result_text += f"NAME: {result.get('name', 'N/A')}\n"
                result_text += f"FATHER NAME: {result.get('father_name', 'N/A')}\n"
                result_text += f"ADDRESS: {result.get('address', 'N/A').replace('!', ', ')}\n"
                result_text += f"CIRCLE: {result.get('circle', 'N/A')}\n"
                result_text += f"ID NUMBER: {result.get('id_number', 'N/A')}\n"
                result_text += f"EMAIL: {result.get('email', 'N/A')}\n\n"
            
            # Add branding
            result_text += "ðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "aadhar", aadhar, len(data))
            
            # Log to channel
            log_message = f"ðŸ” *Aadhar Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {aadhar}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this Aadhar number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Aadhar lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching Aadhar information. Please try again later.", parse_mode="Markdown")

async def family_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "âŒ *Insufficient Credits*\n\n"
            "You don't have enough credits to use this feature.\n\n"
            "Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get Aadhar number from command
    if context.args:
        aadhar = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide an Aadhar number.\n\nUsage: `/family 123456789012`", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["aadhar_family"].format(aadhaar=aadhar))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "ðŸ†” *AADHAR FAMILY INFO*\n\n"
            result_text += f"RC ID: {data.get('rcId', 'N/A')}\n"
            result_text += f"SCHEME: {data.get('schemeName', 'N/A')} ({data.get('schemeId', 'N/A')})\n"
            result_text += f"DISTRICT: {data.get('homeDistName', 'N/A')}\n"
            result_text += f"STATE: {data.get('homeStateName', 'N/A')}\n"
            result_text += f"FPS ID: {data.get('fpsId', 'N/A')}\n\n"
            
            result_text += "ðŸ‘¨â€ðŸ‘©â€ðŸ‘§ *FAMILY MEMBERS:*\n"
            
            members = data.get("memberDetailsList", [])
            for i, member in enumerate(members, 1):
                result_text += f"{i}ï¸âƒ£ {member.get('memberName', 'N/A')} â€” {member.get('releationship_name', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\nðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "family", aadhar, len(members))
            
            # Log to channel
            log_message = f"ðŸ” *Aadhar Family Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {aadhar}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this Aadhar number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Aadhar family lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching Aadhar family information. Please try again later.", parse_mode="Markdown")

async def call_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is member of required channels
    if not await check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits < 600:
        keyboard = [
            [InlineKeyboardButton("ðŸ‘¥ Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"âŒ *Insufficient Credits*\n\n"
            f"You need 600 credits to use this feature. You currently have {credits} credits.\n\n"
            f"Choose an option below to get more credits:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    # Get number from command
    if context.args:
        number = context.args[0]
    else:
        await update.message.reply_text("âŒ Please provide a phone number.\n\nUsage: `/call 9876543210`", parse_mode="Markdown")
        return
    
    # Check if number is blacklisted
    if is_blacklisted_number(number):
        await update.message.reply_text("âŒ This number is blacklisted and cannot be searched.", parse_mode="Markdown")
        return
    
    # Check if number is protected (only owner can check)
    if is_protected_number(number) and not is_owner(user_id):
        await update.message.reply_text("âŒ This number is protected and cannot be searched.", parse_mode="Markdown")
        return
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["call_history"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "ðŸ“ž *CALL HISTORY*\n\n"
            
            # Assuming the API returns a list of calls
            calls = data if isinstance(data, list) else [data]
            
            for i, call in enumerate(calls[:10], 1):  # Limit to 10 calls
                result_text += f"{i}ï¸âƒ£\n"
                result_text += f"DATE: {call.get('date', 'N/A')}\n"
                result_text += f"TIME: {call.get('time', 'N/A')}\n"
                result_text += f"TYPE: {call.get('type', 'N/A')}\n"
                result_text += f"DURATION: {call.get('duration', 'N/A')}\n"
                result_text += f"NUMBER: {call.get('number', 'N/A')}\n\n"
            
            # Add branding
            result_text += "ðŸ” *Powered by DataTrace OSINT*\n"
            result_text += "ðŸ“ž *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 600, "subtract")
            
            # Log search
            log_search(user_id, "call", number, len(calls))
            
            # Log to channel
            log_message = f"ðŸ” *Call History Search*\n\n"
            log_message += f"ðŸ‘¤ User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"ðŸ” Query: {number}\n"
            log_message += f"ðŸ“… Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            await log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("âŒ No information found for this number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in call history lookup: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching call history. Please try again later.", parse_mode="Markdown")

# Admin commands
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    keyboard = [
        [InlineKeyboardButton("ðŸ‘¥ Add Credits", callback_data="admin_add_credits")],
        [InlineKeyboardButton("ðŸš« Ban/Unban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("ðŸ“Š Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("ðŸ“¢ Broadcast Message", callback_data="admin_gcast")],
        [InlineKeyboardButton("ðŸ”’ Protect Number", callback_data="admin_protect_number")],
        [InlineKeyboardButton("â›” Blacklist Number", callback_data="admin_blacklist_number")],
        [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "ðŸ› ï¸ *Admin Panel*\n\n"
        "Choose an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def addcredits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("âŒ Please provide a user ID and amount.\n\nUsage: `/addcredits 123456789 100`", parse_mode="Markdown")
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        
        # Update user credits
        update_user_credits(target_user_id, amount, "add")
        
        # Get user info
        try:
            user_info = await context.bot.get_chat(target_user_id)
            user_info_text = f"{user_info.first_name} (@{user_info.username if user_info.username else 'N/A'})"
        except:
            user_info_text = f"User ID: {target_user_id}"
        
        await update.message.reply_text(
            f"âœ… *Credits Added*\n\n"
            f"User: {user_info_text}\n"
            f"Amount: {amount} credits",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("âŒ Invalid input. Please provide a valid user ID and amount.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in addcredits: {e}")
        await update.message.reply_text("âŒ An error occurred while adding credits.", parse_mode="Markdown")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a user ID.\n\nUsage: `/ban 123456789`", parse_mode="Markdown")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Update user ban status
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()
        
        # Get user info
        try:
            user_info = await context.bot.get_chat(target_user_id)
            user_info_text = f"{user_info.first_name} (@{user_info.username if user_info.username else 'N/A'})"
        except:
            user_info_text = f"User ID: {target_user_id}"
        
        await update.message.reply_text(
            f"âœ… *User Banned*\n\n"
            f"User: {user_info_text}",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("âŒ Invalid input. Please provide a valid user ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in ban: {e}")
        await update.message.reply_text("âŒ An error occurred while banning the user.", parse_mode="Markdown")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a user ID.\n\nUsage: `/unban 123456789`", parse_mode="Markdown")
        return
    
    try:
        target_user_id = int(context.args[0])
        
        # Update user ban status
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()
        
        # Get user info
        try:
            user_info = await context.bot.get_chat(target_user_id)
            user_info_text = f"{user_info.first_name} (@{user_info.username if user_info.username else 'N/A'})"
        except:
            user_info_text = f"User ID: {target_user_id}"
        
        await update.message.reply_text(
            f"âœ… *User Unbanned*\n\n"
            f"User: {user_info_text}",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("âŒ Invalid input. Please provide a valid user ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in unban: {e}")
        await update.message.reply_text("âŒ An error occurred while unbanning the user.", parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        
        # Get total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Get active users (used in last 7 days)
        cursor.execute("SELECT COUNT(*) FROM users WHERE last_used > date('now', '-7 days')")
        active_users = cursor.fetchone()[0]
        
        # Get banned users
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_users = cursor.fetchone()[0]
        
        # Get total searches
        cursor.execute("SELECT COUNT(*) FROM search_logs")
        total_searches = cursor.fetchone()[0]
        
        # Get searches today
        cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date > date('now')")
        today_searches = cursor.fetchone()[0]
        
        # Get total credits sold
        cursor.execute("SELECT SUM(credits) FROM transactions WHERE status = 'completed'")
        total_credits_sold = cursor.fetchone()[0] or 0
        
        # Get revenue
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'completed'")
        total_revenue = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats_text = "ðŸ“Š *Bot Statistics*\n\n"
        stats_text += f"ðŸ‘¥ *Users:*\n"
        stats_text += f"â€¢ Total: {total_users}\n"
        stats_text += f"â€¢ Active (7 days): {active_users}\n"
        stats_text += f"â€¢ Banned: {banned_users}\n\n"
        
        stats_text += f"ðŸ” *Searches:*\n"
        stats_text += f"â€¢ Total: {total_searches}\n"
        stats_text += f"â€¢ Today: {today_searches}\n\n"
        
        stats_text += f"ðŸ’° *Revenue:*\n"
        stats_text += f"â€¢ Credits Sold: {total_credits_sold}\n"
        stats_text += f"â€¢ Total Revenue: â‚¹{total_revenue:.2f}\n"
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await update.message.reply_text("âŒ An error occurred while fetching statistics.", parse_mode="Markdown")

async def gcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a message to broadcast.\n\nUsage: `/gcast Your message here`", parse_mode="Markdown")
        return
    
    message = " ".join(context.args)
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        fail_count = 0
        
        for user in users:
            try:
                await context.bot.send_message(chat_id=user[0], text=message)
                success_count += 1
            except:
                fail_count += 1
        
        await update.message.reply_text(
            f"âœ… *Broadcast Completed*\n\n"
            f"â€¢ Success: {success_count}\n"
            f"â€¢ Failed: {fail_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in gcast: {e}")
        await update.message.reply_text("âŒ An error occurred while broadcasting the message.", parse_mode="Markdown")

async def protect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("âŒ Only the owner can use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a number to protect.\n\nUsage: `/protect 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO protected_numbers (number, added_by, added_date) VALUES (?, ?, ?)",
                      (number, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"âœ… *Number Protected*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in protect: {e}")
        await update.message.reply_text("âŒ An error occurred while protecting the number.", parse_mode="Markdown")

async def unprotect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("âŒ Only the owner can use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a number to unprotect.\n\nUsage: `/unprotect 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM protected_numbers WHERE number = ?", (number,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"âœ… *Number Unprotected*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in unprotect: {e}")
        await update.message.reply_text("âŒ An error occurred while unprotecting the number.", parse_mode="Markdown")

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a number to blacklist.\n\nUsage: `/blacklist 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    if number not in BLACKLISTED_NUMBERS:
        BLACKLISTED_NUMBERS.append(number)
        await update.message.reply_text(
            f"âœ… *Number Blacklisted*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("âŒ This number is already blacklisted.", parse_mode="Markdown")

async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if not is_sudo(user_id):
        await update.message.reply_text("âŒ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("âŒ Please provide a number to unblacklist.\n\nUsage: `/unblacklist 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    if number in BLACKLISTED_NUMBERS:
        BLACKLISTED_NUMBERS.remove(number)
        await update.message.reply_text(
            f"âœ… *Number Unblacklisted*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("âŒ This number is not blacklisted.", parse_mode="Markdown")

# Callback query handlers
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    if query.data == "check_membership":
        if await is_user_member(context, user_id):
            await query.edit_message_text(
                "âœ… *Verification Successful*\n\n"
                "You can now use the bot. Click /start to continue.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "âŒ *Verification Failed*\n\n"
                "You haven't joined all required channels. Please join all channels and try again.",
                parse_mode="Markdown"
            )
    elif query.data == "search_menu":
        keyboard = [
            [InlineKeyboardButton("ðŸ¦ UPI to Info", callback_data="search_upi")],
            [InlineKeyboardButton("ðŸ“± Number to Info", callback_data="search_num")],
            [InlineKeyboardButton("ðŸ‘¤ Telegram User Stats", callback_data="search_tg")],
            [InlineKeyboardButton("ðŸŒ IP to Details", callback_data="search_ip")],
            [InlineKeyboardButton("ðŸ‡µðŸ‡° Pakistan Number to CNIC", callback_data="search_pak")],
            [InlineKeyboardButton("ðŸ†” Aadhar to Details", callback_data="search_aadhar")],
            [InlineKeyboardButton("ðŸ‘¨â€ðŸ‘©â€ðŸ‘§ Aadhar to Family", callback_data="search_family")],
            [InlineKeyboardButton("ðŸ“ž Call History (Paid)", callback_data="search_call")],
            [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ðŸ” *Search Menu*\n\n"
            "Choose a search option below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data == "my_credits":
        credits = get_user_credits(user_id)
        
        # Get referral code
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
        referral_code = cursor.fetchone()[0]
        conn.close()
        
        # Create referral link
        referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"
        
        # Get referral stats
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        referral_count = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(credits_earned) FROM referrals WHERE referrer_id = ?", (user_id,))
        credits_earned = cursor.fetchone()[0] or 0
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("ðŸ’³ Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("ðŸ‘¥ Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"ðŸ’³ *Your Credits: {credits}*\n\n"
            f"ðŸ‘¥ *Referral Stats:*\n"
            f"â€¢ Referrals: {referral_count}\n"
            f"â€¢ Credits Earned: {credits_earned}\n\n"
            f"ðŸ”— *Your Referral Link:*\n{referral_link}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data == "referral_program":
        # Get referral code
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
        referral_code = cursor.fetchone()[0]
        conn.close()
        
        # Create referral link
        referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"
        
        keyboard = [
            [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"ðŸ¤ *Referral Program*\n\n"
            f"Share your referral link and earn rewards!\n\n"
            f"ðŸ”— *Your Referral Link:*\n{referral_link}\n\n"
            f"ðŸ“‹ *How it works:*\n"
            f"â€¢ Share your personal referral link\n"
            f"â€¢ When someone starts the bot using your link, they get 1 free credit\n"
            f"â€¢ Whenever your referral buys credits, you earn 30% commission (in credits)\n\n"
            f"ðŸ“Š *Example:*\n"
            f"â€¢ Friend joins â†’ They get 1 free credit\n"
            f"â€¢ Friend buys 1000 credits â†’ You get 300 credits commission\n"
            f"â€¢ Friend buys 5000 credits â†’ You get 1500 credits commission",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data == "help":
        help_text = "ðŸ“– *DataTrace OSINT Bot Help*\n\n"
        help_text += "ðŸ” *Search Commands:*\n"
        help_text += "â€¢ `/upi [UPI_ID]` - Get UPI details\n"
        help_text += "â€¢ `/num [NUMBER]` - Get number details\n"
        help_text += "â€¢ `/tg [USER_ID]` - Get Telegram user stats\n"
        help_text += "â€¢ `/ip [IP_ADDRESS]` - Get IP details\n"
        help_text += "â€¢ `/pak [NUMBER]` - Get Pakistan number to CNIC\n"
        help_text += "â€¢ `/aadhar [AADHAR_NUMBER]` - Get Aadhar details\n"
        help_text += "â€¢ `/family [AADHAR_NUMBER]` - Get Aadhar family details\n"
        help_text += "â€¢ `/call [NUMBER]` - Get call history (Paid - 600 credits)\n\n"
        
        help_text += "ðŸ’³ *Credit Commands:*\n"
        help_text += "â€¢ `/credits` - Check your credits\n"
        help_text += "â€¢ `/buy` - Buy more credits\n"
        help_text += "â€¢ `/refer` - Get your referral link\n\n"
        
        help_text += "ðŸ”§ *Other Commands:*\n"
        help_text += "â€¢ `/start` - Start the bot\n"
        help_text += "â€¢ `/help` - Show this help message\n\n"
        
        if is_sudo(user_id):
            help_text += "ðŸ› ï¸ *Admin Commands:*\n"
            help_text += "â€¢ `/admin` - Open admin panel\n"
            help_text += "â€¢ `/addcredits [USER_ID] [AMOUNT]` - Add credits to user\n"
            help_text += "â€¢ `/ban [USER_ID]` - Ban a user\n"
            help_text += "â€¢ `/unban [USER_ID]` - Unban a user\n"
            help_text += "â€¢ `/stats` - View bot statistics\n"
            help_text += "â€¢ `/gcast [MESSAGE]` - Broadcast message to all users\n"
            help_text += "â€¢ `/protect [NUMBER]` - Add a number to protected list\n"
            help_text += "â€¢ `/unprotect [NUMBER]` - Remove a number from protected list\n"
            help_text += "â€¢ `/blacklist [NUMBER]` - Add a number to blacklist\n"
            help_text += "â€¢ `/unblacklist [NUMBER]` - Remove a number from blacklist\n\n"
        
        help_text += "ðŸ“ž *Need Help?*\n"
        help_text += "Contact: @DataTraceSupport\n\n"
        help_text += "ðŸ¤ *Referral Program:*\n"
        help_text += "Share your referral link and earn 30% commission when your referrals buy credits!"
        
        keyboard = [
            [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif query.data == "buy_credits":
        keyboard = []
        for credits, price in CREDIT_PRICES.items():
            keyboard.append([
                InlineKeyboardButton(f"ðŸ’³ {credits} Credits - â‚¹{price['inr']} | {price['usdt']} USDT", 
                                   callback_data=f"buy_{credits}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("ðŸ“ž Contact Admin for Custom Plans", url="https://t.me/DataTraceSupport")
        ])
        keyboard.append([
            InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "ðŸ’³ *Buy Credits*\n\n"
            "Choose a credit package below:\n\n"
            "ðŸ’° *Payment Methods:*\n"
            "â€¢ UPI\n"
            "â€¢ USDT (TRC20)\n\n"
            "ðŸ“ž *Need Help?*\n"
            "Contact: @DataTraceSupport",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("buy_"):
        credits_amount = int(query.data.split("_")[1])
        price = CREDIT_PRICES[credits_amount]
        
        keyboard = [
            [InlineKeyboardButton("ðŸ’¸ Pay with UPI", callback_data=f"pay_upi_{credits_amount}")],
            [InlineKeyboardButton("ðŸ’¸ Pay with USDT", callback_data=f"pay_usdt_{credits_amount}")],
            [InlineKeyboardButton("ðŸ“ž Contact Admin", url="https://t.me/DataTraceSupport")],
            [InlineKeyboardButton("ðŸ”™ Back", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"ðŸ’³ *Buy {credits_amount} Credits*\n\n"
            f"ðŸ’° *Price:*\n"
            f"â€¢ â‚¹{price['inr']} (UPI)\n"
            f"â€¢ {price['usdt']} USDT (TRC20)\n\n"
            f"Choose a payment method below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("pay_"):
        payment_method, credits_amount = query.data.split("_")[1:]
        credits_amount = int(credits_amount)
        price = CREDIT_PRICES[credits_amount]
        
        if payment_method == "upi":
            await query.edit_message_text(
                f"ðŸ’³ *UPI Payment*\n\n"
                f"ðŸ’° *Amount:* â‚¹{price['inr']}\n"
                f"ðŸ“Š *Credits:* {credits_amount}\n\n"
                f"ðŸ“± *UPI ID:* example@upi\n\n"
                f"ðŸ“ *Steps:*\n"
                f"1. Send â‚¹{price['inr']} to the UPI ID above\n"
                f"2. Take a screenshot of the payment\n"
                f"3. Send the screenshot to @DataTraceSupport\n"
                f"4. Your credits will be added within 24 hours\n\n"
                f"ðŸ“ž *Need Help?*\n"
                f"Contact: @DataTraceSupport",
                parse_mode="Markdown"
            )
        elif payment_method == "usdt":
            await query.edit_message_text(
                f"ðŸ’³ *USDT Payment*\n\n"
                f"ðŸ’° *Amount:* {price['usdt']} USDT\n"
                f"ðŸ“Š *Credits:* {credits_amount}\n\n"
                f"ðŸ“± *Wallet Address:* TRC20_ADDRESS_HERE\n\n"
                f"ðŸ“ *Steps:*\n"
                f"1. Send {price['usdt']} USDT to the wallet address above\n"
                f"2. Take a screenshot of the payment\n"
                f"3. Send the screenshot to @DataTraceSupport\n"
                f"4. Your credits will be added within 24 hours\n\n"
                f"ðŸ“ž *Need Help?*\n"
                f"Contact: @DataTraceSupport",
                parse_mode="Markdown"
            )
    elif query.data == "back_to_menu":
        user = update.effective_user
        if not user:
            return
            
        user_id = user.id
        
        # Get user credits
        credits = get_user_credits(user_id)
        
        # Get referral code
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
        referral_code = cursor.fetchone()[0]
        conn.close()
        
        # Create referral link
        referral_link = f"https://t.me/{context.bot.username}?start={referral_code}"
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("ðŸ” Search", callback_data="search_menu")],
            [InlineKeyboardButton("ðŸ’³ My Credits", callback_data="my_credits")],
            [InlineKeyboardButton("ðŸ‘¥ Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("â„¹ï¸ Help", callback_data="help")],
            [InlineKeyboardButton("ðŸ“ž Contact Admin", url="https://t.me/DataTraceSupport")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"ðŸ‘‹ *Welcome to DataTrace OSINT Bot, {user.first_name}!*\n\n"
            f"ðŸ” *Your Credits:* {credits}\n\n"
            f"ðŸ“‹ *Features:*\n"
            f"â€¢ UPI to Information\n"
            f"â€¢ Number to Information\n"
            f"â€¢ Telegram User Stats\n"
            f"â€¢ IP to Details\n"
            f"â€¢ Pakistan Number to CNIC\n"
            f"â€¢ Aadhar to Family Details\n"
            f"â€¢ Aadhar to Details\n"
            f"â€¢ Call History (Paid)\n\n"
            f"ðŸ”— *Your Referral Link:*\n{referral_link}\n\n"
            f"Share this link with friends and earn credits!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("search_"):
        search_type = query.data.split("_")[1]
        
        if search_type == "upi":
            await query.edit_message_text(
                "ðŸ¦ *UPI to Information*\n\n"
                "Please send the UPI ID you want to search.\n\n"
                "Example: example@upi\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "num":
            await query.edit_message_text(
                "ðŸ“± *Number to Information*\n\n"
                "Please send the phone number you want to search.\n\n"
                "Example: 9876543210\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "tg":
            await query.edit_message_text(
                "ðŸ‘¤ *Telegram User Stats*\n\n"
                "Please send the Telegram user ID you want to search.\n\n"
                "Example: 123456789\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "ip":
            await query.edit_message_text(
                "ðŸŒ *IP to Details*\n\n"
                "Please send the IP address you want to search.\n\n"
                "Example: 8.8.8.8\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "pak":
            await query.edit_message_text(
                "ðŸ‡µðŸ‡° *Pakistan Number to CNIC*\n\n"
                "Please send the Pakistan phone number you want to search.\n\n"
                "Example: 3362006909\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "aadhar":
            await query.edit_message_text(
                "ðŸ†” *Aadhar to Details*\n\n"
                "Please send the Aadhar number you want to search.\n\n"
                "Example: 123456789012\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "family":
            await query.edit_message_text(
                "ðŸ‘¨â€ðŸ‘©â€ðŸ‘§ *Aadhar to Family Details*\n\n"
                "Please send the Aadhar number you want to search.\n\n"
                "Example: 123456789012\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "call":
            await query.edit_message_text(
                "ðŸ“ž *Call History (Paid - 600 credits)*\n\n"
                "Please send the phone number you want to search.\n\n"
                "Example: 9876543210\n\n"
                "ðŸ”™ Back to Menu",
                parse_mode="Markdown"
            )
    elif query.data.startswith("admin_"):
        if not is_sudo(user_id):
            await query.answer("You don't have permission to use this command.", show_alert=True)
            return
        
        admin_action = query.data.split("_")[1]
        
        if admin_action == "add_credits":
            await query.edit_message_text(
                "ðŸ‘¥ *Add Credits*\n\n"
                "Please use the command format:\n"
                "`/addcredits USER_ID AMOUNT`\n\n"
                "Example: `/addcredits 123456789 100`",
                parse_mode="Markdown"
            )
        elif admin_action == "ban_user":
            await query.edit_message_text(
                "ðŸš« *Ban/Unban User*\n\n"
                "Please use the command format:\n"
                "`/ban USER_ID` or `/unban USER_ID`\n\n"
                "Example: `/ban 123456789`",
                parse_mode="Markdown"
            )
        elif admin_action == "stats":
            try:
                conn = sqlite3.connect('datatrace.db')
                cursor = conn.cursor()
                
                # Get total users
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]
                
                # Get active users (used in last 7 days)
                cursor.execute("SELECT COUNT(*) FROM users WHERE last_used > date('now', '-7 days')")
                active_users = cursor.fetchone()[0]
                
                # Get banned users
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
                banned_users = cursor.fetchone()[0]
                
                # Get total searches
                cursor.execute("SELECT COUNT(*) FROM search_logs")
                total_searches = cursor.fetchone()[0]
                
                # Get searches today
                cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date > date('now')")
                today_searches = cursor.fetchone()[0]
                
                # Get total credits sold
                cursor.execute("SELECT SUM(credits) FROM transactions WHERE status = 'completed'")
                total_credits_sold = cursor.fetchone()[0] or 0
                
                # Get revenue
                cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'completed'")
                total_revenue = cursor.fetchone()[0] or 0
                
                conn.close()
                
                stats_text = "ðŸ“Š *Bot Statistics*\n\n"
                stats_text += f"ðŸ‘¥ *Users:*\n"
                stats_text += f"â€¢ Total: {total_users}\n"
                stats_text += f"â€¢ Active (7 days): {active_users}\n"
                stats_text += f"â€¢ Banned: {banned_users}\n\n"
                
                stats_text += f"ðŸ” *Searches:*\n"
                stats_text += f"â€¢ Total: {total_searches}\n"
                stats_text += f"â€¢ Today: {today_searches}\n\n"
                
                stats_text += f"ðŸ’° *Revenue:*\n"
                stats_text += f"â€¢ Credits Sold: {total_credits_sold}\n"
                stats_text += f"â€¢ Total Revenue: â‚¹{total_revenue:.2f}\n"
                
                keyboard = [
                    [InlineKeyboardButton("ðŸ”™ Back to Admin Panel", callback_data="admin_panel")],
                    [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in stats: {e}")
                await query.edit_message_text("âŒ An error occurred while fetching statistics.", parse_mode="Markdown")
        elif admin_action == "gcast":
            await query.edit_message_text(
                "ðŸ“¢ *Broadcast Message*\n\n"
                "Please use the command format:\n"
                "`/gcast Your message here`\n\n"
                "Example: `/gcast Hello everyone!`",
                parse_mode="Markdown"
            )
        elif admin_action == "protect_number":
            if not is_owner(user_id):
                await query.answer("Only the owner can use this function.", show_alert=True)
                return
            
            await query.edit_message_text(
                "ðŸ”’ *Protect Number*\n\n"
                "Please use the command format:\n"
                "`/protect NUMBER`\n\n"
                "Example: `/protect 9876543210`",
                parse_mode="Markdown"
            )
        elif admin_action == "blacklist_number":
            await query.edit_message_text(
                "â›” *Blacklist Number*\n\n"
                "Please use the command format:\n"
                "`/blacklist NUMBER` or `/unblacklist NUMBER`\n\n"
                "Example: `/blacklist 9876543210`",
                parse_mode="Markdown"
            )
        elif admin_action == "panel":
            keyboard = [
                [InlineKeyboardButton("ðŸ‘¥ Add Credits", callback_data="admin_add_credits")],
                [InlineKeyboardButton("ðŸš« Ban/Unban User", callback_data="admin_ban_user")],
                [InlineKeyboardButton("ðŸ“Š Bot Statistics", callback_data="admin_stats")],
                [InlineKeyboardButton("ðŸ“¢ Broadcast Message", callback_data="admin_gcast")],
                [InlineKeyboardButton("ðŸ”’ Protect Number", callback_data="admin_protect_number")],
                [InlineKeyboardButton("â›” Blacklist Number", callback_data="admin_blacklist_number")],
                [InlineKeyboardButton("ðŸ”™ Back to Menu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "ðŸ› ï¸ *Admin Panel*\n\n"
                "Choose an option below:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

# Message handlers
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Skip for channel posts
    if update.channel_post:
        return
        
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    message_text = update.message.text
    
    # Check if user is banned
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data and user_data[0] == 1:
        await update.message.reply_text("âŒ You are banned from using this bot.", parse_mode="Markdown")
        return
    
    # Check if user is member of required channels
    if not await is_user_member(context, user_id):
        await check_membership(update, context)
        return
    
    # Update last used
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_used = ? WHERE user_id = ?", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()
    
    # Check if message is a number
    if message_text.isdigit():
        # Check if it's a Pakistan number (starts with 92)
        if message_text.startswith("92"):
            # Handle as Pakistan number
            context.args = [message_text]
            await pak_handler(update, context)
        # Check if it's an Indian number (starts with 91)
        elif message_text.startswith("91"):
            # Handle as Indian number
            context.args = [message_text[2:]]
            await num_handler(update, context)
        else:
            # Handle as regular number
            context.args = [message_text]
            await num_handler(update, context)
    # Check if it's a UPI ID
    elif "@" in message_text and "." in message_text.split("@")[1]:
        # Handle as UPI ID
        context.args = [message_text]
        await upi_handler(update, context)
    # Check if it's an IP address
    elif "." in message_text and all(part.isdigit() for part in message_text.split(".")):
        # Handle as IP address
        context.args = [message_text]
        await ip_handler(update, context)
    else:
        # Unknown message type
        await update.message.reply_text(
            "âŒ I don't understand this message.\n\n"
            "Please use the buttons or commands to search for information.",
            parse_mode="Markdown"
        )

async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    
    # Check if user is banned
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data and user_data[0] == 1:
        return  # Don't reply to banned users
    
    # Check if message is a command or mentions the bot
    if message.text and (message.text.startswith('/') or f"@{context.bot.username}" in message.text):
        # Update last used
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_used = ? WHERE user_id = ?", 
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
        conn.commit()
        conn.close()
        
        # Check if message is a number
        if message.text.isdigit():
            # Check if it's a Pakistan number (starts with 92)
            if message.text.startswith("92"):
                # Handle as Pakistan number
                context.args = [message.text]
                await pak_handler(update, context)
            # Check if it's an Indian number (starts with 91)
            elif message.text.startswith("91"):
                # Handle as Indian number
                context.args = [message.text[2:]]
                await num_handler(update, context)
            else:
                # Handle as regular number
                context.args = [message.text]
                await num_handler(update, context)
        # Check if it's a UPI ID
        elif "@" in message.text and "." in message.text.split("@")[1]:
            # Handle as UPI ID
            context.args = [message.text]
            await upi_handler(update, context)
        # Check if it's an IP address
        elif "." in message.text and all(part.isdigit() for part in message.text.split(".")):
            # Handle as IP address
            context.args = [message.text]
            await ip_handler(update, context)
        else:
            # Unknown message type
            return  # Don't reply in groups for unknown messages

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    # Initialize database
    init_db()
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("upi", "Get UPI details"),
        BotCommand("num", "Get number details"),
        BotCommand("tg", "Get Telegram user stats"),
        BotCommand("ip", "Get IP details"),
        BotCommand("pak", "Get Pakistan number to CNIC"),
        BotCommand("aadhar", "Get Aadhar details"),
        BotCommand("family", "Get Aadhar family details"),
        BotCommand("call", "Get call history (Paid)"),
        BotCommand("credits", "Check your credits"),
        BotCommand("buy", "Buy more credits"),
        BotCommand("refer", "Get your referral link"),
        BotCommand("admin", "Open admin panel"),
        BotCommand("addcredits", "Add credits to user (Admin)"),
        BotCommand("ban", "Ban a user (Admin)"),
        BotCommand("unban", "Unban a user (Admin)"),
        BotCommand("stats", "View bot statistics (Admin)"),
        BotCommand("gcast", "Broadcast message (Admin)"),
        BotCommand("protect", "Protect a number (Owner)"),
        BotCommand("unprotect", "Unprotect a number (Owner)"),
        BotCommand("blacklist", "Blacklist a number (Admin)"),
        BotCommand("unblacklist", "Unblacklist a number (Admin)")
    ]
    application.bot.set_my_commands(commands)
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("credits", credits_command))
    application.add_handler(CommandHandler("refer", refer_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("upi", upi_handler))
    application.add_handler(CommandHandler("num", num_handler))
    application.add_handler(CommandHandler("tg", tg_handler))
    application.add_handler(CommandHandler("ip", ip_handler))
    application.add_handler(CommandHandler("pak", pak_handler))
    application.add_handler(CommandHandler("aadhar", aadhar_handler))
    application.add_handler(CommandHandler("family", family_handler))
    application.add_handler(CommandHandler("call", call_handler))
    
    # Admin commands
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("addcredits", addcredits_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("gcast", gcast_command))
    application.add_handler(CommandHandler("protect", protect_command))
    application.add_handler(CommandHandler("unprotect", unprotect_command))
    application.add_handler(CommandHandler("blacklist", blacklist_command))
    application.add_handler(CommandHandler("unblacklist", unblacklist_command))
    
    # Register callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, group_message_handler))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
