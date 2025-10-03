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
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
    filters,
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN_HERE")

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

def is_user_member(context: CallbackContext, user_id: int) -> bool:
    bot = context.bot
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.error(f"Error checking membership for channel {channel['username']}: {e}")
            return False
    return True

def check_membership(update: Update, context: CallbackContext) -> bool:
    user_id = update.effective_user.id
    if not is_user_member(context, user_id):
        keyboard = []
        for channel in REQUIRED_CHANNELS:
            keyboard.append([InlineKeyboardButton(f"Join {channel['username']}", url=f"https://t.me/{channel['username']}")])
        keyboard.append([InlineKeyboardButton("✅ I've joined all channels", callback_data="check_membership")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            "🚫 *You must join all required channels to use this bot*\n\n"
            "Please join the channels below and then click the button:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return False
    return True

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

def log_to_channel(context: CallbackContext, channel_id: int, message: str):
    try:
        context.bot.send_message(chat_id=channel_id, text=message, parse_mode="Markdown")
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
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    
    # Log to start channel
    log_message = f"🆕 *New User Started*\n\n"
    log_message += f"👤 Name: {user.first_name} {user.last_name if user.last_name else ''}\n"
    log_message += f"🔖 Username: @{user.username if user.username else 'N/A'}\n"
    log_message += f"🆔 User ID: {user_id}\n"
    log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    log_to_channel(context, START_LOG_CHANNEL, log_message)
    
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
    if not check_membership(update, context):
        return
    
    # Get user credits
    credits = get_user_credits(user_id)
    
    # Create referral link
    referral_link = f"https://t.me/{context.bot.username}?start={new_referral_code}"
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("🔍 Search", callback_data="search_menu")],
        [InlineKeyboardButton("💳 My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 *Welcome to DataTrace OSINT Bot, {user.first_name}!*\n\n"
        f"🔍 *Your Credits:* {credits}\n\n"
        f"📋 *Features:*\n"
        f"• UPI to Information\n"
        f"• Number to Information\n"
        f"• Telegram User Stats\n"
        f"• IP to Details\n"
        f"• Pakistan Number to CNIC\n"
        f"• Aadhar to Family Details\n"
        f"• Aadhar to Details\n"
        f"• Call History (Paid)\n\n"
        f"🔗 *Your Referral Link:*\n{referral_link}\n\n"
        f"Share this link with friends and earn credits!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def help_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    help_text = "📖 *DataTrace OSINT Bot Help*\n\n"
    help_text += "🔍 *Search Commands:*\n"
    help_text += "• `/upi [UPI_ID]` - Get UPI details\n"
    help_text += "• `/num [NUMBER]` - Get number details\n"
    help_text += "• `/tg [USER_ID]` - Get Telegram user stats\n"
    help_text += "• `/ip [IP_ADDRESS]` - Get IP details\n"
    help_text += "• `/pak [NUMBER]` - Get Pakistan number to CNIC\n"
    help_text += "• `/aadhar [AADHAR_NUMBER]` - Get Aadhar details\n"
    help_text += "• `/family [AADHAR_NUMBER]` - Get Aadhar family details\n"
    help_text += "• `/call [NUMBER]` - Get call history (Paid - 600 credits)\n\n"
    
    help_text += "💳 *Credit Commands:*\n"
    help_text += "• `/credits` - Check your credits\n"
    help_text += "• `/buy` - Buy more credits\n"
    help_text += "• `/refer` - Get your referral link\n\n"
    
    help_text += "🔧 *Other Commands:*\n"
    help_text += "• `/start` - Start the bot\n"
    help_text += "• `/help` - Show this help message\n\n"
    
    if is_sudo(user_id):
        help_text += "🛠️ *Admin Commands:*\n"
        help_text += "• `/admin` - Open admin panel\n"
        help_text += "• `/addcredits [USER_ID] [AMOUNT]` - Add credits to user\n"
        help_text += "• `/ban [USER_ID]` - Ban a user\n"
        help_text += "• `/unban [USER_ID]` - Unban a user\n"
        help_text += "• `/stats` - View bot statistics\n"
        help_text += "• `/gcast [MESSAGE]` - Broadcast message to all users\n"
        help_text += "• `/protect [NUMBER]` - Add a number to protected list\n"
        help_text += "• `/unprotect [NUMBER]` - Remove a number from protected list\n"
        help_text += "• `/blacklist [NUMBER]` - Add a number to blacklist\n"
        help_text += "• `/unblacklist [NUMBER]` - Remove a number from blacklist\n\n"
    
    help_text += "📞 *Need Help?*\n"
    help_text += "Contact: @DataTraceSupport\n\n"
    help_text += "🤝 *Referral Program:*\n"
    help_text += "Share your referral link and earn 30% commission when your referrals buy credits!"
    
    update.message.reply_text(help_text, parse_mode="Markdown")

def credits_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
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
        [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"💳 *Your Credits: {credits}*\n\n"
        f"👥 *Referral Stats:*\n"
        f"• Referrals: {referral_count}\n"
        f"• Credits Earned: {credits_earned}\n\n"
        f"🔗 *Your Referral Link:*\n{referral_link}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def refer_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
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
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"🤝 *Referral Program*\n\n"
        f"Share your referral link and earn rewards!\n\n"
        f"🔗 *Your Referral Link:*\n{referral_link}\n\n"
        f"📋 *How it works:*\n"
        f"• Share your personal referral link\n"
        f"• When someone starts the bot using your link, they get 1 free credit\n"
        f"• Whenever your referral buys credits, you earn 30% commission (in credits)\n\n"
        f"📊 *Example:*\n"
        f"• Friend joins → They get 1 free credit\n"
        f"• Friend buys 1000 credits → You get 300 credits commission\n"
        f"• Friend buys 5000 credits → You get 1500 credits commission",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def buy_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    keyboard = []
    for credits, price in CREDIT_PRICES.items():
        keyboard.append([
            InlineKeyboardButton(f"💳 {credits} Credits - ₹{price['inr']} | {price['usdt']} USDT", 
                               callback_data=f"buy_{credits}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("📞 Contact Admin for Custom Plans", url="https://t.me/DataTraceSupport")
    ])
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "💳 *Buy Credits*\n\n"
        "Choose a credit package below:\n\n"
        "💰 *Payment Methods:*\n"
        "• UPI\n"
        "• USDT (TRC20)\n\n"
        "📞 *Need Help?*\n"
        "Contact: @DataTraceSupport",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# API handlers
def upi_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide a UPI ID.\n\nUsage: `/upi example@upi`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["upi_info"].format(upi_id=upi_id))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            bank_details = data.get("bank_details_raw", {})
            vpa_details = data.get("vpa_details", {})
            
            result_text = "🏦 *UPI DETAILS*\n\n"
            result_text += "👤 *ACCOUNT HOLDER*\n"
            result_text += f"NAME: {vpa_details.get('name', 'N/A')}\n"
            result_text += f"VPA: {vpa_details.get('vpa', 'N/A')}\n\n"
            
            result_text += "🏦 *BANK DETAILS*\n"
            result_text += f"BANK: {bank_details.get('BANK', 'N/A')}\n"
            result_text += f"BRANCH: {bank_details.get('BRANCH', 'N/A')}\n"
            result_text += f"CITY: {bank_details.get('CITY', 'N/A')}\n"
            result_text += f"DISTRICT: {bank_details.get('DISTRICT', 'N/A')}\n"
            result_text += f"STATE: {bank_details.get('STATE', 'N/A')}\n"
            result_text += f"ADDRESS: {bank_details.get('ADDRESS', 'N/A')}\n"
            result_text += f"IFSC: {bank_details.get('IFSC', 'N/A')}\n"
            result_text += f"MICR: {bank_details.get('MICR', 'N/A')}\n"
            result_text += f"IMPS: {'✅' if bank_details.get('IMPS') else '❌'}\n"
            result_text += f"NEFT: {'✅' if bank_details.get('NEFT') else '❌'}\n"
            result_text += f"RTGS: {'✅' if bank_details.get('RTGS') else '❌'}\n"
            result_text += f"UPI: {'✅' if bank_details.get('UPI') else '❌'}\n"
            
            # Add branding
            result_text += "\n\n🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "upi", upi_id, 1)
            
            # Log to channel
            log_message = f"🔍 *UPI Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {upi_id}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this UPI ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in UPI lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching UPI information. Please try again later.", parse_mode="Markdown")

def num_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide a phone number.\n\nUsage: `/num 9876543210`", parse_mode="Markdown")
        return
    
    # Check if number is blacklisted
    if is_blacklisted_number(number):
        update.message.reply_text("❌ This number is blacklisted and cannot be searched.", parse_mode="Markdown")
        return
    
    # Check if number is protected (only owner can check)
    if is_protected_number(number) and not is_owner(user_id):
        update.message.reply_text("❌ This number is protected and cannot be searched.", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["num_info"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data.get("data"):
            # Format response
            result = data["data"][0]
            
            result_text = "📱 *NUMBER DETAILS*\n\n"
            result_text += f"MOBILE: {result.get('mobile', 'N/A')}\n"
            result_text += f"ALT MOBILE: {result.get('alt', 'N/A')}\n"
            result_text += f"NAME: {result.get('name', 'N/A')}\n"
            result_text += f"FULL NAME: {result.get('fname', 'N/A')}\n"
            result_text += f"ADDRESS: {result.get('address', 'N/A').replace('!', ', ')}\n"
            result_text += f"CIRCLE: {result.get('circle', 'N/A')}\n"
            result_text += f"ID: {result.get('id', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\n🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "num", number, len(data["data"]))
            
            # Log to channel
            log_message = f"🔍 *Number Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {number}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in number lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching number information. Please try again later.", parse_mode="Markdown")

def tg_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide a Telegram user ID.\n\nUsage: `/tg 123456789`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["tg_user_stats"].format(user_id=tg_user_id))
        data = response.json()
        
        if response.status_code == 200 and data.get("success"):
            # Format response
            user_data = data["data"]
            
            result_text = "👤 *TELEGRAM USER STATS*\n\n"
            result_text += f"NAME: {user_data.get('first_name', 'N/A')} {user_data.get('last_name', '')}\n"
            result_text += f"USER ID: {user_data.get('id', 'N/A')}\n"
            result_text += f"IS BOT: {'✅' if user_data.get('is_bot') else '❌'}\n"
            result_text += f"ACTIVE: {'✅' if user_data.get('is_active') else '❌'}\n\n"
            
            result_text += "📊 *STATS*\n"
            result_text += f"TOTAL GROUPS: {user_data.get('total_groups', 'N/A')}\n"
            result_text += f"ADMIN IN GROUPS: {user_data.get('adm_in_groups', 'N/A')}\n"
            result_text += f"TOTAL MESSAGES: {user_data.get('total_msg_count', 'N/A')}\n"
            result_text += f"MESSAGES IN GROUPS: {user_data.get('msg_in_groups_count', 'N/A')}\n\n"
            
            result_text += "🕐 *DATES*\n"
            result_text += f"FIRST MSG DATE: {user_data.get('first_msg_date', 'N/A')[:10]}\n"
            result_text += f"LAST MSG DATE: {user_data.get('last_msg_date', 'N/A')[:10]}\n\n"
            
            result_text += "🔄 *CHANGES*\n"
            result_text += f"NAME CHANGES: {user_data.get('names_count', 'N/A')}\n"
            result_text += f"USERNAME CHANGES: {user_data.get('usernames_count', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\n🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "tg", tg_user_id, 1)
            
            # Log to channel
            log_message = f"🔍 *Telegram User Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {tg_user_id}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this Telegram user.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Telegram user lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching Telegram user information. Please try again later.", parse_mode="Markdown")

def ip_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide an IP address.\n\nUsage: `/ip 8.8.8.8`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["ip_details"].format(ip=ip))
        data = response.text
        
        if response.status_code == 200 and data:
            # Format response (API returns formatted text)
            result_text = f"🌐 *IP DETAILS*\n\n{data}\n\n"
            
            # Add branding
            result_text += "🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "ip", ip, 1)
            
            # Log to channel
            log_message = f"🔍 *IP Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {ip}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this IP address.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in IP lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching IP information. Please try again later.", parse_mode="Markdown")

