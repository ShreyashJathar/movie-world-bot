from typing import Optional, Tuple
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import FREE_MOVIE_LIMIT, ADMIN_EXEMPT_FROM_LIMIT, is_admin
from database import (
    get_user_total_downloads,
    is_user_premium,
    get_user_bonus_downloads
)

async def check_user_download_limit(user_id: int, username: Optional[str] = None) -> Tuple[bool, int, int]:
    """
    Check if a user is allowed to download a movie.
    - VIP / Premium subscribers have UNLIMITED movie downloads.
    - Admins exempt if ADMIN_EXEMPT_FROM_LIMIT is True.
    - Free users get FREE_MOVIE_LIMIT (default: 2) lifetime free movies total (does NOT reset daily).
    - Once free movies are exhausted, user must have an active VIP subscription or referral bonus passes.
    Returns: (is_allowed, total_downloads, bonus_passes_left)
    """
    # 💎 VIP / Premium subscribers get UNLIMITED downloads!
    if await is_user_premium(user_id):
        return True, 0, 0

    # Admins exempt if explicitly enabled via ADMIN_EXEMPT_FROM_LIMIT
    if ADMIN_EXEMPT_FROM_LIMIT and is_admin(user_id, username):
        return True, 0, 0

    # Check lifetime free movie quota
    total_downloads = await get_user_total_downloads(user_id)
    if total_downloads < FREE_MOVIE_LIMIT:
        return True, total_downloads, 0

    # 🎁 Check referral bonus downloads (earned from friends who actually use the bot)
    bonus = await get_user_bonus_downloads(user_id)
    if bonus > 0:
        return True, total_downloads, bonus

    return False, total_downloads, 0

# Backward compatibility alias
check_daily_limit = check_user_download_limit

def get_limit_reached_message(total_used: int = FREE_MOVIE_LIMIT, *args, **kwargs) -> str:
    """High-converting paywall message forcing user to take VIP or invite active friends."""
    return (
        f"🔒 <b>Free Movie Quota Exhausted! ({FREE_MOVIE_LIMIT}/{FREE_MOVIE_LIMIT} Used)</b>\n\n"
        f"You have used your <b>{FREE_MOVIE_LIMIT} Free Welcome Movies</b>.\n"
        "<i>Free downloads do NOT reset daily. To continue downloading, unlock access below:</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🌟 <b>OPTION 1: Upgrade to VIP (Recommended)</b>\n"
        "• ⚡ <b>Unlimited Full HD Movies & Series</b> (Zero limits!)\n"
        "• 🚀 <b>High-Speed Instant Delivery</b> — No waiting\n"
        "• 🚫 <b>100% Ad-Free Experience</b>\n"
        "• 🎬 <b>Exclusive Access to Latest Blockbusters</b>\n"
        "• 📥 <b>Direct Movie Request to Admin</b>\n"
        "👉 <i>Plans start from only ₹39! Tap below to subscribe.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>OPTION 2: Invite Friends (Free Passes)</b>\n"
        "• Share your personal invite link with friends.\n"
        "• <b>Note:</b> Friends must <b>use the bot (download 1 movie)</b> to count!\n"
        "• 🎟️ <b>Each Active Friend:</b> +1 Free Movie Pass\n"
        "• 🏆 <b>Invite 10 Active Friends:</b> <b>🌟 1-Week Free VIP Pass!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

# Backward compatibility alias
get_daily_limit_message = get_limit_reached_message

def get_limit_reached_keyboard() -> InlineKeyboardMarkup:
    """Keyboard prompting user to upgrade to VIP or invite friends."""
    buttons = [
        [InlineKeyboardButton("💎 Upgrade to VIP (Unlimited Movies)", callback_data="buy_premium")],
        [InlineKeyboardButton("🎁 Invite Friends & Earn Free Passes", callback_data="show_referral_info")],
        [InlineKeyboardButton("🔍 Search Available Movies", callback_data="help_search")]
    ]
    return InlineKeyboardMarkup(buttons)

# Backward compatibility alias
get_daily_limit_keyboard = get_limit_reached_keyboard
