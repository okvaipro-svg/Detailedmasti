import logging
import re
import asyncio
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode, Message, ChatType
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from aiogram.dispatcher.filters import BoundFilter
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import MessageNotModified

import aiohttp

# ----------------------------
# CONFIGURATION & CONSTANTS
# ----------------------------

API_TOKEN = '8219144171:AAH3HZPZvvtohlxOkTP2jJVDuEAaAllyzdU'

# Channels & logs
CHANNEL_START_LOG = -1002765060940
CHANNEL_SEARCH_LOG = -1003066524164

# Bot Owner & Sudo users
OWNER_ID = 7924074157
SUDO_USERS = {7924074157, 5294360309, 7905267752}  # full access admins

# Blacklisted numbers: no results shown ever
BLACKLISTED_NUMBERS = {"+917724814462"}

# Support & Update Channels (must join)
SUPPORT_CHANNELS = [
    "DataTraceUpdates",
    "DataTraceOSINTSupport"
]

# Admin contact
ADMIN_CONTACT = "@DataTraceSupport"

# Credit prices (to be cheaper than current)
CREDIT_PACKAGES = {
    100: {"inr": 40, "usdt": 0.36},
    200: {"inr": 80, "usdt": 0.72},
    500: {"inr": 200, "usdt": 1.8},
    1000: {"inr": 360, "usdt": 3.2},
    2000: {"inr": 720, "usdt": 6.4},
    5000: {"inr": 2000, "usdt": 16.0},
}

# Referral commission in credits (30%)
REFERRAL_COMMISSION_RATE = 0.30

# Number of free searches without referral
FREE_SEARCHES_NO_REF = 2

# API keys & URLs
API_KEYS = {
    "krobetahack": "SHAD0WINT3L",
    "paidchx": "paidchx",
}

API_URLS = {
    "upi": "https://upi-info.vercel.app/api/upi?upi_id={upi_id}&key=456",
    "num_to_info": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={number}",
    "tg_user_stats": "https://tg-info-neon.vercel.app/user-details?user={user_id}",
    "ip_to_info": "https://karmali.serv00.net/ip_api.php?ip={ip}",
    "pak_num_to_cnic": "https://pak-num-api.vercel.app/search?number={number}",
    "aadhar_to_family": "https://family-members-n5um.vercel.app/fetch?aadhaar={aadhaar}&key=paidchx",
    "aadhar_to_details": "http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={aadhaar}",
    "call_history_paid": "https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7",
}

# Bot commands list for help
COMMANDS_LIST = {
    "start": "Start the bot",
    "help": "Show this help message",
    "num": "Lookup Indian mobile number info",
    "pak": "Lookup Pakistan number info",
    "aadhar": "Lookup Aadhar number info",
    "aadhar2fam": "Lookup Aadhar family info",
    "upi": "Lookup UPI ID info",
    "ip": "Lookup IP address info",
    "tguser": "Lookup Telegram user stats",
    "buycredits": "Buy credits",
    "refer": "Referral info & link",
    "stats": "Admin: Show user count and stats",
    "gcast": "Admin: Global promotion broadcast",
    "addcredits": "Admin: Add credits to user",
    "ban": "Admin: Ban user",
    "unban": "Admin: Unban user",
    "protected": "Owner: View protected numbers",
    "buydb": "Contact admin to buy DB/API",
    "buyapi": "Contact admin to buy DB/API",
}

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory user database simulation (replace with persistent DB in prod)
users_db = {}
# Structure: user_id: {
#   "credits": int,
#   "referrer_id": Optional[int],
#   "referrals": set(user_ids),
#   "banned": bool,
#   "is_protected": bool,
#   "free_searches_done": int,
# }

# Protected numbers only accessible by OWNER_ID
protected_numbers = set()

# Banned users list
banned_users = set()

# ----------------------------
# BOT INITIALIZATION
# ----------------------------

bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# ----------------------------
# HELPERS
# ----------------------------

def is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS or user_id == OWNER_ID

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def format_footer() -> str:
    return ("\n\n<i>Powered by <b>DataTrace OSINT Bot</b>\n"
            "Join our channels:\n"
            "• <a href='https://t.me/DataTraceUpdates'>DataTraceUpdates</a>\n"
            "• <a href='https://t.me/DataTraceOSINTSupport'>DataTraceOSINTSupport</a>\n"
            f"Contact Admin: {ADMIN_CONTACT}</i>")

