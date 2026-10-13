from typing import Dict, Any
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config import AUTO_DELETE_SECONDS, logger
from services.autodelete import schedule_auto_delete
from services.metadata import format_file_size

async def deliver_movie_file(bot: Bot, chat_id: int, movie: Dict[str, Any]) -> bool:
    """
    Sends the movie file to the user and manages auto-deletion.
    Returns True if sent successfully, False otherwise.
    """
    sent_msg = None
    file_name = movie.get("file_name", "Movie")
    file_size_str = format_file_size(movie.get("file_size", 0))
    caption = movie.get("caption") or f"🎬 <b>{file_name}</b>\n📦 Size: <code>{file_size_str}</code>"

    # Strategy 1: Copy message from storage channel if available
    channel_id = movie.get("channel_id")
    message_id = movie.get("message_id")
    if channel_id and message_id:
        try:
            sent_msg = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=channel_id,
                message_id=message_id
            )
        except TelegramError as e:
            logger.warning(f"Could not copy message from channel {channel_id}: {e}. Falling back to file_id.")

    # Strategy 2: Send using file_id
    if not sent_msg:
        file_id = movie.get("file_id")
        mime = movie.get("mime_type", "")
        try:
            if mime and mime.startswith("video/"):
                sent_msg = await bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            else:
                sent_msg = await bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
        except TelegramError as e:
            logger.error(f"Failed to deliver file {movie.get('id')} to chat {chat_id}: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text="❌ <b>Error:</b> Could not send this file. It may have been removed or expired.",
                parse_mode=ParseMode.HTML
            )
            return False

    # Auto-delete timer
    if sent_msg and AUTO_DELETE_SECONDS > 0:
        minutes = AUTO_DELETE_SECONDS // 60
        warning_text = (
            f"⏳ <b>Auto-Delete Notice:</b>\n"
            f"This file will be automatically deleted in <b>{minutes} minute{'s' if minutes != 1 else ''}</b> "
            f"to protect against copyright strikes.\n\n"
            f"👉 <i>Please forward it to your <b>Saved Messages</b> or download it right now!</i>"
        )
        try:
            warning_msg = await bot.send_message(
                chat_id=chat_id,
                text=warning_text,
                parse_mode=ParseMode.HTML
            )
            schedule_auto_delete(bot, chat_id, [sent_msg.message_id, warning_msg.message_id], AUTO_DELETE_SECONDS)
        except Exception as e:
            logger.warning(f"Failed to send autodelete warning: {e}")

    return True
