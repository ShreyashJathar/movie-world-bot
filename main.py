import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, logger
from database import init_db

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Movie World Bot is running!")

    def log_message(self, format, *args):
        pass  # Suppress HTTP access noise in logs

def run_health_server():
    port_str = os.getenv("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Health check HTTP server listening on port {port} for Render/Cloud")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Could not start health check HTTP server: {e}")
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
    reject_payment_command,
    requests_command
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

    # Start background health server if PORT is set (Render/Cloud deployment)
    threading.Thread(target=run_health_server, daemon=True).start()

    # Robust HTTP connection request with higher timeouts
    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )

    # Initialize application
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).post_init(on_startup).build()

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
    app.add_handler(CommandHandler(["requests", "movierequests"], requests_command))
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
    try:
        app.run_polling(drop_pending_updates=True, bootstrap_retries=10)
    except Exception as e:
        logger.error(f"Fatal polling exception: {e}")

if __name__ == "__main__":
    main()
