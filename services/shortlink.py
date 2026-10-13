import secrets
import aiohttp
from typing import Optional, Tuple
from urllib.parse import quote
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import (
    SHORTLINK_ENABLED,
    SHORTLINK_API_URL,
    SHORTLINK_API_KEY,
    VERIFY_EXPIRE_HOURS,
    TUTORIAL_URL,
    is_admin,
    logger
)
from database import is_user_verified, create_pending_verification

async def check_user_access(user_id: int, username: Optional[str] = None) -> bool:
    """
    Check if a user has access to download movies.
    Admins are always granted access.
    If shortlink is disabled, all users are granted access.
    Otherwise, checks if user has an unexpired verification pass.
    """
    if not SHORTLINK_ENABLED:
        return True
    if is_admin(user_id, username):
        return True
    return await is_user_verified(user_id)

async def get_shortlink(destination_url: str) -> str:
    """
    Call the URL shortener API to shorten the destination URL.
    Falls back to direct URL if API is unconfigured or errors.
    """
    if not SHORTLINK_API_KEY or not SHORTLINK_API_URL:
        logger.info("SHORTLINK_API_KEY not configured; using direct link for verification.")
        return destination_url

    api_url = f"{SHORTLINK_API_URL}?api={SHORTLINK_API_KEY}&url={quote(destination_url)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json(content_type=None)
                        if isinstance(data, dict):
                            short = (
                                data.get("shortenedUrl")
                                or data.get("url")
                                or data.get("link")
                                or data.get("short_url")
                            )
                            if short and short.startswith("http"):
                                return short
                    except Exception:
                        # Plain text response
                        text = (await resp.text()).strip()
                        if text.startswith("http://") or text.startswith("https://"):
                            return text
    except Exception as e:
        logger.warning(f"Error calling shortener API ({SHORTLINK_API_URL}): {e}")

    # Fallback to direct URL if shortener failed
    return destination_url

async def create_verification_link(
    bot_username: str,
    user_id: int,
    target_movie_id: Optional[int] = None
) -> Tuple[str, str]:
    """
    Generates a new verification session.
    Returns: (token, short_or_direct_url)
    """
    token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:16]
    await create_pending_verification(token, user_id, target_movie_id)
    destination_url = f"https://t.me/{bot_username}?start=verify_{token}"
    short_url = await get_shortlink(destination_url)
    return token, short_url

def get_verification_keyboard(short_url: str) -> InlineKeyboardMarkup:
    """Build keyboard with Verify Now and Tutorial buttons."""
    buttons = [
        [InlineKeyboardButton("🔓 Verify Now (Click Here)", url=short_url)]
    ]
    if TUTORIAL_URL:
        buttons.append([InlineKeyboardButton("❓ How to Verify (Tutorial)", url=TUTORIAL_URL)])
    return InlineKeyboardMarkup(buttons)

def get_verification_message() -> str:
    """User-facing message explaining shortlink verification."""
    return (
        "🔐 <b>Verification Required!</b>\n\n"
        f"To access movie downloads, please complete a quick 1-time verification.\n"
        f"Once verified, you will unlock <b>unlimited movie downloads for {VERIFY_EXPIRE_HOURS} hours</b>!\n\n"
        "👉 <b>Step 1:</b> Tap <b>Verify Now</b> below.\n"
        "👉 <b>Step 2:</b> Complete the short step on the page.\n"
        "👉 <b>Step 3:</b> You will be automatically redirected back here with full access unlocked!"
    )
