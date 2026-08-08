import asyncio, logging, os, qrcode, random
from io import BytesIO
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, BotCommand, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import config
from database.db import init_db, get_setting, set_setting, ensure_user, get_user, add_credits, deduct_credits, get_stats
from handlers.osint_engine import analyze_user, format_report, search_chats_by_keyword, top_chats_demo
logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if config.BOT_TOKEN else None
dp = Dispatcher()
class OwnerStates(StatesGroup):
    waiting_price=State();waiting_upi=State();waiting_upi_qr=State();waiting_usdt_trc=State();waiting_usdt_bep=State();waiting_add_credit_id=State();waiting_add_credit_amount=State();waiting_broadcast=State()
class UserStates(StatesGroup):
    waiting_target=State();waiting_keyword=State();waiting_payment_proof=State();waiting_word_target=State();waiting_contact=State()

def main_menu(is_owner=False):
    kb=[[InlineKeyboardButton(text="🔍 Search User (1💎)",callback_data="check_user"),InlineKeyboardButton(text="🌐 Search Chats (1💎)",callback_data="chat_search")],
        [InlineKeyboardButton(text="👁 Surveillance (1💎/28d)",callback_data="surveillance"),InlineKeyboardButton(text="📝 Word Analysis (1💎)",callback_data="word_analysis")],
        [InlineKeyboardButton(text="💎 Balance / Buy",callback_data="buy_credits"),InlineKeyboardButton(text="👤 My Profile",callback_data="my_profile")],
        [InlineKeyboardButton(text="📜 History",callback_data="history"),InlineKeyboardButton(text="📊 Top Chats",callback_data="top_chats")],
        [InlineKeyboardButton(text="🔗 Referral",callback_data="referral"),InlineKeyboardButton(text="❓ Help",callback_data="help")],
        [InlineKeyboardButton(text="📥 Export Messages",callback_data="export_msgs")]]
    if is_owner: kb.append([InlineKeyboardButton(text="👑 OWNER PANEL",callback_data="owner_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
def reply_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/menu"),KeyboardButton(text="Check someone")],[KeyboardButton(text="Share contact",request_contact=True)]],resize_keyboard=True,is_persistent=True)
def owner_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Set Price / Credit",callback_data="owner_set_price"),InlineKeyboardButton(text="📊 Stats",callback_data="owner_stats")],[InlineKeyboardButton(text="🏦 Set UPI ID",callback_data="owner_set_upi"),InlineKeyboardButton(text="🖼 Set UPI QR",callback_data="owner_set_upi_qr")],[InlineKeyboardButton(text="💵 Set USDT TRC20",callback_data="owner_set_usdt_trc"),InlineKeyboardButton(text="💵 Set USDT BEP20",callback_data="owner_set_usdt_bep")],[InlineKeyboardButton(text="⏳ Pending Payments",callback_data="owner_pending"),InlineKeyboardButton(text="🗑 Clear UPI QR",callback_data="owner_clear_upi_qr")],[InlineKeyboardButton(text="➕ Add Credits",callback_data="owner_add_credits"),InlineKeyboardButton(text="📢 Broadcast",callback_data="owner_broadcast")],[InlineKeyboardButton(text="🔙 Back to Menu",callback_data="back_menu")]])
def buy_kb(price):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"5 Credits - ₹{5*price}",callback_data="buy_5"),InlineKeyboardButton(text=f"10 Credits - ₹{10*price}",callback_data="buy_10")],[InlineKeyboardButton(text=f"25 Credits - ₹{25*price}",callback_data="buy_25"),InlineKeyboardButton(text=f"50 Credits - ₹{50*price}",callback_data="buy_50")],[InlineKeyboardButton(text=f"100 Credits - ₹{100*price}",callback_data="buy_100")],[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]])
def payment_method_kb(amount,price):
    total=amount*price
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"📱 Pay via UPI - ₹{total}",callback_data=f"pay_upi_{amount}")],[InlineKeyboardButton(text=f"💵 Pay via USDT - ${total/83:.2f}",callback_data=f"pay_usdt_{amount}")],[InlineKeyboardButton(text="🔙 Back",callback_data="buy_credits")]])
async def get_price(): return int(await get_setting("price_per_credit") or config.DEFAULT_PRICE_PER_CREDIT)
async def setup_commands():
    cmds=[BotCommand(command="start",description="Start bot"),BotCommand(command="menu",description="Main menu"),BotCommand(command="search",description="Groups search"),BotCommand(command="topchat",description="Groups catalog"),BotCommand(command="text",description="Search by message text"),BotCommand(command="human",description="Search by name"),BotCommand(command="balance",description="Balance"),BotCommand(command="buy",description="Buy credits"),BotCommand(command="history",description="History"),BotCommand(command="profile",description="Profile"),BotCommand(command="referral",description="Referral"),BotCommand(command="help",description="Help"),BotCommand(command="api",description="API")]
    try: await bot.set_my_commands(cmds)
    except: pass
WELCOME = """
Welcome to the biggest telegram database!

To view information, send:
- username
- user id (or group)
- contact or select recent
- sticker (detect author)
- link to message in group
- forward message from group

Other
- groups catalog /topchat
- groups search /search
- search by message text /text
- search by name /human

Now 1,172,924,888 users, 72,689,608 groups/channels and 131,027,360,600 messages

contact @akulovme
{owner_line}
💎 Price: {price} INR = 1 Credit | 🎁 15 Credits FREE
"""
def stylize_menu_text(user, referals, total_4week, consumption, links=0, invites=0, mentions=0, other=0):
    credits=user[3] if user else 0;uid=user[0] if user else 0
    stealth="Yes" if (len(user)>7 and user[7]==1) else "No"
    lang=user[8] if len(user)>8 and user[8] else "en"
    status=user[9] if len(user)>9 and user[9] else "Guest"
    return f"You have {credits} 💎\n\n├ stαtus: {status}\n├ me: {uid}\n├ referals: {referals}\n├ stεαlth: {stealth}\n└ /lang: {lang}\n\nTotαl in 4 week: {total_4week}\n├ Consumptioη {consumption}\n├ Links: +{links}\n├ Invites: +{invites}\n├ Meηtioηs: +{mentions}\n└ Other: +{other}"
def menu_buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Buy",callback_data="menu_buy"),InlineKeyboardButton(text="🥷 Hide data",callback_data="menu_hide")],
        [InlineKeyboardButton(text="🤝 Invite",callback_data="menu_invite"),InlineKeyboardButton(text="🌕 Coins",callback_data="menu_coins"),InlineKeyboardButton(text="💰 Auction",callback_data="menu_auction")],
        [InlineKeyboardButton(text="🪞 Mirrors",callback_data="menu_mirrors"),InlineKeyboardButton(text="🌐 Other",callback_data="menu_other"),InlineKeyboardButton(text="❗️ News",callback_data="menu_news")]])
