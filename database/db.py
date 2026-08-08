import aiosqlite
import os
from datetime import datetime, timedelta

DB_PATH = os.getenv("DATABASE_PATH", "database/funstat.db")

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    credits INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    referred_by INTEGER,
    joined_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount INTEGER,
    price_inr INTEGER,
    method TEXT,
    status TEXT,
    proof TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watcher_id INTEGER,
    target_username TEXT,
    target_id INTEGER,
    expiry TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target TEXT,
    result TEXT,
    cost INTEGER,
    created_at TEXT
);
"""

DEFAULT_SETTINGS = {
    "price_per_credit": "20",
    "upi_id": "yourname@upi",
    "usdt_trc20": "TX...TRC20...",
    "usdt_bep20": "0x...BEP20...",
    "bot_maintenance": "0"
}

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        for k, v in DEFAULT_SETTINGS.items():
            await db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else DEFAULT_SETTINGS.get(key, "")

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()

async def ensure_user(user_id, username="", first_name="", referred_by=None):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT OR IGNORE INTO users(user_id, username, first_name, credits, joined_at, referred_by) VALUES(?,?,?,?,?,?)",
                             (user_id, username, first_name, 2, datetime.now().isoformat(), referred_by))
            await db.commit()
            # check if inserted (changes)
            cur = await db.execute("SELECT changes()")
            row = await cur.fetchone()
            return row[0] == 1 if row else False
        except:
            return False

async def add_credits(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def deduct_credits(user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute("UPDATE users SET credits = credits - ?, total_spent = total_spent + ? WHERE user_id=?", (amount, amount, user_id))
        await db.commit()
        return True

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*), SUM(credits), SUM(total_spent) FROM users")
        row = await cur.fetchone()
        cur2 = await db.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'")
        pending = (await cur2.fetchone())[0]
        return {"total_users": row[0] or 0, "total_credits": row[1] or 0, "total_spent": row[2] or 0, "pending": pending}
