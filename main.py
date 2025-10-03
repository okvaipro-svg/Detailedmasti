import logging
import json
import requests
import random
import string
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
from telegram.error import BadRequest

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
OWNER_ID = 7924074157
SUDO_USERS = [7924074157, 5294360309, 7905267752]
START_LOGS_CHANNEL = -1002765060940
SEARCH_LOGS_CHANNEL = -1003066524164
MANDATORY_CHANNELS = ["DataTraceUpdates", "DataTraceOSINTSupport"]
ADMIN_CONTACT = "t.me/DataTraceSupport"

# Database (In production, use a proper database)
users_db = {}
referrals_db = {}
credits_db = {}
protected_numbers = ["+917724814462"]
blacklisted_numbers = ["+917724814462"]
pending_purchases = {}

# API Endpoints
API_ENDPOINTS = {
    "upi_info": "https://upi-info.vercel.app/api/upi?upi_id={upi_id}&key=456",
    "num_info": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={number}",
    "tg_user_stats": "https://tg-info-neon.vercel.app/user-details?user={user_id}",
    "ip_details": "https://karmali.serv00.net/ip_api.php?ip={ip}",
    "pak_num_info": "https://pak-num-api.vercel.app/search?number={number}",
    "aadhar_family": "https://family-members-n5um.vercel.app/fetch?aadhaar={aadhaar}&key=paidchx",
    "aadhar_details": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={aadhaar}",
    "call_history": "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
}

# Credit Prices
CREDIT_PRICES = {
    100: {"inr": 50, "usdt": 0.45},
    200: {"inr": 100, "usdt": 0.9},
    500: {"inr": 250, "usdt": 2.25},
    1000: {"inr": 450, "usdt": 4.0},
    2000: {"inr": 900, "usdt": 8.0},
    5000: {"inr": 2250, "usdt": 20.0}
}

# States for conversation
SELECT_SERVICE, ENTER_DETAILS = range(2)

def is_user_member(update: Update, context: CallbackContext) -> bool:
    """Check if user is a member of all mandatory channels"""
    user_id = update.effective_user.id
    bot = context.bot
    
    for channel in MANDATORY_CHANNELS:
        try:
            member = bot.get_chat_member(f"@{channel}", user_id)
            if member.status in ["left", "kicked"]:
                return False
        except BadRequest:
            return False
    
    return True

def send_not_member_message(update: Update, context: CallbackContext):
    """Send message asking user to join mandatory channels"""
    keyboard = []
    for channel in MANDATORY_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"Join {channel}", url=f"http://t.me/{channel}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "❌ You need to join all mandatory channels to use this bot.\n\n"
        "Please join the channels below and then click /start again:",
        reply_markup=reply_markup
    )

