import logging
import json
import requests
import random
import string
import os
from datetime import datetime

# --- Corrected Imports for v20.x ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, ContextTypes
from telegram.ext.filters import Filters
# ------------------------------------

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

# Database (In production, use a proper database like PostgreSQL or MongoDB)
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

# --- All functions are now async ---
async def is_user_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is a member of all mandatory channels"""
    user_id = update.effective_user.id
    bot = context.bot
    
    for channel in MANDATORY_CHANNELS:
        try:
            member = await bot.get_chat_member(f"@{channel}", user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    
    return True

async def send_not_member_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send message asking user to join mandatory channels"""
    keyboard = []
    for channel in MANDATORY_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"Join {channel}", url=f"http://t.me/{channel}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❌ You need to join all mandatory channels to use this bot.\n\n"
        "Please join the channels below and then click /start again:",
        reply_markup=reply_markup
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    
    # Log to channel
    try:
        await context.bot.send_message(
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
    if not await is_user_member(update, context):
        await send_not_member_message(update, context)
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
                    await context.bot.send_message(
                        int(referrer_id),
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
    
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        f"🔍 DataTrace OSINT Bot provides various lookup services.\n\n"
        f"💳 Your Credits: {credits_db[user_id]}\n\n"
        f"🔗 Your Referral Link: {referral_link}\n\n"
        f"Share your referral link to earn free credits!",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Check if user is member of mandatory channels
    if not await is_user_member(update, context):
        await send_not_member_message(update, context)
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
        
        await query.edit_message_text(
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
        
        await query.edit_message_text(
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
        
        await query.edit_message_text(
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
            await query.edit_message_text(
                f"💳 UPI Payment Details\n\n"
                f"Amount: ₹{prices['inr']}\n"
                f"UPI ID: [Your UPI ID Here]\n\n"
                f"After payment, send a screenshot to @{ADMIN_CONTACT} to get your credits."
            )
        else:
            await query.edit_message_text(
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
        
        await query.edit_message_text(
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
        
        await query.edit_message_text(
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
        
        await query.edit_message_text(
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
        
        if "data" in data and len(data["data"]) > 0:
            result = data["data"][0]
            
            formatted_response = (
                f"📱 **NUMBER DETAILS**\n\n"
                f"📞 **MOBILE:** {result.get('mobile', 'N/A')}\n"
                f"📞 **ALT MOBILE:** {result.get('alt', 'N/A')}\n"
                f"👤 **NAME:** {result.get('name', 'N/A')}\n"
                f"👤 **FULL NAME:** {result.get('fname', 'N/A')}\n"
                f"🏠 **ADDRESS:** {result.get('address', 'N/A').replace('!', ', ')}\n"
                f"📡 **CIRCLE:** {result.get('circle', 'N/A')}\n"
                f"🆔 **ID:** {result.get('id', 'N/A')}\n\n"
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
def main():
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    
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
    application.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    # Group message handler
    application.add_handler(MessageHandler(Filters.group & Filters.text, group_message))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Set bot commands
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
    
    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")
    
    # --- Start the Bot ---
    application.run_polling()

if __name__ == '__main__':
    main()
