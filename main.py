import logging, aiohttp, re
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import *
from db import *

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
init_db()

def price_table():
    rows = []
    for c, inr, usdt in CREDIT_PRICES:
        rows.append(f"• {c} credits – ₹{inr} ({usdt} USDT)")
    return "\n".join(rows)

def format_footer():
    return "\n\n🔎 Powered by DataTraceOSINT\n📢 Updates: @DataTraceUpdates\n📩 Contact: @DataTraceSupport"

def format_response(title, body):
    return f"<b>{title}</b>\n{body}{format_footer()}"

def main_menu(is_sudo=False, is_owner=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔎 Lookup", callback_data="lookup"),
        InlineKeyboardButton("💰 Buy Credits", callback_data="buycredits"),
        InlineKeyboardButton("🤝 Referral", callback_data="referral"),
        InlineKeyboardButton("❓ Help", callback_data="help"),
    )
    if is_sudo or is_owner:
        kb.add(InlineKeyboardButton("🛠 Admin Panel", callback_data="adminpanel"))
    kb.add(InlineKeyboardButton("📩 Contact Admin", url="https://t.me/DataTraceSupport"))
    return kb

def lookup_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    kb.add(InlineKeyboardButton("📩 Contact Admin", url="https://t.me/DataTraceSupport"))
    return kb

def admin_menu(is_owner=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Credits", callback_data="addcredits"),
        InlineKeyboardButton("🚫 Ban User", callback_data="banuser"),
        InlineKeyboardButton("✅ Unban User", callback_data="unbanuser"),
        InlineKeyboardButton("📢 Broadcast", callback_data="gcast"),
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
        InlineKeyboardButton("👑 Sudo List", callback_data="sudolist"),
    )
    if is_owner:
        kb.add(
            InlineKeyboardButton("🔐 Protected Numbers", callback_data="protectednums"),
            InlineKeyboardButton("🖤 Blacklist Numbers", callback_data="blacklistnums"),
        )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="back"))
    return kb

async def check_channels(user_id):
    # Real implementation: Use get_chat_member for each channel
    # Return True if user in all
    return True

def get_user_status(user_id):
    u = get_user(user_id)
    is_sudo = (u and u[6]) or user_id in SUDO_IDS
    is_owner = user_id == OWNER_ID
    return is_sudo, is_owner

def show_help(is_sudo=False, is_owner=False):
    txt = (
        "<b>Bot Commands</b>\n"
        "/num <number> – Indian Number Lookup\n"
        "/pak <number> – Pakistan Number to CNIC\n"
        "/aadhar <number> – Aadhaar Info\n"
        "/aadhar2fam <number> – Aadhaar Family Info\n"
        "/upi <vpa> – UPI Info\n"
        "/ip <ip> – IP Info\n"
        "/tgstats <id> – Telegram Stats\n"
        "/callhistory <number> – Call History (₹600)\n"
        "/buycredits – Buy credits\n"
        "/referral – Referral link\n"
        "/menu – Show menu\n"
        "/help – Help\n"
    )
    if is_sudo or is_owner:
        txt += (
            "\n<b>Admin Commands</b>\n"
            "/stats – Total users/searches\n"
            "/gcast <msg> – Broadcast\n"
            "/ban <user_id> – Ban user\n"
            "/unban <user_id> – Unban user\n"
            "/sudolist – Sudo list\n"
        )
        if is_owner:
            txt += (
                "/protected – View protected numbers\n"
                "/blacklist – View blacklist\n"
            )
    return txt

@dp.message_handler(commands=['start'])
async def start_cmd(msg: types.Message):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    ref_by = None
    args = msg.get_args()
    # Only reply in group if tagged or command
    if msg.chat.type in ["group", "supergroup"]:
        await bot.send_message(chat_id, "👋 To use the bot, tag me or send a command/number.")
        return
    if args:
        try:
            ref_by = int(args)
            if ref_by != user_id:
                add_user(user_id, ref_by)
                update_credits(user_id, 1)
                update_credits(ref_by, 1)
        except:
            add_user(user_id)
    else:
        add_user(user_id)
    if not await check_channels(user_id):
        await msg.answer("Join required channels:\n@DataTraceUpdates\n@DataTraceOSINTSupport")
        return
    await bot.send_message(START_CHANNEL, f"User started: {user_id}")
    is_sudo, is_owner = get_user_status(user_id)
    await msg.answer(
        "👋 Welcome to DataTraceOSINT!\n\n"
        f"You have {get_user(user_id)[1]} credits.\n"
        "Use /help for commands.",
        reply_markup=main_menu(is_sudo, is_owner)
    )

@dp.message_handler(commands=['help'])
async def help_cmd(msg: types.Message):
    is_sudo, is_owner = get_user_status(msg.from_user.id)
    await msg.answer(show_help(is_sudo, is_owner), reply_markup=main_menu(is_sudo, is_owner))

