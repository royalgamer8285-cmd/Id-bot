import asyncio, logging, os, qrcode, random
from io import BytesIO
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, BotCommand
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
    waiting_price = State()
    waiting_upi = State()
    waiting_usdt_trc = State()
    waiting_usdt_bep = State()
    waiting_add_credit_id = State()
    waiting_add_credit_amount = State()
    waiting_broadcast = State()

class UserStates(StatesGroup):
    waiting_target = State()
    waiting_keyword = State()
    waiting_payment_proof = State()
    waiting_word_target = State()

# ============== ENGLISH ONLY MENU — EXACT FUNSTAT CLONE ==============
def main_menu(is_owner=False):
    kb = [
        [InlineKeyboardButton(text="🔍 Search User (1💎)", callback_data="check_user"),
         InlineKeyboardButton(text="🌐 Search Chats (1💎)", callback_data="chat_search")],
        [InlineKeyboardButton(text="👁 Surveillance (1💎/28d)", callback_data="surveillance"),
         InlineKeyboardButton(text="📝 Word Analysis (1💎)", callback_data="word_analysis")],
        [InlineKeyboardButton(text="💎 Balance / Buy", callback_data="buy_credits"),
         InlineKeyboardButton(text="👤 My Profile", callback_data="my_profile")],
        [InlineKeyboardButton(text="📜 History", callback_data="history"),
         InlineKeyboardButton(text="📊 Top Chats", callback_data="top_chats")],
        [InlineKeyboardButton(text="🔗 Referral", callback_data="referral"),
         InlineKeyboardButton(text="❓ Help", callback_data="help")],
        [InlineKeyboardButton(text="📥 Export Messages", callback_data="export_msgs")],
    ]
    if is_owner:
        kb.append([InlineKeyboardButton(text="👑 OWNER PANEL", callback_data="owner_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def owner_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Set Price / Credit", callback_data="owner_set_price"),
         InlineKeyboardButton(text="📊 Stats", callback_data="owner_stats")],
        [InlineKeyboardButton(text="🏦 Set UPI ID", callback_data="owner_set_upi"),
         InlineKeyboardButton(text="💵 Set USDT TRC20", callback_data="owner_set_usdt_trc")],
        [InlineKeyboardButton(text="💵 Set USDT BEP20", callback_data="owner_set_usdt_bep"),
         InlineKeyboardButton(text="⏳ Pending Payments", callback_data="owner_pending")],
        [InlineKeyboardButton(text="➕ Add Credits", callback_data="owner_add_credits"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="owner_broadcast")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_menu")]
    ])

def buy_kb(price):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"5 Credits - ₹{5*price}", callback_data="buy_5"),
         InlineKeyboardButton(text=f"10 Credits - ₹{10*price}", callback_data="buy_10")],
        [InlineKeyboardButton(text=f"25 Credits - ₹{25*price}", callback_data="buy_25"),
         InlineKeyboardButton(text=f"50 Credits - ₹{50*price}", callback_data="buy_50")],
        [InlineKeyboardButton(text=f"100 Credits - ₹{100*price}", callback_data="buy_100")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]
    ])

def payment_method_kb(amount, price):
    total = amount * price
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📱 Pay via UPI - ₹{total}", callback_data=f"pay_upi_{amount}")],
        [InlineKeyboardButton(text=f"💵 Pay via USDT - ${total/83:.2f}", callback_data=f"pay_usdt_{amount}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="buy_credits")]
    ])

async def get_price():
    return int(await get_setting("price_per_credit") or config.DEFAULT_PRICE_PER_CREDIT)

async def setup_commands():
    cmds = [
        BotCommand(command="start", description="Start bot"),
        BotCommand(command="menu", description="Main menu"),
        BotCommand(command="search", description="Search user - /search @username"),
        BotCommand(command="balance", description="Check balance"),
        BotCommand(command="buy", description="Buy credits"),
        BotCommand(command="history", description="Search history"),
        BotCommand(command="profile", description="My profile"),
        BotCommand(command="referral", description="Referral link"),
        BotCommand(command="topchats", description="Top chats"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="api", description="API access"),
    ]
    try: await bot.set_my_commands(cmds)
    except: pass

