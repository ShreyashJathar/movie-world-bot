import sys
import asyncio

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters
)
from config import BOT_TOKEN, logger
from database import init_db
from handlers.start import start_command, premium_command
from handlers.search import handle_search_query
from handlers.callbacks import handle_callback_query
from handlers.admin import (
    handle_admin_upload,
    handle_channel_post,
    admin_help_command,
    stats_command,
    reset_limit_command,
    delete_movie_command,
    get_link_command,
    broadcast_command,
    add_premium_command,
    remove_premium_command,
    plans_command,
    pending_payments_command,
    approve_payment_command,
    reject_payment_command
)
from handlers.payment import (
    handle_user_payment_photo,
    set_admin_group_command,
    handle_chat_member_updated
)


async def on_startup(app) -> None:
    """Run database migration on bot startup."""
    await init_db()
    bot_info = await app.bot.get_me()
    logger.info("==========================================")
    logger.info(f"Bot Online: @{bot_info.username} ({bot_info.first_name})")
    logger.info("Movie Sender Bot ready to accept queries!")
    logger.info("==========================================")

def main() -> None:
    """Entry point for the Telegram Movie Sender Bot."""
    if not BOT_TOKEN or "YOUR_BOT_TOKEN_HERE" in BOT_TOKEN:
        logger.error(
            "\n[!] BOT_TOKEN is missing or still set to default placeholder!\n"
            "    Please open the '.env' file in this folder and paste your bot token from @BotFather.\n"
            "    Example: BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ\n"
        )
        sys.exit(1)

    # Initialize application
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    # User & General Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler(["plan", "premium", "buy"], premium_command))
    
    # Admin Commands
    app.add_handler(CommandHandler("admin", admin_help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("plans", plans_command))
    app.add_handler(CommandHandler(["pending", "pendingpayments"], pending_payments_command))
    app.add_handler(CommandHandler("approve", approve_payment_command))
    app.add_handler(CommandHandler("reject", reject_payment_command))
    app.add_handler(CommandHandler("addpremium", add_premium_command))
    app.add_handler(CommandHandler("removepremium", remove_premium_command))
    app.add_handler(CommandHandler("resetlimit", reset_limit_command))
    app.add_handler(CommandHandler("delete", delete_movie_command))
    app.add_handler(CommandHandler("link", get_link_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler(["setadmingroup", "linkgroup", "id"], set_admin_group_command))

    # Auto-link Private Admin Group when bot is added to group
    app.add_handler(ChatMemberHandler(handle_chat_member_updated, ChatMemberHandler.MY_CHAT_MEMBER))

    # Channel Auto-Indexing Handler (when files posted to channel)
    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL),
            handle_channel_post
        )
    )

    # User Payment Proof Upload Handler (photos and image documents in private chat)
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.PHOTO | (filters.Document.IMAGE)),
            handle_user_payment_photo
        )
    )

    # Direct Media Upload Handler (when admin sends movie file to bot)
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.VIDEO | filters.Document.ALL),
            handle_admin_upload
        )
    )

    # Inline Keyboard Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Text Search Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_query))

    logger.info("Starting bot polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