# Profile card generator like image 3
def profile_card(user_id, username="@akulovme", name="Sayang"):
    # Demo stats like image 3
    return f"""This is {name}
Message diversity 91.36%
C 14.05.2026 to 07.08.2026
150 messages in 12 chats
67.33% replay 46.67% media
Mugs: 0, votes: 0
Favorite chat: TITAN COMMUNITY
Wanted: 1

ID: {user_id}
usernames:
| {username}
Names:
├ 2026-08-08  →  honey"""
def profile_kb(user_id):
    # Exact buttons as image 3 - green style (we use emojis)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Profile",callback_data=f"p_profile:{user_id}"),InlineKeyboardButton(text="🔔 Track",callback_data=f"p_track:{user_id}"),InlineKeyboardButton(text="📛 Names, tags",callback_data=f"p_names:{user_id}")],
        [InlineKeyboardButton(text="👁 Groups",callback_data=f"p_groups:{user_id}"),InlineKeyboardButton(text="🔍 Analysis",callback_data=f"p_analysis:{user_id}"),InlineKeyboardButton(text="📢 - Channels",callback_data=f"p_channels:{user_id}")],
        [InlineKeyboardButton(text="👍 Reputation",callback_data=f"p_reputation:{user_id}"),InlineKeyboardButton(text="👥 Familiar",callback_data=f"p_familiar:{user_id}"),InlineKeyboardButton(text="😍 Reactions",callback_data=f"p_reactions:{user_id}")],
        [InlineKeyboardButton(text="🎁 Present",callback_data=f"p_present:{user_id}"),InlineKeyboardButton(text="🤝 Share",callback_data=f"p_share:{user_id}"),InlineKeyboardButton(text="🗣 Word frequency",callback_data=f"p_words:{user_id}")],
        [InlineKeyboardButton(text="👥 General groups",callback_data=f"p_general:{user_id}")]
    ])

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    referred_by=None
    if len(message.text.split())>1:
        try:
            ref=int(message.text.split()[1])
            if ref!=message.from_user.id:
                referred_by=ref
                from database.db import get_user as gu
                existing=await gu(message.from_user.id)
                if not existing:
                    try:
                        await add_credits(ref,1)
                        try: await bot.send_message(ref,f"🎉 <b>Referral bonus!</b>\nUser {message.from_user.first_name} joined via your link. +1 Credit added!")
                        except: pass
                    except: pass
        except: pass
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "",referred_by)
    price=await get_price();is_owner=config.is_owner(message.from_user.id)
    owner_line="👑 <b>You are OWNER</b> — Full control enabled!\n" if is_owner else ""
    await message.answer(WELCOME.format(price=price,owner_line=owner_line),reply_markup=main_menu(is_owner))
    await message.answer("👇 Use bottom buttons: Check someone to select a user",reply_markup=reply_menu())

@dp.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext):
    await state.clear()
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    user=await get_user(message.from_user.id)
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(message.from_user.id,))
        referals=(await cur.fetchone())[0] or 0
        cur2=await db.execute("SELECT SUM(cost) FROM history WHERE user_id=? AND created_at > datetime('now','-28 days')",(message.from_user.id,))
        row2=await cur2.fetchone();total_spent_4w=row2[0] or 0;invites_earned=referals*5
    total_4week=f"-{total_spent_4w}" if total_spent_4w else "-0";consumption=f"-{total_spent_4w}" if total_spent_4w else "-0"
    text=stylize_menu_text(user,referals,total_4week,consumption,links=0,invites=invites_earned,mentions=0,other=0)
    await message.answer(text,reply_markup=menu_buttons())

@dp.message(F.text=="Check someone")
async def check_someone_btn(message: Message, state: FSMContext):
    await message.answer("📱 <b>Choose a User</b>\n\nForward a message, share contact, send @username/ID, or send a sticker to detect author.\n\nYou can also type directly:\n<code>/search @username</code>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Search by username",callback_data="check_user")]]))

@dp.message(F.contact)
async def contact_handler(message: Message, state: FSMContext):
    # Contact shared -> treat as user ID (phone)
    user_id=message.contact.user_id or message.contact.phone_number
    await handle_profile_request(message, str(user_id), state)

@dp.message(F.sticker)
async def sticker_handler(message: Message, state: FSMContext):
    # Detect author of sticker -> mock
    await message.answer("🎨 <b>Sticker author detected:</b> @sticker_author (demo)\nUse /search @username for full report")
    # Also treat as search for sticker set owner? For demo, show profile card
    await handle_profile_request(message, message.sticker.file_id[:10], state)

async def handle_profile_request(message, target, state):
    # Check credits
    user=await get_user(message.from_user.id)
    if not user: 
        await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
        user=await get_user(message.from_user.id)
    if user[3]<1:
        price=await get_price()
        await message.answer(f"❌ Need 1 Credit to view <b>{target}</b>! Balance: {user[3]} 💎",reply_markup=buy_kb(price))
        return
    ok=await deduct_credits(message.from_user.id,1)
    if not ok:
        await message.answer("❌ Not enough credits! /buy")
        return
    await message.answer(f"⏳ Analyzing <b>{target}</b>...")
    # For demo, use target as username, generate fake ID
    fake_id=8031385118 if "sayang" in target.lower() or "akulov" in target.lower() else random.randint(100000000,999999999)
    fake_username="@akulovme" if fake_id==8031385118 else f"@{target.lstrip('@')[:10]}"
    name="Sayang" if fake_id==8031385118 else target.lstrip('@')[:10]
    text=profile_card(fake_id,fake_username,name)
    # Save history
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("INSERT INTO history(user_id,target,result,cost,created_at) VALUES(?,?,?,?,?)",(message.from_user.id,str(target),text[:3000],1,datetime.now().isoformat()))
        await db.commit()
    await message.answer(text + "\n\n💎 1 Credit deducted",reply_markup=profile_kb(fake_id))
    try: await state.clear()
    except: pass

@dp.message(UserStates.waiting_target)
async def waiting_target_handler(message: Message, state: FSMContext):
    if message.text and message.text.strip()=="/cancel":
        await state.clear()
        is_owner=config.is_owner(message.from_user.id)
        await message.answer("❌ Cancelled",reply_markup=main_menu(is_owner))
        return
    target=message.text.strip() if message.text else ""
    if message.forward_from: target=str(message.forward_from.id)
    elif message.forward_from_chat: target=str(message.forward_from_chat.id)
    elif message.contact: target=str(message.contact.user_id or message.contact.phone_number)
    await state.clear()
    await handle_profile_request(message, target, state)

@dp.callback_query(F.data=="check_user")
async def check_user_cb(c: CallbackQuery, state: FSMContext):
    user=await get_user(c.from_user.id)
    if not user:
        await ensure_user(c.from_user.id,c.from_user.username or "",c.from_user.first_name or "")
        user=await get_user(c.from_user.id)
    if user[3]<1:
        price=await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit! Balance: {user[3]} 💎",reply_markup=buy_kb(price))
        await c.answer();return
    await state.set_state(UserStates.waiting_target)
    await c.message.edit_text("🔍 <b>Send @username, ID, forwarded message, contact or sticker</b>\n<i>Example: @durov, 8031385118</i>\n/cancel to cancel",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="chat_search")
async def chat_search_cb(c: CallbackQuery, state: FSMContext):
    user=await get_user(c.from_user.id)
    if not user or user[3]<1:
        price=await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit!",reply_markup=buy_kb(price));await c.answer();return
    await state.set_state(UserStates.waiting_keyword)
    await c.message.edit_text("🌐 <b>Search Chats</b>\nSend keyword to find public chats/channels\n<i>Example: crypto, gaya</i>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel",callback_data="back_menu")]]))
    await c.answer()

@dp.message(UserStates.waiting_keyword)
async def chat_search_process(message: Message, state: FSMContext):
    keyword=message.text.strip()
    # Use same credit check
    from database.db import get_user as gu
    u=await gu(message.from_user.id)
    if not u or u[3]<1:
        await message.answer("❌ Not enough credits! /buy");await state.clear();return
    ok=await deduct_credits(message.from_user.id,1)
    if not ok: await message.answer("❌ Not enough credits");await state.clear();return
    await message.answer(f"🔎 Searching for <b>{keyword}</b>...")
    results=await search_chats_by_keyword(keyword)
    text=f"🌐 <b>Results for '{keyword}':</b>\n\n"+"\n".join([f"{i+1}. {r}" for i,r in enumerate(results)])+"\n\n💎 1 Credit used"
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Menu",callback_data="back_menu")]]))
    await state.clear()

@dp.callback_query(F.data=="surveillance")
async def surveillance_cb(c: CallbackQuery, state: FSMContext):
    user=await get_user(c.from_user.id)
    if not user or user[3]<1:
        price=await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit for 28d surveillance!",reply_markup=buy_kb(price));await c.answer();return
    await state.set_state(UserStates.waiting_target)
    try: await state.update_data(surveillance=True)
    except: pass
    await c.message.edit_text("👁 <b>Surveillance — 28 Days (1💎)</b>\nWho to track? Send @username / ID / forwarded message",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="word_analysis")
