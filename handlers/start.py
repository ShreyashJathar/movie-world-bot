from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import add_user, get_movie_by_code, record_user_download
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.delivery import deliver_movie_file
from services.ratelimit import (
    check_daily_limit,
    get_daily_limit_message,
    get_daily_limit_keyboard
)
from handlers.payment import display_storefront
from config import ADMIN_CONTACT_USERNAME

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command and deep links."""
    if not update.effective_user or not update.effective_message:
        return

    user = update.effective_user
    chat = update.effective_chat
    await add_user(user.id, user.username, user.first_name)

    # Check for deep link arguments (e.g. /start file_code)
    args = context.args
    if args and len(args) > 0:
        param = args[0]
        share_code = param.replace("file_", "").strip()
        
        # Check Force-Subscription
        subscribed = await is_user_subscribed(context.bot, user.id)
        if not subscribed:
            await update.effective_message.reply_text(
                text=get_fsub_message(),
                reply_markup=get_fsub_keyboard(callback_data=f"check_fsub:file:{share_code}"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Fetch movie
        movie = await get_movie_by_code(share_code)
        if not movie:
            await update.effective_message.reply_text(
                text="❌ <b>Link Expired:</b> This movie file could not be found or has been removed.",
                parse_mode=ParseMode.HTML
            )
            return

        # Check 1 Movie Per Day Limit (VIP subscribers bypass)
        allowed, hours_left, mins_left = await check_daily_limit(user.id, user.username)
        if not allowed:
            await update.effective_message.reply_text(
                text=get_daily_limit_message(hours_left, mins_left),
                reply_markup=get_daily_limit_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        await update.effective_message.reply_text("⏳ <i>Sending your requested movie file...</i>", parse_mode=ParseMode.HTML)
        success = await deliver_movie_file(context.bot, chat.id, movie)
        if success:
            await record_user_download(user.id, movie["id"])
        return

    # Regular /start: Do NOT send payment plans or QR code automatically
    context.user_data["awaiting_payment_proof"] = False

    name = user.first_name or "there"
    welcome_text = (
        f"👋 <b>Hello {name}!</b>\n\n"
        "🎬 <b>Welcome to Movie World Bot</b>\n"
        "     <b>BY SHREYASH JATHAR 96</b>\n\n"
        "🔍 <b>How to find movies:</b>\n"
        "Just type and send the movie name right here in this chat.\n\n"
        "💡 <b>Examples:</b>\n"
        "• Interstellar\n"
        "• Avengers Endgame 1080p\n"
        "• Dark Knight\n\n"
        "Enjoy your streaming! 🍿"
    )

    welcome_keyboard = [
        [
            InlineKeyboardButton("💎 VIP Subscription / Plans", callback_data="buy_premium"),
            InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")
        ]
    ]

    await update.effective_message.reply_text(
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup(welcome_keyboard),
        parse_mode=ParseMode.HTML
    )

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /buy command to view UPI QR code and pricing."""
    await display_storefront(update, context)

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /plan or /premium command to view VIP pricing and status."""
    await display_storefront(update, context)

