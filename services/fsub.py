from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from config import FSUB_CHANNEL_ID, FSUB_INVITE_LINK, logger

async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    """
    Check if a user is subscribed to the required channel.
    Returns True if FSUB is disabled or user is a member.
    """
    if not FSUB_CHANNEL_ID:
        return True

    try:
        member = await bot.get_chat_member(chat_id=FSUB_CHANNEL_ID, user_id=user_id)
        if member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]:
            return True
        elif member.status == ChatMemberStatus.RESTRICTED:
            return True
        return False
    except TelegramError as e:
        logger.warning(f"FSUB Check error for user {user_id} in {FSUB_CHANNEL_ID}: {e}")
        # If bot is not admin or channel is unreachable, default to True to avoid locking out users
        if "bot is not a member" in str(e).lower() or "chat not found" in str(e).lower():
            logger.error("FSUB Channel error: Bot must be added as administrator in the FSUB channel!")
            return True
        return False

def get_fsub_keyboard(callback_data: str = "check_fsub:home") -> InlineKeyboardMarkup:
    """Generate keyboard with join link and refresh button."""
    join_url = FSUB_INVITE_LINK
    if not join_url:
        if isinstance(FSUB_CHANNEL_ID, str) and FSUB_CHANNEL_ID.startswith("@"):
            join_url = f"https://t.me/{FSUB_CHANNEL_ID[1:]}"
        else:
            join_url = "https://t.me/telegram"

    keyboard = [
        [InlineKeyboardButton("📢 Join Our Updates Channel", url=join_url)],
        [InlineKeyboardButton("🔄 I Have Joined (Verify)", callback_data=callback_data)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fsub_message() -> str:
    """Message shown when user is not subscribed."""
    return (
        "🔒 **Access Restricted!**\n\n"
        "You must join our official updates channel to use this bot and access movie files.\n\n"
        "1. Click the button below to join the channel.\n"
        "2. Then tap **I Have Joined (Verify)** to get your movie!"
    )