WELCOME = """
<b>🔍 FunStat Bot — Know everything about Telegram user</b>

With FunStat you can discover:
• 👥 Which <b>public groups/chats</b> user is in
• 💬 <b>Public messages</b> history from open sources
• 🔄 <b>Account history</b> — name, username, photo changes
• 📈 <b>Activity</b> level & active hours graph
• 🎯 <b>Interests</b> & languages (Crypto, Jobs, Gaming etc.)
• ❤️ <b>Favorite reactions</b> & frequent words
• 👁 <b>Surveillance</b> 24/7 with notifications
• 📊 <b>Top chats</b> ranking & social graph

<i>All data collected 24/7 in real time. Only public data!</i>

💎 <b>Price:</b> {price} INR = 1 Credit
🎁 <b>New users get 2 Credits FREE!</b>
{owner_line}
👇 <b>Choose an action from menu:</b>
"""

# ============== BASIC COMMANDS ==============
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    referred_by = None
    if len(message.text.split()) > 1:
        try:
            ref = int(message.text.split()[1])
            if ref != message.from_user.id:
                referred_by = ref
                # Reward referrer 1 credit if new user
                from database.db import get_user as gu
                existing = await gu(message.from_user.id)
                if not existing:
                    try:
                        await add_credits(ref, 1)
                        try: await bot.send_message(ref, f"🎉 <b>Referral bonus!</b>\nUser {message.from_user.first_name} joined via your link. +1 Credit added!")
                        except: pass
                    except: pass
        except: pass
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "", referred_by)
    price = await get_price()
    is_owner = config.is_owner(message.from_user.id)
    owner_line = "👑 <b>You are OWNER</b> — Full control enabled!\n" if is_owner else ""
    await message.answer(WELCOME.format(price=price, owner_line=owner_line), reply_markup=main_menu(is_owner))

@dp.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext):
    await state.clear()
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    price = await get_price()
    is_owner = config.is_owner(message.from_user.id)
    user = await get_user(message.from_user.id)
    credits = user[3] if user else 0
    await message.answer(f"📋 <b>Main Menu</b>\n\n💎 Balance: <b>{credits} Credits</b> | Price: {price} INR/Credit\n\nCommands: /search @username, /balance, /history, /help, /topchats", reply_markup=main_menu(is_owner))

