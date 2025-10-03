import logging
import sqlite3
import json
import requests
import time
import os
import re
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
)
from telegram.error import BadRequest

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8219144171:AAH3HZPZvvtohlxOkTP2jJVDuEAaAllyzdU"  # Replace with your bot token
OWNER_ID = 7924074157
SUDO_USERS = [7924074157, 5294360309, 7905267752]
LOG_CHANNEL_START = -1002765060940
LOG_CHANNEL_SEARCH = -1003066524164
MANDATORY_CHANNELS = [
    {"title": "DataTrace Updates", "username": "DataTraceUpdates"},
    {"title": "DataTrace OSINT Support", "username": "DataTraceOSINTSupport"}
]

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

# Initialize database
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
        credits INTEGER DEFAULT 0,
        referred_by INTEGER,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        has_joined_channels INTEGER DEFAULT 0
    )
    ''')
    
    # Referrals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        referral_date TEXT,
        credits_earned INTEGER DEFAULT 0,
        FOREIGN KEY (referrer_id) REFERENCES users (user_id),
        FOREIGN KEY (referred_id) REFERENCES users (user_id)
    )
    ''')
    
    # Transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        credits INTEGER,
        transaction_date TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Protected numbers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS protected_numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE,
        added_by INTEGER,
        added_date TEXT,
        FOREIGN KEY (added_by) REFERENCES users (user_id)
    )
    ''')
    
    # Search logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS search_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        search_type TEXT,
        query TEXT,
        result_count INTEGER,
        search_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Check if user exists in database
def user_exists(user_id):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Add user to database
def add_user(user_id, username, first_name, last_name, referred_by=None):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
    INSERT INTO users (user_id, username, first_name, last_name, credits, referred_by, join_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, 0, referred_by, join_date))
    
    # Add referral record if referred_by is provided
    if referred_by:
        cursor.execute('''
        INSERT INTO referrals (referrer_id, referred_id, referral_date)
        VALUES (?, ?, ?)
        ''', (referred_by, user_id, join_date))
        
        # Give 1 credit to the new user
        cursor.execute("UPDATE users SET credits = credits + 1 WHERE user_id=?", (user_id,))
        
        # Give 1 credit to the referrer
        cursor.execute("UPDATE users SET credits = credits + 1 WHERE user_id=?", (referred_by,))
    
    conn.commit()
    conn.close()

# Get user credits
def get_user_credits(user_id):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Update user credits
def update_user_credits(user_id, credits):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (credits, user_id))
    conn.commit()
    conn.close()

# Check if user is banned
def is_user_banned(user_id):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

# Check if user has joined mandatory channels
def has_joined_channels(user_id, context):
    for channel in MANDATORY_CHANNELS:
        try:
            member = context.bot.get_chat_member(channel["username"], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            return False
    return True

# Check if number is blacklisted
def is_blacklisted(number):
    # Normalize number format
    normalized = number.replace(" ", "").replace("-", "")
    if not normalized.startswith("+"):
        normalized = "+" + normalized
    
    return normalized in BLACKLISTED_NUMBERS

# Check if number is protected
def is_protected(number):
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    cursor.execute("SELECT number FROM protected_numbers WHERE number=?", (number,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Log search to database and channel
def log_search(user_id, search_type, query, result_count, context):
    # Log to database
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    search_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
    INSERT INTO search_logs (user_id, search_type, query, result_count, search_date)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, search_type, query, result_count, search_date))
    
    conn.commit()
    conn.close()
    
    # Log to channel
    try:
        user = context.bot.get_chat(user_id)
        username = f"@{user.username}" if user.username else user.first_name
        log_message = f"""
🔍 NEW SEARCH
👤 User: {username} ({user_id})
🔎 Type: {search_type}
🔍 Query: {query}
📊 Results: {result_count}
🕐 Time: {search_date}
        """
        context.bot.send_message(LOG_CHANNEL_SEARCH, log_message)
    except Exception as e:
        logger.error(f"Failed to log search to channel: {e}")

# Format UPI info response
def format_upi_info(data):
    bank_details = data.get("bank_details_raw", {})
    vpa_details = data.get("vpa_details", {})
    
    response = """
🏦 **BANK DETAILS**
ADDRESS: {address}
BANK: {bank}
BANKCODE: {bankcode}
BRANCH: {branch}
CENTRE: {centre}
CITY: {city}
DISTRICT: {district}
STATE: {state}
IFSC: {ifsc}
MICR: {micr}
IMPS: {imps}
NEFT: {neft}
RTGS: {rtgs}
UPI: {upi}
SWIFT: {swift}

👤 **ACCOUNT HOLDER**
IFSC: {vpa_ifsc}
NAME: {name}
VPA: {vpa}
    """.format(
        address=bank_details.get("ADDRESS", "N/A"),
        bank=bank_details.get("BANK", "N/A"),
        bankcode=bank_details.get("BANKCODE", "N/A"),
        branch=bank_details.get("BRANCH", "N/A"),
        centre=bank_details.get("CENTRE", "N/A"),
        city=bank_details.get("CITY", "N/A"),
        district=bank_details.get("DISTRICT", "N/A"),
        state=bank_details.get("STATE", "N/A"),
        ifsc=bank_details.get("IFSC", "N/A"),
        micr=bank_details.get("MICR", "N/A"),
        imps="✅" if bank_details.get("IMPS") else "❌",
        neft="✅" if bank_details.get("NEFT") else "❌",
        rtgs="✅" if bank_details.get("RTGS") else "❌",
        upi="✅" if bank_details.get("UPI") else "❌",
        swift=bank_details.get("SWIFT", "N/A"),
        vpa_ifsc=vpa_details.get("ifsc", "N/A"),
        name=vpa_details.get("name", "N/A"),
        vpa=vpa_details.get("vpa", "N/A")
    )
    
    return response

# Format IP details response
def format_ip_details(data):
    response = """
🗾 **IP DETAILS**
🗾 IP Valid: {valid}
🌎 Country: {country}
💠 Country Code: {country_code}
🥬 Region: {region}
🗺️ Region Name: {region_name}
🏠 City: {city}
✉️ Zip: {zip}
🦠 Latitude: {latitude}
⭐ Longitude: {longitude}
🕢 Timezone: {timezone}
🗼 ISP: {isp}
🔥 Organization: {org}
🌾 AS: {as_info}
🛰 IP: {ip}
    """.format(
        valid=data.get("IP Valid", "N/A"),
        country=data.get("Country", "N/A"),
        country_code=data.get("Country Code", "N/A"),
        region=data.get("Region", "N/A"),
        region_name=data.get("Region Name", "N/A"),
        city=data.get("City", "N/A"),
        zip=data.get("Zip", "N/A"),
        latitude=data.get("Latitude", "N/A"),
        longitude=data.get("Longitude", "N/A"),
        timezone=data.get("Timezone", "N/A"),
        isp=data.get("ISP", "N/A"),
        org=data.get("Organization", "N/A"),
        as_info=data.get("AS", "N/A"),
        ip=data.get("IP", "N/A")
    )
    
    return response

# Format number info response
def format_number_info(data):
    if not data or "data" not in data or not data["data"]:
        return "❌ No information found for this number."
    
    result = data["data"][0]  # Take the first result
    
    response = """
📱 **NUMBER DETAILS**
MOBILE: {mobile}
ALT MOBILE: {alt}
NAME: {name}
FULL NAME: {full_name}
ADDRESS: {address}
CIRCLE: {circle}
ID: {id}
    """.format(
        mobile=result.get("mobile", "N/A"),
        alt=result.get("alt", "N/A"),
        name=result.get("name", "N/A"),
        full_name=result.get("fname", "N/A"),
        address=result.get("address", "N/A").replace("!", ", "),
        circle=result.get("circle", "N/A"),
        id=result.get("id", "N/A")
    )
    
    return response

# Format Aadhar info response
def format_aadhar_info(data):
    if not data or not isinstance(data, list) or len(data) == 0:
        return "❌ No information found for this Aadhar number."
    
    result = data[0]  # Take the first result
    
    response = """
🆔 **AADHAR DETAILS**
ID: {id}
MOBILE: {mobile}
NAME: {name}
FATHER'S NAME: {father_name}
ADDRESS: {address}
ALT MOBILE: {alt_mobile}
CIRCLE: {circle}
AADHAR NUMBER: {aadhar_number}
EMAIL: {email}
    """.format(
        id=result.get("id", "N/A"),
        mobile=result.get("mobile", "N/A"),
        name=result.get("name", "N/A"),
        father_name=result.get("father_name", "N/A"),
        address=result.get("address", "N/A").replace("!", ", "),
        alt_mobile=result.get("alt_mobile", "N/A"),
        circle=result.get("circle", "N/A"),
        aadhar_number=result.get("id_number", "N/A"),
        email=result.get("email", "N/A")
    )
    
    return response

# Format Pakistan number info response
def format_pak_num_info(data):
    if not data or "results" not in data or not data["results"]:
        return "❌ No information found for this Pakistan number."
    
    results = data["results"]
    response = "🇵🇰 **PAKISTAN INFO**\n\n"
    
    for i, result in enumerate(results, 1):
        response += f"{i}️⃣\n"
        response += f"NAME: {result.get('Name', 'N/A')}\n"
        response += f"CNIC: {result.get('CNIC', 'N/A')}\n"
        response += f"MOBILE: {result.get('Mobile', 'N/A')}\n"
        address = result.get('Address', 'N/A')
        response += f"ADDRESS: {address if address else '(Not Available)'}\n\n"
    
    return response

# Format Aadhar family info response
def format_aadhar_family_info(data):
    if not data:
        return "❌ No information found for this Aadhar number."
    
    response = """
🆔 **AADHAR FAMILY INFO**
RC ID: {rc_id}
SCHEME: {scheme} ({scheme_name})
DISTRICT: {district}
STATE: {state}
FPS ID: {fps_id}

👨‍👩‍👧 **FAMILY MEMBERS:**
    """.format(
        rc_id=data.get("rcId", "N/A"),
        scheme=data.get("schemeId", "N/A"),
        scheme_name=data.get("schemeName", "N/A"),
        district=data.get("homeDistName", "N/A"),
        state=data.get("homeStateName", "N/A"),
        fps_id=data.get("fpsId", "N/A")
    )
    
    members = data.get("memberDetailsList", [])
    for i, member in enumerate(members, 1):
        name = member.get("memberName", "N/A")
        relation = member.get("releationship_name", "N/A")
        response += f"{i}. {name} — {relation}\n"
    
    return response

# Format Telegram user stats response
def format_tg_user_stats(data):
    if not data or "data" not in data:
        return "❌ No information found for this Telegram user."
    
    user_data = data["data"]
    
    response = """
👤 **TELEGRAM USER STATS**
NAME: {name}
USER ID: {user_id}
IS BOT: {is_bot}
ACTIVE: {is_active}

📊 **STATS**
TOTAL GROUPS: {total_groups}
ADMIN IN GROUPS: {admin_in_groups}
TOTAL MESSAGES: {total_msg_count}
MESSAGES IN GROUPS: {msg_in_groups}

🕐 **TIMESTAMPS**
FIRST MSG DATE: {first_msg_date}
LAST MSG DATE: {last_msg_date}

🔄 **CHANGES**
NAME CHANGES: {names_count}
USERNAME CHANGES: {usernames_count}
    """.format(
        name=user_data.get("first_name", "N/A") + (" " + user_data.get("last_name", "") if user_data.get("last_name") else ""),
        user_id=user_data.get("id", "N/A"),
        is_bot="✅" if user_data.get("is_bot") else "❌",
        is_active="✅" if user_data.get("is_active") else "❌",
        total_groups=user_data.get("total_groups", "N/A"),
        admin_in_groups=user_data.get("adm_in_groups", "N/A"),
        total_msg_count=user_data.get("total_msg_count", "N/A"),
        msg_in_groups=user_data.get("msg_in_groups_count", "N/A"),
        first_msg_date=user_data.get("first_msg_date", "N/A").replace("T", " ").replace("Z", ""),
        last_msg_date=user_data.get("last_msg_date", "N/A").replace("T", " ").replace("Z", ""),
        names_count=user_data.get("names_count", "N/A"),
        usernames_count=user_data.get("usernames_count", "N/A")
    )
    
    return response

# Add branding footer to response
def add_branding_footer(response):
    footer = """
    
━━━━━━━━━━━━━━━━━━━━
🔍 DataTrace OSINT Bot
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
👤 Contact Admin: @DataTraceSupport
━━━━━━━━━━━━━━━━━━━━
    """
    return response + footer

# Start command handler
def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    
    # Log start to channel
    try:
        log_message = f"""
🚀 NEW USER STARTED BOT
👤 User: {user.first_name} (@{user.username}) ({user_id})
🕐 Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        context.bot.send_message(LOG_CHANNEL_START, log_message)
    except Exception as e:
        logger.error(f"Failed to log start to channel: {e}")
    
    # Check if user is banned
    if is_user_banned(user_id):
        update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    # Check if user exists in database
    if not user_exists(user_id):
        # Extract referral ID from start command if present
        referred_by = None
        if context.args:
            try:
                referred_by = int(context.args[0])
            except ValueError:
                pass
        
        # Add user to database
        add_user(
            user_id,
            user.username,
            user.first_name,
            user.last_name,
            referred_by
        )
    
    # Check if user has joined mandatory channels
    if not has_joined_channels(user_id, context):
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([InlineKeyboardButton(f"Join {channel['title']}", url=f"https://t.me/{channel['username']}")])
        
        buttons.append([InlineKeyboardButton("✅ I've Joined All Channels", callback_data="check_joined")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        update.message.reply_text(
            "🔒 **You need to join our mandatory channels to use this bot:**\n\n"
            "Please join all channels below and then click the verification button:",
            reply_markup=reply_markup
        )
        return
    
    # Generate referral link
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    
    # Get user credits
    credits = get_user_credits(user_id)
    
    # Create main menu
    buttons = [
        [InlineKeyboardButton("🔍 Lookups", callback_data="lookups_menu")],
        [InlineKeyboardButton("💰 My Credits", callback_data="my_credits")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
        [InlineKeyboardButton("🛡️ Protect My Number", callback_data="protect_number")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    welcome_text = f"""
👋 **Welcome, {user.first_name}!**

🔍 **DataTrace OSINT Bot** - Your gateway to information retrieval.

💰 **Credits:** {credits}

🤝 **Referral Link:**
`{referral_link}`
Share this link with friends to earn credits!

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
    """
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup)

# Handle callback queries
def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Check if user is banned
    if is_user_banned(user_id):
        query.edit_message_text("❌ You are banned from using this bot.")
        return
    
    # Check if user has joined mandatory channels
    if not has_joined_channels(user_id, context) and query.data != "check_joined":
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([InlineKeyboardButton(f"Join {channel['title']}", url=f"https://t.me/{channel['username']}")])
        
        buttons.append([InlineKeyboardButton("✅ I've Joined All Channels", callback_data="check_joined")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        query.edit_message_text(
            "🔒 **You need to join our mandatory channels to use this bot:**\n\n"
            "Please join all channels below and then click the verification button:",
            reply_markup=reply_markup
        )
        return
    
    # Handle different callback actions
    if query.data == "check_joined":
        if has_joined_channels(user_id, context):
            # Update user's join status in database
            conn = sqlite3.connect('datatrace.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET has_joined_channels = 1 WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
            
            # Generate referral link
            referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
            
            # Get user credits
            credits = get_user_credits(user_id)
            
            # Create main menu
            buttons = [
                [InlineKeyboardButton("🔍 Lookups", callback_data="lookups_menu")],
                [InlineKeyboardButton("💰 My Credits", callback_data="my_credits")],
                [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
                [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
                [InlineKeyboardButton("🛡️ Protect My Number", callback_data="protect_number")],
                [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(buttons)
            
            welcome_text = f"""
✅ **Verification Successful!**

👋 **Welcome, {update.effective_user.first_name}!**

🔍 **DataTrace OSINT Bot** - Your gateway to information retrieval.

💰 **Credits:** {credits}

🤝 **Referral Link:**
`{referral_link}`
Share this link with friends to earn credits!

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
            """
            
            query.edit_message_text(welcome_text, reply_markup=reply_markup)
        else:
            query.edit_message_text(
                "❌ **Verification Failed!**\n\n"
                "You haven't joined all mandatory channels yet. Please join all channels and try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="check_joined")]
                ])
            )
    
    elif query.data == "lookups_menu":
        buttons = [
            [InlineKeyboardButton("📱 Number Info", callback_data="num_info")],
            [InlineKeyboardButton("🇵🇰 Pakistan Number", callback_data="pak_num")],
            [InlineKeyboardButton("🆔 Aadhar Details", callback_data="aadhar_details")],
            [InlineKeyboardButton("👨‍👩‍👧 Aadhar to Family", callback_data="aadhar_family")],
            [InlineKeyboardButton("🏦 UPI Info", callback_data="upi_info")],
            [InlineKeyboardButton("🌐 IP Details", callback_data="ip_details")],
            [InlineKeyboardButton("👤 Telegram User Stats", callback_data="tg_user_stats")],
            [InlineKeyboardButton("📞 Call History (Paid)", callback_data="call_history")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        query.edit_message_text(
            "🔍 **Select a lookup service:**",
            reply_markup=reply_markup
        )
    
    elif query.data == "my_credits":
        credits = get_user_credits(user_id)
        
        # Get referral stats
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        referral_count = cursor.fetchone()[0]
        conn.close()
        
        buttons = [
            [InlineKeyboardButton("💳 Buy More Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        text = f"""
💰 **My Credits**

🪙 **Current Balance:** {credits} credits

👥 **Referrals:** {referral_count} users

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == "referral_program":
        # Generate referral link
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        
        # Get referral stats
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        referral_count = cursor.fetchone()[0]
        conn.close()
        
        buttons = [
            [InlineKeyboardButton("📋 Copy Referral Link", callback_data="copy_referral")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        text = f"""
🤝 **Referral Program**

🔗 **Your Referral Link:**
`{referral_link}`

📊 **Your Referrals:** {referral_count} users

🎁 **How it works:**
• Share your personal referral link
• When someone starts the bot using your link, they get 1 free credit
• You get 1 credit for each referral
• When your referral buys credits, you earn 30% commission

💡 **Example:**
• Friend joins → They get 1 free credit
• Friend buys 1000 credits → You get 300 credits commission
• Friend buys 5000 credits → You get 1500 credits commission

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == "copy_referral":
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="referral_program")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(
            f"📋 **Referral Link Copied!**\n\n`{referral_link}`\n\nShare this link with your friends to earn credits!",
            reply_markup=reply_markup
        )
    
    elif query.data == "buy_credits":
        buttons = [
            [InlineKeyboardButton("💳 100 Credits - ₹30 | 0.45 USDT", callback_data="buy_100")],
            [InlineKeyboardButton("💳 200 Credits - ₹60 | 0.9 USDT", callback_data="buy_200")],
            [InlineKeyboardButton("💳 500 Credits - ₹150 | 2.25 USDT", callback_data="buy_500")],
            [InlineKeyboardButton("💳 1000 Credits - ₹270 | 4.0 USDT", callback_data="buy_1000")],
            [InlineKeyboardButton("💳 2000 Credits - ₹540 | 8.0 USDT", callback_data="buy_2000")],
            [InlineKeyboardButton("💳 5000 Credits - ₹1350 | 20.0 USDT", callback_data="buy_5000")],
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        text = """
💳 **Buy Credits**

Select a package below:

💰 **Pricing:**
• 100 credits – ₹30 | 0.45 USDT
• 200 credits – ₹60 | 0.9 USDT
• 500 credits – ₹150 | 2.25 USDT
• 1,000 credits – ₹270 | 4.0 USDT
• 2,000 credits – ₹540 | 8.0 USDT
• 5,000 credits – ₹1350 | 20.0 USDT

💡 **Payment Methods:**
• UPI
• USDT (TRC20)
• Other methods (contact admin)

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data.startswith("buy_"):
        credits_amount = query.data.split("_")[1]
        
        buttons = [
            [InlineKeyboardButton("💳 Pay with UPI", callback_data=f"pay_upi_{credits_amount}")],
            [InlineKeyboardButton("💳 Pay with USDT", callback_data=f"pay_usdt_{credits_amount}")],
            [InlineKeyboardButton("📞 Contact Admin for Other Methods", url="https://t.me/DataTraceSupport")],
            [InlineKeyboardButton("⬅️ Back", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(
            f"💳 **Payment for {credits_amount} Credits**\n\n"
            f"Select your payment method:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith("pay_"):
        payment_method, credits_amount = query.data.split("_")[1:]
        
        # Get pricing based on credits amount
        pricing = {
            "100": ("₹30", "0.45 USDT"),
            "200": ("₹60", "0.9 USDT"),
            "500": ("₹150", "2.25 USDT"),
            "1000": ("₹270", "4.0 USDT"),
            "2000": ("₹540", "8.0 USDT"),
            "5000": ("₹1350", "20.0 USDT")
        }
        
        if credits_amount in pricing:
            inr_price, usdt_price = pricing[credits_amount]
            
            if payment_method == "upi":
                query.edit_message_text(
                    f"💳 **UPI Payment Details**\n\n"
                    f"**Amount:** {inr_price}\n"
                    f"**Credits:** {credits_amount}\n\n"
                    f"📱 **UPI ID:** `example@upi`\n\n"
                    f"1. Send {inr_price} to the UPI ID above\n"
                    f"2. Take a screenshot of the payment\n"
                    f"3. Send the screenshot to @DataTraceSupport\n"
                    f"4. Your credits will be added after verification\n\n"
                    f"⚠️ **Note:** Include your User ID ({user_id}) in the payment message",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Back", callback_data=f"buy_{credits_amount}")]
                    ])
                )
            elif payment_method == "usdt":
                query.edit_message_text(
                    f"💳 **USDT Payment Details**\n\n"
                    f"**Amount:** {usdt_price}\n"
                    f"**Credits:** {credits_amount}\n\n"
                    f"📱 **USDT Address (TRC20):** `TXXXXXX...XXXXXX`\n\n"
                    f"1. Send {usdt_price} to the address above\n"
                    f"2. Take a screenshot of the transaction\n"
                    f"3. Send the screenshot to @DataTraceSupport\n"
                    f"4. Your credits will be added after verification\n\n"
                    f"⚠️ **Note:** Include your User ID ({user_id}) in the payment message",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ Back", callback_data=f"buy_{credits_amount}")]
                    ])
                )
    
    elif query.data == "protect_number":
        buttons = [
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        text = """
🛡️ **Protect My Number**

To protect your number from being searched in our bot, you need to pay a protection fee of ₹300.

📞 **Contact Admin:**
@DataTraceSupport

🔒 **Benefits:**
• Your number will be added to our protected database
• No one will be able to search your number
• Only the bot owner can view protected numbers

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == "help_menu":
        buttons = [
            [InlineKeyboardButton("📱 Number Info", callback_data="help_num")],
            [InlineKeyboardButton("🇵🇰 Pakistan Number", callback_data="help_pak")],
            [InlineKeyboardButton("🆔 Aadhar Details", callback_data="help_aadhar")],
            [InlineKeyboardButton("👨‍👩‍👧 Aadhar to Family", callback_data="help_aadhar_fam")],
            [InlineKeyboardButton("🏦 UPI Info", callback_data="help_upi")],
            [InlineKeyboardButton("🌐 IP Details", callback_data="help_ip")],
            [InlineKeyboardButton("👤 Telegram User Stats", callback_data="help_tg")],
            [InlineKeyboardButton("📞 Call History", callback_data="help_call")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        text = """
❓ **Help & Commands**

Select a topic to learn more:

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data.startswith("help_"):
        help_topic = query.data.split("_")[1]
        
        help_texts = {
            "num": """
📱 **Number Info**

**Commands:**
• `/num <number>` - Get information about a phone number
• Send a phone number directly in chat

**Examples:**
• `/num 9876543210`
• `9876543210`

**Cost:** 1 credit per search
            """,
            "pak": """
🇵🇰 **Pakistan Number**

**Commands:**
• `/pak <number>` - Get information about a Pakistan phone number
• Send a Pakistan number with +92 prefix

**Examples:**
• `/pak 923001234567`
• `+923001234567`

**Cost:** 1 credit per search
            """,
            "aadhar": """
🆔 **Aadhar Details**

**Commands:**
• `/aadhar <number>` - Get information linked to an Aadhar number

**Examples:**
• `/aadhar 123456789012`

**Cost:** 1 credit per search
            """,
            "aadhar_fam": """
👨‍👩‍👧 **Aadhar to Family**

**Commands:**
• `/aadhar2fam <number>` - Get family details linked to an Aadhar number

**Examples:**
• `/aadhar2fam 123456789012`

**Cost:** 1 credit per search
            """,
            "upi": """
🏦 **UPI Info**

**Commands:**
• `/upi <upi_id>` - Get information about a UPI ID

**Examples:**
• `/upi example@upi`

**Cost:** 1 credit per search
            """,
            "ip": """
🌐 **IP Details**

**Commands:**
• `/ip <ip_address>` - Get information about an IP address

**Examples:**
• `/ip 8.8.8.8`

**Cost:** 1 credit per search
            """,
            "tg": """
👤 **Telegram User Stats**

**Commands:**
• `/tg <user_id>` - Get statistics about a Telegram user

**Examples:**
• `/tg 123456789`

**Cost:** 1 credit per search
            """,
            "call": """
📞 **Call History**

**Commands:**
• `/call <number>` - Get call history for a phone number

**Examples:**
• `/call 9876543210`

**Cost:** 600 credits per search
⚠️ **Note:** This is a premium service with no demo
            """
        }
        
        text = help_texts.get(help_topic, "❌ Help topic not found.")
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back to Help", callback_data="help_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == "back_to_main":
        # Generate referral link
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        
        # Get user credits
        credits = get_user_credits(user_id)
        
        # Create main menu
        buttons = [
            [InlineKeyboardButton("🔍 Lookups", callback_data="lookups_menu")],
            [InlineKeyboardButton("💰 My Credits", callback_data="my_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("🛡️ Protect My Number", callback_data="protect_number")],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        welcome_text = f"""
👋 **Welcome, {update.effective_user.first_name}!**

🔍 **DataTrace OSINT Bot** - Your gateway to information retrieval.

💰 **Credits:** {credits}

🤝 **Referral Link:**
`{referral_link}`
Share this link with friends to earn credits!

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
━━━━━━━━━━━━━━━━━━━━
        """
        
        query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    elif query.data in ["num_info", "pak_num", "aadhar_details", "aadhar_family", "upi_info", "ip_details", "tg_user_stats", "call_history"]:
        # Handle lookup selection
        lookup_type = query.data
        
        # Create appropriate prompt based on lookup type
        prompts = {
            "num_info": "📱 **Number Info**\n\nPlease send a phone number (with or without country code):",
            "pak_num": "🇵🇰 **Pakistan Number**\n\nPlease send a Pakistan phone number (with +92 prefix):",
            "aadhar_details": "🆔 **Aadhar Details**\n\nPlease send an Aadhar number:",
            "aadhar_family": "👨‍👩‍👧 **Aadhar to Family**\n\nPlease send an Aadhar number:",
            "upi_info": "🏦 **UPI Info**\n\nPlease send a UPI ID:",
            "ip_details": "🌐 **IP Details**\n\nPlease send an IP address:",
            "tg_user_stats": "👤 **Telegram User Stats**\n\nPlease send a Telegram User ID:",
            "call_history": "📞 **Call History**\n\nPlease send a phone number:\n\n⚠️ **Cost: 600 credits per search**"
        }
        
        # Store the lookup type in user_data
        context.user_data["pending_lookup"] = lookup_type
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="lookups_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(
            prompts.get(lookup_type, "Please send the required information:"),
            reply_markup=reply_markup
        )

# Handle text messages
def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    message_text = update.message.text
    
    # Check if user is banned
    if is_user_banned(user_id):
        update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    # Check if user has joined mandatory channels
    if not has_joined_channels(user_id, context):
        buttons = []
        for channel in MANDATORY_CHANNELS:
            buttons.append([InlineKeyboardButton(f"Join {channel['title']}", url=f"https://t.me/{channel['username']}")])
        
        buttons.append([InlineKeyboardButton("✅ I've Joined All Channels", callback_data="check_joined")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        update.message.reply_text(
            "🔒 **You need to join our mandatory channels to use this bot:**\n\n"
            "Please join all channels below and then click the verification button:",
            reply_markup=reply_markup
        )
        return
    
    # Check if user has a pending lookup
    if "pending_lookup" in context.user_data:
        lookup_type = context.user_data["pending_lookup"]
        del context.user_data["pending_lookup"]
        
        # Process the lookup based on type
        if lookup_type == "num_info":
            process_number_lookup(update, context, message_text)
        elif lookup_type == "pak_num":
            process_pak_number_lookup(update, context, message_text)
        elif lookup_type == "aadhar_details":
            process_aadhar_lookup(update, context, message_text)
        elif lookup_type == "aadhar_family":
            process_aadhar_family_lookup(update, context, message_text)
        elif lookup_type == "upi_info":
            process_upi_lookup(update, context, message_text)
        elif lookup_type == "ip_details":
            process_ip_lookup(update, context, message_text)
        elif lookup_type == "tg_user_stats":
            process_tg_user_lookup(update, context, message_text)
        elif lookup_type == "call_history":
            process_call_history_lookup(update, context, message_text)
        return
    
    # Check if the message is a direct number lookup
    if re.match(r'^(\+?\d{10,15}|\d{10})$', message_text):
        # Determine if it's a Pakistan number or regular number
        if message_text.startswith("+92") or (len(message_text) >= 10 and message_text.startswith("92")):
            process_pak_number_lookup(update, context, message_text)
        else:
            process_number_lookup(update, context, message_text)
        return
    
    # Handle group messages
    if update.message.chat.type != "private":
        # Only reply if the bot is mentioned or if it's a command
        if f"@{context.bot.username}" in message_text or message_text.startswith("/"):
            update.message.reply_text(
                "🔍 **DataTrace OSINT Bot**\n\n"
                "Please use the bot in private messages for lookups.\n\n"
                "📞 Contact Admin: @DataTraceSupport"
            )
        return
    
    # Default response for unrecognized messages
    update.message.reply_text(
        "❓ I don't understand that command.\n\n"
        "Please use the buttons below to navigate:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Lookups", callback_data="lookups_menu")],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu")]
        ])
    )

# Process number lookup
def process_number_lookup(update: Update, context: CallbackContext, number: str) -> None:
    user_id = update.effective_user.id
    
    # Normalize number
    normalized = number.replace(" ", "").replace("-", "")
    if not normalized.startswith("+"):
        if len(normalized) == 10:  # Assume Indian number
            normalized = "+91" + normalized
        else:
            normalized = "+" + normalized
    
    # Check if number is blacklisted
    if is_blacklisted(normalized):
        update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    # Check if number is protected
    if is_protected(normalized) and user_id != OWNER_ID:
        update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["num_info"].format(number=normalized.replace("+", ""))
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_number_info(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Number Info", normalized, len(data.get("data", [])), context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in number lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process Pakistan number lookup
def process_pak_number_lookup(update: Update, context: CallbackContext, number: str) -> None:
    user_id = update.effective_user.id
    
    # Normalize number
    normalized = number.replace(" ", "").replace("-", "")
    if not normalized.startswith("+"):
        normalized = "+" + normalized
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["pak_num"].format(number=normalized.replace("+", ""))
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_pak_num_info(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Pakistan Number", normalized, len(data.get("results", [])), context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in Pakistan number lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process Aadhar lookup
def process_aadhar_lookup(update: Update, context: CallbackContext, aadhar: str) -> None:
    user_id = update.effective_user.id
    
    # Normalize Aadhar number
    normalized = aadhar.replace(" ", "").replace("-", "")
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["aadhar_details"].format(aadhar=normalized)
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_aadhar_info(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Aadhar Details", normalized, len(data) if isinstance(data, list) else 1, context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in Aadhar lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process Aadhar family lookup
def process_aadhar_family_lookup(update: Update, context: CallbackContext, aadhar: str) -> None:
    user_id = update.effective_user.id
    
    # Normalize Aadhar number
    normalized = aadhar.replace(" ", "").replace("-", "")
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["aadhar_family"].format(aadhaar=normalized)
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_aadhar_family_info(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Aadhar Family", normalized, len(data.get("memberDetailsList", [])), context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in Aadhar family lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process UPI lookup
def process_upi_lookup(update: Update, context: CallbackContext, upi_id: str) -> None:
    user_id = update.effective_user.id
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["upi_info"].format(upi_id=upi_id)
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_upi_info(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "UPI Info", upi_id, 1, context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in UPI lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process IP lookup
def process_ip_lookup(update: Update, context: CallbackContext, ip: str) -> None:
    user_id = update.effective_user.id
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["ip_details"].format(ip=ip)
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_ip_details(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "IP Details", ip, 1, context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in IP lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process Telegram user lookup
def process_tg_user_lookup(update: Update, context: CallbackContext, user_id_str: str) -> None:
    user_id = update.effective_user.id
    
    try:
        target_user_id = int(user_id_str)
    except ValueError:
        update.message.reply_text("❌ Invalid User ID. Please provide a valid Telegram User ID.")
        return
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 1:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 1 credit to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -1)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["tg_user_stats"].format(user_id=target_user_id)
        response = requests.get(url)
        data = response.json()
        
        # Format response
        formatted_response = format_tg_user_stats(data)
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Telegram User Stats", str(target_user_id), 1, context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in Telegram user lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Process call history lookup
def process_call_history_lookup(update: Update, context: CallbackContext, number: str) -> None:
    user_id = update.effective_user.id
    
    # Normalize number
    normalized = number.replace(" ", "").replace("-", "")
    if not normalized.startswith("+"):
        if len(normalized) == 10:  # Assume Indian number
            normalized = "+91" + normalized
        else:
            normalized = "+" + normalized
    
    # Check if number is blacklisted
    if is_blacklisted(normalized):
        update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    # Check if number is protected
    if is_protected(normalized) and user_id != OWNER_ID:
        update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    # Check if user has enough credits
    credits = get_user_credits(user_id)
    if credits < 600:
        # Show options to get credits
        buttons = [
            [InlineKeyboardButton("👥 Refer a Friend", callback_data="referral_program")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        update.message.reply_text(
            "❌ **Insufficient Credits**\n\n"
            "You need 600 credits to perform this search.\n\n"
            "Get more credits:",
            reply_markup=reply_markup
        )
        return
    
    # Deduct credit
    update_user_credits(user_id, -600)
    
    # Show processing message
    processing_message = update.message.reply_text("🔍 Searching... Please wait.")
    
    try:
        # Make API request
        url = API_ENDPOINTS["call_history"].format(number=normalized.replace("+", ""))
        response = requests.get(url)
        data = response.json()
        
        # Format response (basic formatting for call history)
        formatted_response = "📞 **CALL HISTORY**\n\n"
        
        if data and isinstance(data, list) and len(data) > 0:
            for i, call in enumerate(data[:10], 1):  # Limit to 10 calls
                formatted_response += f"{i}. Date: {call.get('date', 'N/A')}\n"
                formatted_response += f"   Number: {call.get('number', 'N/A')}\n"
                formatted_response += f"   Duration: {call.get('duration', 'N/A')} seconds\n"
                formatted_response += f"   Type: {call.get('type', 'N/A')}\n\n"
        else:
            formatted_response += "No call history found for this number."
        
        formatted_response = add_branding_footer(formatted_response)
        
        # Log search
        log_search(user_id, "Call History", normalized, len(data) if isinstance(data, list) else 0, context)
        
        # Update processing message
        processing_message.edit_text(formatted_response)
        
    except Exception as e:
        logger.error(f"Error in call history lookup: {e}")
        processing_message.edit_text(
            "❌ **Error:** Failed to fetch information. Please try again later.\n\n"
            "📞 Contact Admin: @DataTraceSupport"
        )

# Admin commands
def admin_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Check if user is admin or sudo
    if user_id != OWNER_ID and user_id not in SUDO_USERS:
        update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Show admin panel
    buttons = [
        [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Add Sudo User", callback_data="admin_add_sudo")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
        [InlineKeyboardButton("💰 Add Credits", callback_data="admin_add_credits")],
        [InlineKeyboardButton("🛡️ Protected Numbers", callback_data="admin_protected_numbers")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    update.message.reply_text(
        "🔧 **Admin Panel**\n\n"
        "Select an action:",
        reply_markup=reply_markup
    )

# Handle admin callback queries
def admin_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Check if user is admin or sudo
    if user_id != OWNER_ID and user_id not in SUDO_USERS:
        query.edit_message_text("❌ You don't have permission to use this command.")
        return
    
    if query.data == "admin_stats":
        # Get bot stats
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Active users (joined in last 7 days)
        cursor.execute("SELECT COUNT(*) FROM users WHERE join_date > datetime('now', '-7 days')")
        active_users = cursor.fetchone()[0]
        
        # Total searches
        cursor.execute("SELECT COUNT(*) FROM search_logs")
        total_searches = cursor.fetchone()[0]
        
        # Today's searches
        cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date > date('now')")
        today_searches = cursor.fetchone()[0]
        
        # Total credits purchased
        cursor.execute("SELECT SUM(credits) FROM transactions WHERE status='completed'")
        total_credits_purchased = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats_text = f"""
📊 **Bot Statistics**

👥 **Users:**
• Total Users: {total_users}
• Active Users (7 days): {active_users}

🔍 **Searches:**
• Total Searches: {total_searches}
• Today's Searches: {today_searches}

💰 **Credits:**
• Total Credits Purchased: {total_credits_purchased}
        """
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    elif query.data == "admin_panel":
        # Show admin panel
        buttons = [
            [InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Add Sudo User", callback_data="admin_add_sudo")],
            [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user")],
            [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
            [InlineKeyboardButton("💰 Add Credits", callback_data="admin_add_credits")],
            [InlineKeyboardButton("🛡️ Protected Numbers", callback_data="admin_protected_numbers")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(
            "🔧 **Admin Panel**\n\n"
            "Select an action:",
            reply_markup=reply_markup
        )
    
    elif query.data == "admin_add_sudo":
        # Store action in user_data
        context.user_data["admin_action"] = "add_sudo"
        
        query.edit_message_text(
            "👥 **Add Sudo User**\n\n"
            "Please send the User ID of the user you want to add as sudo:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    
    elif query.data == "admin_ban_user":
        # Store action in user_data
        context.user_data["admin_action"] = "ban_user"
        
        query.edit_message_text(
            "🚫 **Ban User**\n\n"
            "Please send the User ID of the user you want to ban:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    
    elif query.data == "admin_unban_user":
        # Store action in user_data
        context.user_data["admin_action"] = "unban_user"
        
        query.edit_message_text(
            "✅ **Unban User**\n\n"
            "Please send the User ID of the user you want to unban:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    
    elif query.data == "admin_add_credits":
        # Store action in user_data
        context.user_data["admin_action"] = "add_credits"
        
        query.edit_message_text(
            "💰 **Add Credits**\n\n"
            "Please send the User ID and amount in this format:\n"
            "`user_id credits`\n\n"
            "Example: `123456789 100`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    
    elif query.data == "admin_protected_numbers":
        # Only owner can view protected numbers
        if user_id != OWNER_ID:
            query.edit_message_text("❌ Only the bot owner can view protected numbers.")
            return
        
        # Get protected numbers
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT number, added_by, added_date FROM protected_numbers ORDER BY added_date DESC")
        protected_numbers = cursor.fetchall()
        conn.close()
        
        if not protected_numbers:
            protected_text = "🛡️ **Protected Numbers**\n\nNo protected numbers found."
        else:
            protected_text = "🛡️ **Protected Numbers**\n\n"
            for number, added_by, added_date in protected_numbers:
                protected_text += f"• {number} (Added by {added_by} on {added_date})\n"
        
        buttons = [
            [InlineKeyboardButton("➕ Add Protected Number", callback_data="admin_add_protected")],
            [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        query.edit_message_text(protected_text, reply_markup=reply_markup)
    
    elif query.data == "admin_add_protected":
        # Only owner can add protected numbers
        if user_id != OWNER_ID:
            query.edit_message_text("❌ Only the bot owner can add protected numbers.")
            return
        
        # Store action in user_data
        context.user_data["admin_action"] = "add_protected"
        
        query.edit_message_text(
            "🛡️ **Add Protected Number**\n\n"
            "Please send the phone number you want to protect:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    
    elif query.data == "admin_broadcast":
        # Store action in user_data
        context.user_data["admin_action"] = "broadcast"
        
        query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "Please send the message you want to broadcast to all users:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
            ])
        )

# Handle admin actions
def handle_admin_action(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Check if user is admin or sudo
    if user_id != OWNER_ID and user_id not in SUDO_USERS:
        update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Check if user has an admin action pending
    if "admin_action" not in context.user_data:
        return
    
    action = context.user_data["admin_action"]
    del context.user_data["admin_action"]
    
    if action == "add_sudo":
        try:
            target_user_id = int(message_text.strip())
            
            # Add to sudo users list (in a real implementation, this would be stored in a database)
            if target_user_id not in SUDO_USERS:
                SUDO_USERS.append(target_user_id)
                update.message.reply_text(f"✅ User {target_user_id} has been added as a sudo user.")
            else:
                update.message.reply_text(f"❌ User {target_user_id} is already a sudo user.")
                
        except ValueError:
            update.message.reply_text("❌ Invalid User ID. Please provide a valid User ID.")
    
    elif action == "ban_user":
        try:
            target_user_id = int(message_text.strip())
            
            # Check if user exists
            if user_exists(target_user_id):
                # Ban user in database
                conn = sqlite3.connect('datatrace.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id=?", (target_user_id,))
                conn.commit()
                conn.close()
                
                update.message.reply_text(f"✅ User {target_user_id} has been banned.")
            else:
                update.message.reply_text(f"❌ User {target_user_id} does not exist in the database.")
                
        except ValueError:
            update.message.reply_text("❌ Invalid User ID. Please provide a valid User ID.")
    
    elif action == "unban_user":
        try:
            target_user_id = int(message_text.strip())
            
            # Check if user exists
            if user_exists(target_user_id):
                # Unban user in database
                conn = sqlite3.connect('datatrace.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id=?", (target_user_id,))
                conn.commit()
                conn.close()
                
                update.message.reply_text(f"✅ User {target_user_id} has been unbanned.")
            else:
                update.message.reply_text(f"❌ User {target_user_id} does not exist in the database.")
                
        except ValueError:
            update.message.reply_text("❌ Invalid User ID. Please provide a valid User ID.")
    
    elif action == "add_credits":
        try:
            parts = message_text.strip().split()
            if len(parts) != 2:
                raise ValueError
            
            target_user_id = int(parts[0])
            credits = int(parts[1])
            
            # Check if user exists
            if user_exists(target_user_id):
                # Add credits to user
                update_user_credits(target_user_id, credits)
                
                # Log transaction
                conn = sqlite3.connect('datatrace.db')
                cursor = conn.cursor()
                transaction_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                INSERT INTO transactions (user_id, amount, payment_method, credits, transaction_date, status)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (target_user_id, 0, "admin_add", credits, transaction_date, "completed"))
                
                conn.commit()
                conn.close()
                
                update.message.reply_text(f"✅ Added {credits} credits to user {target_user_id}.")
            else:
                update.message.reply_text(f"❌ User {target_user_id} does not exist in the database.")
                
        except ValueError:
            update.message.reply_text("❌ Invalid format. Please use: `user_id credits`")
    
    elif action == "add_protected":
        # Only owner can add protected numbers
        if user_id != OWNER_ID:
            update.message.reply_text("❌ Only the bot owner can add protected numbers.")
            return
        
        # Normalize number
        normalized = message_text.strip().replace(" ", "").replace("-", "")
        if not normalized.startswith("+"):
            if len(normalized) == 10:  # Assume Indian number
                normalized = "+91" + normalized
            else:
                normalized = "+" + normalized
        
        # Add to protected numbers
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        added_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            cursor.execute('''
            INSERT INTO protected_numbers (number, added_by, added_date)
            VALUES (?, ?, ?)
            ''', (normalized, user_id, added_date))
            
            conn.commit()
            update.message.reply_text(f"✅ Number {normalized} has been added to protected numbers.")
            
        except sqlite3.IntegrityError:
            update.message.reply_text(f"❌ Number {normalized} is already in the protected list.")
            
        finally:
            conn.close()
    
    elif action == "broadcast":
        # Get all users
        conn = sqlite3.connect('datatrace.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        fail_count = 0
        
        for user in users:
            try:
                context.bot.send_message(user[0], message_text)
                success_count += 1
                time.sleep(0.1)  # Avoid flooding
            except Exception:
                fail_count += 1
        
        update.message.reply_text(
            f"📢 **Broadcast Complete**\n\n"
            f"✅ Successfully sent to: {success_count} users\n"
            f"❌ Failed to send to: {fail_count} users"
        )

# Stats command for sudo users
def stats_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Check if user is admin or sudo
    if user_id != OWNER_ID and user_id not in SUDO_USERS:
        update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Get bot stats
    conn = sqlite3.connect('datatrace.db')
    cursor = conn.cursor()
    
    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Active users (joined in last 7 days)
    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date > datetime('now', '-7 days')")
    active_users = cursor.fetchone()[0]
    
    # Total searches
    cursor.execute("SELECT COUNT(*) FROM search_logs")
    total_searches = cursor.fetchone()[0]
    
    # Today's searches
    cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date > date('now')")
    today_searches = cursor.fetchone()[0]
    
    # Total credits purchased
    cursor.execute("SELECT SUM(credits) FROM transactions WHERE status='completed'")
    total_credits_purchased = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""
📊 **Bot Statistics**

👥 **Users:**
• Total Users: {total_users}
• Active Users (7 days): {active_users}

🔍 **Searches:**
• Total Searches: {total_searches}
• Today's Searches: {today_searches}

💰 **Credits:**
• Total Credits Purchased: {total_credits_purchased}
    """
    
    update.message.reply_text(stats_text)

# Broadcast command for sudo users
def broadcast_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Check if user is admin or sudo
    if user_id != OWNER_ID and user_id not in SUDO_USERS:
        update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    # Store action in user_data
    context.user_data["admin_action"] = "broadcast"
    
    update.message.reply_text(
        "📢 **Broadcast Message**\n\n"
        "Please send the message you want to broadcast to all users:"
    )

# Buy DB/API command
def buydb_command(update: Update, context: CallbackContext) -> None:
    buttons = [
        [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    update.message.reply_text(
        "🗄️ **Buy Database/API**\n\n"
        "To purchase our database or API access, please contact our admin:\n\n"
        "📞 @DataTraceSupport",
        reply_markup=reply_markup
    )

# Buy API command
def buyapi_command(update: Update, context: CallbackContext) -> None:
    buttons = [
        [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/DataTraceSupport")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    update.message.reply_text(
        "🔌 **Buy API Access**\n\n"
        "To purchase API access, please contact our admin:\n\n"
        "📞 @DataTraceSupport",
        reply_markup=reply_markup
    )

# Command handlers for direct lookups
def num_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide a phone number.\n\nExample: /num 9876543210")
        return
    
    number = context.args[0]
    process_number_lookup(update, context, number)

def pak_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide a Pakistan phone number.\n\nExample: /pak 923001234567")
        return
    
    number = context.args[0]
    process_pak_number_lookup(update, context, number)

def aadhar_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide an Aadhar number.\n\nExample: /aadhar 123456789012")
        return
    
    aadhar = context.args[0]
    process_aadhar_lookup(update, context, aadhar)

def aadhar2fam_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide an Aadhar number.\n\nExample: /aadhar2fam 123456789012")
        return
    
    aadhar = context.args[0]
    process_aadhar_family_lookup(update, context, aadhar)

def upi_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide a UPI ID.\n\nExample: /upi example@upi")
        return
    
    upi_id = context.args[0]
    process_upi_lookup(update, context, upi_id)

def ip_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide an IP address.\n\nExample: /ip 8.8.8.8")
        return
    
    ip = context.args[0]
    process_ip_lookup(update, context, ip)

def tg_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide a Telegram User ID.\n\nExample: /tg 123456789")
        return
    
    user_id_str = context.args[0]
    process_tg_user_lookup(update, context, user_id_str)

def call_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ Please provide a phone number.\n\nExample: /call 9876543210")
        return
    
    number = context.args[0]
    process_call_history_lookup(update, context, number)

# Help command
def help_command(update: Update, context: CallbackContext) -> None:
    help_text = """
🔍 **DataTrace OSINT Bot - Help**

**📱 Number Lookup Commands:**
• `/num <number>` - Get information about a phone number
• `/pak <number>` - Get information about a Pakistan phone number

**🆔 ID Lookup Commands:**
• `/aadhar <number>` - Get information linked to an Aadhar number
• `/aadhar2fam <number>` - Get family details linked to an Aadhar number

**💳 Payment Commands:**
• `/upi <upi_id>` - Get information about a UPI ID

**🌐 Network Commands:**
• `/ip <ip_address>` - Get information about an IP address

**👤 Social Commands:**
• `/tg <user_id>` - Get statistics about a Telegram user

**📞 Premium Commands:**
• `/call <number>` - Get call history for a phone number (600 credits)

**💰 Other Commands:**
• `/start` - Start the bot and get your referral link
• `/help` - Show this help message
• `/buydb` - Buy database access
• `/buyapi` - Buy API access

**🔧 Admin Commands:**
• `/admin` - Admin panel (sudo users only)
• `/stats` - Bot statistics (sudo users only)
• `/gcast <message>` - Broadcast message to all users (sudo users only)

**💡 Tips:**
• You can also send numbers directly without commands
• Use the referral system to earn free credits
• Join our mandatory channels to use the bot

━━━━━━━━━━━━━━━━━━━━
📢 Join: @DataTraceUpdates
💬 Support: @DataTraceOSINTSupport
👤 Contact Admin: @DataTraceSupport
━━━━━━━━━━━━━━━━━━━━
    """
    
    update.message.reply_text(help_text)

# Error handler
def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"Update {update} caused error {context.error}")

# Main function
def main() -> None:
    # Initialize database
    init_db()
    
    # Create the Updater and pass it your bot's token.
    updater = Updater(BOT_TOKEN)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))
    dispatcher.add_handler(CommandHandler("gcast", broadcast_command))
    dispatcher.add_handler(CommandHandler("buydb", buydb_command))
    dispatcher.add_handler(CommandHandler("buyapi", buyapi_command))
    
    # Register lookup command handlers
    dispatcher.add_handler(CommandHandler("num", num_command))
    dispatcher.add_handler(CommandHandler("pak", pak_command))
    dispatcher.add_handler(CommandHandler("aadhar", aadhar_command))
    dispatcher.add_handler(CommandHandler("aadhar2fam", aadhar2fam_command))
    dispatcher.add_handler(CommandHandler("upi", upi_command))
    dispatcher.add_handler(CommandHandler("ip", ip_command))
    dispatcher.add_handler(CommandHandler("tg", tg_command))
    dispatcher.add_handler(CommandHandler("call", call_command))
    
    # Register callback query handler
    dispatcher.add_handler(CallbackQueryHandler(button_callback))
    dispatcher.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # Register message handler
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Register admin action handler
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_admin_action))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("num", "Number lookup"),
        BotCommand("pak", "Pakistan number lookup"),
        BotCommand("aadhar", "Aadhar lookup"),
        BotCommand("aadhar2fam", "Aadhar to family lookup"),
        BotCommand("upi", "UPI lookup"),
        BotCommand("ip", "IP lookup"),
        BotCommand("tg", "Telegram user lookup"),
        BotCommand("call", "Call history lookup"),
        BotCommand("buydb", "Buy database access"),
        BotCommand("buyapi", "Buy API access"),
        BotCommand("admin", "Admin panel"),
        BotCommand("stats", "Bot statistics"),
        BotCommand("gcast", "Broadcast message")
    ]
    
    updater.bot.set_my_commands(commands)
    
    # Start the Bot
    updater.start_polling()
    
    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == "__main__":
    main()        help_text = (
            "📖 Help & Commands\n\n"
            "🔍 Lookup Commands:\n"
            "• /num [number] - Get number information\n"
            "• /pak [number] - Get Pakistan number information\n"
            "• /aadhar [aadhaar] - Get Aadhaar details\n"
            "• /aadhar2fam [aadhaar] - Get Aadhaar family information\n"
            "• /upi [upi_id] - Get UPI information\n"
            "• /ip [ip_address] - Get IP details\n"
            "• /stats [user_id] - Get Telegram user stats\n"
            "• /call [number] - Get call history (Paid - 600 credits)\n\n"
            "💰 Credit Commands:\n"
            "• /balance - Check your credit balance\n"
            "• /buy - Buy credits\n\n"
            "👥 Referral Commands:\n"
            "• /referral - Get your referral link\n\n"
            "🛡️ Protection Commands:\n"
            "• /protect - Protect your data\n\n"
            "📞 Contact:\n"
            "• /admin - Contact admin\n\n"
            "ℹ️ You can also use the bot by directly sending a number or UPI ID without commands."
        )
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            help_text,
            reply_markup=reply_markup
        )
        
    elif query.data == "back_to_main":
        # Generate referral link
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        
        # Create main menu
        keyboard = [
            [InlineKeyboardtelegram.extButton("🔍 Lookup Services", callback_data="lookup_services")],
            [InlineKeyboardButton("💰 Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("🛡️ Protect Your Data", callback_data="protect_data")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("📞 Contact Admin", url=f"https://{ADMIN_CONTACT}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👋 Welcome, {update.effective_user.first_name}!\n\n"
            f"🔍 DataTrace OSINT Bot provides various lookup services.\n\n"
            f"💳 Your Credits: {credits_db[user_id]}\n\n"
            f"🔗 Your Referral Link: {referral_link}\n\n"
            f"Share your referral link to earn free credits!",
            reply_markup=reply_markup
        )
        
    elif query.data in ["num_info", "pak_num_info", "aadhar_details", "aadhar_family", 
                       "upi_info", "ip_details", "tg_user_stats", "call_history"]:
        # Set the state for the conversation
        context.user_data['service'] = query.data
        
        # Create appropriate prompt based on service
        prompts = {
            "num_info": "Please send the mobile number (with or without country code):",
            "pak_num_info": "Please send the Pakistan mobile number (with country code):",
            "aadhar_details": "Please send the Aadhaar number:",
            "aadhar_family": "Please send the Aadhaar number:",
            "upi_info": "Please send the UPI ID:",
            "ip_details": "Please send the IP address:",
            "tg_user_stats": "Please send the Telegram user ID:",
            "call_history": "Please send the mobile number for call history (600 credits will be deducted):"
        }
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="lookup_services")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            prompts[query.data],
            reply_markup=reply_markup
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct messages (non-command)"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    # Check if user is member of mandatory channels
    if not await is_user_member(update, context):
        await send_not_member_message(update, context)
        return
    
    # Check if user has enough credits
    if user_id not in credits_db or credits_db[user_id] <= 0:
        await update.message.reply_text(
            "❌ You don't have enough credits to use this service.\n\n"
            "💰 Buy more credits or refer friends to earn free credits."
        )
        return
    
    # Check if user is in a conversation state
    if 'service' in context.user_data:
        service = context.user_data['service']
        
        # Process based on service
        if service == "num_info":
            await process_number_info(update, context, message_text)
        elif service == "pak_num_info":
            await process_pak_num_info(update, context, message_text)
        elif service == "aadhar_details":
            await process_aadhar_details(update, context, message_text)
        elif service == "aadhar_family":
            await process_aadhar_family(update, context, message_text)
        elif service == "upi_info":
            await process_upi_info(update, context, message_text)
        elif service == "ip_details":
            await process_ip_details(update, context, message_text)
        elif service == "tg_user_stats":
            await process_tg_user_stats(update, context, message_text)
        elif service == "call_history":
            await process_call_history(update, context, message_text)
        
        # Clear the service state
        del context.user_data['service']
        return
    
    # If not in a conversation state, try to detect the service based on input
    if message_text.startswith("+"):
        if message_text.startswith("+92"):
            # Pakistan number
            await process_pak_num_info(update, context, message_text)
        else:
            # Other international number
            await process_number_info(update, context, message_text)
    elif message_text.isdigit() and len(message_text) >= 10:
        # Likely a mobile number
        await process_number_info(update, context, message_text)
    elif "@" in message_text and "." in message_text:
        # Likely a UPI ID
        await process_upi_info(update, context, message_text)
    elif "." in message_text and len(message_text.split(".")) == 4:
        # Likely an IP address
        await process_ip_details(update, context, message_text)
    elif message_text.isdigit() and len(message_text) == 12:
        # Likely an Aadhaar number
        await process_aadhar_details(update, context, message_text)
    else:
        await update.message.reply_text(
            "❌ I couldn't recognize your input.\n\n"
            "Please use the /help command to see available services or select from the menu."
        )

async def process_number_info(update: Update, context: ContextTypes.DEFAULT_TYPE, number: str):
    """Process number information request"""
    user_id = update.effective_user.id
    
    if number in blacklisted_numbers:
        await update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    if number in protected_numbers and user_id != OWNER_ID:
        await update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    if number.startswith("+91"):
        number = number[3:]
    
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"📱 Number Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Number: {number}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for number information...")
    
    try:
        response = requests.get(API_ENDPOINTS["num_info"].format(number=number), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # --- THIS IS THE KEY CHANGE ---
        # Check if the response is a list and not empty
        if isinstance(data, list) and len(data) > 0:
            result = data[0]  # Get the first item from the list directly
            
            # --- UPDATED FORMATTING ---
            formatted_response = (
                f"📱 **NUMBER DETAILS**\n\n"
                f"📞 **MOBILE:** {result.get('mobile', 'N/A')}\n"
                f"📞 **ALT MOBILE:** {result.get('alt_mobile', 'N/A')}\n"
                f"👤 **NAME:** {result.get('name', 'N/A')}\n"
                f"👨 **FATHER'S NAME:** {result.get('father_name', 'N/A')}\n"
                f"🏠 **ADDRESS:** {result.get('address', 'N/A').replace('!', ', ')}\n"
                f"📡 **CIRCLE:** {result.get('circle', 'N/A')}\n"
                f"🆔 **ID NUMBER:** {result.get('id_number', 'N/A')}\n\n"
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this number.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing number info: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_pak_num_info(update: Update, context: ContextTypes.DEFAULT_TYPE, number: str):
    """Process Pakistan number information request"""
    user_id = update.effective_user.id
    
    if number in blacklisted_numbers:
        await update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    if number in protected_numbers and user_id != OWNER_ID:
        await update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    if number.startswith("+92"):
        number = number[3:]
    
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"🇵🇰 Pakistan Number Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Number: {number}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for Pakistan number information...")
    
    try:
        response = requests.get(API_ENDPOINTS["pak_num_info"].format(number=number), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "results" in data and len(data["results"]) > 0:
            formatted_response = "🇵🇰 **PAKISTAN INFO**\n\n"
            
            for i, result in enumerate(data["results"], 1):
                formatted_response += (
                    f"{i}️⃣\n"
                    f"👤 **NAME:** {result.get('Name', 'N/A')}\n"
                    f"🆔 **CNIC:** {result.get('CNIC', 'N/A')}\n"
                    f"📞 **MOBILE:** {result.get('Mobile', 'N/A')}\n"
                    f"🏠 **ADDRESS:** {result.get('Address', 'Not Available')}\n\n"
                )
            
            formatted_response += (
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this number.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing Pakistan number info: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_aadhar_details(update: Update, context: ContextTypes.DEFAULT_TYPE, aadhaar: str):
    """Process Aadhaar details request"""
    user_id = update.effective_user.id
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"🆔 Aadhaar Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Aadhaar: {aadhaar[:4]}XXXX{aadhaar[-4:] if len(aadhaar) > 8 else ''}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for Aadhaar details...")
    
    try:
        response = requests.get(API_ENDPOINTS["aadhar_details"].format(aadhaar=aadhaar), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            formatted_response = "🆔 **AADHAR DETAILS**\n\n"
            
            for i, result in enumerate(data, 1):
                formatted_response += (
                    f"{i}️⃣\n"
                    f"📞 **MOBILE:** {result.get('mobile', 'N/A')}\n"
                    f"👤 **NAME:** {result.get('name', 'N/A')}\n"
                    f"👨 **FATHER'S NAME:** {result.get('father_name', 'N/A')}\n"
                    f"🏠 **ADDRESS:** {result.get('address', 'N/A').replace('!', ', ')}\n"
                    f"📞 **ALT MOBILE:** {result.get('alt_mobile', 'N/A')}\n"
                    f"📡 **CIRCLE:** {result.get('circle', 'N/A')}\n"
                    f"🆔 **ID NUMBER:** {result.get('id_number', 'N/A')}\n"
                    f"📧 **EMAIL:** {result.get('email', 'N/A')}\n\n"
                )
            
            formatted_response += (
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this Aadhaar number.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing Aadhar details: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_aadhar_family(update: Update, context: ContextTypes.DEFAULT_TYPE, aadhaar: str):
    """Process Aadhaar family information request"""
    user_id = update.effective_user.id
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"👨‍👩‍👧 Aadhaar Family Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Aadhaar: {aadhaar[:4]}XXXX{aadhaar[-4:] if len(aadhaar) > 8 else ''}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for Aadhaar family information...")
    
    try:
        response = requests.get(API_ENDPOINTS["aadhar_family"].format(aadhaar=aadhaar), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "memberDetailsList" in data and len(data["memberDetailsList"]) > 0:
            formatted_response = (
                f"🆔 **AADHAR FAMILY INFO**\n\n"
                f"🆔 **RC ID:** {data.get('rcId', 'N/A')}\n"
                f"📋 **SCHEME:** {data.get('schemeName', 'N/A')} ({data.get('scheme', 'N/A')})\n"
                f"🏙️ **DISTRICT:** {data.get('homeDistName', 'N/A')}\n"
                f"🌍 **STATE:** {data.get('homeStateName', 'N/A')}\n"
                f"🏪 **FPS ID:** {data.get('fpsId', 'N/A')}\n\n"
                f"👨‍👩‍👧 **FAMILY MEMBERS:**\n"
            )
            
            for i, member in enumerate(data["memberDetailsList"], 1):
                formatted_response += (
                    f"{i}️⃣ {member.get('memberName', 'N/A')} — {member.get('releationship_name', 'N/A')}\n"
                )
            
            formatted_response += (
                f"\n📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this Aadhaar number.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing Aadhar family info: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_upi_info(update: Update, context: ContextTypes.DEFAULT_TYPE, upi_id: str):
    """Process UPI information request"""
    user_id = update.effective_user.id
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"💳 UPI Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 UPI ID: {upi_id}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for UPI information...")
    
    try:
        response = requests.get(API_ENDPOINTS["upi_info"].format(upi_id=upi_id), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "bank_details_raw" in data and "vpa_details" in data:
            bank_details = data["bank_details_raw"]
            vpa_details = data["vpa_details"]
            
            formatted_response = (
                f"🏦 **BANK DETAILS**\n\n"
                f"🏠 **ADDRESS:** {bank_details.get('ADDRESS', 'N/A')}\n"
                f"🏦 **BANK:** {bank_details.get('BANK', 'N/A')}\n"
                f"🔢 **BANKCODE:** {bank_details.get('BANKCODE', 'N/A')}\n"
                f"🏢 **BRANCH:** {bank_details.get('BRANCH', 'N/A')}\n"
                f"🌆 **CENTRE:** {bank_details.get('CENTRE', 'N/A')}\n"
                f"🏙️ **CITY:** {bank_details.get('CITY', 'N/A')}\n"
                f"📞 **CONTACT:** {bank_details.get('CONTACT', 'N/A')}\n"
                f"🗺️ **DISTRICT:** {bank_details.get('DISTRICT', 'N/A')}\n"
                f"🔢 **IFSC:** {bank_details.get('IFSC', 'N/A')}\n"
                f"📟 **MICR:** {bank_details.get('MICR', 'N/A')}\n"
                f"🌍 **STATE:** {bank_details.get('STATE', 'N/A')}\n"
                f"💸 **IMPS:** {'✅' if bank_details.get('IMPS') else '❌'}\n"
                f"💸 **NEFT:** {'✅' if bank_details.get('NEFT') else '❌'}\n"
                f"💸 **RTGS:** {'✅' if bank_details.get('RTGS') else '❌'}\n"
                f"💸 **UPI:** {'✅' if bank_details.get('UPI') else '❌'}\n"
                f"💸 **SWIFT:** {bank_details.get('SWIFT', 'N/A')}\n\n"
                f"👤 **ACCOUNT HOLDER**\n\n"
                f"🔢 **IFSC:** {vpa_details.get('ifsc', 'N/A')}\n"
                f"👤 **NAME:** {vpa_details.get('name', 'N/A')}\n"
                f"💳 **VPA:** {vpa_details.get('vpa', 'N/A')}\n\n"
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this UPI ID.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing UPI info: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_ip_details(update: Update, context: ContextTypes.DEFAULT_TYPE, ip_address: str):
    """Process IP details request"""
    user_id = update.effective_user.id
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"🌐 IP Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 IP: {ip_address}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for IP details...")
    
    try:
        response = requests.get(API_ENDPOINTS["ip_details"].format(ip=ip_address), timeout=10)
        response.raise_for_status()
        data = response.text
        
        if data:
            formatted_response = (
                f"{data}\n\n"
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response)
        else:
            await processing_message.edit_text("❌ No information found for this IP address.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing IP details: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_tg_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_str: str):
    """Process Telegram user stats request"""
    user_id = update.effective_user.id
    credits_db[user_id] -= 1
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"👤 Telegram User Stats Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Target User ID: {user_id_str}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for Telegram user stats...")
    
    try:
        response = requests.get(API_ENDPOINTS["tg_user_stats"].format(user_id=user_id_str), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("success") and "data" in data:
            user_data = data["data"]
            
            formatted_response = (
                f"👤 **TELEGRAM USER STATS**\n\n"
                f"👤 **NAME:** {user_data.get('first_name', 'N/A')} {user_data.get('last_name', '')}\n"
                f"🆔 **USER ID:** {user_data.get('id', 'N/A')}\n"
                f"🤖 **IS BOT:** {'✅' if user_data.get('is_bot') else '❌'}\n"
                f"🟢 **ACTIVE:** {'✅' if user_data.get('is_active') else '❌'}\n\n"
                f"📊 **STATS**\n\n"
                f"👥 **TOTAL GROUPS:** {user_data.get('total_groups', 'N/A')}\n"
                f"👑 **ADMIN IN GROUPS:** {user_data.get('adm_in_groups', 'N/A')}\n"
                f"💬 **TOTAL MESSAGES:** {user_data.get('total_msg_count', 'N/A')}\n"
                f"💬 **MESSAGES IN GROUPS:** {user_data.get('msg_in_groups_count', 'N/A')}\n"
                f"🕐 **FIRST MSG DATE:** {user_data.get('first_msg_date', 'N/A')}\n"
                f"🕐 **LAST MSG DATE:** {user_data.get('last_msg_date', 'N/A')}\n"
                f"📝 **NAME CHANGES:** {user_data.get('names_count', 'N/A')}\n"
                f"📝 **USERNAME CHANGES:** {user_data.get('usernames_count', 'N/A')}\n\n"
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No information found for this user ID.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing TG user stats: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

async def process_call_history(update: Update, context: ContextTypes.DEFAULT_TYPE, number: str):
    """Process call history request"""
    user_id = update.effective_user.id
    
    if user_id not in credits_db or credits_db[user_id] < 600:
        await update.message.reply_text(
            "❌ You don't have enough credits for this service.\n\n"
            "💰 Call history requires 600 credits.\n"
            "Buy more credits to use this service."
        )
        return
    
    if number in blacklisted_numbers:
        await update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    if number in protected_numbers and user_id != OWNER_ID:
        await update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    if number.startswith("+91"):
        number = number[3:]
    
    credits_db[user_id] -= 600
    
    try:
        await context.bot.send_message(
            SEARCH_LOGS_CHANNEL,
            f"📞 Call History Search\n\n"
            f"👤 User: {update.effective_user.first_name} ({user_id})\n"
            f"🔍 Number: {number}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log search: {e}")
    
    processing_message = await update.message.reply_text("🔍 Searching for call history...")
    
    try:
        response = requests.get(API_ENDPOINTS["call_history"].format(number=number), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data:
            formatted_response = (
                f"📞 **CALL HISTORY**\n\n"
                f"📞 **NUMBER:** {number}\n\n"
                f"📊 **CALL DETAILS:**\n"
                f"```json\n{json.dumps(data, indent=2)}\n```\n\n"
                f"📊 Data provided by @DataTraceUpdates\n"
                f"📞 Contact Admin: @{ADMIN_CONTACT}"
            )
            
            await processing_message.edit_text(formatted_response, parse_mode='Markdown')
        else:
            await processing_message.edit_text("❌ No call history found for this number.")
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        await processing_message.edit_text("❌ The API is currently down. Please try again later.")
    except Exception as e:
        logger.error(f"Error processing call history: {e}")
        await processing_message.edit_text("❌ An error occurred while processing your request.")

# --- Command Handlers ---
async def num_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_number_info(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide a number after the command.\n\nExample: /num 9876543210")

async def pak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_pak_num_info(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide a Pakistan number after the command.\n\nExample: /pak 923001234567")

async def aadhar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_aadhar_details(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide an Aadhaar number after the command.\n\nExample: /aadhar 123456789012")

async def aadhar2fam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_aadhar_family(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide an Aadhaar number after the command.\n\nExample: /aadhar2fam 123456789012")

async def upi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_upi_info(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide a UPI ID after the command.\n\nExample: /upi example@upi")

async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_ip_details(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide an IP address after the command.\n\nExample: /ip 8.8.8.8")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_tg_user_stats(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide a user ID after the command.\n\nExample: /stats 123456789")

async def call_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await process_call_history(update, context, context.args[0])
    else:
        await update.message.reply_text("Please provide a number after the command.\n\nExample: /call 9876543210")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    credits = credits_db.get(user_id, 0)
    await update.message.reply_text(
        f"💳 **Your Credit Balance:** {credits} credits\n\n"
        f"💰 Buy more credits or refer friends to earn free credits."
    )

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    referral_count = len(referrals_db.get(str(user_id), []))
    await update.message.reply_text(
        f"👥 **Referral Program**\n\n"
        f"🔗 **Your Referral Link:** {referral_link}\n\n"
        f"📊 **Your Referrals:** {referral_count}\n\n"
        f"🎁 **Referral Benefits:**\n"
        f"• 1 credit for each person who joins using your link\n"
        f"• 30% commission (in credits) when your referrals buy credits\n\n"
        f"**Example:**\n"
        f"• Friend joins → They get 1 free credit\n"
        f"• Friend buys 1000 credits → You get 300 credits commission\n"
        f"• Friend buys 5000 credits → You get 1500 credits commission"
    )

async def protect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🛡️ **Protect Your Data**\n\n"
        f"For ₹300, you can protect your personal information from being searched through this bot.\n\n"
        f"Contact @{ADMIN_CONTACT} to proceed with data protection."
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 **Contact Admin**\n\n"
        f"For any queries or support, please contact:\n"
        f"@{ADMIN_CONTACT}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **Help & Commands**\n\n"
        "🔍 **Lookup Commands:**\n"
        "• /num [number] - Get number information\n"
        "• /pak [number] - Get Pakistan number information\n"
        "• /aadhar [aadhaar] - Get Aadhaar details\n"
        "• /aadhar2fam [aadhaar] - Get Aadhaar family information\n"
        "• /upi [upi_id] - Get UPI information\n"
        "• /ip [ip_address] - Get IP details\n"
        "• /stats [user_id] - Get Telegram user stats\n"
        "• /call [number] - Get call history (Paid - 600 credits)\n\n"
        "💰 **Credit Commands:**\n"
        "• /balance - Check your credit balance\n"
        "• /buy - Buy credits\n\n"
        "👥 **Referral Commands:**\n"
        "• /referral - Get your referral link\n\n"
        "🛡️ **Protection Commands:**\n"
        "• /protect - Protect your data\n\n"
        "📞 **Contact:**\n"
        "• /admin - Contact admin\n\n"
        "ℹ️ You can also use the bot by directly sending a number or UPI ID without commands."
    )
    await update.message.reply_text(help_text)

# --- Admin Commands ---
async def add_credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addcredits [user_id] [credits]")
        return
    
    target_user_id = int(context.args[0])
    credits_to_add = int(context.args[1])
    
    if target_user_id in credits_db:
        credits_db[target_user_id] += credits_to_add
    else:
        credits_db[target_user_id] = credits_to_add
    
    await update.message.reply_text(f"✅ Added {credits_to_add} credits to user {target_user_id}.")
    
    try:
        await context.bot.send_message(
            target_user_id,
            f"🎉 You've received {credits_to_add} credits from an admin!\n"
            f"Your current balance: {credits_db[target_user_id]} credits"
        )
    except Exception as e:
        logger.error(f"Failed to notify user about added credits: {e}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /ban [user_id]")
        return
    
    target_user_id = int(context.args[0])
    if target_user_id in users_db:
        users_db[target_user_id]["banned"] = True
        await update.message.reply_text(f"✅ User {target_user_id} has been banned.")
    else:
        await update.message.reply_text(f"❌ User {target_user_id} not found in database.")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unban [user_id]")
        return
    
    target_user_id = int(context.args[0])
    if target_user_id in users_db:
        users_db[target_user_id]["banned"] = False
        await update.message.reply_text(f"✅ User {target_user_id} has been unbanned.")
    else:
        await update.message.reply_text(f"❌ User {target_user_id} not found in database.")

async def sudo_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for admins only.")
        return
    
    sudo_list = "\n".join([f"• {sudo_id}" for sudo_id in SUDO_USERS])
    await update.message.reply_text(f"👑 **Sudo Users List:**\n\n{sudo_list}")

async def protected_numbers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ This command is for the owner only.")
        return
    
    protected_list = "\n".join([f"• {number}" for number in protected_numbers])
    await update.message.reply_text(f"🛡️ **Protected Numbers List:**\n\n{protected_list}")

async def stats_count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for sudo users only.")
        return
    
    total_users = len(users_db)
    total_credits = sum(credits_db.values())
    total_referrals = sum(len(referrals) for referrals in referrals_db.values())
    
    await update.message.reply_text(
        f"📊 **Bot Statistics:**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"💳 **Total Credits Distributed:** {total_credits}\n"
        f"👥 **Total Referrals:** {total_referrals}\n"
        f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

async def gcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in SUDO_USERS:
        await update.message.reply_text("❌ This command is for sudo users only.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /gcast [message]")
        return
    
    message = " ".join(context.args)
    success_count = 0
    fail_count = 0
    
    await update.message.reply_text("📢 Broadcasting message to all users...")
    
    for uid in users_db:
        try:
            await context.bot.send_message(uid, message)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send message to {uid}: {e}")
            fail_count += 1
    
    await update.message.reply_text(
        f"✅ Broadcast completed!\n\n"
        f"✅ **Success:** {success_count} users\n"
        f"❌ **Failed:** {fail_count} users"
    )

async def buydb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🗄️ **Buy Database/API**\n\n"
        f"To purchase our database or API access, please contact:\n"
        f"@{ADMIN_CONTACT}\n\n"
        f"We offer various packages tailored to your needs."
    )

async def buyapi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔌 **Buy API Access**\n\n"
        f"To purchase API access, please contact:\n"
        f"@{ADMIN_CONTACT}\n\n"
        f"We offer various packages tailored to your needs."
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for credits, prices in CREDIT_PRICES.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{credits} Credits - ₹{prices['inr']} | {prices['usdt']} USDT",
                callback_data=f"buy_{credits}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💰 Select a credit package to purchase:", reply_markup=reply_markup)

async def group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in groups"""
    message = update.message
    if f"@{context.bot.username}" in message.text or message.text.strip().isdigit():
        if not await is_user_member(update, context):
            await send_not_member_message(update, context)
            return
        
        if message.text.strip().isdigit():
            await process_number_info(update, context, message.text.strip())
        else:
            help_text = (
                "📖 **DataTrace OSINT Bot**\n\n"
                "I can help you find information about:\n"
                "• Phone numbers\n"
                "• UPI IDs\n"
                "• IP addresses\n"
                "• Aadhaar numbers\n"
                "• And more!\n\n"
                "Send me a number or UPI ID directly, or use /help to see all commands."
            )
            await message.reply_text(help_text)

# --- New Error Handler for v20.x ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update: %s", context.error)

# --- Main function with new structure ---
# ... (keep all the code above this point the same) ...

# --- New post_init function for async setup ---
async def post_init(application: Application) -> None:
    """
    Post-initialization function to set bot commands.
    This is the recommended way to run async setup code.
    """
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("num", "Get number information"),
        BotCommand("pak", "Get Pakistan number information"),
        BotCommand("aadhar", "Get Aadhaar details"),
        BotCommand("aadhar2fam", "Get Aadhaar family information"),
        BotCommand("upi", "Get UPI information"),
        BotCommand("ip", "Get IP details"),
        BotCommand("stats", "Get Telegram user stats"),
        BotCommand("call", "Get call history (Paid)"),
        BotCommand("balance", "Check your credit balance"),
        BotCommand("referral", "Get your referral link"),
        BotCommand("protect", "Protect your data"),
        BotCommand("admin", "Contact admin"),
        BotCommand("help", "Show help"),
        BotCommand("buy", "Buy credits"),
        BotCommand("buydb", "Buy database"),
        BotCommand("buyapi", "Buy API access")
    ]
    await application.bot.set_my_commands(commands)


# --- Corrected main function ---
def main():
    """Start the bot."""
    # Build the application and register the post_init handler
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)  # <-- This is the key change
        .build()
    )
    
    # --- Add handlers to the application ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("num", num_command))
    application.add_handler(CommandHandler("pak", pak_command))
    application.add_handler(CommandHandler("aadhar", aadhar_command))
    application.add_handler(CommandHandler("aadhar2fam", aadhar2fam_command))
    application.add_handler(CommandHandler("upi", upi_command))
    application.add_handler(CommandHandler("ip", ip_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("call", call_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("protect", protect_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("buydb", buydb_command))
    application.add_handler(CommandHandler("buyapi", buyapi_command))
    
    # Admin commands
    application.add_handler(CommandHandler("addcredits", add_credits_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("sudolist", sudo_list_command))
    application.add_handler(CommandHandler("protected", protected_numbers_command))
    application.add_handler(CommandHandler("statscount", stats_count_command))
    application.add_handler(CommandHandler("gcast", gcast_command))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handler for direct messages
    # NEW (Correct)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # NEW (Correct)
    application.add_handler(MessageHandler(filters.ChatType.GROUP & filters.TEXT, group_message))
    # Error handler
    application.add_error_handler(error_handler)
    
    # --- Start the Bot ---
    # This is a synchronous call that starts the async event loop
    application.run_polling()


if __name__ == '__main__':
    main()
