import logging, aiohttp, asyncio, re
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
        rows.append(f"• {c} credits – ₹{inr} | {usdt} USDT")
    return "\n".join(rows)

def format_response(title, body):
    return f"🔎 <b>{title}</b>\n{body}\n\n🔗 <a href='http://t.me/DataTraceUpdates'>Join Updates</a>\n👤 Contact Admin: {ADMIN_CONTACT}"

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔎 Search", callback_data="search"),
        InlineKeyboardButton("💳 Buy Credits", callback_data="buycredits"),
        InlineKeyboardButton("👨‍👩‍👧 Referral", callback_data="referral"),
        InlineKeyboardButton("📢 Updates", url="http://t.me/DataTraceUpdates"),
        InlineKeyboardButton("👤 Contact Admin", url="https://t.me/DataTraceSupport"),
        InlineKeyboardButton("⬅️ Back", callback_data="back"),
    )
    return kb

async def check_channels(user_id):
    # Implement required channel check (stubbed, use get_chat_member)
    return True

@dp.message_handler(commands=['start'])
async def start_cmd(msg: types.Message):
    user_id = msg.from_user.id
    ref_by = None
    if msg.get_args():
        try:
            ref_by = int(msg.get_args())
            if ref_by != user_id:
                add_user(user_id, ref_by)
                update_credits(user_id, 1)  # 1 free credit for referral
                update_credits(ref_by, 1)   # Optionally credit to referrer
        except: add_user(user_id)
    else:
        add_user(user_id)
    if not await check_channels(user_id):
        await msg.answer("Join required channels to use the bot:\n" +
                         "\n".join([f"@{x}" for x in REQUIRED_CHANNELS]))
        return
    await bot.send_message(START_CHANNEL, f"User started: {user_id}")
    await msg.answer("Welcome! You have 2 free searches.\nRefer friends for credits!\n" +
                     price_table(), reply_markup=main_menu())

@dp.message_handler(commands=['stats'])
async def stats_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS: return
    users, searches = get_stats()
    await msg.answer(f"👥 Total Users: {users}\n🔎 Total Searches: {searches}")

@dp.message_handler(commands=['gcast'])
async def gcast_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS: return
    to_send = msg.text[len("/gcast "):]
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    all_users = c.fetchall()
    conn.close()
    for (uid,) in all_users:
        try:
            await bot.send_message(uid, to_send)
        except: pass
    await msg.answer("Gcast done.")

@dp.message_handler(commands=['ban'])
async def ban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS: return
    try:
        target = int(msg.text.split()[1])
        set_ban(target, 1)
        await msg.answer(f"User {target} banned.")
    except:
        await msg.answer("Usage: /ban <user_id>")

@dp.message_handler(commands=['unban'])
async def unban_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS: return
    try:
        target = int(msg.text.split()[1])
        set_ban(target, 0)
        await msg.answer(f"User {target} unbanned.")
    except:
        await msg.answer("Usage: /unban <user_id>")

@dp.message_handler(commands=['sudo'])
async def sudo_cmd(msg: types.Message):
    if msg.from_user.id not in SUDO_IDS: return
    lst = get_sudo_list()
    await msg.answer(f"Sudo list: {lst}")

@dp.message_handler(commands=['buydb', 'buyapi'])
async def buy_cmd(msg: types.Message):
    await msg.answer(f"Contact admin: {ADMIN_CONTACT}")

@dp.message_handler(commands=['menu'])
async def menu_cmd(msg: types.Message):
    await msg.answer("Choose an action:", reply_markup=main_menu())

@dp.message_handler(commands=['protect'])
async def protect_cmd(msg: types.Message):
    user_id = msg.from_user.id
    if get_user(user_id)[2] < 300:
        await msg.answer("You need 300 credits to protect your details!")
        return
    set_protected(user_id, 1)
    update_credits(user_id, -300)
    await msg.answer("Your details are now protected.")

@dp.message_handler(commands=['refer'])
async def refer_cmd(msg: types.Message):
    uid = msg.from_user.id
    ref_link = f"https://t.me/YourBotName?start={uid}"
    count = get_referrals(uid)
    await msg.answer(f"Refer friends and earn credits!\nYour link:\n{ref_link}\nTotal referrals: {count}")