def pak_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide a Pakistan phone number.\n\nUsage: `/pak 3362006909`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["pak_num"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data.get("results"):
            # Format response
            results = data["results"]
            
            result_text = "🇵🇰 *PAKISTAN INFO*\n\n"
            
            for i, result in enumerate(results, 1):
                result_text += f"{i}️⃣\n"
                result_text += f"NAME: {result.get('Name', 'N/A')}\n"
                result_text += f"CNIC: {result.get('CNIC', 'N/A')}\n"
                result_text += f"MOBILE: {result.get('Mobile', 'N/A')}\n"
                result_text += f"ADDRESS: {result.get('Address', 'Not Available')}\n\n"
            
            # Add branding
            result_text += "🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "pak", number, len(results))
            
            # Log to channel
            log_message = f"🔍 *Pakistan Number Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {number}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this Pakistan number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Pakistan number lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching Pakistan number information. Please try again later.", parse_mode="Markdown")

def aadhar_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide an Aadhar number.\n\nUsage: `/aadhar 123456789012`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["aadhar_details"].format(aadhaar=aadhar))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "🆔 *AADHAR DETAILS*\n\n"
            
            for i, result in enumerate(data, 1):
                result_text += f"{i}️⃣\n"
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
            result_text += "🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "aadhar", aadhar, len(data))
            
            # Log to channel
            log_message = f"🔍 *Aadhar Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {aadhar}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this Aadhar number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Aadhar lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching Aadhar information. Please try again later.", parse_mode="Markdown")

