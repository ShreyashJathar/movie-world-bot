from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import DAILY_MOVIE_LIMIT, ADMIN_EXEMPT_FROM_LIMIT, is_admin, logger
from database import get_user_downloads_today, is_user_premium

async def check_daily_limit(user_id: int, username: Optional[str] = None) -> Tuple[bool, int, int]:
    """
    Check if a user has reached their daily movie download limit for today (resets at midnight).
    VIP / Premium subscribers have UNLIMITED movie downloads with NO limits.
    Returns: (is_allowed, hours_left, minutes_left)
    """
    if DAILY_MOVIE_LIMIT <= 0:
        return True, 0, 0

    # 💎 VIP / Premium subscribers get UNLIMITED downloads!
    if await is_user_premium(user_id):
        return True, 0, 0

    # Admins exempt if explicitly enabled via ADMIN_EXEMPT_FROM_LIMIT
    if ADMIN_EXEMPT_FROM_LIMIT and is_admin(user_id, username):
        return True, 0, 0

    count = await get_user_downloads_today(user_id)
    if count < DAILY_MOVIE_LIMIT:
        return True, 0, 0

    # Calculate remaining time until next midnight
    now_local = datetime.now().astimezone()
    next_midnight = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_left = max(60, int((next_midnight - now_local).total_seconds()))
    hours_left = seconds_left // 3600
    minutes_left = (seconds_left % 3600) // 60

    return False, hours_left, minutes_left

def get_daily_limit_message(hours_left: int, minutes_left: int) -> str:
    """Friendly message shown when daily download limit is reached."""
    time_str = f"{hours_left}h {minutes_left}m" if hours_left > 0 else f"{minutes_left} minutes"
    return (
        "⏳ <b>Daily Download Limit Reached!</b>\n\n"
        f"Free users can download <b>{DAILY_MOVIE_LIMIT} movie per day</b>.\n"
        "You have already claimed your free movie for today.\n\n"
        f"⏰ <b>Limit Resets At Midnight:</b> in <code>{time_str}</code>\n\n"
        "💎 <b>Want Unlimited Movies Without Waiting?</b>\n"
        "Upgrade to <b>Premium</b> to unlock unlimited movie downloads instantly!"
    )

def get_daily_limit_keyboard() -> InlineKeyboardMarkup:
    """Keyboard prompting user to upgrade to Premium."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Buy Premium (Unlimited Movies)", callback_data="buy_premium")],
        [InlineKeyboardButton("🔍 Search More Movies", callback_data="help_search")]
    ])