@dp.message_handler(commands=['buycredits'])
async def buycredits_cmd(msg: types.Message):
    await msg.answer(f"Buy credits:\n{price_table()}\nContact {ADMIN_CONTACT} to buy.")

@dp.callback_query_handler(lambda c: True)
async def cb_handler(call: types.CallbackQuery):
    if call.data == "buycredits":
        await call.message.edit_text(f"Buy credits:\n{price_table()}\nContact {ADMIN_CONTACT} to buy.", reply_markup=main_menu())
    elif call.data == "referral":
        uid = call.from_user.id
        ref_link = f"https://t.me/YourBotName?start={uid}"
        count = get_referrals(uid)
        await call.message.edit_text(f"Refer friends and earn credits!\nYour link:\n{ref_link}\nTotal referrals: {count}", reply_markup=main_menu())
    elif call.data == "back":
        await call.message.edit_text("Choose an action:", reply_markup=main_menu())
    elif call.data == "search":
        await call.message.edit_text("Send input (UPI, Number, IP, Aadhaar, etc):")

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
    if not u or u[4] == 1:
        await msg.answer("You are banned from using the bot.")
        return
    # CREDIT CHECK
    if not has_credits(user_id):
        await msg.answer("Not enough credits! Refer friends or buy credits.", reply_markup=main_menu())
        return
    # Blacklist
    if any(num in txt for num in BLACKLIST_NUMBERS):
        await msg.answer("Blacklisted number. No result.")
        return
    # Channel join check
    if not await check_channels(user_id):
        await msg.answer("Join required channels to use the bot:\n" +
                         "\n".join([f"@{x}" for x in REQUIRED_CHANNELS]))
        return
    # Number to Info
    if re.match(r"^(\+91)?\d{10}$", txt):
        api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=mobile&term={txt[-10:]}"
        data = await fetch_api(api_url)
        try:
            res = data['data'][0]
            body = (f"MOBILE: {res['mobile']}\nALT MOBILE: {res['alt']}\nNAME: {res['name']}\n"
                    f"FULL NAME: {res['fname']}\nADDRESS: {res['address'].replace('!', ', ')}\n"
                    f"CIRCLE: {res['circle']}\nID: {res['id']}")
            await msg.answer(format_response("NUMBER DETAILS", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # Pakistan CNIC
    if txt.startswith("+92") or (txt.isdigit() and len(txt) == 12 and txt.startswith("92")):
        api_url = f"https://pak-num-api.vercel.app/search?number={txt}"
        data = await fetch_api(api_url)
        try:
            items = data['results']
            msg_text = ""
            for idx, item in enumerate(items, 1):
                msg_text += f"{idx}️⃣\nNAME: {item['Name']}\nCNIC: {item['CNIC']}\nMOBILE: {item['Mobile']}\nADDRESS: {item['Address'] if item['Address'] else '(Not Available)'}\n"
            await msg.answer(format_response("🇵🇰 PAKISTAN INFO", msg_text))
            log_query(user_id, txt, msg_text)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # UPI to Info
    if "@" in txt and not txt.startswith("/"):
        api_url = f"https://upi-info.vercel.app/api/upi?upi_id={txt}&key=456"
        data = await fetch_api(api_url)
        try:
            bd = data['bank_details_raw']
            vd = data['vpa_details']
            body = (f"🏦 BANK DETAILS\nADDRESS: {bd['ADDRESS']}\nBANK: {bd['BANK']}\nBANKCODE: {bd['BANKCODE']}\nBRANCH: {bd['BRANCH']}\nCENTRE: {bd['CENTRE']}\nCITY: {bd['CITY']}\nDISTRICT: {bd['DISTRICT']}\nSTATE: {bd['STATE']}\nIFSC: {bd['IFSC']}\nMICR: {bd['MICR']}\nIMPS: {'✅' if bd['IMPS'] else '❌'}\nNEFT: {'✅' if bd['NEFT'] else '❌'}\nRTGS: {'✅' if bd['RTGS'] else '❌'}\nUPI: {'✅' if bd['UPI'] else '❌'}\nSWIFT: {bd['SWIFT']}\n👤 ACCOUNT HOLDER\nIFSC: {vd['ifsc']}\nNAME: {vd['name']}\nVPA: {vd['vpa']}")
            await msg.answer(format_response("UPI DETAILS", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # IP to Details
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", txt):
        api_url = f"https://karmali.serv00.net/ip_api.php?ip={txt}"
        data = await fetch_api(api_url)
        try:
            body = (f"🗾 IP Valid: ✅\n🌎 Country: {data['country']}\n💠 Country Code: {data['countryCode']}\n🥬 Region: {data['region']}\n🗺️ Region Name: {data['regionName']}\n🏠 City: {data['city']}\n✉️ Zip: {data['zip']}\n🦠 Latitude: {data['lat']}\n⭐ Longitude: {data['lon']}\n🕢 Timezone: {data['timezone']}\n🗼 ISP: {data['isp']}\n🔥 Organization: {data['org']}\n🌾 AS: {data['as']}\n🛰 IP: {data['query']}")
            await msg.answer(format_response("IP DETAILS", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # Aadhaar to Family
    if txt.isdigit() and len(txt) == 12:
        api_url = f"https://family-members-n5um.vercel.app/fetch?aadhaar={txt}&key=paidchx"
        data = await fetch_api(api_url)
        try:
            lst = data['memberDetailsList']
            members_txt = ""
            for idx, m in enumerate(lst, 1):
                members_txt += f"{idx}️⃣ {m['memberName']} — {m['releationship_name']}\n"
            body = (f"RC ID: {data['rcId']}\nSCHEME: {data['schemeName']} ({data['schemeId']})\nDISTRICT: {data['homeDistName']}\nSTATE: {data['homeStateName']}\nFPS ID: {data['fpsId']}\n👨‍👩‍👧 FAMILY MEMBERS:\n{members_txt}")
            await msg.answer(format_response("AADHAAR FAMILY INFO", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # Aadhaar to Details
    if txt.isdigit() and len(txt) == 12:
        api_url = f"http://osintx.info/API/krobetahack.php?key=SHAD0WINT3L&type=id_number&term={txt}"
        data = await fetch_api(api_url)
        try:
            res = data['data'][0]
            body = (f"MOBILE: {res['mobile']}\nALT MOBILE: {res['alt']}\nNAME: {res['name']}\nFULL NAME: {res['fname']}\nADDRESS: {res['address'].replace('!', ', ')}\nCIRCLE: {res['circle']}\nID: {res['id']}")
            await msg.answer(format_response("AADHAAR DETAILS", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # Telegram User Stats
    if txt.startswith("/stats "):
        tid = txt.split()[1]
        api_url = f"https://tg-info-neon.vercel.app/user-details?user={tid}"
        data = await fetch_api(api_url)
        try:
            d = data['data']
            body = (f"NAME: {d['first_name']}\nUSER ID: {d['id']}\nIS BOT: {'✅' if d['is_bot'] else '❌'}\nACTIVE: {'✅' if d['is_active'] else '❌'}\n📊 STATS\nTOTAL GROUPS: {d['total_groups']}\nADMIN IN GROUPS: {d['adm_in_groups']}\nTOTAL MESSAGES: {d['total_msg_count']}\nMESSAGES IN GROUPS: {d['msg_in_groups_count']}\n🕐 FIRST MSG DATE: {d['first_msg_date']}\n🕐 LAST MSG DATE: {d['last_msg_date']}\nNAME CHANGES: {d['names_count']}\nUSERNAME CHANGES: {d['usernames_count']}")
            await msg.answer(format_response("TELEGRAM USER STATS", body))
            log_query(user_id, txt, body)
            deduct_credits(user_id)
        except:
            await msg.answer("No info found.")
        return
    # Call History (PAID ONLY)
    if txt.startswith("/call "):
        num = txt.split()[1]
        if not u or u[1] < 600:
            await msg.answer("Call history is paid only: ₹600/search, no demo.\nContact Admin.")
            return
        api_url = f"https://my-vercel-flask-qmfgrzwdl-okvaipro-svgs-projects.vercel.app/api/call_statement?number={num}&days=7"
        data = await fetch_api(api_url)
        await msg.answer(format_response("CALL HISTORY", str(data)))
        log_query(user_id, txt, str(data))
        deduct_credits(user_id, 600)
        return
    await msg.answer("Unknown command or input. Use the menu.", reply_markup=main_menu())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)