def start(update: Update, context: CallbackContext):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Log to channel
    try:
        context.bot.send_message(
            START_LOGS_CHANNEL,
            f"🆕 New User Started\n\n"
            f"👤 Name: {user.first_name} {user.last_name or ''}\n"
            f"🆔 ID: {user_id}\n"
            f"🔗 Username: @{user.username}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to log start message: {e}")
    
    # Check if user is member of mandatory channels
    if not is_user_member(update, context):
        send_not_member_message(update, context)
        return
    
    # Process referral if any
    if context.args:
        referrer_id = context.args[0]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            if referrer_id not in referrals_db:
                referrals_db[referrer_id] = []
            
            if user_id not in referrals_db[referrer_id]:
                referrals_db[referrer_id].append(user_id)
                
                # Give referral bonus
                if referrer_id in credits_db:
                    credits_db[referrer_id] += 1
                else:
                    credits_db[referrer_id] = 1
                
                # Give new user bonus
                if user_id in credits_db:
                    credits_db[user_id] += 1
                else:
                    credits_db[user_id] = 1
                
                try:
                    context.bot.send_message(
                        referrer_id,
                        f"🎉 Someone joined using your referral link!\n"
                        f"You've received 1 credit as a bonus.\n"
                        f"Your current balance: {credits_db[referrer_id]} credits"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer: {e}")
    
    # Initialize user in database if not exists
    if user_id not in users_db:
        users_db[user_id] = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "banned": False
        }
    
    # Initialize credits if not exists
    if user_id not in credits_db:
        credits_db[user_id] = 2  # Give 2 free credits on start
    
    # Generate referral link
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    
    # Create main menu
    keyboard = [
        [InlineKeyboardButton("🔍 Lookup Services", callback_data="lookup_services")],
        [InlineKeyboardButton("💰 Buy Credits", callback_data="buy_credits")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
        [InlineKeyboardButton("🛡️ Protect Your Data", callback_data="protect_data")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://{ADMIN_CONTACT}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        f"🔍 DataTrace OSINT Bot provides various lookup services.\n\n"
        f"💳 Your Credits: {credits_db[user_id]}\n\n"
        f"🔗 Your Referral Link: {referral_link}\n\n"
        f"Share your referral link to earn free credits!",
        reply_markup=reply_markup
    )

def button_callback(update: Update, context: CallbackContext):
    """Handle button callbacks"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Check if user is member of mandatory channels
    if not is_user_member(update, context):
        send_not_member_message(update, context)
        return
    
    if query.data == "lookup_services":
        keyboard = [
            [InlineKeyboardButton("📱 Number Info", callback_data="num_info")],
            [InlineKeyboardButton("🇵🇰 Pakistan Number", callback_data="pak_num_info")],
            [InlineKeyboardButton("🆔 Aadhar Details", callback_data="aadhar_details")],
            [InlineKeyboardButton("👨‍👩‍👧 Aadhar to Family", callback_data="aadhar_family")],
            [InlineKeyboardButton("💳 UPI Info", callback_data="upi_info")],
            [InlineKeyboardButton("🌐 IP Details", callback_data="ip_details")],
            [InlineKeyboardButton("👤 Telegram User Stats", callback_data="tg_user_stats")],
            [InlineKeyboardButton("📞 Call History (Paid)", callback_data="call_history")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "🔍 Select a lookup service:",
            reply_markup=reply_markup
        )
        
    elif query.data == "buy_credits":
        keyboard = []
        for credits, prices in CREDIT_PRICES.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{credits} Credits - ₹{prices['inr']} | {prices['usdt']} USDT",
                    callback_data=f"buy_{credits}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "💰 Select a credit package to purchase:",
            reply_markup=reply_markup
        )
        
    elif query.data.startswith("buy_"):
        credits_amount = int(query.data.split("_")[1])
        prices = CREDIT_PRICES[credits_amount]
        
        # Store pending purchase
        pending_purchases[user_id] = credits_amount
        
        keyboard = [
            [InlineKeyboardButton("💳 Pay with UPI", callback_data="pay_upi")],
            [InlineKeyboardButton("💎 Pay with USDT", callback_data="pay_usdt")],
            [InlineKeyboardButton("📞 Contact Admin for Payment", url=f"https://{ADMIN_CONTACT}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="buy_credits")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"💰 Selected Package: {credits_amount} Credits\n\n"
            f"💵 Price: ₹{prices['inr']} or {prices['usdt']} USDT\n\n"
            f"Select a payment method:",
            reply_markup=reply_markup
        )
        
    elif query.data in ["pay_upi", "pay_usdt"]:
        payment_method = "UPI" if query.data == "pay_upi" else "USDT"
        credits_amount = pending_purchases.get(user_id, 0)
        prices = CREDIT_PRICES[credits_amount]
        
        if payment_method == "UPI":
            query.edit_message_text(
                f"💳 UPI Payment Details\n\n"
                f"Amount: ₹{prices['inr']}\n"
                f"UPI ID: [Your UPI ID Here]\n\n"
                f"After payment, send a screenshot to @{ADMIN_CONTACT} to get your credits."
            )
        else:
            query.edit_message_text(
                f"💎 USDT Payment Details\n\n"
                f"Amount: {prices['usdt']} USDT\n"
                f"Wallet Address: [Your USDT Wallet Here]\n\n"
                f"After payment, send a screenshot to @{ADMIN_CONTACT} to get your credits."
            )
    
    elif query.data == "referral_program":
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        referral_count = len(referrals_db.get(str(user_id), []))
        
        keyboard = [
            [InlineKeyboardButton("📤 Share Referral Link", switch_inline_query=referral_link)],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"👥 Referral Program\n\n"
            f"🔗 Your Referral Link: {referral_link}\n\n"
            f"📊 Your Referrals: {referral_count}\n\n"
            f"🎁 Referral Benefits:\n"
            f"• 1 credit for each person who joins using your link\n"
            f"• 30% commission (in credits) when your referrals buy credits\n\n"
            f"Example:\n"
            f"• Friend joins → They get 1 free credit\n"
            f"• Friend buys 1000 credits → You get 300 credits commission\n"
            f"• Friend buys 5000 credits → You get 1500 credits commission",
            reply_markup=reply_markup
        )
        
    elif query.data == "protect_data":
        keyboard = [
            [InlineKeyboardButton("📞 Contact Admin for Protection", url=f"https://{ADMIN_CONTACT}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"🛡️ Protect Your Data\n\n"
            f"For ₹300, you can protect your personal information from being searched through this bot.\n\n"
            f"Contact @{ADMIN_CONTACT} to proceed with data protection.",
            reply_markup=reply_markup
        )
        
    elif query.data == "help":
        help_text = (
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
        
        query.edit_message_text(
            help_text,
            reply_markup=reply_markup
        )
        
    elif query.data == "back_to_main":
        # Generate referral link
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
        
        # Create main menu
        keyboard = [
            [InlineKeyboardButton("🔍 Lookup Services", callback_data="lookup_services")],
            [InlineKeyboardButton("💰 Buy Credits", callback_data="buy_credits")],
            [InlineKeyboardButton("👥 Referral Program", callback_data="referral_program")],
            [InlineKeyboardButton("🛡️ Protect Your Data", callback_data="protect_data")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("📞 Contact Admin", url=f"https://{ADMIN_CONTACT}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
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
        
        query.edit_message_text(
            prompts[query.data],
            reply_markup=reply_markup
        )
        
        return SELECT_SERVICE

def handle_message(update: Update, context: CallbackContext):
    """Handle direct messages (non-command)"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    # Check if user is member of mandatory channels
    if not is_user_member(update, context):
        send_not_member_message(update, context)
        return
    
    # Check if user has enough credits
    if user_id not in credits_db or credits_db[user_id] <= 0:
        update.message.reply_text(
            "❌ You don't have enough credits to use this service.\n\n"
            "💰 Buy more credits or refer friends to earn free credits."
        )
        return
    
    # Check if user is in a conversation state
    if 'service' in context.user_data:
        service = context.user_data['service']
        
        # Process based on service
        if service == "num_info":
            process_number_info(update, context, message_text)
        elif service == "pak_num_info":
            process_pak_num_info(update, context, message_text)
        elif service == "aadhar_details":
            process_aadhar_details(update, context, message_text)
        elif service == "aadhar_family":
            process_aadhar_family(update, context, message_text)
        elif service == "upi_info":
            process_upi_info(update, context, message_text)
        elif service == "ip_details":
            process_ip_details(update, context, message_text)
        elif service == "tg_user_stats":
            process_tg_user_stats(update, context, message_text)
        elif service == "call_history":
            process_call_history(update, context, message_text)
        
        # Clear the service state
        del context.user_data['service']
        return
    
    # If not in a conversation state, try to detect the service based on input
    if message_text.startswith("+"):
        if message_text.startswith("+92"):
            # Pakistan number
            process_pak_num_info(update, context, message_text)
        else:
            # Other international number
            process_number_info(update, context, message_text)
    elif message_text.isdigit() and len(message_text) >= 10:
        # Likely a mobile number
        process_number_info(update, context, message_text)
    elif "@" in message_text and "." in message_text:
        # Likely a UPI ID
        process_upi_info(update, context, message_text)
    elif "." in message_text and len(message_text.split(".")) == 4:
        # Likely an IP address
        process_ip_details(update, context, message_text)
    elif message_text.isdigit() and len(message_text) == 12:
        # Likely an Aadhaar number
        process_aadhar_details(update, context, message_text)
    else:
        update.message.reply_text(
            "❌ I couldn't recognize your input.\n\n"
            "Please use the /help command to see available services or select from the menu."
        )

def process_number_info(update: Update, context: CallbackContext, number: str):
    """Process number information request"""
    user_id = update.effective_user.id
    
    # Check if number is blacklisted
    if number in blacklisted_numbers:
        update.message.reply_text("❌ This number is blacklisted and cannot be searched.")
        return
    
    # Check if number is protected and user is not owner
    if number in protected_numbers and user_id != OWNER_ID:
        update.message.reply_text("❌ This number is protected and cannot be searched.")
        return
    
    # Clean the number (remove +91 if pait msg.answer("Broadcast sent.")

@dp.message_handler(commands=['sudolist'])
async def sudolist_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    lst = get_sudo_list()
    await msg.answer(f"Sudo list: {lst}")

@dp.message_handler(commands=['buydb', 'buyapi'])
async def buy_cmd(msg: types.Message):
    await msg.answer(f"Contact admin: {ADMIN_CONTACT}")

@dp.message_handler(commands=['protected'])
async def protected_cmd(msg: types.Message):
    if msg.from_user.id == OWNER_ID:
        await msg.answer(f"Protected Numbers:\n{PROTECTED_NUMBERS}")
    else:
        await msg.answer("Only owner can view protected numbers.")

@dp.message_handler(commands=['blacklist'])
async def blacklist_cmd(msg: types.Message):
    if msg.from_user.id == OWNER_ID:
        await msg.answer(f"Blacklisted Numbers:\n{BLACKLIST_NUMBERS}")
    else:
        await msg.answer("Only owner can view blacklist.")

# --- Unified Query Handlers ---
async def fetch_api(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                return await resp.json()
            except:
                return await resp.text()

async def handle_number(msg, number):
    user_id = msg.from_user.id
    if number in BLACKLIST_NUMBERS:
        await msg.answer("Blacklisted number. No result.")
        return
    api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={number[-10:]}"
    data = await fetch_api(api_url)
    try:
        res = data['data'][0]
        body = (
            f"📞 Mobile: {res['mobile']} | Alt: {res['alt']}\n"
            f"👤 Name: {res['name']}\n"
            f"🧾 Full Name: {res['fname']}\n"
            f"🏠 Address: {res['address'].replace('!', ', ')}\n"
            f"🌐 Circle: {res['circle']}\n"
            f"🆔 ID: {res['id']}"
        )
        await msg.answer(format_response("📱 NUMBER SEARCH RESULT", body))
        log_query(user_id, number, body)
    except:
        await msg.answer("No info found.")

async def handle_pak(msg, number):
    user_id = msg.from_user.id
    api_url = f"https://pak-num-api.vercel.app/search?number={number}"
    data = await fetch_api(api_url)
    try:
        items = data['results']
        msg_text = ""
        for idx, item in enumerate(items, 1):
            msg_text += (
                f"{idx}️⃣\n👤 Name: {item['Name']}\n🆔 CNIC: {item['CNIC']}\n📞 Mobile: {item['Mobile']}\n"
                f"🏠 Address: {item['Address'] if item['Address'] else '(Not Available)'}\n"
            )
        await msg.answer(format_response("🇵🇰 PAKISTAN SEARCH RESULT", msg_text))
        log_query(user_id, number, msg_text)
    except:
        await msg.answer("No info found.")

async def handle_aadhar(msg, number):
    user_id = msg.from_user.id
    api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={number}"
    data = await fetch_api(api_url)
    try:
        res = data['data'][0]
        body = (
            f"📞 Mobile: {res['mobile']} | Alt: {res['alt']}\n"
            f"👤 Name: {res['name']}\n"
            f"🧾 Full Name: {res['fname']}\n"
            f"🏠 Address: {res['address'].replace('!', ', ')}\n"
            f"🌐 Circle: {res['circle']}\n"
            f"🆔 ID: {res['id']}"
        )
        await msg.answer(format_response("🆔 AADHAR SEARCH RESULT", body))
        log_query(user_id, number, body)
    except:
        await msg.answer("No info found.")

async def handle_aadhar2fam(msg, number):
    user_id = msg.from_user.id
    api_url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={number}&key=paidchx"
    data = await fetch_api(api_url)
    try:
        lst = data['memberDetailsList']
        members_txt = ""
        for idx, m in enumerate(lst, 1):
            members_txt += f"{idx}️⃣ {m['memberName']} — {m['releationship_name']}\n"
        body = (
            f"RC ID: {data['rcId']}\nScheme: {data['schemeName']}\nDistrict: {data['homeDistName']}\n"
            f"State: {data['homeStateName']}\nFPS ID: {data['fpsId']}\n\n👨‍👩‍👧 FAMILY MEMBERS:\n{members_txt}"
        )
        await msg.answer(format_response("🆔 AADHAR FAMILY SEARCH RESULT", body))
        log_query(user_id, number, body)
    except:
        await msg.answer("No info found.")

async def handle_upi(msg, vpa):
    user_id = msg.from_user.id
    api_url = f"https://upi-info.vercel.app/api/upi?upi_id={vpa}&key=456"
    data = await fetch_api(api_url)
    try:
        bd = data['bank_details_raw']
        vd = data['vpa_details']
        body = (
            f"👤 Name: {vd['name']}\n💳 VPA: {vd['vpa']}\n🏦 Bank: {bd['BANK']} ({bd['BRANCH']})\n"
            f"📍 Address: {bd['ADDRESS']}\nIFSC: {bd['IFSC']} | MICR: {bd['MICR']}"
        )
        await msg.answer(format_response("🏦 UPI SEARCH RESULT", body))
        log_query(user_id, vpa, body)
    except:
        await msg.answer("No info found.")

async def handle_ip(msg, ip):
    user_id = msg.from_user.id
    api_url = f"https://karmali.serv00.net/ip_api.php?ip={ip}"
    data = await fetch_api(api_url)
    try:
        body = (
            f"🌍 Country: {data['country']} ({data['countryCode']})\n"
            f"📍 Region: {data['regionName']}, City: {data['city']}\n"
            f"📮 Zip: {data['zip']}\n🕒 Timezone: {data['timezone']}\n"
            f"📡 ISP: {data['isp']}\n🔥 Org: {data['org']}\nAS: {data['as']}\nIP: {data['query']}"
        )
        await msg.answer(format_response("🛰 IP SEARCH RESULT", body))
        log_query(user_id, ip, body)
    except:
        await msg.answer("No info found.")

async def handle_tgstats(msg, tg_id):
    user_id = msg.from_user.id
    api_url = f"https://tg-info-neon.vercel.app/user-details?user={tg_id}"
    data = await fetch_api(api_url)
    try:
        d = data['data']
        body = (
            f"Name: {d['first_name']}\nUser ID: {d['id']}\nActive: {'✅' if d['is_active'] else '❌'}\nBot: {'✅' if d['is_bot'] else '❌'}\n\n"
            f"📊 Stats:\nGroups Joined: {d['total_groups']}\nAdmin in: {d['adm_in_groups']}\nTotal Messages: {d['total_msg_count']}\n"
            f"Messages in Groups: {d['msg_in_groups_count']}\nName Changes: {d['names_count']}\nUsername Changes: {d['usernames_count']}\n"
            f"🕐 First Msg: {d['first_msg_date']}\n🕐 Last Msg: {d['last_msg_date']}"
        )
        await msg.answer(format_response("👤 TELEGRAM USER STATS", body))
        log_query(user_id, tg_id, body)
    except:
        await msg.answer("No info found.")

async def handle_callhistory(msg, number):
    user_id = msg.from_user.id
    u = get_user(user_id)
    if not u or u[1] < CALL_HISTORY_PRICE:
        await msg.answer(f"Call history is paid only: ₹{CALL_HISTORY_PRICE}/search. Not enough credits.\nContact Admin.")
        return
    api_url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={number}&days=7"
    data = await fetch_api(api_url)
    await msg.answer(format_response("📞 CALL HISTORY", str(data)))
    log_query(user_id, number, str(data))
    update_credits(user_id, -CALL_HISTORY_PRICE)

# --- Main Message Handler ---
@dp.message_handler()
async def main_handler(msg: types.Message):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    txt = msg.text.strip()
    u = get_user(user_id)
    # In group: reply only if tagged, command, or number
    if msg.chat.type in ["group", "supergroup"]:
        if (msg.reply_to_message and msg.reply_to_message.from_user.id == bot.id) or \
           (msg.text.startswith("/") or re.search(r"\+91\d{10}|\d{10}|\+92\d{10}|@|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", txt)):
            pass
        else:
            return
    # Credits enforcement (except support group)
    if msg.chat.type == "private":
        # Free searches first
        free_searches = get_free_searches(user_id)
        if free_searches > 0:
            update_free_searches(user_id, -1)
        elif not u or u[1] <= 0:
            await msg.answer("Not enough credits! Refer friends or buy credits.", reply_markup=main_menu(*get_user_status(user_id)))
            return
    # Blacklist/protected logic
    if any(num in txt for num in BLACKLIST_NUMBERS):
        await msg.answer("Blacklisted number. No result.")
        return
    if txt in PROTECTED_NUMBERS and user_id != OWNER_ID:
        await msg.answer("Protected number. No result.")
        return
    # API triggers
    if re.match(r"^(\+91)?\d{10}$", txt):
        await handle_number(msg, txt)
        log_query(user_id, txt, "search")
        await bot.send_message(LOG_CHANNEL, f"User {user_id} searched: {txt}")
        return
    if txt.startswith("+92") or (txt.isdigit() and len(txt) == 12 and txt.startswith("92")):
        await handle_pak(msg, txt)
        log_query(user_id, txt, "search")
        await bot.send_message(LOG_CHANNEL, f"User {user_id} searched: {txt}")
        return
    if re.match(r"^\d{12}$", txt):
        await handle_aadhar(msg, txt)
        log_query(user_id, txt, "search")
        await bot.send_message(LOG_CHANNEL, f"User {user_id} searched: {txt}")
        return
    if "@" in txt and not txt.startswith("/"):
        await handle_upi(msg, txt)
        log_query(user_id, txt, "search")
        await bot.send_message(LOG_CHANNEL, f"User {user_id} searched: {txt}")
        return
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", txt):
        await handle_ip(msg, txt)
        log_query(user_id, txt, "search")
        await bot.send_message(LOG_CHANNEL, f"User {user_id} searched: {txt}")
        return
    await msg.answer("Unknown command or input. Use /help.", reply_markup=main_menu(*get_user_status(user_id)))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

def admin_menu(is_owner=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🚫 Ban User", callback_data="banuser"),
        InlineKeyboardButton("✅ Unban User", callback_data="unbanuser"),
        InlineKeyboardButton("📢 Broadcast", callback_data="gcast"),
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
        InlineKeyboardButton("👑 Sudo List", callback_data="sudolist"),
        InlineKeyboardButton("📋 All Logs", callback_data="alllogs"),
        InlineKeyboardButton("⬅️ Back", callback_data="back"),
    )
    if is_owner:
        kb.add(
            InlineKeyboardButton("🔐 Protected Numbers", callback_data="protectednums"),
            InlineKeyboardButton("🖤 Blacklist Numbers", callback_data="blacklistnums"),
        )
    return kb

async def check_channels(user_id):
    # Stub: always returns True, but you can implement real channel membership check with get_chat_member
    return True

def get_user_status(user_id):
    is_admin = user_id in SUDO_IDS
    is_owner = user_id == OWNER_ID
    return is_admin, is_owner

@dp.message_handler(commands=['start'])
async def start_cmd(msg: types.Message):
    user_id = msg.from_user.id
    ref_by = None
    args = msg.get_args()
    if args:
        try:
            ref_by = int(args)
            if ref_by != user_id:
                add_user(user_id, ref_by)
                update_credits(user_id, 1)
                update_credits(ref_by, 1)
        except: add_user(user_id)
    else:
        add_user(user_id)
    if not await check_channels(user_id):
        await msg.answer("Join required channels to use the bot:\n" +
                         "\n".join([f"@{x}" for x in MANDATORY_CHANNELS]))
        return
    await bot.send_message(START_CHANNEL, f"User started: {user_id}")
    is_admin, _ = get_user_status(user_id)
    await msg.answer(
        "👋 <b>Welcome to DataTraceOSINT!</b>\n\n"
        "You have 2 free searches in DM. Refer friends or buy cheap credits to unlock more.\n\n"
        "Channels required: @DataTraceUpdates & @DataTraceOSINTSupport\n\n"
        "Use commands or buttons below.",
        reply_markup=user_menu(is_admin))

@dp.callback_query_handler(lambda c: True)
async def cb_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    is_admin, is_owner = get_user_status(user_id)
    if call.data == "back":
        await call.message.edit_text("Choose an action:", reply_markup=user_menu(is_admin))
    elif call.data == "buycredits":
        await call.message.edit_text(
            f"<b>Buy Credits:</b>\n{price_table()}\n\nContact {ADMIN_CONTACT} to buy.",
            reply_markup=user_menu(is_admin))
    elif call.data == "referral":
        ref_link = f"https://t.me/YourBotName?start={user_id}"
        count = get_referrals(user_id)
        await call.message.edit_text(
            f"<b>Your Referral Link:</b>\n{ref_link}\n\nTotal referrals: {count}\n\n"
            "Earn 30% commission when referrals buy credits!",
            reply_markup=user_menu(is_admin))
    elif call.data == "protect":
        u = get_user(user_id)
        if u and u[1] < PROTECT_PRICE:
            await call.message.edit_text("Need 300 credits to protect your details.", reply_markup=user_menu(is_admin))
        else:
            set_protected(user_id, 1)
            update_credits(user_id, -PROTECT_PRICE)
            await call.message.edit_text("Your details are protected.", reply_markup=user_menu(is_admin))
    elif call.data == "mylogs":
        logs = get_logs(user_id)
        logs_txt = "\n".join([f"{l[3][:16]}: {l[2]}" for l in logs[-10:]]) if logs else "No logs found."
        await call.message.edit_text(f"Your last 10 searches:\n{logs_txt}", reply_markup=user_menu(is_admin))
    elif call.data == "help":
        await call.message.edit_text(
            "Send any input (number, UPI, IP, Aadhaar, etc) or use commands:\n"
            "/callhistory <num> – Paid call history\n"
            "/stats – User & search stats\n"
            "/gcast <msg> – Broadcast\n"
            "/ban <user_id>, /unban <user_id> – Admin only\n"
            "/buydb /buyapi – Contact admin\n"
            "/protect – Protect details\n"
            "/referral – Referral link\n"
            "/menu – Show menu\n",
            reply_markup=user_menu(is_admin))
    elif call.data == "search":
        await call.message.edit_text("Send input (UPI, Number, IP, Aadhaar, etc):", reply_markup=user_menu(is_admin))
    elif call.data == "adminpanel" and is_admin:
        await call.message.edit_text("Admin Panel:", reply_markup=admin_menu(is_owner))
    elif call.data == "banuser" and is_admin:
        await call.message.edit_text("Send: /ban <user_id>", reply_markup=admin_menu(is_owner))
    elif call.data == "unbanuser" and is_admin:
        await call.message.edit_text("Send: /unban <user_id>", reply_markup=admin_menu(is_owner))
    elif call.data == "gcast" and is_admin:
        await call.message.edit_text("Send: /gcast <message>", reply_markup=admin_menu(is_owner))
    elif call.data == "stats" and is_admin:
        users, searches = get_stats()
        await call.message.edit_text(f"👥 Total Users: {users}\n🔎 Total Searches: {searches}", reply_markup=admin_menu(is_owner))
    elif call.data == "sudolist" and is_admin:
        lst = get_sudo_list()
        await call.message.edit_text(f"Sudo list: {lst}", reply_markup=admin_menu(is_owner))
    elif call.data == "alllogs" and is_admin:
        logs = get_logs()
        logs_txt = "\n".join([f"{l[3][:16]}: {l[2]}" for l in logs[-15:]]) if logs else "No logs found."
        await call.message.edit_text(f"Last 15 searches (all users):\n{logs_txt}", reply_markup=admin_menu(is_owner))
    elif call.data == "protectednums" and is_owner:
        await call.message.edit_text(f"Protected Numbers: {PROTECTED_NUMBERS}", reply_markup=admin_menu(is_owner))
    elif call.data == "blacklistnums" and is_owner:
        await call.message.edit_text(f"Blacklisted Numbers: {BLACKLIST_NUMBERS}", reply_markup=admin_menu(is_owner))

@dp.message_handler(commands=['menu'])
async def menu_cmd(msg: types.Message):
    is_admin, _ = get_user_status(msg.from_user.id)
    await msg.answer("Choose an action:", reply_markup=user_menu(is_admin))

@dp.message_handler(commands=['protect'])
async def protect_cmd(msg: types.Message):
    user_id = msg.from_user.id
    u = get_user(user_id)
    if u and u[1] < PROTECT_PRICE:
        await msg.answer("Need 300 credits to protect your details.", reply_markup=user_menu(*get_user_status(user_id)))
    else:
        set_protected(user_id, 1)
        update_credits(user_id, -PROTECT_PRICE)
        await msg.answer("Your details are protected.", reply_markup=user_menu(*get_user_status(user_id)))

@dp.message_handler(commands=['referral'])
async def refer_cmd(msg: types.Message):
    user_id = msg.from_user.id
    ref_link = f"https://t.me/YourBotName?start={user_id}"
    count = get_referrals(user_id)
    await msg.answer(f"Referral link:\n{ref_link}\nReferrals: {count}", reply_markup=user_menu(*get_user_status(user_id)))

@dp.message_handler(commands=['buycredits'])
async def buycredits_cmd(msg: types.Message):
    await msg.answer(f"Buy credits:\n{price_table()}\nContact {ADMIN_CONTACT} to buy.", reply_markup=user_menu(*get_user_status(msg.from_user.id)))

@dp.message_handler(commands=['mylogs'])
async def mylogs_cmd(msg: types.Message):
    logs = get_logs(msg.from_user.id)
    logs_txt = "\n".join([f"{l[3][:16]}: {l[2]}" for l in logs[-10:]]) if logs else "No logs found."
    await msg.answer(f"Your last 10 searches:\n{logs_txt}", reply_markup=user_menu(*get_user_status(msg.from_user.id)))

@dp.message_handler(commands=['help'])
async def help_cmd(msg: types.Message):
    await msg.answer(
        "Send any input (number, UPI, IP, Aadhaar, etc) or use commands:\n"
        "/callhistory <num> – Paid call history\n"
        "/stats – User & search stats\n"
        "/gcast <msg> – Broadcast\n"
        "/ban <user_id>, /unban <user_id> – Admin only\n"
        "/buydb /buyapi – Contact admin\n"
        "/protect – Protect details\n"
        "/referral – Referral link\n"
        "/menu – Show menu\n",
        reply_markup=user_menu(*get_user_status(msg.from_user.id)))

@dp.message_handler(commands=['ban'])
async def ban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    try:
        target = int(msg.text.split()[1])
        set_ban(target, 1)
        await msg.answer(f"User {target} banned.", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))
    except:
        await msg.answer("Usage: /ban <user_id>", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))

@dp.message_handler(commands=['unban'])
async def unban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    try:
        target = int(msg.text.split()[1])
        set_ban(target, 0)
        await msg.answer(f"User {target} unbanned.", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))
    except:
        await msg.answer("Usage: /unban <user_id>", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))

