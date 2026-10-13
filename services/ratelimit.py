from datetime import datetime, timedelta
from typing import Optional, Tuple
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import DAILY_MOVIE_LIMIT, ADMIN_EXEMPT_FROM_LIMIT, is_admin, SHORTLINK_ENABLED
from database import (
    get_user_downloads_today,
    is_user_premium,
    is_user_verified,
    get_user_bonus_downloads
)

async def check_daily_limit(user_id: int, username: Optional[str] = None) -> Tuple[bool, int, int]:
    """
    Check if a user has reached their daily movie download limit for today (resets at midnight).
    VIP / Premium subscribers have UNLIMITED movie downloads with NO limits.
    Users with an active Shortlink pass have UNLIMITED movie downloads.
    Users with referral bonus downloads can use their extra passes.
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

    # 🔓 Shortlink pass verification (active 24h pass)
    if await is_user_verified(user_id):
        return True, 0, 0

    count = await get_user_downloads_today(user_id)
    if count < DAILY_MOVIE_LIMIT:
        return True, 0, 0

    # 🎁 Check referral bonus downloads
    bonus = await get_user_bonus_downloads(user_id)
    if bonus > 0:
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
        "<b>Ways to continue downloading right now:</b>\n"
        "1. 💎 <b>Upgrade to VIP:</b> Unlimited downloads with zero limits & no ads\n"
        "2. 🔓 <b>Free 24h Pass:</b> Complete 1 quick link to unlock 24h access\n"
        "3. 🎁 <b>Invite Friends:</b> Earn +1 download pass per friend & free VIP days!"
    )

def get_daily_limit_keyboard() -> InlineKeyboardMarkup:
    """Keyboard prompting user to upgrade to VIP, unlock via Shortlink, or Invite friends."""
    buttons = [
        [InlineKeyboardButton("💎 Buy VIP (Unlimited Downloads)", callback_data="buy_premium")]
    ]
    if SHORTLINK_ENABLED:
        buttons.append([InlineKeyboardButton("🔓 Unlock 24h Pass (Free Link)", callback_data="get_shortlink_pass")])
    buttons.append([InlineKeyboardButton("🎁 Invite Friends & Earn Free VIP", callback_data="show_referral_info")])
    buttons.append([InlineKeyboardButton("🔍 Search More Movies", callback_data="help_search")])
    return InlineKeyboardMarkup(buttons)