def family_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits <= 0:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide an Aadhar number.\n\nUsage: `/family 123456789012`", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["aadhar_family"].format(aadhaar=aadhar))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "🆔 *AADHAR FAMILY INFO*\n\n"
            result_text += f"RC ID: {data.get('rcId', 'N/A')}\n"
            result_text += f"SCHEME: {data.get('schemeName', 'N/A')} ({data.get('schemeId', 'N/A')})\n"
            result_text += f"DISTRICT: {data.get('homeDistName', 'N/A')}\n"
            result_text += f"STATE: {data.get('homeStateName', 'N/A')}\n"
            result_text += f"FPS ID: {data.get('fpsId', 'N/A')}\n\n"
            
            result_text += "👨‍👩‍👧 *FAMILY MEMBERS:*\n"
            
            members = data.get("memberDetailsList", [])
            for i, member in enumerate(members, 1):
                result_text += f"{i}️⃣ {member.get('memberName', 'N/A')} — {member.get('releationship_name', 'N/A')}\n"
            
            # Add branding
            result_text += "\n\n🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 1, "subtract")
            
            # Log search
            log_search(user_id, "family", aadhar, len(members))
            
            # Log to channel
            log_message = f"🔍 *Aadhar Family Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {aadhar}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this Aadhar number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in Aadhar family lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching Aadhar family information. Please try again later.", parse_mode="Markdown")