@dp.message_handler(commands=['stats'])
async def stats_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    users, searches = get_stats()
    await msg.answer(f"👥 Total Users: {users}\n🔎 Total Searches: {searches}", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))

@dp.message_handler(commands=['gcast'])
async def gcast_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    to_send = msg.text[len("/gcast "):]
    for uid in get_all_users():
        try:
            await bot.send_message(uid, to_send)
        except: pass
    await msg.answer("Broadcast sent.", reply_markup=admin_menu(msg.from_user.id==OWNER_ID))

@dp.message_handler(commands=['buydb', 'buyapi'])
async def buy_cmd(msg: types.Message):
    await msg.answer(f"Contact admin: {ADMIN_CONTACT}")

@dp.message_handler(commands=['callhistory'])
async def callhistory_cmd(msg: types.Message):
    user_id = msg.from_user.id
    u = get_user(user_id)
    try:
        num = msg.text.split()[1]
    except:
        await msg.answer("Usage: /callhistory <number>")
        return
    if not u or u[1] < CALL_HISTORY_PRICE:
        await msg.answer(f"Call history is paid only: ₹{CALL_HISTORY_PRICE}/search. Not enough credits.\nContact Admin.", reply_markup=user_menu(*get_user_status(user_id)))
        return
    api_url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as resp:
            try:
                data = await resp.json()
            except:
                data = await resp.text()
    await msg.answer(format_response("CALL HISTORY", str(data)), reply_markup=user_menu(*get_user_status(user_id)))
    log_query(user_id, msg.text, str(data))
    update_credits(user_id, -CALL_HISTORY_PRICE)
    await bot.send_message(LOG_CHANNEL, f"Call history search: {user_id}, {num}")