async def word_analysis_cb(c: CallbackQuery, state: FSMContext):
    user=await get_user(c.from_user.id)
    if not user or user[3]<1:
        price=await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit!",reply_markup=buy_kb(price));await c.answer();return
    await state.set_state(UserStates.waiting_word_target)
    await c.message.edit_text("📝 <b>Word Frequency</b>\nSend @username or ID",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel",callback_data="back_menu")]]))
    await c.answer()

@dp.message(UserStates.waiting_word_target)
async def word_analysis_process(message: Message, state: FSMContext):
    target=message.text.strip()
    ok=await deduct_credits(message.from_user.id,1)
    if not ok: await message.answer("❌ Not enough credits");await state.clear();return
    demo=[("crypto",47),("bro",34),("free",29),("profit",24),("join",20)]
    text=f"🗣 <b>Word frequency {target}</b>\n"+"\n".join([f"{w}: {cnt}" for w,cnt in demo])
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await state.clear()

@dp.callback_query(F.data=="my_profile")
async def my_profile_cb(c: CallbackQuery):
    user=await get_user(c.from_user.id);price=await get_price()
    await c.message.edit_text(f"👤 <b>My Profile</b>\n🆔 ID: <code>{user[0]}</code>\n📛 Name: {user[2]}\n🔗 Username: @{user[1] or 'none'}\n💎 Balance: <b>{user[3]} Credits</b>\n🔥 Spent: {user[4]}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy Credits",callback_data="buy_credits")],[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="history")
async def history_cb(c: CallbackQuery):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT target,cost,created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5",(c.from_user.id,));rows=await cur.fetchall()
    if not rows: text="📜 <b>No history yet</b>"
    else: text="📜 <b>History (last 5):</b>\n"+"\n".join([f"• {r[0]} — {r[1]}💎 — {r[2][:10]}" for r in rows])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="top_chats")
async def top_chats_cb2(c: CallbackQuery):
    rows=await top_chats_demo()
    txt="📊 <b>Top Chats</b>\n"
    txt+="\n".join([f"{i}. {icon} {name} — {members}" for i,(name,members,icon) in enumerate(rows,1)])
    await c.message.edit_text(txt,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="referral")
async def referral_cb2(c: CallbackQuery):
    botname=(await bot.get_me()).username;link=f"https://t.me/{botname}?start={c.from_user.id}"
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(c.from_user.id,));cnt=(await cur.fetchone())[0] or 0
    await c.message.edit_text(f"🔗 <b>Referral</b>\nYour link:\n<code>{link}</code>\nInvited: <b>{cnt}</b>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="help")
async def help_cb2(c: CallbackQuery):
    price=await get_price()
    await c.message.edit_text(f"❓ <b>Help</b>\nCommands: /search @username — 1💎 = {price} INR\n/menu — Menu",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data=="export_msgs")
async def export_msgs_cb2(c: CallbackQuery):
    await c.message.edit_text("📥 <b>Export Messages</b>\nSend @username / ID to export\nUse 🔍 Search User",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Search Now",callback_data="check_user"),InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]))
    await c.answer()

# Reuse existing handlers for search, balance etc (shortened for brevity, full handlers below)
@dp.message(Command("search"))
async def search_cmd(message: Message, state: FSMContext):
    args=message.text.split(maxsplit=1)
    if len(args)<2:
        user=await get_user(message.from_user.id)
        if not user:
            await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
            user=await get_user(message.from_user.id)
        if user[3]<1:
            price=await get_price()
            await message.answer(f"❌ Not enough credits! Balance: {user[3]} 💎 | Need: 1 💎",reply_markup=buy_kb(price))
            return
        await state.set_state(UserStates.waiting_target)
        await message.answer("🔍 <b>Search User</b>\n\nSend: @username, ID, forwarded message, contact, sticker\n<i>Example: @durov</i>\n/cancel to cancel",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel",callback_data="back_menu")]]))
        return
    target=args[1].strip()
    await handle_profile_request(message,target,state)

@dp.message(Command("balance"))
async def balance_cmd(message: Message):
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    user=await get_user(message.from_user.id);price=await get_price()
    await message.answer(f"💎 <b>Balance</b>\n👤 {message.from_user.first_name}\n🆔 <code>{message.from_user.id}</code>\n💎 Credits: <b>{user[3]} 💎</b>\n🔥 Spent: {user[4]} 💎\n💰 Price: {price} INR",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy Credits",callback_data="buy_credits"),InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("buy"))
async def buy_cmd(message: Message):
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    price=await get_price();user=await get_user(message.from_user.id);credits=user[3] if user else 0
    await message.answer(f"💎 <b>Buy Credits</b>\nBalance: <b>{credits} 💎</b>\nPrice: <b>{price} INR</b> per Credit\nSelect package:",reply_markup=buy_kb(price))
@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    user=await get_user(message.from_user.id);price=await get_price()
    await message.answer(f"👤 <b>My Profile</b>\n🆔 ID: <code>{user[0]}</code>\n📛 Name: {user[2]}\n🔗 Username: @{user[1] or 'none'}\n💎 Balance: <b>{user[3]} 💎</b>\n🔥 Spent: {user[4]} 💎\n📅 Joined: {user[6][:10]}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy",callback_data="buy_credits"),InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("history"))
async def history_cmd(message: Message):
    import aiosqlite,os;await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT target,cost,created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10",(message.from_user.id,));rows=await cur.fetchall()
    if not rows: text="📜 <b>No history yet</b>\nMake your first search: /search @username"
    else: text="📜 <b>Search History (last 10):</b>\n\n"+"\n".join([f"• {r[0]} — {r[1]}💎 — {r[2][:10]}" for r in rows])
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("referral"))
async def referral_cmd(message: Message):
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    botname=(await bot.get_me()).username;link=f"https://t.me/{botname}?start={message.from_user.id}"
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(message.from_user.id,));cnt=(await cur.fetchone())[0] or 0
    await message.answer(f"🔗 <b>Referral Program</b>\n👥 Your link:\n<code>{link}</code>\n👥 Invited: <b>{cnt}</b>\n💰 Reward: <b>5 tokens per verified referral</b> (verified after 1 search)\nShare and earn!",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("topchat"))
async def topchat_cmd(message: Message):
    rows=await top_chats_demo();text="📂 <b>Groups Catalog /topchat</b>\n\n"+"\n".join([f"{i}. {icon} <b>{name}</b> — {members} members" for i,(name,members,icon) in enumerate(rows,1)])+"\n<i>72,689,608 groups indexed</i>"
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Search Groups",callback_data="chat_search"),InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("text"))
async def text_search_cmd(message: Message):
    args=message.text.split(maxsplit=1)
    if len(args)<2:
        await message.answer("🔍 <b>Search by message text /text</b>\nSend: <code>/text hello world</code>\nCost: 1 Credit",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
        return
    keyword=args[1].strip();user=await get_user(message.from_user.id)
    if not user or user[3]<1:
        price=await get_price();await message.answer(f"❌ Need 1 Credit!",reply_markup=buy_kb(price));return
    ok=await deduct_credits(message.from_user.id,1)
    if not ok: await message.answer("❌ Not enough credits");return
    await message.answer(f"🔍 Searching messages for <b>{keyword}</b>...")
    results=await search_chats_by_keyword(keyword);text=f"📝 <b>Messages containing '{keyword}':</b>\n\n"+"\n".join([f"• {r}" for r in results[:5]])+"\n\n💎 1 Credit used"
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("human"))
async def human_search_cmd(message: Message):
    args=message.text.split(maxsplit=1)
    if len(args)<2:
        await message.answer("👤 <b>Search by name /human</b>\nSend: <code>/human John</code>\nCost: 1 Credit",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
        return
    name=args[1].strip();user=await get_user(message.from_user.id)
    if not user or user[3]<1:
        price=await get_price();await message.answer(f"❌ Need 1 Credit!",reply_markup=buy_kb(price));return
    ok=await deduct_credits(message.from_user.id,1)
    if not ok: await message.answer("❌ Not enough credits");return
    await message.answer(f"🔍 Searching by name <b>{name}</b>...")
    results=[f"👤 {name} • @{(name.lower()+'123')[:12]} • 1,240 msgs",f"👤 {name} Smith • @{(name.lower()+'smith')[:12]} • 892 msgs"]
    text=f"👤 <b>Results for name '{name}':</b>\n\n"+"\n".join(results)+"\n\n💎 1 Credit used"
    await message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("help"))
async def help_cmd(message: Message):
    price=await get_price()
    await message.answer(f"❓ <b>Help</b>\nCommands: /start /menu /search /topchat /text /human /balance /buy /history\nPrice {price} INR/💎",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("api"))
async def api_cmd(message: Message):
    user=await get_user(message.from_user.id);is_owner=config.is_owner(message.from_user.id);has_paid=(user[4] if user else 0)>0 or is_owner
    if not has_paid:
        await message.answer("🔗 <b>API Access</b>\nRequires client status. Buy: /buy",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy",callback_data="buy_credits")]]))
        return
    price=await get_price()
    await message.answer(f"🔗 <b>FunStat API</b>\nBase: <code>https://api.funstat.example/v1</code>\nPrice: 1 req = 1 Credit = {price} INR\nYour Key: <code>FS-{message.from_user.id}-KEY</code>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]))
@dp.message(Command("lang"))
async def lang_handler(message: Message):
    await ensure_user(message.from_user.id,message.from_user.username or "",message.from_user.first_name or "")
    user=await get_user(message.from_user.id);current=user[8] if len(user)>8 and user[8] else "en"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇬🇧 English"+(" ✅" if current=="en" else ""),callback_data="set_lang_en"),InlineKeyboardButton(text="🇷🇺 Русский"+(" ✅" if current=="ru" else ""),callback_data="set_lang_ru")],[InlineKeyboardButton(text="📋 Menu",callback_data="menu_back")]])
    await message.answer(f"🌐 <b>Language</b>\nCurrent: <b>{current}</b>",reply_markup=kb)

# Callbacks for main menu etc (abbreviated, full handlers in original)
@dp.callback_query(F.data=="back_menu")
async def back_menu(c: CallbackQuery,state: FSMContext):
    await state.clear()
    is_owner=config.is_owner(c.from_user.id)
    try: await c.message.edit_text("📋 <b>Main Menu</b>\nChoose action:",reply_markup=main_menu(is_owner))
    except: await c.message.answer("📋 <b>Main Menu</b>",reply_markup=main_menu(is_owner))
    await c.answer()
@dp.callback_query(F.data=="menu_back")
async def menu_back_cb(c: CallbackQuery):
    user=await get_user(c.from_user.id)
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(c.from_user.id,));referals=(await cur.fetchone())[0] or 0
        cur2=await db.execute("SELECT SUM(cost) FROM history WHERE user_id=? AND created_at > datetime('now','-28 days')",(c.from_user.id,));row2=await cur2.fetchone();total_spent_4w=row2[0] or 0;invites_earned=referals*5
    total_4week=f"-{total_spent_4w}" if total_spent_4w else "-0";consumption=f"-{total_spent_4w}" if total_spent_4w else "-0"
    text=f"You have {user[3] if user else 0} 💎\n\n├ stαtus: {user[9] if len(user)>9 and user[9] else 'Guest'}\n├ me: {user[0] if user else 0}\n├ referals: {referals}\n├ stεαlth: {'Yes' if (len(user)>7 and user[7]==1) else 'No'}\n└ /lang: {user[8] if len(user)>8 and user[8] else 'en'}\n\nTotαl in 4 week: {total_4week}\n├ Consumptioη {consumption}\n├ Links: +0\n├ Invites: +{invites_earned}\n├ Meηtioηs: +0\n└ Other: +0"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Buy",callback_data="menu_buy"),InlineKeyboardButton(text="🥷 Hide data",callback_data="menu_hide")],[InlineKeyboardButton(text="🤝 Invite",callback_data="menu_invite"),InlineKeyboardButton(text="🌕 Coins",callback_data="menu_coins"),InlineKeyboardButton(text="💰 Auction",callback_data="menu_auction")],[InlineKeyboardButton(text="🪞 Mirrors",callback_data="menu_mirrors"),InlineKeyboardButton(text="🌐 Other",callback_data="menu_other"),InlineKeyboardButton(text="❗️ News",callback_data="menu_news")]])
    await c.message.edit_text(text,reply_markup=kb);await c.answer()
@dp.callback_query(F.data=="set_lang_en")
async def set_lang_en(c: CallbackQuery):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE users SET lang='en' WHERE user_id=?",(c.from_user.id,));await db.commit()
    await c.answer("English ✅");await menu_back_cb(c)
@dp.callback_query(F.data=="set_lang_ru")
async def set_lang_ru(c: CallbackQuery):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE users SET lang='ru' WHERE user_id=?",(c.from_user.id,));await db.commit()
    await c.answer("Русский ✅");await menu_back_cb(c)
# Menu 8 buttons
@dp.callback_query(F.data=="menu_buy")
async def menu_buy_cb(c: CallbackQuery):
    price=await get_price();user=await get_user(c.from_user.id);credits=user[3] if user else 0
    await c.message.edit_text(f"💸 <b>Buy Tokens</b>\n💎 Balance: <b>{credits} 💎</b>\nPrice: <b>{price} INR</b> per token\nSelect package:",reply_markup=buy_kb(price));await c.answer()
@dp.callback_query(F.data=="menu_hide")
async def menu_hide_cb(c: CallbackQuery):
    user=await get_user(c.from_user.id);cur=int(user[7]) if len(user)>7 and user[7] else 0;new=0 if cur else 1
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE users SET stealth=? WHERE user_id=?",(new,c.from_user.id));await db.commit()
    status="ENABLED 🥷 (hidden from searches)" if new else "DISABLED (visible)"
    await c.message.edit_text(f"🥷 <b>Hide Data</b>\nStealth: <b>{status}</b>\nWhen enabled, others cannot find you.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()
@dp.callback_query(F.data=="menu_invite")
async def menu_invite_cb(c: CallbackQuery):
    botname=(await bot.get_me()).username;link=f"https://t.me/{botname}?start={c.from_user.id}"
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?",(c.from_user.id,));cnt=(await cur.fetchone())[0] or 0
    text=f"🤝 <b>Invite</b>\n🔗 Your link:\n<code>{link}</code>\n👥 Invited: <b>{cnt}</b>\n💰 Reward: <b>5 tokens per verified referral</b>\nVerified = referred user does 1 search"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Verify & Claim",callback_data="menu_invite_verify")],[InlineKeyboardButton(text="📤 Share",url=f"https://t.me/share/url?url={link}")],[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]])
    await c.message.edit_text(text,reply_markup=kb);await c.answer()
@dp.callback_query(F.data=="menu_invite_verify")
async def menu_invite_verify_cb(c: CallbackQuery):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT user_id FROM users WHERE referred_by=?",(c.from_user.id,));refs=await cur.fetchall();verified=0
        for (rid,) in refs:
            cur2=await db.execute("SELECT total_spent FROM users WHERE user_id=?",(rid,));row=await cur2.fetchone()
            if row and row[0]>0: verified+=1
        if verified==0:
            await c.answer("No verified yet — they need 1 search!",show_alert=True);return
        reward=verified*5;await db.execute("UPDATE users SET credits=credits+? WHERE user_id=?",(reward,c.from_user.id));await db.commit()
    await c.message.edit_text(f"✅ Verified: {verified}\n💰 Rewarded: <b>{reward} tokens</b>!",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()
@dp.callback_query(F.data=="menu_coins")
async def menu_coins_cb(c: CallbackQuery):
    user=await get_user(c.from_user.id);await c.message.edit_text(f"🌕 <b>Coins</b>\n💎 Balance: {user[3] if user else 0}\n🔥 Spent: {user[4] if user else 0}\nCoins = tokens",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Buy",callback_data="menu_buy"),InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()
@dp.callback_query(F.data=="menu_auction")
async def menu_auction_cb(c: CallbackQuery): await c.message.edit_text("💰 <b>Auction</b>\nNo active auctions. Check News!",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()
@dp.callback_query(F.data=="menu_mirrors")
async def menu_mirrors_cb(c: CallbackQuery):
    botname=(await bot.get_me()).username
    await c.message.edit_text(f"🪞 <b>Mirrors</b>\n• @{botname} (main)\n• @funstat_mirror1_bot\n• @funstat_mirror2_bot",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()
@dp.callback_query(F.data=="menu_other")
async def menu_other_cb(c: CallbackQuery):
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👁 Tracked Users",callback_data="other_tracked"),InlineKeyboardButton(text="🔑 My Access",callback_data="other_access")],[InlineKeyboardButton(text="📊 Top Group/Message",callback_data="other_topmsg"),InlineKeyboardButton(text="👥 Top Groups/Users",callback_data="other_topusers")],[InlineKeyboardButton(text="🔗 Top by Link Counts",callback_data="other_toplinks")],[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]])
    await c.message.edit_text("🌐 <b>Other</b>\nChoose:",reply_markup=kb);await c.answer()
@dp.callback_query(F.data=="other_tracked")
async def other_tracked_cb(c: CallbackQuery):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT target_username,expiry FROM tracking WHERE watcher_id=? AND active=1",(c.from_user.id,));rows=await cur.fetchall()
    if not rows: text="👁 <b>Tracked Users</b>\nNo tracked users. Use 👁 Surveillance (1💎/28d)."
    else: text="👁 <b>Tracked Users:</b>\n"+"\n".join([f"• {r[0]} — until {r[1][:10]}" for r in rows])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_other")]]));await c.answer()
@dp.callback_query(F.data=="other_access")
async def other_access_cb(c: CallbackQuery):
    user=await get_user(c.from_user.id);status=user[9] if len(user)>9 and user[9] else "Guest"
    has="✅ Premium" if status!="Guest" or (user[4] if user else 0)>0 else "❌ Guest"
    await c.message.edit_text(f"🔑 <b>My Access</b>\nStatus: {status}\nAccess: {has}\nAPI: /api",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_other")]]));await c.answer()
@dp.callback_query(F.data=="other_topmsg")
async def other_topmsg_cb(c: CallbackQuery):
    rows=await top_chats_demo();msg=rows[0][0] if rows else "No data"
    await c.message.edit_text(f"📊 <b>Top Group/Message</b>\nTop Group: <b>{msg}</b>\nTop Message: Most forwarded (demo).",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_other")]]));await c.answer()
@dp.callback_query(F.data=="other_topusers")
async def other_topusers_cb(c: CallbackQuery):
    rows=await top_chats_demo();text="👥 <b>Top Groups / Active Users</b>\n"+"\n".join([f"{i}. {icon} {name} — {members}" for i,(name,members,icon) in enumerate(rows,1)])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_other")]]));await c.answer()
@dp.callback_query(F.data=="other_toplinks")
async def other_toplinks_cb(c: CallbackQuery):
    await c.message.edit_text("🔗 <b>Top by Link Counts</b>\n1. Crypto Traders India — 1,240 links\n2. Gaya Bihar Jobs — 892 links\n3. FunStat Talk — 650 links",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_other")]]));await c.answer()
@dp.callback_query(F.data=="menu_news")
async def menu_news_cb(c: CallbackQuery): await c.message.edit_text("❗️ <b>News</b>\n📢 FunStat indexes 131B messages!\n• New: Word Analysis\n• Fix: Faster search\nChannel: @fustat_talk",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_back")]]));await c.answer()

# Profile card buttons
@dp.callback_query(F.data.startswith("p_profile:"))
async def p_profile(c: CallbackQuery):
    uid=c.data.split(":")[1];await c.message.answer(f"📊 <b>Profile {uid}</b>\nGroups: 18, Channels: 5, ID: {uid}, Username: @akulovme\nBio: honey\nUse Groups/Channels buttons for details",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_track:"))
async def p_track(c: CallbackQuery):
    uid=c.data.split(":")[1];kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Enable Tracking (1💎/28d)",callback_data=f"track_enable:{uid}")],[InlineKeyboardButton(text="❌ Disable",callback_data=f"track_disable:{uid}")],[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]])
    await c.message.answer(f"🔔 <b>Track {uid}</b>\nEnable tracking for new groups, left groups, profile changes, messages, reactions?\nHow to disable: Send ID -> Track -> Disable\nList: Menu -> Other -> Tracked users",reply_markup=kb);await c.answer()
@dp.callback_query(F.data.startswith("track_enable:"))
async def track_enable(c: CallbackQuery):
    uid=c.data.split(":")[1];user=await get_user(c.from_user.id)
    if user[3]<1: price=await get_price();await c.message.edit_text(f"❌ Need 1💎!",reply_markup=buy_kb(price));return
    ok=await deduct_credits(c.from_user.id,1)
    if not ok: await c.message.answer("❌ No credits");return
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("INSERT INTO tracking(watcher_id,target_username,target_id,expiry,active) VALUES(?,?,?,?,?)",(c.from_user.id,uid,uid,(datetime.now()+timedelta(days=28)).isoformat(),1));await db.commit()
    await c.message.edit_text(f"✅ Tracking enabled for {uid} (28 days, 1💎 deducted)",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("track_disable:"))
async def track_disable(c: CallbackQuery):
    uid=c.data.split(":")[1]
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE tracking SET active=0 WHERE watcher_id=? AND target_username=?",(c.from_user.id,uid));await db.commit()
    await c.message.edit_text(f"❌ Tracking disabled for {uid}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_names:"))
async def p_names(c: CallbackQuery):
    uid=c.data.split(":")[1];await c.message.answer(f"📛 <b>Names for {uid}</b>\n2026-08-08 → honey\n2026-06-26 → Sayang\nHistory: @akulovme",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_groups:"))
async def p_groups(c: CallbackQuery):
    uid=c.data.split(":")[1]
    # Demo groups like image 4
    groups=[("Broken partner c..",40,"07 Aug"),("NFT Traders",21,"07 Aug"),("Legit Officials..",19,"07 Aug"),("TITAN CO..",51,"25 Jul")]
    text=f"Known groups of account {uid}.\n👮-admin, 🔒-private, ✖-left\nLast msg - group (total messages)\n\n"+"\n".join([f"{d} {n} ({cnt})" for n,cnt,d in groups])+"\n\nWithout messages:\n├ TBATE (the beginning af..\n├ Gift News & Updates Rep..\n└ English Chatting Group..\n\nTotal 18, page 1 of 2"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ 2",callback_data=f"p_groups2:{uid}"),InlineKeyboardButton(text="⏭ 2",callback_data=f"p_groups2:{uid}")],[InlineKeyboardButton(text="⬅️ Back",callback_data="back_menu"),InlineKeyboardButton(text="💾 Download as file",callback_data=f"p_groups_dl:{uid}")]])
    await c.message.answer(text,reply_markup=kb);await c.answer()
@dp.callback_query(F.data.startswith("p_groups_dl:"))
async def p_groups_dl(c: CallbackQuery):
    uid=c.data.split(":")[1]
    import json,csv,io
    groups=["Broken partner c..","NFT Traders","Legit Officials..","TITAN CO.."]
    # Excel
    from openpyxl import Workbook
    wb=Workbook();ws=wb.active;ws.append(["Group","Messages"]);[ws.append([g,random.randint(1,50)]) for g in groups]
    bio=BytesIO();wb.save(bio);bio.seek(0)
    await c.message.answer_document(BufferedInputFile(bio.getvalue(),filename=f"groups_{uid}.xlsx"),caption=f"📥 Groups for {uid} - Excel")
    # JSON
    j=json.dumps(groups,ensure_ascii=False,indent=2)
    await c.message.answer_document(BufferedInputFile(j.encode(),filename=f"groups_{uid}.json"),caption="JSON")
    await c.answer()
@dp.callback_query(F.data.startswith("p_analysis:"))
async def p_analysis(c: CallbackQuery):
    uid=c.data.split(":")[1]
    text=f"🔍 <b>Analysis for {uid}</b>\nLikes: 12\nDislikes: 2\nGifts sent: 3 (to @user1, @user2)\nGifts received: 1 (from @admin)\nAge: 24\nMentions: mentioned @akulovme 5 times, was mentioned 3 times\nOthers: ... (demo)"
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_channels:"))
async def p_channels(c: CallbackQuery):
    uid=c.data.split(":")[1]
    channels=["Ptg Official (1)","PTG GIVEAWAY (40)","KARAN ERA.. (2)","UPDATES (1)","ILT TIO (51)","Trader News (21)"]
    text=f"Channels Sayang (@akulovme):\n"+"\n".join([f"├ 2026-08-07 → {ch}" for ch in channels])+"\n└ The Beginning After The End Light Novel"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💾 Download as file",callback_data=f"p_channels_dl:{uid}")],[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]])
    await c.message.answer(text,reply_markup=kb);await c.answer()
@dp.callback_query(F.data.startswith("p_channels_dl:"))
async def p_channels_dl(c: CallbackQuery):
    uid=c.data.split(":")[1];channels=["Ptg Official","PTG GIVEAWAY","KARAN ERA"]
    import json
    j=json.dumps(channels,ensure_ascii=False,indent=2)
    await c.message.answer_document(BufferedInputFile(j.encode(),filename=f"channels_{uid}.json"),caption="Channels JSON")
    from openpyxl import Workbook;wb=Workbook();ws=wb.active;ws.append(["Channel","Count"]);[ws.append([ch,1]) for ch in channels];bio=BytesIO();wb.save(bio);bio.seek(0)
    await c.message.answer_document(BufferedInputFile(bio.getvalue(),filename=f"channels_{uid}.xlsx"),caption="Excel")
    await c.answer()
@dp.callback_query(F.data.startswith("p_reputation:"))
async def p_reputation(c: CallbackQuery):
    uid=c.data.split(":")[1]
    await c.message.answer(f"👍 <b>Reputation {uid}</b>\nReviews: 12\nScore: 4.7/5\n• 5★: 9\n• 4★: 2\n• 1★: 1\nTrusted user",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_familiar:"))
async def p_familiar(c: CallbackQuery):
    uid=c.data.split(":")[1]
    friends=[("Sayang","@akulovme"),("Arthur","@arthur"),("Chico","@chico")]
    text="👥 <b>Familiar / Friends</b>\n"+ "\n".join([f"• {n} ({u})" for n,u in friends])+"\n<i>Tap username to open DM (use /search for full)</i>"
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_reactions:"))
async def p_reactions(c: CallbackQuery):
    uid=c.data.split(":")[1]
    reacts=["@user1 reacted ❤️ on message 123","@user2 reacted 👍 on message 45","@admin reacted 🔥"]
    text="😍 <b>Reactions</b>\n"+"\n".join(reacts)+"\n<i>Click username to DM (demo)</i>"
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_present:"))
async def p_present(c: CallbackQuery):
    uid=c.data.split(":")[1]
    await c.message.answer(f"🎁 <b>Gifts {uid}</b>\nSent: 🎁 to @user1 (2026-08-01), 🎁 to @user2\nReceived: 🎁 from @admin\nClick username to open DM",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_share:"))
async def p_share(c: CallbackQuery):
    uid=c.data.split(":")[1];botname=(await bot.get_me()).username
    link=f"https://t.me/{botname}?start=share_{uid}_{c.from_user.id}"
    text=f"🤝 <b>Share</b>\nАηγ ᴜѕ℮r who сłiскs оη the liηқ wiⅼł ց℮τ αсc℮ѕs τo τhе dατa Sαγαηg ({uid}) ατ γour ℮xp℮ηѕ℮, сrγѕταℓѕ wilⅼ b℮ wiτhdrαwη ƒrom γoᴜ.\n\n➡️ Link: <code>{link}</code>\nThe link is also a referral link if this is a new user\nThe link is one-time, clicking it again creates a new one"
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_words:"))
async def p_words(c: CallbackQuery):
    uid=c.data.split(":")[1]
    demo_words=[("crypto",47),("bro",34),("free",29),("profit",24),("join",20)]
    text=f"🗣 <b>Word frequency {uid}</b>\n"+"\n".join([f"{w}: {cnt}" for w,cnt in demo_words])
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
@dp.callback_query(F.data.startswith("p_general:"))
async def p_general(c: CallbackQuery):
    uid=c.data.split(":")[1]
    text=f"👥 <b>General groups</b> for {uid} and you\n• Crypto Traders India\n• Gaya Jobs\n• Shared: 2 groups"
    await c.message.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]]));await c.answer()
# Message filter submenu (as per image 5)
@dp.callback_query(F.data=="msg_filter")
async def msg_filter_cb(c: CallbackQuery):
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="All (150)",callback_data="msg_all")],
        [InlineKeyboardButton(text="Voices ✖ No",callback_data="msg_voices"),InlineKeyboardButton(text="Circles ✖ No",callback_data="msg_circles")],
        [InlineKeyboardButton(text="Gif/sticker ✓ 68",callback_data="msg_gif"),InlineKeyboardButton(text="Links ✖ No",callback_data="msg_links")],
        [InlineKeyboardButton(text="Video ✓ 1",callback_data="msg_video"),InlineKeyboardButton(text="Files ✓ 1",callback_data="msg_files")],
        [InlineKeyboardButton(text="Images ✓ 1",callback_data="msg_images"),InlineKeyboardButton(text="Geo/contacts ✖ No",callback_data="msg_geo")],
        [InlineKeyboardButton(text="💾 Download as file",callback_data="msg_dl")],[InlineKeyboardButton(text="🔙 Back",callback_data="back_menu")]])
    await c.message.edit_text("Select message type",reply_markup=kb);await c.answer()
@dp.callback_query(F.data=="msg_all")
async def msg_all_cb(c: CallbackQuery):
    # Demo messages like image 6
    msgs="Account ID 8031385118.\nMode: All. [R] - reply someone; 📢 - channel commets\n\n🔊 Broken partne.. [07 Aug] > [R] [Sticker]\n🔊 NFT Traders [07 Aug] > Netflix 4k on mail available 299rs / 3$\nOn my mail single screen with pin 99rs / 1$ Escrow / mm ac..\n🔊 NFT Traders [07 Aug] > [R] Spam free?\nTotal 150, page 1 of 15"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ 2",callback_data="msg_all2"),InlineKeyboardButton(text="⏭ 15",callback_data="msg_all15")],[InlineKeyboardButton(text="⬅️ Back",callback_data="msg_filter"),InlineKeyboardButton(text="💾 Download as file",callback_data="msg_dl")]])
    await c.message.edit_text(msgs,reply_markup=kb);await c.answer()
@dp.callback_query(F.data=="msg_dl")
async def msg_dl_cb(c: CallbackQuery):
    import json
    msgs=[{"text":"Netflix 4k 299rs","chat":"NFT Traders","date":"07 Aug"},{"text":"Spam free?","chat":"Legit Official"}]
    j=json.dumps(msgs,ensure_ascii=False,indent=2)
    await c.message.answer_document(BufferedInputFile(j.encode(),filename="messages.json"),caption="Messages JSON")
    await c.message.answer_document(BufferedInputFile(b"Excel placeholder",filename="messages.xlsx"),caption="Excel")
    await c.answer()

# Other callbacks for main menu (buy etc)
@dp.callback_query(F.data=="buy_credits")
async def buy_credits(c: CallbackQuery):
    price=await get_price();user=await get_user(c.from_user.id);credits=user[3] if user else 0
    await c.message.edit_text(f"💎 <b>Buy Credits</b>\nBalance: <b>{credits} Credits</b>\nPrice: <b>{price} INR</b> per Credit\nSelect package:",reply_markup=buy_kb(price));await c.answer()
@dp.callback_query(F.data.startswith("buy_"))
async def buy_amount(c: CallbackQuery):
    amount=int(c.data.split("_")[1]);price=await get_price();total=amount*price
    await c.message.edit_text(f"🧾 <b>Order</b>\nCredits: <b>{amount}</b>\nPrice: {price} x {amount} = <b>₹{total}</b>\nUSDT: ~${total/83:.2f}\nChoose:",reply_markup=payment_method_kb(amount,price));await c.answer()
@dp.callback_query(F.data.startswith("pay_upi_"))
async def pay_upi(c: CallbackQuery,state: FSMContext):
    amount=int(c.data.split("_")[2]);price=await get_price();total=amount*price;upi_id=await get_setting("upi_id")
    # Amount Locked QR — generate dynamic QR with amount locked (user requested)
    # Check if owner has custom QR but we will still generate amount-locked QR (custom is static without amount)
    # If you want static custom QR without amount, disable amount lock via /owner panel setting (future)
    caption=f"📱 <b>UPI Payment — Amount Locked 🔒</b>\n\n💎 {amount} Credits\n💰 Amount: <b>₹{total}</b> <i>(Locked — pay exact amount only)</i>\n🏦 UPI: <code>{upi_id}</code>\n\n1. Scan QR — amount auto-filled ₹{total}\n2. Pay <b>exact ₹{total}</b> only (don't edit amount)\n3. Send screenshot with Transaction ID\n3. Owner will verify amount & confirm in 5-10 min\n\n⚠️ <i>If you pay less/more, credits will NOT be added!</i>"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ I Paid — Send Screenshot",callback_data=f"proof_upi_{amount}_{total}")],[InlineKeyboardButton(text="🔙 Back",callback_data="buy_credits")]])
    # Generate amount-locked QR with amount text overlay
    upi_url=f"upi://pay?pa={upi_id}&pn=FunStat&am={total}&cu=INR"
    qr_img=qrcode.make(upi_url,box_size=10,border=2)
    # Add amount text below QR for clarity (locked)
    try:
        from PIL import Image, ImageDraw, ImageFont
        qr_w,qr_h=qr_img.size
        extra_h=40
        new_img=Image.new("RGB",(qr_w,qr_h+extra_h),"white")
        new_img.paste(qr_img,(0,0))
        draw=ImageDraw.Draw(new_img)
        # Try default font, else load pil default
        try: font=ImageFont.load_default()
        except: font=None
        text=f"Pay ₹{total} ONLY"
        # Center text
        bbox=draw.textbbox((0,0),text,font=font) if font else (0,0,100,20)
        tw=bbox[2]-bbox[0];th=bbox[3]-bbox[1]
        tx=(qr_w - tw)//2;ty=qr_h + (extra_h - th)//2 - 2
        draw.text((tx,ty),text,fill="black",font=font)
        bio=BytesIO();new_img.save(bio,format='PNG');bio.seek(0)
        await c.message.answer_photo(photo=BufferedInputFile(bio.getvalue(),filename="upi_qr_locked.png"),caption=caption,reply_markup=kb);await c.answer()
        await state.set_state(UserStates.waiting_payment_proof);await state.update_data(pay_amount=amount,pay_total=total,pay_method="UPI")
        return
    except:
        # Fallback to simple QR
        bio2=BytesIO();qr_img.save(bio2,format='PNG');bio2.seek(0)
        await c.message.answer_photo(photo=BufferedInputFile(bio2.getvalue(),filename="upi_qr.png"),caption=caption,reply_markup=kb);await c.answer()
        await state.set_state(UserStates.waiting_payment_proof);await state.update_data(pay_amount=amount,pay_total=total,pay_method="UPI")
        return
@dp.callback_query(F.data.startswith("pay_usdt_"))
async def pay_usdt(c: CallbackQuery,state: FSMContext):
    amount=int(c.data.split("_")[2]);price=await get_price();total=amount*price;usdt_trc=await get_setting("usdt_trc20");usdt_bep=await get_setting("usdt_bep20");usd=total/83
    caption=f"💵 <b>USDT Payment</b>\n💎 {amount} Credits\n💰 Amount: <b>₹{total} (~${usd:.2f})</b>\n<b>TRC20:</b>\n<code>{usdt_trc}</code>\n<b>BEP20:</b>\n<code>{usdt_bep}</code>\n1. Send exact USDT\n2. Send hash\n3. Owner confirm"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ I Paid — Send Hash",callback_data=f"proof_usdt_{amount}_{total}")],[InlineKeyboardButton(text="🔙 Back",callback_data="buy_credits")]])
    await c.message.answer(caption,reply_markup=kb);await c.answer()
    await state.set_state(UserStates.waiting_payment_proof);await state.update_data(pay_amount=amount,pay_total=total,pay_method="USDT")
@dp.callback_query(F.data.startswith("proof_"))
async def proof_ask(c: CallbackQuery,state: FSMContext): await c.message.answer("📤 <b>Send proof:</b>\n• UPI — screenshot\n• USDT — hash / screenshot");await c.answer()
@dp.message(UserStates.waiting_payment_proof)
async def proof_receive(message: Message,state: FSMContext):
    data=await state.get_data();amount=data.get("pay_amount");total=data.get("pay_total");method=data.get("pay_method")
    import aiosqlite,os;proof_text=message.text or message.caption or "photo"
    if message.photo: proof_text=f"photo_{message.photo[-1].file_id}"
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("INSERT INTO transactions(user_id,type,amount,price_inr,method,status,proof,created_at) VALUES(?,?,?,?,?,?,?,?)",(message.from_user.id,"buy",amount,total,method,"pending",proof_text,datetime.now().isoformat()));await db.commit()
    if config.OWNER_ID:
        try:
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve",callback_data=f"approve_{message.from_user.id}_{amount}"),InlineKeyboardButton(text="❌ Reject",callback_data=f"reject_{message.from_user.id}")]])
            await bot.send_message(config.OWNER_ID,f"🔔 <b>New Payment!</b>\n👤 {message.from_user.first_name} (@{message.from_user.username}) ID: <code>{message.from_user.id}</code>\n💎 {amount} Credits\n💰 ₹{total} via {method}\n📎 {proof_text[:100]}",reply_markup=kb)
            if message.photo: await bot.forward_message(config.OWNER_ID,message.from_user.id,message.message_id)
        except: pass
    await message.answer(f"✅ <b>Request sent!</b>\n💎 {amount} Credits — ₹{total} via {method}\nOwner will confirm in 5-10 min.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu",callback_data="back_menu")]]));await state.clear()
@dp.callback_query(F.data=="owner_panel")
async def owner_panel(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): await c.answer("❌ Owner only!",show_alert=True);return
    price=await get_price();upi=await get_setting("upi_id");trc=await get_setting("usdt_trc20");stats=await get_stats()
    await c.message.edit_text(f"👑 <b>OWNER PANEL</b>\n💰 Price/Credit: <b>₹{price}</b>\n🏦 UPI: <code>{upi}</code>\n💵 TRC20: <code>{trc[:15]}...</code>\n📊 Users: {stats['total_users']} | Pending: {stats['pending']}",reply_markup=owner_panel_kb());await c.answer()
@dp.callback_query(F.data=="owner_set_price")
async def owner_set_price(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_price);await c.message.answer("💰 <b>Set Price Per Credit</b>\nSend new price in INR (e.g. 15,20,50)\nCurrent: ₹"+await get_setting("price_per_credit"));await c.answer()
@dp.message(OwnerStates.waiting_price)
async def owner_price_save(message: Message,state: FSMContext):
    try: price=int(message.text.strip());await set_setting("price_per_credit",str(price));await message.answer(f"✅ Price updated: <b>₹{price}/Credit</b>",reply_markup=owner_panel_kb())
    except: await message.answer("❌ Send number, e.g. 20")
    await state.clear()
@dp.callback_query(F.data=="owner_set_upi")
async def owner_set_upi(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_upi);await c.message.answer(f"🏦 <b>Set UPI ID</b>\nCurrent: <code>{await get_setting('upi_id')}</code>\nSend new UPI");await c.answer()
@dp.message(OwnerStates.waiting_upi)
async def owner_upi_save(message: Message,state: FSMContext): await set_setting("upi_id",message.text.strip());await message.answer(f"✅ UPI updated: <code>{message.text.strip()}</code>",reply_markup=owner_panel_kb());await state.clear()
@dp.callback_query(F.data=="owner_set_upi_qr")
async def owner_set_upi_qr(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_upi_qr)
    current=await get_setting("upi_qr_file_id")
    has="✅ Custom QR set" if current and current not in ["","none"] else "❌ No custom QR (auto-generated)"
    await c.message.answer(f"🖼 <b>Set UPI QR</b>\nCurrent: {has}\n\nSend a new QR image as <b>Photo</b>.\nThis QR will be shown to users at payment instead of auto-generated.\nSend /cancel to cancel.")
    await c.answer()
@dp.message(OwnerStates.waiting_upi_qr, F.photo)
async def owner_upi_qr_save(message: Message,state: FSMContext):
    file_id=message.photo[-1].file_id
    await set_setting("upi_qr_file_id",file_id)
    await message.answer("✅ Custom UPI QR updated! Users will now see this QR at payment.",reply_markup=owner_panel_kb())
    await state.clear()
@dp.message(OwnerStates.waiting_upi_qr)
async def owner_upi_qr_invalid(message: Message,state: FSMContext):
    if message.text and message.text.strip()=="/cancel":
        await state.clear()
        await message.answer("❌ Cancelled",reply_markup=owner_panel_kb())
        return
    await message.answer("❌ Please send a <b>Photo</b> of your UPI QR, or /cancel")
@dp.callback_query(F.data=="owner_clear_upi_qr")
async def owner_clear_upi_qr(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    await set_setting("upi_qr_file_id","")
    await c.message.edit_text("🗑 Custom QR cleared! Now auto-generated QR will be shown.",reply_markup=owner_panel_kb())
    await c.answer()
@dp.callback_query(F.data=="owner_set_usdt_trc")
async def owner_set_usdt_trc(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_usdt_trc);await c.message.answer(f"💵 <b>Set USDT TRC20</b>\nCurrent: <code>{await get_setting('usdt_trc20')}</code>\nSend new TRC20");await c.answer()
@dp.message(OwnerStates.waiting_usdt_trc)
async def owner_usdt_trc_save(message: Message,state: FSMContext): await set_setting("usdt_trc20",message.text.strip());await message.answer("✅ TRC20 updated!",reply_markup=owner_panel_kb());await state.clear()
@dp.callback_query(F.data=="owner_set_usdt_bep")
async def owner_set_usdt_bep(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_usdt_bep);await c.message.answer(f"💵 <b>Set USDT BEP20</b>\nCurrent: <code>{await get_setting('usdt_bep20')}</code>\nSend new BEP20");await c.answer()
@dp.message(OwnerStates.waiting_usdt_bep)
async def owner_usdt_bep_save(message: Message,state: FSMContext): await set_setting("usdt_bep20",message.text.strip());await message.answer("✅ BEP20 updated!",reply_markup=owner_panel_kb());await state.clear()
@dp.callback_query(F.data=="owner_stats")
async def owner_stats(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    stats=await get_stats();await c.message.answer(f"📊 <b>Bot Stats</b>\n👥 Total Users: {stats['total_users']}\n💎 Total Credits: {stats['total_credits']}\n🔥 Total Spent: {stats['total_spent']}\n⏳ Pending: {stats['pending']}\n💰 Price: ₹{await get_setting('price_per_credit')}",reply_markup=owner_panel_kb());await c.answer()
@dp.callback_query(F.data=="owner_add_credits")
async def owner_add_credits_start(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_add_credit_id);await c.message.answer("➕ <b>Add Credits</b>\nSend Telegram ID");await c.answer()
@dp.message(OwnerStates.waiting_add_credit_id)
async def owner_add_id(message: Message,state: FSMContext):
    try: uid=int(message.text.strip());await state.update_data(target_id=uid);await state.set_state(OwnerStates.waiting_add_credit_amount);await message.answer(f"ID: {uid}\nHow many credits?")
    except: await message.answer("❌ Invalid ID")
@dp.message(OwnerStates.waiting_add_credit_amount)
async def owner_add_amount(message: Message,state: FSMContext):
    try:
        amt=int(message.text.strip());data=await state.get_data();uid=data['target_id'];await add_credits(uid,amt);await message.answer(f"✅ Added {amt} credits to {uid}!",reply_markup=owner_panel_kb())
        try: await bot.send_message(uid,f"🎉 <b>{amt} Credits added!</b> by Owner\nCheck /balance or /menu")
        except: pass
        await state.clear()
    except: await message.answer("❌ Send number")
@dp.callback_query(F.data.startswith("approve_"))
async def approve_pay(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    parts=c.data.split("_");uid=int(parts[1]);amt=int(parts[2]);await add_credits(uid,amt)
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE transactions SET status='approved' WHERE user_id=? AND status='pending'",(uid,));await db.commit()
    await c.message.edit_text(f"✅ Approved {amt} credits to {uid}")
    try: await bot.send_message(uid,f"✅ <b>Payment Approved!</b>\n💎 {amt} Credits added\nUse /menu")
    except: pass
    await c.answer("Approved!")
@dp.callback_query(F.data.startswith("reject_"))
async def reject_pay(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    uid=int(c.data.split("_")[1])
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        await db.execute("UPDATE transactions SET status='rejected' WHERE user_id=? AND status='pending'",(uid,));await db.commit()
    await c.message.edit_text(f"❌ Rejected for {uid}")
    try: await bot.send_message(uid,"❌ Payment rejected. Contact owner.")
    except: pass
    await c.answer()
@dp.callback_query(F.data=="owner_pending")
async def owner_pending(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT user_id,amount,price_inr,method,proof FROM transactions WHERE status='pending' LIMIT 5");rows=await cur.fetchall()
    if not rows: await c.message.answer("✅ No pending payments",reply_markup=owner_panel_kb())
    else:
        text="⏳ <b>Pending Payments:</b>\n"+"".join([f"• {r[0]} — {r[1]}💎 — ₹{r[2]} {r[3]} — {r[4][:20]}\n" for r in rows])
        await c.message.answer(text,reply_markup=owner_panel_kb())
    await c.answer()
@dp.callback_query(F.data=="owner_broadcast")
async def owner_broadcast_start(c: CallbackQuery,state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_broadcast);await c.message.answer("📢 <b>Broadcast</b>\nSend message to broadcast to all users:");await c.answer()
@dp.message(OwnerStates.waiting_broadcast)
async def owner_broadcast_send(message: Message,state: FSMContext):
    import aiosqlite,os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH","database/funstat.db")) as db:
        cur=await db.execute("SELECT user_id FROM users");users=await cur.fetchall()
    count=0
    for (uid,) in users:
        try: await bot.copy_message(uid,message.from_user.id,message.message_id);count+=1
        except: pass
    await message.answer(f"✅ Broadcast sent to {count} users",reply_markup=owner_panel_kb());await state.clear()
@dp.message(Command("owner"))
async def owner_cmd(message: Message):
    if not config.is_owner(message.from_user.id): await message.answer("❌ Owner only!");return
    price=await get_price();await message.answer(f"👑 Owner Panel — Price: ₹{price}/Credit",reply_markup=owner_panel_kb())
# Keep-alive
async def health_server():
    from aiohttp import web
    app=web.Application()
    async def health(req): return web.Response(text="✅ FunStat Bot is Running! Uptime: OK")
    async def root(req): return web.Response(text="FunStat Bot - Keep Alive OK")
    app.router.add_get('/',root);app.router.add_get('/health',health)
    runner=web.AppRunner(app);await runner.setup();port=int(os.getenv("PORT","10000"));site=web.TCPSite(runner,'0.0.0.0',port);await site.start();print(f"🌐 Keep-Alive server running on port {port} - /health")
async def main():
    if not config.BOT_TOKEN: print("❌ BOT_TOKEN missing!");return
    await init_db();await setup_commands();asyncio.create_task(health_server());print(f"🚀 FunStat Bot Started! Owner: {config.OWNER_ID} Price: {await get_setting('price_per_credit')} INR - KeepAlive enabled");await dp.start_polling(bot)
if __name__=="__main__": asyncio.run(main())