def call_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Check if user is member of required channels
    if not check_membership(update, context):
        return
    
    # Check if user has credits
    credits = get_user_credits(user_id)
    if credits < 600:
        keyboard = [
            [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            f"❌ *Insufficient Credits*\n\n"
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
        update.message.reply_text("❌ Please provide a phone number.\n\nUsage: `/call 9876543210`", parse_mode="Markdown")
        return
    
    # Check if number is blacklisted
    if is_blacklisted_number(number):
        update.message.reply_text("❌ This number is blacklisted and cannot be searched.", parse_mode="Markdown")
        return
    
    # Check if number is protected (only owner can check)
    if is_protected_number(number) and not is_owner(user_id):
        update.message.reply_text("❌ This number is protected and cannot be searched.", parse_mode="Markdown")
        return
    
    # Send typing action
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Call API
        response = requests.get(API_ENDPOINTS["call_history"].format(number=number))
        data = response.json()
        
        if response.status_code == 200 and data:
            # Format response
            result_text = "📞 *CALL HISTORY*\n\n"
            
            # Assuming the API returns a list of calls
            calls = data if isinstance(data, list) else [data]
            
            for i, call in enumerate(calls[:10], 1):  # Limit to 10 calls
                result_text += f"{i}️⃣\n"
                result_text += f"DATE: {call.get('date', 'N/A')}\n"
                result_text += f"TIME: {call.get('time', 'N/A')}\n"
                result_text += f"TYPE: {call.get('type', 'N/A')}\n"
                result_text += f"DURATION: {call.get('duration', 'N/A')}\n"
                result_text += f"NUMBER: {call.get('number', 'N/A')}\n\n"
            
            # Add branding
            result_text += "🔍 *Powered by DataTrace OSINT*\n"
            result_text += "📞 *Contact Admin: @DataTraceSupport*"
            
            # Update user credits
            update_user_credits(user_id, 600, "subtract")
            
            # Log search
            log_search(user_id, "call", number, len(calls))
            
            # Log to channel
            log_message = f"🔍 *Call History Search*\n\n"
            log_message += f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            log_message += f"🔍 Query: {number}\n"
            log_message += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            log_to_channel(context, SEARCH_LOG_CHANNEL, log_message)
            
            update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            update.message.reply_text("❌ No information found for this number.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in call history lookup: {e}")
        update.message.reply_text("❌ An error occurred while fetching call history. Please try again later.", parse_mode="Markdown")

# Admin commands
def admin_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 Add Credits", callback_data="admin_add_credits")],
        [InlineKeyboardButton("🚫 Ban/Unban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_gcast")],
        [InlineKeyboardButton("🔒 Protect Number", callback_data="admin_protect_number")],
        [InlineKeyboardButton("⛔ Blacklist Number", callback_data="admin_blacklist_number")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🛠️ *Admin Panel*\n\n"
        "Choose an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def addcredits_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 2:
        update.message.reply_text("❌ Please provide a user ID and amount.\n\nUsage: `/addcredits 123456789 100`", parse_mode="Markdown")
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        
        # Update user credits
        update_user_credits(target_user_id, amount, "add")
        
        # Get user info
        try:
            user = context.bot.get_chat(target_user_id)
            user_info = f"{user.first_name} (@{user.username if user.username else 'N/A'})"
        except:
            user_info = f"User ID: {target_user_id}"
        
        update.message.reply_text(
            f"✅ *Credits Added*\n\n"
            f"User: {user_info}\n"
            f"Amount: {amount} credits",
            parse_mode="Markdown"
        )
    except ValueError:
        update.message.reply_text("❌ Invalid input. Please provide a valid user ID and amount.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in addcredits: {e}")
        update.message.reply_text("❌ An error occurred while adding credits.", parse_mode="Markdown")

def ban_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a user ID.\n\nUsage: `/ban 123456789`", parse_mode="Markdown")
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
            user = context.bot.get_chat(target_user_id)
            user_info = f"{user.first_name} (@{user.username if user.username else 'N/A'})"
        except:
            user_info = f"User ID: {target_user_id}"
        
        update.message.reply_text(
            f"✅ *User Banned*\n\n"
            f"User: {user_info}",
            parse_mode="Markdown"
        )
    except ValueError:
        update.message.reply_text("❌ Invalid input. Please provide a valid user ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in ban: {e}")
        update.message.reply_text("❌ An error occurred while banning the user.", parse_mode="Markdown")

def unban_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a user ID.\n\nUsage: `/unban 123456789`", parse_mode="Markdown")
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
            user = context.bot.get_chat(target_user_id)
            user_info = f"{user.first_name} (@{user.username if user.username else 'N/A'})"
        except:
            user_info = f"User ID: {target_user_id}"
        
        update.message.reply_text(
            f"✅ *User Unbanned*\n\n"
            f"User: {user_info}",
            parse_mode="Markdown"
        )
    except ValueError:
        update.message.reply_text("❌ Invalid input. Please provide a valid user ID.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in unban: {e}")
        update.message.reply_text("❌ An error occurred while unbanning the user.", parse_mode="Markdown")

def stats_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
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
        
        stats_text = "📊 *Bot Statistics*\n\n"
        stats_text += f"👥 *Users:*\n"
        stats_text += f"• Total: {total_users}\n"
        stats_text += f"• Active (7 days): {active_users}\n"
        stats_text += f"• Banned: {banned_users}\n\n"
        
        stats_text += f"🔍 *Searches:*\n"
        stats_text += f"• Total: {total_searches}\n"
        stats_text += f"• Today: {today_searches}\n\n"
        
        stats_text += f"💰 *Revenue:*\n"
        stats_text += f"• Credits Sold: {total_credits_sold}\n"
        stats_text += f"• Total Revenue: ₹{total_revenue:.2f}\n"
        
        update.message.reply_text(stats_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        update.message.reply_text("❌ An error occurred while fetching statistics.", parse_mode="Markdown")

def gcast_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a message to broadcast.\n\nUsage: `/gcast Your message here`", parse_mode="Markdown")
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
                context.bot.send_message(chat_id=user[0], text=message)
                success_count += 1
            except:
                fail_count += 1
        
        update.message.reply_text(
            f"✅ *Broadcast Completed*\n\n"
            f"• Success: {success_count}\n"
            f"• Failed: {fail_count}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in gcast: {e}")
        update.message.reply_text("❌ An error occurred while broadcasting the message.", parse_mode="Markdown")

def protect_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        update.message.reply_text("❌ Only the owner can use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a number to protect.\n\nUsage: `/protect 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO protected_numbers (number, added_by, added_date) VALUES (?, ?, ?)",
                      (number, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        update.message.reply_text(
            f"✅ *Number Protected*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in protect: {e}")
        update.message.reply_text("❌ An error occurred while protecting the number.", parse_mode="Markdown")

def unprotect_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        update.message.reply_text("❌ Only the owner can use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a number to unprotect.\n\nUsage: `/unprotect 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    try:
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM protected_numbers WHERE number = ?", (number,))
        conn.commit()
        conn.close()
        
        update.message.reply_text(
            f"✅ *Number Unprotected*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in unprotect: {e}")
        update.message.reply_text("❌ An error occurred while unprotecting the number.", parse_mode="Markdown")

def blacklist_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a number to blacklist.\n\nUsage: `/blacklist 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    if number not in BLACKLISTED_NUMBERS:
        BLACKLISTED_NUMBERS.append(number)
        update.message.reply_text(
            f"✅ *Number Blacklisted*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text("❌ This number is already blacklisted.", parse_mode="Markdown")

def unblacklist_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_sudo(user_id):
        update.message.reply_text("❌ You don't have permission to use this command.", parse_mode="Markdown")
        return
    
    if len(context.args) < 1:
        update.message.reply_text("❌ Please provide a number to unblacklist.\n\nUsage: `/unblacklist 9876543210`", parse_mode="Markdown")
        return
    
    number = context.args[0]
    
    if number in BLACKLISTED_NUMBERS:
        BLACKLISTED_NUMBERS.remove(number)
        update.message.reply_text(
            f"✅ *Number Unblacklisted*\n\n"
            f"Number: {number}",
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text("❌ This number is not blacklisted.", parse_mode="Markdown")

# Callback query handlers
def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "check_membership":
        if is_user_member(context, user_id):
            query.edit_message_text(
                "✅ *Verification Successful*\n\n"
                "You can now use the bot. Click /start to continue.",
                parse_mode="Markdown"
            )
        else:
            query.edit_message_text(
                "❌ *Verification Failed*\n\n"
                "You haven't joined all required channels. Please join all channels and try again.",
                parse_mode="Markdown"
            )
    elif query.data == "search_menu":
        keyboard = [
            [InlineKeyboardButton("🏦 UPI to Info", callback_data="search_upi")],
            [InlineKeyboardButton("📱 Number to Info", callback_data="search_num")],
            [InlineKeyboardButton("👤 Telegram User Stats", callback_data="search_tg")],
            [InlineKeyboardButton("🌐 IP to Details", callback_data="search_ip")],
            [InlineKeyboardButton("🇵🇰 Pakistan Number to CNIC", callback_data="search_pak")],
            [InlineKeyboardButton("🆔 Aadhar to Details", callback_data="search_aadhar")],
            [InlineKeyboardButton("👨‍👩‍👧 Aadhar to Family", callback_data="search_family")],
            [InlineKeyboardButton("📞 Call History (Paid)", callback_data="search_call")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "🔍 *Search Menu*\n\n"
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
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"💳 *Your Credits: {credits}*\n\n"
            f"👥 *Referral Stats:*\n"
            f"• Referrals: {referral_count}\n"
            f"• Credits Earned: {credits_earned}\n\n"
            f"🔗 *Your Referral Link:*\n{referral_link}",
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
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"🤝 *Referral Program*\n\n"
            f"Share your referral link and earn rewards!\n\n"
            f"🔗 *Your Referral Link:*\n{referral_link}\n\n"
            f"📋 *How it works:*\n"
            f"• Share your personal referral link\n"
            f"• When someone starts the bot using your link, they get 1 free credit\n"
            f"• Whenever your referral buys credits, you earn 30% commission (in credits)\n\n"
            f"📊 *Example:*\n"
            f"• Friend joins → They get 1 free credit\n"
            f"• Friend buys 1000 credits → You get 300 credits commission\n"
            f"• Friend buys 5000 credits → You get 1500 credits commission",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data == "help":
        help_text = "📖 *DataTrace OSINT Bot Help*\n\n"
        help_text += "🔍 *Search Commands:*\n"
        help_text += "• `/upi [UPI_ID]` - Get UPI details\n"
        help_text += "• `/num [NUMBER]` - Get number details\n"
        help_text += "• `/tg [USER_ID]` - Get Telegram user stats\n"
        help_text += "• `/ip [IP_ADDRESS]` - Get IP details\n"
        help_text += "• `/pak [NUMBER]` - Get Pakistan number to CNIC\n"
        help_text += "• `/aadhar [AADHAR_NUMBER]` - Get Aadhar details\n"
        help_text += "• `/family [AADHAR_NUMBER]` - Get Aadhar family details\n"
        help_text += "• `/call [NUMBER]` - Get call history (Paid - 600 credits)\n\n"
        
        help_text += "💳 *Credit Commands:*\n"
        help_text += "• `/credits` - Check your credits\n"
        help_text += "• `/buy` - Buy more credits\n"
        help_text += "• `/refer` - Get your referral link\n\n"
        
        help_text += "🔧 *Other Commands:*\n"
        help_text += "• `/start` - Start the bot\n"
        help_text += "• `/help` - Show this help message\n\n"
        
        if is_sudo(user_id):
            help_text += "🛠️ *Admin Commands:*\n"
            help_text += "• `/admin` - Open admin panel\n"
            help_text += "• `/addcredits [USER_ID] [AMOUNT]` - Add credits to user\n"
            help_text += "• `/ban [USER_ID]` - Ban a user\n"
            help_text += "• `/unban [USER_ID]` - Unban a user\n"
            help_text += "• `/stats` - View bot statistics\n"
            help_text += "• `/gcast [MESSAGE]` - Broadcast message to all users\n"
            help_text += "• `/protect [NUMBER]` - Add a number to protected list\n"
            help_text += "• `/unprotect [NUMBER]` - Remove a number from protected list\n"
            help_text += "• `/blacklist [NUMBER]` - Add a number to blacklist\n"
            help_text += "• `/unblacklist [NUMBER]` - Remove a number from blacklist\n\n"
        
        help_text += "📞 *Need Help?*\n"
        help_text += "Contact: @DataTraceSupport\n\n"
        help_text += "🤝 *Referral Program:*\n"
        help_text += "Share your referral link and earn 30% commission when your referrals buy credits!"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif query.data == "buy_credits":
        keyboard = []
        for credits, price in CREDIT_PRICES.items():
            keyboard.append([
                InlineKeyboardButton(f"💳 {credits} Credits - ₹{price['inr']} | {price['usdt']} USDT", 
                                   callback_data=f"buy_{credits}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("📞 Contact Admin for Custom Plans", url="https://t.me/DataTraceSupport")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "💳 *Buy Credits*\n\n"
            "Choose a credit package below:\n\n"
            "💰 *Payment Methods:*\n"
            "• UPI\n"
            "• USDT (TRC20)\n\n"
            "📞 *Need Help?*\n"
            "Contact: @DataTraceSupport",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("buy_"):
        credits_amount = int(query.data.split("_")[1])
        price = CREDIT_PRICES[credits_amount]
        
        keyboard = [
            [InlineKeyboardButton("💸 Pay with UPI", callback_data=f"pay_upi_{credits_amount}")],
            [InlineKeyboardButton("💸 Pay with USDT", callback_data=f"pay_usdt_{credits_amount}")],
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")],
            [InlineKeyboardButton("🔙 Back", callback_data="buy_credits")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"💳 *Buy {credits_amount} Credits*\n\n"
            f"💰 *Price:*\n"
            f"• ₹{price['inr']} (UPI)\n"
            f"• {price['usdt']} USDT (TRC20)\n\n"
            f"Choose a payment method below:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("pay_"):
        payment_method, credits_amount = query.data.split("_")[1:]
        credits_amount = int(credits_amount)
        price = CREDIT_PRICES[credits_amount]
        
        if payment_method == "upi":
            query.edit_message_text(
                f"💳 *UPI Payment*\n\n"
                f"💰 *Amount:* ₹{price['inr']}\n"
                f"📊 *Credits:* {credits_amount}\n\n"
                f"📱 *UPI ID:* example@upi\n\n"
                f"📝 *Steps:*\n"
                f"1. Send ₹{price['inr']} to the UPI ID above\n"
                f"2. Take a screenshot of the payment\n"
                f"3. Send the screenshot to @DataTraceSupport\n"
                f"4. Your credits will be added within 24 hours\n\n"
                f"📞 *Need Help?*\n"
                f"Contact: @DataTraceSupport",
                parse_mode="Markdown"
            )
        elif payment_method == "usdt":
            query.edit_message_text(
                f"💳 *USDT Payment*\n\n"
                f"💰 *Amount:* {price['usdt']} USDT\n"
                f"📊 *Credits:* {credits_amount}\n\n"
                f"📱 *Wallet Address:* TRC20_ADDRESS_HERE\n\n"
                f"📝 *Steps:*\n"
                f"1. Send {price['usdt']} USDT to the wallet address above\n"
                f"2. Take a screenshot of the payment\n"
                f"3. Send the screenshot to @DataTraceSupport\n"
                f"4. Your credits will be added within 24 hours\n\n"
                f"📞 *Need Help?*\n"
                f"Contact: @DataTraceSupport",
                parse_mode="Markdown"
            )
    elif query.data == "back_to_menu":
        user = update.effective_user
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
            [InlineKeyboardButton("🔍 Search", callback_data="search_menu")],
            [InlineKeyboardButton("💳 My Credits", callback_data="my_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"👋 *Welcome to DataTrace OSINT Bot, {user.first_name}!*\n\n"
            f"🔍 *Your Credits:* {credits}\n\n"
            f"📋 *Features:*\n"
            f"• UPI to Information\n"
            f"• Number to Information\n"
            f"• Telegram User Stats\n"
            f"• IP to Details\n"
            f"• Pakistan Number to CNIC\n"
            f"• Aadhar to Family Details\n"
            f"• Aadhar to Details\n"
            f"• Call History (Paid)\n\n"
            f"🔗 *Your Referral Link:*\n{referral_link}\n\n"
            f"Share this link with friends and earn credits!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif query.data.startswith("search_"):
        search_type = query.data.split("_")[1]
        
        if search_type == "upi":
            query.edit_message_text(
                "🏦 *UPI to Information*\n\n"
                "Please send the UPI ID you want to search.\n\n"
                "Example: example@upi\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "num":
            query.edit_message_text(
                "📱 *Number to Information*\n\n"
                "Please send the phone number you want to search.\n\n"
                "Example: 9876543210\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "tg":
            query.edit_message_text(
                "👤 *Telegram User Stats*\n\n"
                "Please send the Telegram user ID you want to search.\n\n"
                "Example: 123456789\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "ip":
            query.edit_message_text(
                "🌐 *IP to Details*\n\n"
                "Please send the IP address you want to search.\n\n"
                "Example: 8.8.8.8\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "pak":
            query.edit_message_text(
                "🇵🇰 *Pakistan Number to CNIC*\n\n"
                "Please send the Pakistan phone number you want to search.\n\n"
                "Example: 3362006909\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "aadhar":
            query.edit_message_text(
                "🆔 *Aadhar to Details*\n\n"
                "Please send the Aadhar number you want to search.\n\n"
                "Example: 123456789012\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "family":
            query.edit_message_text(
                "👨‍👩‍👧 *Aadhar to Family Details*\n\n"
                "Please send the Aadhar number you want to search.\n\n"
                "Example: 123456789012\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
        elif search_type == "call":
            query.edit_message_text(
                "📞 *Call History (Paid - 600 credits)*\n\n"
                "Please send the phone number you want to search.\n\n"
                "Example: 9876543210\n\n"
                "🔙 Back to Menu",
                parse_mode="Markdown"
            )
    elif query.data.startswith("admin_"):
        if not is_sudo(user_id):
            query.answer("You don't have permission to use this command.", show_alert=True)
            return
        
        admin_action = query.data.split("_")[1]
        
        if admin_action == "add_credits":
            query.edit_message_text(
                "👥 *Add Credits*\n\n"
                "Please use the command format:\n"
                "`/addcredits USER_ID AMOUNT`\n\n"
                "Example: `/addcredits 123456789 100`",
                parse_mode="Markdown"
            )
        elif admin_action == "ban_user":
            query.edit_message_text(
                "🚫 *Ban/Unban User*\n\n"
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
                
                stats_text = "📊 *Bot Statistics*\n\n"
                stats_text += f"👥 *Users:*\n"
                stats_text += f"• Total: {total_users}\n"
                stats_text += f"• Active (7 days): {active_users}\n"
                stats_text += f"• Banned: {banned_users}\n\n"
                
                stats_text += f"🔍 *Searches:*\n"
                stats_text += f"• Total: {total_searches}\n"
                stats_text += f"• Today: {today_searches}\n\n"
                
                stats_text += f"💰 *Revenue:*\n"
                stats_text += f"• Credits Sold: {total_credits_sold}\n"
                stats_text += f"• Total Revenue: ₹{total_revenue:.2f}\n"
                
                keyboard = [
                    [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")],
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in stats: {e}")
                query.edit_message_text("❌ An error occurred while fetching statistics.", parse_mode="Markdown")
        elif admin_action == "gcast":
            query.edit_message_text(
                "📢 *Broadcast Message*\n\n"
                "Please use the command format:\n"
                "`/gcast Your message here`\n\n"
                "Example: `/gcast Hello everyone!`",
                parse_mode="Markdown"
            )
        elif admin_action == "protect_number":
            if not is_owner(user_id):
                query.answer("Only the owner can use this function.", show_alert=True)
                return
            
            query.edit_message_text(
                "🔒 *Protect Number*\n\n"
                "Please use the command format:\n"
                "`/protect NUMBER`\n\n"
                "Example: `/protect 9876543210`",
                parse_mode="Markdown"
            )
        elif admin_action == "blacklist_number":
            query.edit_message_text(
                "⛔ *Blacklist Number*\n\n"
                "Please use the command format:\n"
                "`/blacklist NUMBER` or `/unblacklist NUMBER`\n\n"
                "Example: `/blacklist 9876543210`",
                parse_mode="Markdown"
            )
        elif admin_action == "panel":
            keyboard = [
                [InlineKeyboardButton("👥 Add Credits", callback_data="admin_add_credits")],
                [InlineKeyboardButton("🚫 Ban/Unban User", callback_data="admin_ban_user")],
                [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
                [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_gcast")],
                [InlineKeyboardButton("🔒 Protect Number", callback_data="admin_protect_number")],
                [InlineKeyboardButton("⛔ Blacklist Number", callback_data="admin_blacklist_number")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(
                "🛠️ *Admin Panel*\n\n"
                "Choose an option below:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

# Message handlers
def message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Check if user is banned
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data and user_data[0] == 1:
        update.message.reply_text("❌ You are banned from using this bot.", parse_mode="Markdown")
        return
    
    # Check if user is member of required channels
    if not is_user_member(context, user_id):
        check_membership(update, context)
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
            pak_handler(update, context)
        # Check if it's an Indian number (starts with 91)
        elif message_text.startswith("91"):
            # Handle as Indian number
            context.args = [message_text[2:]]
            num_handler(update, context)
        else:
            # Handle as regular number
            context.args = [message_text]
            num_handler(update, context)
    # Check if it's a UPI ID
    elif "@" in message_text and "." in message_text.split("@")[1]:
        # Handle as UPI ID
        context.args = [message_text]
        upi_handler(update, context)
    # Check if it's an IP address
    elif "." in message_text and all(part.isdigit() for part in message_text.split(".")):
        # Handle as IP address
        context.args = [message_text]
        ip_handler(update, context)
    else:
        # Unknown message type
        update.message.reply_text(
            "❌ I don't understand this message.\n\n"
            "Please use the buttons or commands to search for information.",
            parse_mode="Markdown"
        )

def group_message_handler(update: Update, context: CallbackContext):
    message = update.message
    user_id = update.effective_user.id
    
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
                pak_handler(update, context)
            # Check if it's an Indian number (starts with 91)
            elif message.text.startswith("91"):
                # Handle as Indian number
                context.args = [message.text[2:]]
                num_handler(update, context)
            else:
                # Handle as regular number
                context.args = [message.text]
                num_handler(update, context)
        # Check if it's a UPI ID
        elif "@" in message.text and "." in message.text.split("@")[1]:
            # Handle as UPI ID
            context.args = [message.text]
            upi_handler(update, context)
        # Check if it's an IP address
        elif "." in message.text and all(part.isdigit() for part in message.text.split(".")):
            # Handle as IP address
            context.args = [message.text]
            ip_handler(update, context)
        else:
            # Unknown message type
            return  # Don't reply in groups for unknown messages

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    # Initialize database
    init_db()
    
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
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
    updater.bot.set_my_commands(commands)
    
    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("credits", credits_command))
    dispatcher.add_handler(CommandHandler("refer", refer_command))
    dispatcher.add_handler(CommandHandler("buy", buy_command))
    dispatcher.add_handler(CommandHandler("upi", upi_handler))
    dispatcher.add_handler(CommandHandler("num", num_handler))
    dispatcher.add_handler(CommandHandler("tg", tg_handler))
    dispatcher.add_handler(CommandHandler("ip", ip_handler))
    dispatcher.add_handler(CommandHandler("pak", pak_handler))
    dispatcher.add_handler(CommandHandler("aadhar", aadhar_handler))
    dispatcher.add_handler(CommandHandler("family", family_handler))
    dispatcher.add_handler(CommandHandler("call", call_handler))
    
    # Admin commands
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CommandHandler("addcredits", addcredits_command))
    dispatcher.add_handler(CommandHandler("ban", ban_command))
    dispatcher.add_handler(CommandHandler("unban", unban_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))
    dispatcher.add_handler(CommandHandler("gcast", gcast_command))
    dispatcher.add_handler(CommandHandler("protect", protect_command))
    dispatcher.add_handler(CommandHandler("unprotect", unprotect_command))
    dispatcher.add_handler(CommandHandler("blacklist", blacklist_command))
    dispatcher.add_handler(CommandHandler("unblacklist", unblacklist_command))
    
    # Register callback query handler
    dispatcher.add_handler(CallbackQueryHandler(button_callback))
    
    # Register message handlers
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, group_message_handler))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)
    
    # Start the Bot
    updater.start_polling()
    
    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