@dp.callback_query_handler(lambda c: True)
async def cb_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    is_sudo, is_owner = get_user_status(user_id)
    if call.data == "back":
        await call.message.edit_text("Main Menu:", reply_markup=main_menu(is_sudo, is_owner))
    elif call.data == "lookup":
        await call.message.edit_text("Send any number, UPI, Aadhaar, IP, etc below.", reply_markup=lookup_menu())
    elif call.data == "buycredits":
        await call.message.edit_text(f"<b>Buy Credits</b>\n{price_table()}\nContact {ADMIN_CONTACT} to buy.", reply_markup=main_menu(is_sudo, is_owner))
    elif call.data == "referral":
        ref_link = f"https://t.me/YourBotName?start={user_id}"
        count = get_referrals(user_id)
        await call.message.edit_text(f"Your referral link:\n{ref_link}\nReferrals: {count}", reply_markup=main_menu(is_sudo, is_owner))
    elif call.data == "help":
        await call.message.edit_text(show_help(is_sudo, is_owner), reply_markup=main_menu(is_sudo, is_owner))
    elif call.data == "adminpanel" and (is_sudo or is_owner):
        await call.message.edit_text("Admin Panel:", reply_markup=admin_menu(is_owner))
    elif call.data == "protectednums" and is_owner:
        await call.message.edit_text(f"Protected Numbers:\n{PROTECTED_NUMBERS}", reply_markup=admin_menu(is_owner))
    elif call.data == "blacklistnums" and is_owner:
        await call.message.edit_text(f"Blacklisted Numbers:\n{BLACKLIST_NUMBERS}", reply_markup=admin_menu(is_owner))

@dp.message_handler(commands=['menu'])
async def menu_cmd(msg: types.Message):
    is_sudo, is_owner = get_user_status(msg.from_user.id)
    await msg.answer("Main Menu:", reply_markup=main_menu(is_sudo, is_owner))

@dp.message_handler(commands=['num'])
async def num_cmd(msg: types.Message):
    number = msg.get_args().strip()
    await handle_number(msg, number)

@dp.message_handler(commands=['pak'])
async def pak_cmd(msg: types.Message):
    number = msg.get_args().strip()
    await handle_pak(msg, number)

@dp.message_handler(commands=['aadhar'])
async def aadhar_cmd(msg: types.Message):
    number = msg.get_args().strip()
    await handle_aadhar(msg, number)

@dp.message_handler(commands=['aadhar2fam'])
async def aadhar2fam_cmd(msg: types.Message):
    number = msg.get_args().strip()
    await handle_aadhar2fam(msg, number)

@dp.message_handler(commands=['upi'])
async def upi_cmd(msg: types.Message):
    vpa = msg.get_args().strip()
    await handle_upi(msg, vpa)

@dp.message_handler(commands=['ip'])
async def ip_cmd(msg: types.Message):
    ip = msg.get_args().strip()
    await handle_ip(msg, ip)

@dp.message_handler(commands=['tgstats'])
async def tgstats_cmd(msg: types.Message):
    tg_id = msg.get_args().strip()
    await handle_tgstats(msg, tg_id)

@dp.message_handler(commands=['callhistory'])
async def callhistory_cmd(msg: types.Message):
    number = msg.get_args().strip()
    await handle_callhistory(msg, number)

@dp.message_handler(commands=['buycredits'])
async def buycredits_cmd(msg: types.Message):
    await msg.answer(f"<b>Buy Credits</b>\n{price_table()}\nContact {ADMIN_CONTACT} to buy.", reply_markup=main_menu(*get_user_status(msg.from_user.id)))

@dp.message_handler(commands=['referral'])
async def refer_cmd(msg: types.Message):
    user_id = msg.from_user.id
    ref_link = f"https://t.me/YourBotName?start={user_id}"
    count = get_referrals(user_id)
    await msg.answer(f"Your referral link:\n{ref_link}\nReferrals: {count}", reply_markup=main_menu(*get_user_status(user_id)))

@dp.message_handler(commands=['ban'])
async def ban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    try:
        target = int(msg.get_args().strip())
        set_ban(target, 1)
        await msg.answer(f"User {target} banned.")
    except:
        await msg.answer("Usage: /ban <user_id>")

@dp.message_handler(commands=['unban'])
async def unban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    try:
        target = int(msg.get_args().strip())
        set_ban(target, 0)
        await msg.answer(f"User {target} unbanned.")
    except:
        await msg.answer("Usage: /unban <user_id>")

@dp.message_handler(commands=['stats'])
async def stats_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    users, searches = get_stats()
    await msg.answer(f"👥 Total Users: {users}\n🔎 Total Searches: {searches}")

@dp.message_handler(commands=['gcast'])
async def gcast_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS and msg.from_user.id != OWNER_ID: return
    to_send = msg.get_args()
    for uid in get_all_users():
        try:
            await bot.send_message(uid, to_send)
        except: pass
    await msg.answer("Broadcast sent.")

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
    executor.start_polling(dp, skip_updates=True)    if is_admin:
        kb.add(InlineKeyboardButton("🛡 Admin Panel", callback_data="adminpanel"))
    return kb

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
