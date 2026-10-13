from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from database import (
    add_user,
    get_movie_by_code,
    get_movie_by_id,
    record_user_download,
    add_referral,
    get_referral_stats,
    consume_user_bonus_download,
    complete_verification,
    get_user_downloads_today
)
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.delivery import deliver_movie_file
from services.ratelimit import (
    check_daily_limit,
    get_daily_limit_message,
    get_daily_limit_keyboard
)
from handlers.payment import display_storefront
from config import ADMIN_CONTACT_USERNAME, VERIFY_EXPIRE_HOURS, DAILY_MOVIE_LIMIT

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command, deep links (file, verify, referral)."""
    if not update.effective_user or not update.effective_message:
        return

    user = update.effective_user
    chat = update.effective_chat
    await add_user(user.id, user.username, user.first_name)

    # Check for deep link arguments
    args = context.args
    if args and len(args) > 0:
        param = args[0].strip()

        # 1. VIRAL REFERRAL LINK: ref_<user_id>
        if param.startswith("ref_"):
            ref_str = param.replace("ref_", "").strip()
            if ref_str.isdigit():
                referrer_id = int(ref_str)
                success, reason, total = await add_referral(referrer_id, user.id)
                if success:
                    try:
                        milestone_note = ""
                        if total % 3 == 0:
                            milestone_note = "\n🌟 <b>Milestone Unlocked:</b> You received <b>3 Days of Free VIP Membership</b>!"

                        ref_notice = (
                            f"🎉 <b>New Referral Joined!</b>\n\n"
                            f"Your friend <b>{user.first_name}</b> just joined Movie World using your invite link!\n"
                            f"• Total Referrals: <b>{total}</b>\n"
                            f"• Reward: <b>+1 Extra Movie Download Pass</b> added to your account!{milestone_note}\n\n"
                            f"Keep sharing to unlock more free VIP days!"
                        )
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=ref_notice,
                            parse_mode=ParseMode.HTML
                        )
                    except TelegramError:
                        pass

        # 2. SHORTLINK VERIFICATION REDIRECT: verify_<token>
        elif param.startswith("verify_"):
            token = param.replace("verify_", "").strip()
            is_valid, target_movie_id, exp_str = await complete_verification(token, hours=VERIFY_EXPIRE_HOURS)

            if is_valid:
                success_msg = (
                    "✅ <b>Shortlink Verification Successful!</b>\n\n"
                    f"You have unlocked <b>Unlimited Movie Downloads</b> for the next <b>{VERIFY_EXPIRE_HOURS} Hours</b>!\n"
                    f"⏰ <b>Valid Until:</b> <code>{exp_str}</code>\n\n"
                    "Enjoy your streaming without limits! 🍿"
                )
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")]
                ])
                await update.effective_message.reply_text(success_msg, reply_markup=markup, parse_mode=ParseMode.HTML)

                # If user was attempting to download a specific movie, deliver it now!
                if target_movie_id:
                    movie = await get_movie_by_id(target_movie_id)
                    if movie:
                        await update.effective_message.reply_text("⏳ <i>Sending your requested movie file...</i>", parse_mode=ParseMode.HTML)
                        delivered = await deliver_movie_file(context.bot, chat.id, movie)
                        if delivered:
                            await record_user_download(user.id, movie["id"])
                return
            else:
                await update.effective_message.reply_text(
                    "❌ <b>Verification Session Expired or Invalid!</b>\nPlease tap below to generate a new verification link.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔓 Get New Verification Link", callback_data="get_shortlink_pass")]
                    ]),
                    parse_mode=ParseMode.HTML
                )
                return

        # 3. MOVIE FILE DEEP LINK: file_<share_code>
        elif param.startswith("file_") or len(param) >= 6:
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

            # Check Daily Limit (VIP, Shortlink Pass, or Referral Bonus bypass)
            allowed, hours_left, mins_left = await check_daily_limit(user.id, user.username)
            if not allowed:
                await update.effective_message.reply_text(
                    text=get_daily_limit_message(hours_left, mins_left),
                    reply_markup=get_daily_limit_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                return

            # If user has already reached standard daily limit but was allowed via referral bonus pass:
            count = await get_user_downloads_today(user.id)
            if count >= DAILY_MOVIE_LIMIT:
                await consume_user_bonus_download(user.id)

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
            InlineKeyboardButton("🎁 Invite & Earn Free VIP", callback_data="show_referral_info")
        ],
        [
            InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")
        ]
    ]

    await update.effective_message.reply_text(
        text=welcome_text,
        reply_markup=InlineKeyboardMarkup(welcome_keyboard),
        parse_mode=ParseMode.HTML
    )

async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /invite and /refer commands to view personal referral link & stats."""
    user = update.effective_user
    if not user or not update.effective_message:
        return

    bot_info = await context.bot.get_me()
    stats = await get_referral_stats(user.id)
    total_refs = stats["total_referrals"]
    bonus_passes = stats["bonus_downloads"]

    invite_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    share_text = quote(f"🎬 Watch & download HD movies for free on Movie World!\nJoin now: {invite_link}")
    share_url = f"https://t.me/share/url?url={invite_link}&text={share_text}"

    text = (
        "🎁 <b>Invite Friends & Earn Free Rewards!</b>\n\n"
        "Share your personal invite link with friends or Telegram groups:\n"
        f"🔗 <b>Your Personal Invite Link:</b>\n"
        f"<code>{invite_link}</code>\n\n"
        "💎 <b>Rewards You Earn:</b>\n"
        "• <b>Every 1 Friend:</b> +1 Extra Movie Download Pass today!\n"
        "• <b>Every 3 Friends:</b> <b>🌟 3 Days Free VIP Membership</b> (Unlimited downloads)!\n\n"
        "📊 <b>Your Referral Statistics:</b>\n"
        f"• Friends Joined: <b>{total_refs}</b>\n"
        f"• Extra Download Passes Available: <b>{bonus_passes}</b>\n\n"
        "👇 <i>Tap below to share directly with your friends:</i>"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Share with Friends", url=share_url)],
        [
            InlineKeyboardButton("💎 View VIP Plans", callback_data="buy_premium"),
            InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")
        ]
    ])

    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /buy command to view UPI QR code and pricing."""
    await display_storefront(update, context)

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /plan or /premium command to view VIP pricing and status."""
    await display_storefront(update, context)
