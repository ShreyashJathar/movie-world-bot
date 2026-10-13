import asyncio
from typing import List
from telegram import Bot
from telegram.error import TelegramError
from config import AUTO_DELETE_SECONDS, logger

async def _delete_after_delay(bot: Bot, chat_id: int, message_ids: List[int], delay: int) -> None:
    """Wait for delay seconds and delete messages."""
    try:
        await asyncio.sleep(delay)
        for msg_id in message_ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except TelegramError as e:
                logger.debug(f"Could not delete message {msg_id} in {chat_id}: {e}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in autodelete task: {e}")

def schedule_auto_delete(bot: Bot, chat_id: int, message_ids: List[int], delay: int = AUTO_DELETE_SECONDS) -> None:
    """Schedule asynchronous deletion of sent movie files."""
    if delay <= 0 or not message_ids:
        return
    asyncio.create_task(_delete_after_delay(bot, chat_id, message_ids, delay))