async def fetch_api(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                return await resp.json()
            except:
                return await resp.text()

def has_credits(user_id):
    u = get_user(user_id)
    return u and u[1] > 0 and u[4] == 0

def deduct_credits(user_id, n=1):
    update_credits(user_id, -n)

def is_protected(number, user_id):
    if number in PROTECTED_NUMBERS and user_id != OWNER_ID:
        return True
    return False

@dp.message_handler()
async def main_handler(msg: types.Message):
    user_id = msg.from_user.id
    txt = msg.text.strip()
    u = get_user(user_id)
    # Support group logic: free inside support group
    in_group = False
    if hasattr(msg.chat, "id") and msg.chat.id == SUPPORT_GROUP_ID:
        in_group = True
    if not in_group:
        if not u or u[4] == 1:
            await msg.answer("You are banned from using the bot.")
            return
        if not has_credits(user_id):
            await msg.answer("Not enough credits! Refer friends or buy credits.", reply_markup=user_menu(*get_user_status(user_id)))
            return
    if any(num in txt for num in BLACKLIST_NUMBERS):
        await msg.answer("Blacklisted number. No result.")
        return
    if is_protected(txt, user_id):
        await msg.answer("Protected number. Access denied.")
        return
    if not await check_channels(user_id):
        await msg.answer("Join required channels to use the bot:\n" +
                         "\n".join([f"@{x}" for x in MANDATORY_CHANNELS]))
        return

    # Log every search
    await bot.send_message(LOG_CHANNEL, f"Search: {user_id}, {txt}")

    # UPI
    if "@" in txt and not txt.startswith("/"):
        api_url = f"https://upi-info.vercel.app/api/upi?upi_id={txt}&key=456"
        data = await fetch_api(api_url)
        try:
            name = data['vpa_details']['name']
            vpa = data['vpa_details']['vpa']
            bank = data['bank_details_raw']['BANK']
            branch = data['bank_details_raw']['BRANCH']
            address = data['bank_details_raw']['ADDRESS']
            ifsc = data['bank_details_raw']['IFSC']
            micr = data['bank_details_raw']['MICR']
            body = (f"👤 Name: <b>{name}</b>\n💳 VPA: <b>{vpa}</b>\n🏦 Bank: <b>{bank}</b> ({branch})\n📍 Address: <b>{address}</b>\nIFSC: <b>{ifsc}</b> | MICR: <b>{micr}</b>")
            await msg.answer(format_response("🏦 UPI SEARCH RESULT", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # Number India
    if re.match(r"^(\+91)?\d{10}$", txt):
        api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={txt[-10:]}"
        data = await fetch_api(api_url)
        try:
            res = data['data'][0]
            body = (f"📞 Mobile: <b>{res['mobile']}</b> | Alt: <b>{res['alt']}</b>\n👤 Name: <b>{res['name']}</b>\n🧾 Full Name: <b>{res['fname']}</b>\n🏠 Address: <b>{res['address'].replace('!', ', ')}</b>\n🌐 Circle: <b>{res['circle']}</b>\n🆔 ID: <b>{res['id']}</b>")
            await msg.answer(format_response("📱 NUMBER SEARCH RESULT", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # Pakistan CNIC
    if txt.startswith("+92") or (txt.isdigit() and len(txt) == 12 and txt.startswith("92")):
        api_url = f"https://pak-num-api.vercel.app/search?number={txt}"
        data = await fetch_api(api_url)
        try:
            items = data['results']
            msg_text = ""
            for idx, item in enumerate(items, 1):
                msg_text += f"{idx}️⃣\n👤 Name: <b>{item['Name']}</b>\n🆔 CNIC: <b>{item['CNIC']}</b>\n📞 Mobile: <b>{item['Mobile']}</b>\n🏠 Address: <b>{item['Address'] if item['Address'] else '(Not Available)'}</b>\n"
            await msg.answer(format_response("🇵🇰 PAKISTAN SEARCH RESULT", msg_text), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, msg_text)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # Aadhaar to Info
    if txt.isdigit() and len(txt) == 12:
        api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={txt}"
        data = await fetch_api(api_url)
        try:
            res = data['data'][0]
            body = (f"📞 Mobile: <b>{res['mobile']}</b> | Alt: <b>{res['alt']}</b>\n👤 Name: <b>{res['name']}</b>\n🧾 Full Name: <b>{res['fname']}</b>\n🏠 Address: <b>{res['address'].replace('!', ', ')}</b>\n🌐 Circle: <b>{res['circle']}</b>\n🆔 ID: <b>{res['id']}</b>")
            await msg.answer(format_response("📱 NUMBER SEARCH RESULT", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # Aadhaar to Family
    if txt.isdigit() and len(txt) == 12:
        api_url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={txt}&key=paidchx"
        data = await fetch_api(api_url)
        try:
            lst = data['memberDetailsList']
            members_txt = ""
            for idx, m in enumerate(lst, 1):
                members_txt += f"{idx}️⃣ <b>{m['memberName']}</b> — {m['releationship_name']}\n"
            body = (f"RC ID: <b>{data['rcId']}</b>\nScheme: <b>{data['schemeName']}</b>\nDistrict: <b>{data['homeDistName']}</b>\nState: <b>{data['homeStateName']}</b>\nFPS ID: <b>{data['fpsId']}</b>\n\n👨‍👩‍👧 FAMILY MEMBERS:\n{members_txt}")
            await msg.answer(format_response("🆔 AADHAR FAMILY SEARCH RESULT", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # IP Details
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", txt):
        api_url = f"https://karmali.serv00.net/ip_api.php?ip={txt}"
        data = await fetch_api(api_url)
        try:
            body = (f"🌍 Country: <b>{data['country']}</b> ({data['countryCode']})\n📍 Region: <b>{data['regionName']}</b>, City: <b>{data['city']}</b>\n📮 Zip: <b>{data['zip']}</b>\n🕒 Timezone: <b>{data['timezone']}</b>\n📡 ISP: <b>{data['isp']}</b>\n🔥 Org: <b>{data['org']}</b>\nAS: <b>{data['as']}</b>\nIP: <b>{data['query']}</b>")
            await msg.answer(format_response("🛰 IP SEARCH RESULT", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    # TG User Stats
    if txt.startswith("/tgstats "):
        tid = txt.split()[1]
        api_url = f"https://tg-info-neon.vercel.app/user-details?user={tid}"
        data = await fetch_api(api_url)
        try:
            d = data['data']
            body = (f"Name: <b>{d['first_name']}</b>\nUser ID: <b>{d['id']}</b>\nActive: {'✅' if d['is_active'] else '❌'}\nBot: {'✅' if d['is_bot'] else '❌'}\n\n📊 Stats:\nGroups Joined: <b>{d['total_groups']}</b>\nAdmin in: <b>{d['adm_in_groups']}</b>\nTotal Messages: <b>{d['total_msg_count']}</b>\nMessages in Groups: <b>{d['msg_in_groups_count']}</b>\nName Changes: <b>{d['names_count']}</b>\nUsername Changes: <b>{d['usernames_count']}</b>\n\n🕐 First Msg: <b>{d['first_msg_date']}</b>\n🕐 Last Msg: <b>{d['last_msg_date']}</b>")
            await msg.answer(format_response("👤 TELEGRAM USER STATS", body), reply_markup=user_menu(*get_user_status(user_id)))
            log_query(user_id, txt, body)
            if not in_group: deduct_credits(user_id)
        except:
            await msg.answer("No info found.", reply_markup=user_menu(*get_user_status(user_id)))
        return

    await msg.answer("Unknown command or input. Use the menu.", reply_markup=user_menu(*get_user_status(user_id)))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