def is_number_blacklisted(number: str) -> bool:
    return number in BLACKLISTED_NUMBERS

def clean_number(number: str) -> str:
    # Remove all non-digit except + sign, standardize format
    number = number.strip()
    if number.startswith("+"):
        number = "+" + re.sub(r"\D", "", number)
    else:
        number = re.sub(r"\D", "", number)
    return number

def credit_package_info_text() -> str:
    lines = ["💰 <b>Credit Packages (Cheap Rates!)</b>"]
    for credits, price in CREDIT_PACKAGES.items():
        lines.append(f"• {credits} credits – ₹{price['inr']} | {price['usdt']} USDT")
    return "\n".join(lines)

def user_referral_link(user_id: int) -> str:
    return f"https://t.me/YourBotUsername?start=ref{user_id}"

def check_user_join_channels(user_id: int) -> bool:
    # Dummy for demo: In production, use Telegram API or bot API to check membership
    # Here we assume user joined both channels
    return True

def get_user_data(user_id: int) -> dict:
    if user_id not in users_db:
        users_db[user_id] = {
            "credits": 0,
            "referrer_id": None,
            "referrals": set(),
            "banned": False,
            "is_protected": False,
            "free_searches_done": 0,
        }
    return users_db[user_id]

async def fetch_api_json(session: aiohttp.ClientSession, url: str) -> Optional[dict]:
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.warning(f"API request failed [{resp.status}]: {url}")
    except Exception as e:
        logger.error(f"API request exception: {e}")
    return None

def create_main_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Lookup Number", callback_data="lookup_num"),
        InlineKeyboardButton("Lookup UPI ID", callback_data="lookup_upi"),
    )
    kb.add(
        InlineKeyboardButton("Buy Credits", callback_data="buy_credits"),
        InlineKeyboardButton("Referral Info", callback_data="referral_info"),
    )
    kb.add(InlineKeyboardButton("Help / Commands", callback_data="help_commands"))
    return kb

def create_back_contact_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"),
        InlineKeyboardButton("Contact Admin", url=f"https://t.me/{ADMIN_CONTACT.strip('@')}")
    )
    return kb

