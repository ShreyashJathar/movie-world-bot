import sys
import os
import logging
from typing import Optional
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MovieBot")

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin IDs and Usernames
_admin_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = set()
ADMIN_USERNAMES = set()
if _admin_raw:
    for item in _admin_raw.split(","):
        clean_item = item.strip()
        if clean_item.startswith("@"):
            ADMIN_USERNAMES.add(clean_item[1:].lower())
        elif clean_item.isdigit() or (clean_item.startswith("-") and clean_item[1:].isdigit()):
            ADMIN_IDS.add(int(clean_item))
        elif clean_item:
            ADMIN_USERNAMES.add(clean_item.lower())

# Storage Channel ID (numeric, usually starts with -100)
_storage_raw = os.getenv("STORAGE_CHANNEL_ID", "").strip()
STORAGE_CHANNEL_ID = None
if _storage_raw:
    try:
        STORAGE_CHANNEL_ID = int(_storage_raw)
    except ValueError:
        logger.warning("STORAGE_CHANNEL_ID must be an integer, e.g., -1001234567890")

# Force-Subscribe (FSUB) settings
FSUB_CHANNEL_ID = os.getenv("FSUB_CHANNEL_ID", "").strip() or None
if FSUB_CHANNEL_ID:
    # Check if it's numeric ID
    try:
        FSUB_CHANNEL_ID = int(FSUB_CHANNEL_ID)
    except ValueError:
        # It's a channel username like @channelname
        if not FSUB_CHANNEL_ID.startswith("@") and not FSUB_CHANNEL_ID.startswith("http"):
            FSUB_CHANNEL_ID = f"@{FSUB_CHANNEL_ID}"

FSUB_INVITE_LINK = os.getenv("FSUB_INVITE_LINK", "").strip() or None

# Auto Delete Time (in seconds, default 600s = 10 mins)
try:
    AUTO_DELETE_SECONDS = int(os.getenv("AUTO_DELETE_SECONDS", "600").strip())
except ValueError:
    AUTO_DELETE_SECONDS = 600

# Daily Download Limit per user (default: 1 movie per day, 0 to disable)
try:
    DAILY_MOVIE_LIMIT = int(os.getenv("DAILY_MOVIE_LIMIT", "1").strip())
except ValueError:
    DAILY_MOVIE_LIMIT = 1

# Whether admins bypass the daily limit (default: False so you can test the limit)
ADMIN_EXEMPT_FROM_LIMIT = os.getenv("ADMIN_EXEMPT_FROM_LIMIT", "False").strip().lower() in ["true", "1", "yes"]

# OMDb API Key
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip() or None

# Shortlink Verification Settings
SHORTLINK_ENABLED = os.getenv("SHORTLINK_ENABLED", "True").strip().lower() in ["true", "1", "yes"]
SHORTLINK_API_URL = os.getenv("SHORTLINK_API_URL", "https://gplinks.in/api").strip()
SHORTLINK_API_KEY = os.getenv("SHORTLINK_API_KEY", "").strip()
try:
    VERIFY_EXPIRE_HOURS = int(os.getenv("VERIFY_EXPIRE_HOURS", "24").strip())
except ValueError:
    VERIFY_EXPIRE_HOURS = 24
TUTORIAL_URL = os.getenv("TUTORIAL_URL", "").strip() or None

# Database Path
DATABASE_PATH = os.getenv("DATABASE_PATH", "movies.db").strip()

# Assets & QR paths
WEEKLY_QR_IMAGE = os.getenv(
    "WEEKLY_QR_IMAGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "qr_weekly_39.jpg")
)
MONTH1_QR_IMAGE = os.getenv(
    "MONTH1_QR_IMAGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "qr_1month_89.jpg")
)
MONTH3_QR_IMAGE = os.getenv(
    "MONTH3_QR_IMAGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "qr_3months_219.jpg")
)
MONTH6_QR_IMAGE = os.getenv(
    "MONTH6_QR_IMAGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "qr_6months_349.jpg")
)
YEAR1_QR_IMAGE = os.getenv(
    "YEAR1_QR_IMAGE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "qr_1year_649.jpg")
)

# VIP Subscription Plans
SUBSCRIPTION_PLANS = [
    {
        "id": "plan_weekly",
        "name": "Weekly Pass",
        "days": 7,
        "price": 39,
        "currency": "₹",
        "badge": "🌟",
        "label": "Weekly (7 Days) — ₹39",
        "description": "Unlimited downloads for 7 days",
        "qr_image": WEEKLY_QR_IMAGE
    },
    {
        "id": "plan_1month",
        "name": "1 Month VIP",
        "days": 30,
        "price": 89,
        "currency": "₹",
        "badge": "🌟",
        "label": "1 Month (30 Days) — ₹89",
        "description": "Unlimited downloads for 30 days",
        "qr_image": MONTH1_QR_IMAGE
    },
    {
        "id": "plan_3months",
        "name": "3 Months VIP",
        "days": 90,
        "price": 219,
        "currency": "₹",
        "badge": "🔥",
        "label": "3 Months (90 Days) — ₹219",
        "description": "Unlimited downloads for 90 days (Popular)",
        "qr_image": MONTH3_QR_IMAGE
    },
    {
        "id": "plan_6months",
        "name": "6 Months VIP",
        "days": 180,
        "price": 349,
        "currency": "₹",
        "badge": "👑",
        "label": "6 Months (180 Days) — ₹349",
        "description": "Unlimited downloads for 180 days (Value)",
        "qr_image": MONTH6_QR_IMAGE
    },
    {
        "id": "plan_1year",
        "name": "One Year VIP",
        "days": 365,
        "price": 649,
        "currency": "₹",
        "badge": "⚡",
        "label": "One Year (365 Days) — ₹649",
        "description": "Unlimited downloads for 365 days (Best Value)",
        "qr_image": YEAR1_QR_IMAGE
    }
]

def get_plan_by_id(plan_id: str) -> Optional[dict]:
    """Retrieve subscription plan by ID."""
    for plan in SUBSCRIPTION_PLANS:
        if plan["id"] == plan_id:
            return plan
    return None

# Payment & Contact Settings
UPI_ID = os.getenv("UPI_ID", "").strip() or "7741053589-3@ybl"
UPI_NAME = os.getenv("UPI_NAME", "Movie World VIP").strip()
ADMIN_CONTACT_USERNAME = os.getenv("ADMIN_CONTACT_USERNAME", "JatharPatil").strip().lstrip("@")
PAYMENT_QR_IMAGE = os.getenv("PAYMENT_QR_IMAGE", "").strip()

# Private Admin Verification Group (for subscription APPROVES and REJECTS)
_admin_group_raw = os.getenv("ADMIN_GROUP_ID", "").strip()
ADMIN_GROUP_ID = None
if _admin_group_raw:
    try:
        ADMIN_GROUP_ID = int(_admin_group_raw)
    except ValueError:
        logger.warning("ADMIN_GROUP_ID must be a numeric integer, e.g. -100xxxxxxxxxx")

def is_admin(user_id: Optional[int] = None, username: Optional[str] = None) -> bool:
    """Check if a given user is an admin by numeric user_id or @username."""
    if user_id and user_id in ADMIN_IDS:
        return True
    if username and username.lower() in ADMIN_USERNAMES:
        return True
    return False