@dp.message(Command("search"))
async def search_cmd(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        user = await get_user(message.from_user.id)
        if not user:
            await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
            user = await get_user(message.from_user.id)
        if user[3] < 1:
            price = await get_price()
            await message.answer(f"❌ <b>Not enough credits!</b>\nBalance: {user[3]} 💎 | Need: 1 💎", reply_markup=buy_kb(price))
            return
        await state.set_state(UserStates.waiting_target)
        await message.answer("🔍 <b>Search User</b>\n\nSend:\n• @username\n• User ID\n• Or forwarded message\n\n<i>Example: @durov or 123456789</i>\n\n/cancel to cancel", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_menu")]]))
        return
    target = args[1].strip()
    user = await get_user(message.from_user.id)
    if not user:
        await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
        user = await get_user(message.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await message.answer(f"❌ Not enough credits! Balance: {user[3]} | Need: 1", reply_markup=buy_kb(price))
        return
    ok = await deduct_credits(message.from_user.id, 1)
    if not ok:
        await message.answer("❌ Not enough credits!")
        return
    await message.answer(f"⏳ <b>Analyzing {target}...</b> <i>Please wait 5-10 sec</i>")
    report = await analyze_user(target)
    text = format_report(report, target)
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        await db.execute("INSERT INTO history(user_id, target, result, cost, created_at) VALUES(?,?,?,?,?)", (message.from_user.id, target, text[:3000], 1, datetime.now().isoformat()))
        await db.commit()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Word Analysis", callback_data="word_analysis"), InlineKeyboardButton(text="👁 Track", callback_data="surveillance")],
        [InlineKeyboardButton(text="📥 Export", callback_data="export_msgs"), InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]
    ])
    await message.answer(text + "\n\n💎 1 Credit deducted", reply_markup=kb)

@dp.message(Command("balance"))
async def balance_cmd(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    user = await get_user(message.from_user.id)
    price = await get_price()
    await message.answer(f"💎 <b>Balance</b>\n\n👤 {message.from_user.first_name}\n🆔 <code>{message.from_user.id}</code>\n💎 Credits: <b>{user[3]} 💎</b>\n🔥 Spent: {user[4]} 💎\n💰 Price: {price} INR / 1 Credit\n\nUse /buy to purchase", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy Credits", callback_data="buy_credits"), InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("buy"))
async def buy_cmd(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    price = await get_price()
    user = await get_user(message.from_user.id)
    credits = user[3] if user else 0
    await message.answer(f"💎 <b>Buy Credits</b>\n\nBalance: <b>{credits} 💎</b>\nPrice: <b>{price} INR</b> per Credit\n\nSelect package:", reply_markup=buy_kb(price))

@dp.message(Command("profile"))
async def profile_cmd(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    user = await get_user(message.from_user.id)
    price = await get_price()
    await message.answer(f"👤 <b>My Profile</b>\n\n🆔 ID: <code>{user[0]}</code>\n📛 Name: {user[2]}\n🔗 Username: @{user[1] or 'none'}\n💎 Balance: <b>{user[3]} 💎</b>\n🔥 Spent: {user[4]} 💎\n📅 Joined: {user[6][:10]}\n💰 Price: {price} INR/Credit", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy", callback_data="buy_credits"), InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("history"))
async def history_cmd(message: Message):
    import aiosqlite, os
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT target, cost, created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10", (message.from_user.id,))
        rows = await cur.fetchall()
    if not rows:
        text = "📜 <b>No history yet</b>\nMake your first search: /search @username"
    else:
        text = "📜 <b>Search History (last 10):</b>\n\n" + "\n".join([f"• {r[0]} — {r[1]}💎 — {r[2][:10]}" for r in rows])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("referral"))
async def referral_cmd(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    botname = (await bot.get_me()).username
    link = f"https://t.me/{botname}?start={message.from_user.id}"
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT COUNT(*), SUM(credits) FROM users WHERE referred_by=?", (message.from_user.id,))
        row = await cur.fetchone()
        cnt = row[0] or 0
    await message.answer(f"🔗 <b>Referral Program</b>\n\n👥 Your referral link:\n<code>{link}</code>\n\n👥 Invited: <b>{cnt} users</b>\n💰 Reward: <b>1 Credit per referral</b> + 25-35% from their purchases (like FunStat)\n\nShare and earn crystals! /balance to check", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("topchats"))
async def topchats_cmd(message: Message):
    rows = await top_chats_demo()
    text = "📊 <b>Top Chats (by activity):</b>\n\n"
    for i, (name, members, icon) in enumerate(rows, 1):
        text += f"{i}. {icon} <b>{name}</b> — {members} members\n"
    text += "\n<i>Bot checks ~500k links/day, 5-10% are valid chats</i>"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("help"))
async def help_cmd(message: Message):
    price = await get_price()
    await message.answer(f"""
❓ <b>Help — FunStat Bot</b>

<b>Commands (English only):</b>
/start — Start bot
/menu — Main menu
/search @username — Search user (1💎 = {price} INR)
/balance — Check balance
/buy — Buy credits
/history — View history
/profile — My profile
/referral — Referral link
/topchats — Top chats ranking
/help — This help
/api — API docs (clients only)

<b>How to use:</b>
1. Tap 🔍 Search User or type /search @username
2. Costs 1 Credit = {price} INR
3. Bot shows groups, messages, history, interests, reactions, words, account age, scam check

<b>Features included (all original):</b>
✓ Chats user is in ✓ Public messages export ✓ Name/photo/username history ✓ Activity graph ✓ Interests & languages ✓ Favorite reactions ✓ Word frequency ✓ Surveillance 28d ✓ Search chats by keyword ✓ Social graph ✓ Referral 35% ✓ API access ✓ Top chats

<b>Payment:</b> UPI (raman18k@fam) & USDT TRC20/BEP20
<b>Surveillance:</b> 1💎 / 28 days — notifications on changes

Support: Contact owner 👑 via /menu → Owner Panel
""", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

@dp.message(Command("api"))
async def api_cmd(message: Message):
    user = await get_user(message.from_user.id)
    is_owner = config.is_owner(message.from_user.id)
    has_paid = (user[4] if user else 0) > 0 or is_owner
    if not has_paid:
        await message.answer("🔗 <b>API Access</b>\n\nAPI requires client status. Get it by:\n1. Any purchase ( /buy )\n2. Or referral earnings\n\nBuy crystals: /buy", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy", callback_data="buy_credits")]]))
        return
    price = await get_price()
    await message.answer(f"""
🔗 <b>FunStat API</b>

<b>Docs:</b> Send /api in bot for details
<b>Base URL:</b> <code>https://api.funstat.example/v1</code>
<b>Price:</b> 1 request = 1 Credit = {price} INR

<b>Example:</b>
<code>POST /v1/search
{{"username":"@durov","api_key":"YOUR_KEY"}}</code>

<b>Your Demo Key:</b> <code>FS-{message.from_user.id}-KEY</code>
Contact owner to activate full API.
Status: {"✅ Client" if has_paid else "❌ Need purchase"}
""", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))

# ============== CALLBACKS ==============
@dp.callback_query(F.data == "back_menu")
async def back_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    price = await get_price()
    is_owner = config.is_owner(c.from_user.id)
    user = await get_user(c.from_user.id)
    credits = user[3] if user else 0
    try:
        await c.message.edit_text(f"📋 <b>Main Menu</b>\n\n💎 Balance: <b>{credits} Credits</b> | Price: {price} INR/Credit\nChoose action:", reply_markup=main_menu(is_owner))
    except:
        await c.message.answer(f"📋 <b>Main Menu</b>\n\n💎 Balance: <b>{credits}</b> | Price: {price} INR", reply_markup=main_menu(is_owner))
    await c.answer()

@dp.callback_query(F.data == "my_profile")
async def my_profile(c: CallbackQuery):
    user = await get_user(c.from_user.id)
    price = await get_price()
    await c.message.edit_text(f"👤 <b>My Profile</b>\n\n🆔 ID: <code>{user[0]}</code>\n📛 Name: {user[2]}\n🔗 Username: @{user[1] or 'none'}\n💎 <b>Balance:</b> {user[3]} Credits\n🔥 Spent: {user[4]} Credits\n📅 Joined: {user[6][:10]}\n💰 Price: {price} INR/Credit", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Buy Credits", callback_data="buy_credits")],[InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "referral")
async def referral_cb(c: CallbackQuery):
    botname = (await bot.get_me()).username
    link = f"https://t.me/{botname}?start={c.from_user.id}"
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (c.from_user.id,))
        cnt = (await cur.fetchone())[0] or 0
    await c.message.edit_text(f"🔗 <b>Referral Program</b>\n\nYour link:\n<code>{link}</code>\n\n👥 Invited: <b>{cnt} users</b>\n💰 Reward: 1 Credit per invite + 35% from their purchases", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "top_chats")
async def top_chats_cb(c: CallbackQuery):
    rows = await top_chats_demo()
    text = "📊 <b>Top Chats Ranking</b>\n\n"
    for i, (name, members, icon) in enumerate(rows, 1):
        text += f"{i}. {icon} <b>{name}</b> — {members} members\n"
    text += "\n<i>Bot checks ~500k links/day</i>"
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "export_msgs")
async def export_msgs_cb(c: CallbackQuery):
    user = await get_user(c.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit for export!", reply_markup=buy_kb(price))
        return
    await c.message.edit_text("📥 <b>Export Messages</b>\n\nSend @username / ID to export public messages\nCosts 1 Credit\n\nUse 🔍 Search User — report includes export preview.\nFor full export file, do /search @username", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Search Now", callback_data="check_user"), InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    price = await get_price()
    await c.message.edit_text(f"❓ <b>Help</b>\n\nCommands:\n/search @username — Search (1💎 = {price} INR)\n/menu — Menu\n/balance — Balance\n/buy — Buy\n/history — History\n/topchats — Top chats\n\nTap 🔍 Search to start!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "history")
async def history_cb(c: CallbackQuery):
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT target, cost, created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5", (c.from_user.id,))
        rows = await cur.fetchall()
    if not rows:
        text = "📜 <b>No history yet</b>\nUse /search @username"
    else:
        text = "📜 <b>History (last 5):</b>\n\n" + "\n".join([f"• {r[0]} — {r[1]}💎 — {r[2][:10]}" for r in rows])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")]]))
    await c.answer()

# Search user callback
@dp.callback_query(F.data == "check_user")
async def check_user_start(c: CallbackQuery, state: FSMContext):
    user = await get_user(c.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await c.message.edit_text(f"❌ <b>Not enough credits!</b>\nBalance: {user[3]} 💎 | Need: 1 💎", reply_markup=buy_kb(price))
        return
    await state.set_state(UserStates.waiting_target)
    await c.message.edit_text("🔍 <b>Send @username, ID or forwarded message</b>\n\n<i>Example: @durov, 123456789</i>\n\n/cancel to cancel", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_menu")]]))
    await c.answer()

@dp.message(UserStates.waiting_target)
async def check_user_process(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        is_owner = config.is_owner(message.from_user.id)
        await message.answer("❌ Cancelled", reply_markup=main_menu(is_owner))
        return
    data = await state.get_data()
    is_surv = data.get("surveillance", False)
    target = message.text.strip() if message.text else ""
    if message.forward_from: target = str(message.forward_from.id)
    elif message.forward_from_chat: target = str(message.forward_from_chat.id)
    if is_surv:
        ok = await deduct_credits(message.from_user.id, 1)
        if not ok:
            await message.answer("❌ Not enough credits! /buy")
            await state.clear()
            return
        import aiosqlite, os
        async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
            await db.execute("INSERT INTO tracking(watcher_id, target_username, target_id, expiry, active) VALUES(?,?,?,?,?)", (message.from_user.id, target, 0, (datetime.now()+timedelta(days=28)).isoformat(), 1))
            await db.commit()
        await message.answer(f"👁 <b>Surveillance activated!</b>\n\n🎯 Target: {target}\n⏳ Duration: 28 days\n💎 Deducted: 1 Credit\n\nYou will get notifications on profile changes and new messages.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))
        await state.clear()
        return
    ok = await deduct_credits(message.from_user.id, 1)
    if not ok:
        await message.answer("❌ Not enough credits! /buy")
        await state.clear()
        return
    await message.answer("⏳ <b>Analyzing...</b> <i>Please wait 5-10 sec</i>")
    report = await analyze_user(target)
    text = format_report(report, target)
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        await db.execute("INSERT INTO history(user_id, target, result, cost, created_at) VALUES(?,?,?,?,?)", (message.from_user.id, target, text[:3000], 1, datetime.now().isoformat()))
        await db.commit()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Word Analysis", callback_data="word_analysis"), InlineKeyboardButton(text="👁 Track", callback_data="surveillance")],
        [InlineKeyboardButton(text="🔍 Another Search", callback_data="check_user"), InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]
    ])
    await message.answer(text + "\n\n💎 1 Credit deducted", reply_markup=kb)
    await state.clear()

@dp.callback_query(F.data == "chat_search")
async def chat_search_start(c: CallbackQuery, state: FSMContext):
    user = await get_user(c.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await c.message.edit_text(f"❌ Need 1 Credit!", reply_markup=buy_kb(price))
        return
    await state.set_state(UserStates.waiting_keyword)
    await c.message.edit_text("🌐 <b>Search Chats</b>\n\nSend keyword to find public chats/channels\n<i>Example: crypto, gaya, job, funstat</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_menu")]]))
    await c.answer()

@dp.message(UserStates.waiting_keyword)
async def chat_search_process(message: Message, state: FSMContext):
    keyword = message.text.strip()
    ok = await deduct_credits(message.from_user.id, 1)
    if not ok:
        await message.answer("❌ Not enough credits")
        await state.clear()
        return
    await message.answer(f"🔎 Searching for <b>{keyword}</b>...")
    results = await search_chats_by_keyword(keyword)
    text = f"🌐 <b>Results for '{keyword}':</b>\n\n" + "\n".join([f"{i+1}. {r}" for i, r in enumerate(results)]) + "\n\n💎 1 Credit used"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Menu", callback_data="back_menu")]]))
    await state.clear()

@dp.callback_query(F.data == "word_analysis")
async def word_analysis_start(c: CallbackQuery, state: FSMContext):
    user = await get_user(c.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await c.message.edit_text("❌ Need 1 Credit!", reply_markup=buy_kb(price))
        return
    await state.set_state(UserStates.waiting_word_target)
    await c.message.edit_text("📝 <b>Word Frequency Analysis</b>\n\nSend @username or ID to analyze most used words", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_menu")]]))
    await c.answer()

@dp.message(UserStates.waiting_word_target)
async def word_analysis_process(message: Message, state: FSMContext):
    target = message.text.strip()
    ok = await deduct_credits(message.from_user.id, 1)
    if not ok:
        await message.answer("❌ Not enough credits")
        await state.clear()
        return
    demo_words = [("crypto", 47), ("bro", 34), ("free", 29), ("profit", 24), ("join", 20), ("india", 16), ("help", 12)]
    text = f"📝 <b>Word Analysis: {target}</b>\n\n<b>Top words:</b>\n"
    for w, cnt in demo_words:
        bar = "█" * (cnt // 6)
        text += f"<code>{w:<10}</code> {cnt:>3} {bar}\n"
    text += "\n<i>Demo — Real API will analyze actual messages</i>\n💎 1 Credit used"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Menu", callback_data="back_menu")]]))
    await state.clear()

@dp.callback_query(F.data == "surveillance")
async def surveillance_start(c: CallbackQuery, state: FSMContext):
    user = await get_user(c.from_user.id)
    if user[3] < 1:
        price = await get_price()
        await c.message.edit_text("❌ Need 1 Credit for 28 days surveillance!", reply_markup=buy_kb(price))
        return
    await state.set_state(UserStates.waiting_target)
    await state.update_data(surveillance=True)
    await c.message.edit_text("👁 <b>Surveillance — 28 Days (1💎)</b>\n\nWho to track? Send @username / ID / forwarded message\nYou will get notifications on profile changes & new messages", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_menu")]]))
    await c.answer()

@dp.callback_query(F.data == "buy_credits")
async def buy_credits(c: CallbackQuery):
    price = await get_price()
    user = await get_user(c.from_user.id)
    credits = user[3] if user else 0
    await c.message.edit_text(f"💎 <b>Buy Credits</b>\n\nBalance: <b>{credits} Credits</b>\nPrice: <b>{price} INR</b> per Credit\n\nSelect package:", reply_markup=buy_kb(price))
    await c.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_amount(c: CallbackQuery):
    amount = int(c.data.split("_")[1])
    price = await get_price()
    total = amount * price
    await c.message.edit_text(f"🧾 <b>Order Summary</b>\n\nCredits: <b>{amount} Credits</b>\nPrice: {price} INR × {amount} = <b>₹{total}</b>\nUSDT: ~${total/83:.2f}\n\nChoose payment method:", reply_markup=payment_method_kb(amount, price))
    await c.answer()

@dp.callback_query(F.data.startswith("pay_upi_"))
async def pay_upi(c: CallbackQuery, state: FSMContext):
    amount = int(c.data.split("_")[2])
    price = await get_price()
    total = amount * price
    upi_id = await get_setting("upi_id")
    upi_url = f"upi://pay?pa={upi_id}&pn=FunStat&am={total}&cu=INR"
    qr = qrcode.make(upi_url)
    bio = BytesIO(); qr.save(bio, format='PNG'); bio.seek(0)
    caption = f"📱 <b>UPI Payment</b>\n\n💎 {amount} Credits\n💰 Amount: <b>₹{total}</b>\n🏦 UPI ID: <code>{upi_id}</code>\n\n1. Scan QR or pay to UPI\n2. Send screenshot with Transaction ID\n3. Owner will confirm in 5-10 min"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ I Paid — Send Screenshot", callback_data=f"proof_upi_{amount}_{total}")],[InlineKeyboardButton(text="🔙 Back", callback_data="buy_credits")]])
    await c.message.answer_photo(BufferedInputFile(bio.getvalue(), filename="upi_qr.png"), caption=caption, reply_markup=kb)
    await c.answer()
    await state.set_state(UserStates.waiting_payment_proof)
    await state.update_data(pay_amount=amount, pay_total=total, pay_method="UPI")

@dp.callback_query(F.data.startswith("pay_usdt_"))
async def pay_usdt(c: CallbackQuery, state: FSMContext):
    amount = int(c.data.split("_")[2])
    price = await get_price()
    total = amount * price
    usdt_trc = await get_setting("usdt_trc20")
    usdt_bep = await get_setting("usdt_bep20")
    usd = total/83
    caption = f"💵 <b>USDT Payment</b>\n\n💎 {amount} Credits\n💰 Amount: <b>₹{total} (~${usd:.2f})</b>\n\n<b>TRC20 (Tron):</b>\n<code>{usdt_trc}</code>\n\n<b>BEP20 (BSC):</b>\n<code>{usdt_bep}</code>\n\n1. Send exact USDT\n2. Send Transaction Hash\n3. Owner will confirm"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ I Paid — Send Hash", callback_data=f"proof_usdt_{amount}_{total}")],[InlineKeyboardButton(text="🔙 Back", callback_data="buy_credits")]])
    await c.message.answer(caption, reply_markup=kb)
    await c.answer()
    await state.set_state(UserStates.waiting_payment_proof)
    await state.update_data(pay_amount=amount, pay_total=total, pay_method="USDT")

@dp.callback_query(F.data.startswith("proof_"))
async def proof_ask(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📤 <b>Send proof:</b>\n\n• For UPI — Send screenshot\n• For USDT — Send Transaction Hash / screenshot")
    await c.answer()

@dp.message(UserStates.waiting_payment_proof)
async def proof_receive(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get("pay_amount"); total = data.get("pay_total"); method = data.get("pay_method")
    import aiosqlite, os
    proof_text = message.text or message.caption or "photo"
    if message.photo: proof_text = f"photo_{message.photo[-1].file_id}"
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        await db.execute("INSERT INTO transactions(user_id, type, amount, price_inr, method, status, proof, created_at) VALUES(?,?,?,?,?,?,?,?)", (message.from_user.id, "buy", amount, total, method, "pending", proof_text, datetime.now().isoformat()))
        await db.commit()
    if config.OWNER_ID:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{message.from_user.id}_{amount}"), InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{message.from_user.id}")]])
            await bot.send_message(config.OWNER_ID, f"🔔 <b>New Payment Pending!</b>\n\n👤 {message.from_user.first_name} (@{message.from_user.username}) ID: <code>{message.from_user.id}</code>\n💎 {amount} Credits\n💰 ₹{total} via {method}\n📎 {proof_text[:100]}", reply_markup=kb)
            if message.photo: await bot.forward_message(config.OWNER_ID, message.from_user.id, message.message_id)
        except: pass
    await message.answer(f"✅ <b>Request sent!</b>\n\n💎 {amount} Credits — ₹{total} via {method}\nOwner will confirm in 5-10 min.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Menu", callback_data="back_menu")]]))
    await state.clear()

# Owner
@dp.callback_query(F.data == "owner_panel")
async def owner_panel(c: CallbackQuery):
    if not config.is_owner(c.from_user.id):
        await c.answer("❌ Owner only!", show_alert=True)
        return
    price = await get_price(); upi = await get_setting("upi_id"); trc = await get_setting("usdt_trc20"); stats = await get_stats()
    await c.message.edit_text(f"👑 <b>OWNER PANEL</b>\n\n💰 Price/Credit: <b>₹{price}</b>\n🏦 UPI: <code>{upi}</code>\n💵 TRC20: <code>{trc[:15]}...</code>\n\n📊 Users: {stats['total_users']} | Pending: {stats['pending']}", reply_markup=owner_panel_kb())
    await c.answer()

@dp.callback_query(F.data == "owner_set_price")
async def owner_set_price(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_price)
    await c.message.answer("💰 <b>Set Price Per Credit</b>\nSend new price in INR (e.g. 15, 20, 50)\nCurrent: ₹" + await get_setting("price_per_credit"))
    await c.answer()
@dp.message(OwnerStates.waiting_price)
async def owner_price_save(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        await set_setting("price_per_credit", str(price))
        await message.answer(f"✅ Price updated: <b>₹{price}/Credit</b>", reply_markup=owner_panel_kb())
    except: await message.answer("❌ Send number, e.g. 20")
    await state.clear()

@dp.callback_query(F.data == "owner_set_upi")
async def owner_set_upi(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_upi)
    await c.message.answer(f"🏦 <b>Set UPI ID</b>\nCurrent: <code>{await get_setting('upi_id')}</code>\n\nSend new UPI ID (e.g. name@upi)")
    await c.answer()
@dp.message(OwnerStates.waiting_upi)
async def owner_upi_save(message: Message, state: FSMContext):
    await set_setting("upi_id", message.text.strip())
    await message.answer(f"✅ UPI updated: <code>{message.text.strip()}</code>", reply_markup=owner_panel_kb())
    await state.clear()

@dp.callback_query(F.data == "owner_set_usdt_trc")
async def owner_set_usdt_trc(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_usdt_trc)
    await c.message.answer(f"💵 <b>Set USDT TRC20</b>\nCurrent: <code>{await get_setting('usdt_trc20')}</code>\n\nSend new TRC20 address")
    await c.answer()
@dp.message(OwnerStates.waiting_usdt_trc)
async def owner_usdt_trc_save(message: Message, state: FSMContext):
    await set_setting("usdt_trc20", message.text.strip())
    await message.answer("✅ USDT TRC20 updated!", reply_markup=owner_panel_kb())
    await state.clear()

@dp.callback_query(F.data == "owner_set_usdt_bep")
async def owner_set_usdt_bep(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_usdt_bep)
    await c.message.answer(f"💵 <b>Set USDT BEP20</b>\nCurrent: <code>{await get_setting('usdt_bep20')}</code>\n\nSend new BEP20 address")
    await c.answer()
@dp.message(OwnerStates.waiting_usdt_bep)
async def owner_usdt_bep_save(message: Message, state: FSMContext):
    await set_setting("usdt_bep20", message.text.strip())
    await message.answer("✅ USDT BEP20 updated!", reply_markup=owner_panel_kb())
    await state.clear()

@dp.callback_query(F.data == "owner_stats")
async def owner_stats(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    stats = await get_stats()
    await c.message.answer(f"📊 <b>Bot Stats</b>\n\n👥 Total Users: {stats['total_users']}\n💎 Total Credits: {stats['total_credits']}\n🔥 Total Spent: {stats['total_spent']}\n⏳ Pending: {stats['pending']}\n💰 Price: ₹{await get_setting('price_per_credit')}", reply_markup=owner_panel_kb())
    await c.answer()
@dp.callback_query(F.data == "owner_add_credits")
async def owner_add_credits_start(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_add_credit_id)
    await c.message.answer("➕ <b>Add Credits</b>\n\nSend Telegram ID of user (e.g. 123456789)")
    await c.answer()
@dp.message(OwnerStates.waiting_add_credit_id)
async def owner_add_id(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await state.update_data(target_id=uid)
        await state.set_state(OwnerStates.waiting_add_credit_amount)
        await message.answer(f"ID: {uid}\nHow many credits to add?")
    except: await message.answer("❌ Invalid ID")
@dp.message(OwnerStates.waiting_add_credit_amount)
async def owner_add_amount(message: Message, state: FSMContext):
    try:
        amt = int(message.text.strip())
        data = await state.get_data(); uid = data['target_id']
        await add_credits(uid, amt)
        await message.answer(f"✅ Added {amt} credits to {uid}!", reply_markup=owner_panel_kb())
        try: await bot.send_message(uid, f"🎉 <b>{amt} Credits added!</b> by Owner\nCheck /balance or /menu")
        except: pass
        await state.clear()
    except: await message.answer("❌ Send number")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_pay(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    parts = c.data.split("_"); uid = int(parts[1]); amt = int(parts[2])
    await add_credits(uid, amt)
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        await db.execute("UPDATE transactions SET status='approved' WHERE user_id=? AND status='pending'", (uid,))
        await db.commit()
    await c.message.edit_text(f"✅ Approved {amt} credits to {uid}")
    try: await bot.send_message(uid, f"✅ <b>Payment Approved!</b>\n💎 {amt} Credits added\nUse /menu")
    except: pass
    await c.answer("Approved!")
@dp.callback_query(F.data.startswith("reject_"))
async def reject_pay(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    uid = int(c.data.split("_")[1])
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        await db.execute("UPDATE transactions SET status='rejected' WHERE user_id=? AND status='pending'", (uid,))
        await db.commit()
    await c.message.edit_text(f"❌ Rejected for {uid}")
    try: await bot.send_message(uid, "❌ Payment rejected. Contact owner.")
    except: pass
    await c.answer()
@dp.callback_query(F.data == "owner_pending")
async def owner_pending(c: CallbackQuery):
    if not config.is_owner(c.from_user.id): return
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT user_id, amount, price_inr, method, proof FROM transactions WHERE status='pending' LIMIT 5")
        rows = await cur.fetchall()
    if not rows:
        await c.message.answer("✅ No pending payments", reply_markup=owner_panel_kb())
    else:
        text = "⏳ <b>Pending Payments:</b>\n\n"
        for r in rows:
            text += f"• {r[0]} — {r[1]}💎 — ₹{r[2]} {r[3]} — {r[4][:20]}\n"
        await c.message.answer(text, reply_markup=owner_panel_kb())
    await c.answer()
@dp.callback_query(F.data == "owner_broadcast")
async def owner_broadcast_start(c: CallbackQuery, state: FSMContext):
    if not config.is_owner(c.from_user.id): return
    await state.set_state(OwnerStates.waiting_broadcast)
    await c.message.answer("📢 <b>Broadcast</b>\nSend message to broadcast to all users:")
    await c.answer()
@dp.message(OwnerStates.waiting_broadcast)
async def owner_broadcast_send(message: Message, state: FSMContext):
    import aiosqlite, os
    async with aiosqlite.connect(os.getenv("DATABASE_PATH", "database/funstat.db")) as db:
        cur = await db.execute("SELECT user_id FROM users")
        users = await cur.fetchall()
    count = 0
    for (uid,) in users:
        try:
            await bot.copy_message(uid, message.from_user.id, message.message_id)
            count += 1
        except: pass
    await message.answer(f"✅ Broadcast sent to {count} users", reply_markup=owner_panel_kb())
    await state.clear()

@dp.message(Command("owner"))
async def owner_cmd(message: Message):
    if not config.is_owner(message.from_user.id):
        await message.answer("❌ Owner only!")
        return
    price = await get_price()
    await message.answer(f"👑 Owner Panel — Price: ₹{price}/Credit", reply_markup=owner_panel_kb())

# Keep-alive Web Server to prevent Render sleep
async def health_server():
    from aiohttp import web
    app = web.Application()
    async def health(req): return web.Response(text="✅ FunStat Bot is Running! Uptime: OK")
    async def root(req): return web.Response(text="FunStat Bot - Keep Alive OK")
    app.router.add_get('/', root)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Keep-Alive server running on port {port} - /health")

async def main():
    if not config.BOT_TOKEN:
        print("❌ BOT_TOKEN missing!")
        return
    await init_db()
    await setup_commands()
    # Start keep-alive server in background (prevents Render sleep)
    asyncio.create_task(health_server())
    print(f"🚀 FunStat Bot (ENGLISH) Started! Owner: {config.OWNER_ID} Price: {await get_setting('price_per_credit')} INR - KeepAlive enabled")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