def create_buy_credits_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for credits, price in CREDIT_PACKAGES.items():
        text = f"Buy {credits} credits - ₹{price['inr']}"
        kb.insert(InlineKeyboardButton(text, callback_data=f"buy_{credits}"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    return kb

def format_credits_balance(user_id: int) -> str:
    user_data = get_user_data(user_id)
    return f"💳 Your credits balance: <b>{user_data['credits']}</b> credits"

def add_credits(user_id: int, amount: int):
    user_data = get_user_data(user_id)
    user_data['credits'] += amount

def deduct_credits(user_id: int, amount: int) -> bool:
    user_data = get_user_data(user_id)
    if user_data['credits'] >= amount:
        user_data['credits'] -= amount
        return True
    return False

def add_referral(referrer_id: int, referred_id: int):
    referrer = get_user_data(referrer_id)
    referrer['referrals'].add(referred_id)

def add_referral_commission(referrer_id: int, amount_credits: int):
    commission = int(amount_credits * REFERRAL_COMMISSION_RATE)
    add_credits(referrer_id, commission)
    return commission

# ----------------------------
# FILTERS
# ----------------------------

class IsUserBanned(BoundFilter):
    async def check(self, message: Message) -> bool:
        user_id = message.from_user.id
        return get_user_data(user_id).get("banned", False)

class IsUserJoinedChannels(BoundFilter):
    async def check(self, message: Message) -> bool:
        user_id = message.from_user.id
        return check_user_join_channels(user_id)

# Only reply in groups when bot is mentioned or command used or number message
class ReplyInGroupFilter(BoundFilter):
    async def check(self, message: Message) -> bool:
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            # Reply only if bot is mentioned or command is used or message contains number pattern
            bot_mentioned = False
            if message.entities:
                for entity in message.entities:
                    if entity.type == "mention":
                        text = message.text[entity.offset:entity.offset + entity.length]
                        if text.lower() == f"@{(await bot.get_me()).username.lower()}":
                            bot_mentioned = True
                            break
            is_command = bool(message.entities and message.entities[0].type == "bot_command")
            has_number = bool(re.search(r"\+?\d{7,15}", message.text or ""))
            return bot_mentioned or is_command or has_number
        return True  # Always reply in private chats

dp.filters_factory.bind(IsUserBanned)
dp.filters_factory.bind(IsUserJoinedChannels)
dp.filters_factory.bind(ReplyInGroupFilter)

# ----------------------------
# STATES FOR FSM
# ----------------------------

class LookupStates(StatesGroup):
    waiting_for_input = State()

# ----------------------------
# COMMAND HANDLERS
# ----------------------------

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args()
    user_data = get_user_data(user_id)

    # Log start usage
    await bot.send_message(CHANNEL_START_LOG, f"User <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> started the bot.")

    # Check referral parameter
    if args.startswith("ref"):
        try:
            referrer_id = int(args[3:])
            if referrer_id != user_id and referrer_id in users_db:
                if user_data['referrer_id'] is None:
                    user_data['referrer_id'] = referrer_id
                    add_referral(referrer_id, user_id)
                    # Give 1 free credit to referred user and referrer commission 0 for this event
                    add_credits(user_id, 1)
                    commission = add_referral_commission(referrer_id, 0)  # no purchase yet, no commission
        except ValueError:
            pass

    # Check user joined required channels
    if not check_user_join_channels(user_id):
        text = ("<b>❗ You must join our channels to use this bot:</b>\n"
                "• <a href='https://t.me/DataTraceUpdates'>DataTraceUpdates</a>\n"
                "• <a href='https://t.me/DataTraceOSINTSupport'>DataTraceOSINTSupport</a>\n\n"
                "After joining, please /start again.")
        await message.answer(text)
        return

    # Welcome message with main menu
    text = (f"👋 Hello, <b>{message.from_user.full_name}</b>!\n\n"
            "This bot provides OSINT lookups with referral-based credits system.\n\n"
            + format_credits_balance(user_id) +
            "\n\nUse the buttons below to start.\n"
            + format_footer())
    await message.answer(text, reply_markup=create_main_keyboard())

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = "<b>🤖 Bot Commands & Usage</b>\n\n"
    for cmd, desc in COMMANDS_LIST.items():
        help_text += f"/{cmd} - {desc}\n"
    help_text += "\n" + format_footer()
    await message.answer(help_text, reply_markup=create_back_contact_keyboard())

@dp.message_handler(commands=['stats'])
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    if not is_sudo(user_id):
        await message.reply("❌ You don't have permission to use this command.")
        return
    user_count = len(users_db)
    banned_count = sum(1 for u in users_db.values() if u.get("banned"))
    protected_count = len(protected_numbers)
    text = (f"<b>📊 Bot Stats</b>\n\n"
            f"• Total users: {user_count}\n"
            f"• Banned users: {banned_count}\n"
            f"• Protected numbers: {protected_count}\n"
            f"• Sudo admins: {len(SUDO_USERS)}\n\n" + format_footer())
    await message.answer(text)

@dp.message_handler(commands=['gcast'])
async def cmd_gcast(message: types.Message):
    user_id = message.from_user.id
    if not is_sudo(user_id):
        await message.reply("❌ You don't have permission to send global messages.")
        return
    text = message.get_args()
    if not text:
        await message.reply("Usage: /gcast <message>")
        return
    count = 0
    for uid in users_db.keys():
        try:
            await bot.send_message(uid, text)
            count += 1
            await asyncio.sleep(0.05)  # small delay to avoid flood
        except Exception:
            continue
    await message.reply(f"✅ Broadcast sent to {count} users.")

@dp.message_handler(commands=['ban'])
async def cmd_ban(message: types.Message):
    user_id = message.from_user.id
    if not is_sudo(user_id):
        await message.reply("❌ You don't have permission to ban users.")
        return
    args = message.get_args()
    if not args.isdigit():
        await message.reply("Usage: /ban <user_id>")
        return
    target_id = int(args)
    user_data = get_user_data(target_id)
    user_data['banned'] = True
    banned_users.add(target_id)
    await message.reply(f"User {target_id} has been banned.")

@dp.message_handler(commands=['unban'])
async def cmd_unban(message: types.Message):
    user_id = message.from_user.id
    if not is_sudo(user_id):
        await message.reply("❌ You don't have permission to unban users.")
        return
    args = message.get_args()
    if not args.isdigit():
        await message.reply("Usage: /unban <user_id>")
        return
    target_id = int(args)
    user_data = get_user_data(target_id)
    user_data['banned'] = False
    banned_users.discard(target_id)
    await message.reply(f"User {target_id} has been unbanned.")

@dp.message_handler(commands=['addcredits'])
async def cmd_addcredits(message: types.Message):
    user_id = message.from_user.id
    if not is_sudo(user_id):
        await message.reply("❌ You don't have permission to add credits.")
        return
    args = message.get_args().split()
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        await message.reply("Usage: /addcredits <user_id> <amount>")
        return
    target_id = int(args[0])
    amount = int(args[1])
    add_credits(target_id, amount)
    await message.reply(f"Added {amount} credits to user {target_id}.")

@dp.message_handler(commands=['protected'])
async def cmd_protected(message: types.Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply("❌ You don't have permission to view protected numbers.")
        return
    if not protected_numbers:
        await message.reply("No protected numbers set.")
        return
    text = "<b>🔒 Protected Numbers (Owner Only)</b>\n\n"
    for num in protected_numbers:
        text += f"• {num}\n"
    await message.answer(text)

@dp.message_handler(commands=['buydb', 'buyapi'])
async def cmd_buydb_buyapi(message: types.Message):
    await message.answer(f"To buy DB/API access, please contact admin: {ADMIN_CONTACT}")

# ----------------------------
# CALLBACK QUERY HANDLERS
# ----------------------------

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def callback_back_to_main(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        f"👋 Welcome back! Use the buttons below to start.\n\n{format_credits_balance(callback_query.from_user.id)}\n\n{format_footer()}",
        reply_markup=create_main_keyboard()
    )
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "lookup_num")
async def callback_lookup_num(callback_query: types.CallbackQuery):
    await LookupStates.waiting_for_input.set()
    await callback_query.message.edit_text("📱 Please send me the Indian or Pakistani mobile number to lookup.\n\n"
                                           "You can send with or without country code (+91 or +92).\n\n"
                                           "Or send /cancel to abort.\n\n" + format_footer(),
                                           reply_markup=create_back_contact_keyboard())
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "lookup_upi")
async def callback_lookup_upi(callback_query: types.CallbackQuery):
    await LookupStates.waiting_for_input.set()
    state = dp.current_state(user=callback_query.from_user.id)
    await state.update_data(lookup_type="upi")
    await callback_query.message.edit_text("💳 Please send me the UPI ID to lookup.\n\nExample: example@upi\n\n"
                                           "Or send /cancel to abort.\n\n" + format_footer(),
                                           reply_markup=create_back_contact_keyboard())
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "buy_credits")
async def callback_buy_credits(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("💰 Choose a credit package to buy:\n\n" +
                                           credit_package_info_text() + "\n\n" + format_footer(),
                                           reply_markup=create_buy_credits_keyboard())
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "referral_info")
async def callback_referral_info(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user_data = get_user_data(user_id)
    referral_link = user_referral_link(user_id)
    referral_count = len(user_data.get("referrals", set()))
    text = (
        "<b>🤝 Referral Program</b>\n\n"
        "Earn rewards by inviting friends to use the bot!\n\n"
        "How it works:\n"
        f"• Share your personal referral link:\n<code>{referral_link}</code>\n"
        "• When someone starts the bot using your link, they get 1 free credit instantly.\n"
        "• When your referral buys credits, you earn 30% commission in credits.\n\n"
        f"Your referrals: <b>{referral_count}</b>\n"
        f"Your current credits: <b>{user_data['credits']}</b>\n\n"
        "Invite more friends to earn more credits!\n\n" + format_footer()
    )
    await callback_query.message.edit_text(text, reply_markup=create_back_contact_keyboard())
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def callback_buy_package(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    amount_str = callback_query.data[4:]
    if not amount_str.isdigit():
        await callback_query.answer("Invalid package selected.", show_alert=True)
        return
    credits = int(amount_str)
    # Note: In real bot, here you would integrate payment gateway to process purchase
    # For demo, we simulate instant purchase
    add_credits(user_id, credits)
    await callback_query.message.edit_text(
        f"✅ You have successfully bought <b>{credits}</b> credits!\n\n{format_credits_
