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
        rows.append(f"• <b>{c} credits</b> – ₹{inr} ({usdt} USDT)")
    return "\n".join(rows)

def branding_footer():
    return ("\n\n🔎 Powered by <b>DataTraceOSINT</b>\n"
            "📢 Updates: @DataTraceUpdates\n"
            "📩 Contact: @DataTraceSupport")

def format_response(title, body):
    return f"<b>{title}</b>\n{body}{branding_footer()}"

def user_menu(is_admin=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔎 Search", callback_data="search"),
        InlineKeyboardButton("💰 Buy Credits", callback_data="buycredits"),
        InlineKeyboardButton("🤝 Referral", callback_data="referral"),
        InlineKeyboardButton("🔒 Protect", callback_data="protect"),
        InlineKeyboardButton("📋 My Logs", callback_data="mylogs"),
        InlineKeyboardButton("❓ Help", callback_data="help"),
        InlineKeyboardButton("⬅️ Back", callback_data="back"),
    )
    if is_admin:
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
