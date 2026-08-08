import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

DATABASE_PATH = os.getenv("DATABASE_PATH", "database/funstat.db")

DEFAULT_PRICE_PER_CREDIT = int(os.getenv("DEFAULT_PRICE_PER_CREDIT", "20"))
DEFAULT_UPI_ID = os.getenv("DEFAULT_UPI_ID", "yourname@upi")
DEFAULT_USDT_TRC20 = os.getenv("DEFAULT_USDT_TRC20", "TX...TRC20...")
DEFAULT_USDT_BEP20 = os.getenv("DEFAULT_USDT_BEP20", "0x...BEP20...")

WEB_ADMIN_PORT = int(os.getenv("WEB_ADMIN_PORT", "5000"))
WEB_ADMIN_SECRET = os.getenv("WEB_ADMIN_SECRET", "funstat-secret-2024")

# Feature Costs (in credits)
COSTS = {
    "search_user": 1,      # User profile + chats + messages
    "search_chats": 1,     # Chat search by keyword
    "word_analysis": 1,    # Word frequency
    "tracking_28d": 1,     # Surveillance 28 days
    "full_report": 2       # Complete OSINT Report
}

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS
