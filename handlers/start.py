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
    get_user_downloads_today,
    get_user_total_downloads,
    check_and_reward_referral,
    is_user_premium
)
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.delivery import deliver_movie_file
from services.ratelimit import (
    check_user_download_limit,
    get_limit_reached_message,
    get_limit_reached_keyboard
)
from handlers.payment import display_storefront
from config import ADMIN_CONTACT_USERNAME, FREE_MOVIE_LIMIT

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command, deep links (file, referral)."""
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
                        ref_notice = (
                            "👋 <b>A Friend Joined via Your Link!</b>\n\n"
                            f"Your friend <b>{user.first_name}</b> just joined Movie World!\n\n"
                            "⏳ <b>Verification Status: Pending</b>\n"
                            "To prevent fake accounts, your friend must <b>download at least 1 movie</b> (start using the bot) before your reward is unlocked.\n\n"
                            "🎁 <b>As soon as they download a movie:</b>\n"
                            "• You get <b>+1 Extra Free Movie Pass</b>!\n"
                            "• 🏆 Invite 10 active friends to unlock a <b>🌟 1-Week Free VIP Pass</b>!"
                        )
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=ref_notice,
                            parse_mode=ParseMode.HTML
                        )
                    except TelegramError:
                        pass

        # 2. MOVIE FILE DEEP LINK: file_<share_code>
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

            # Check Movie Limit (2 Free Movies Lifetime, VIP, or Active Referral Bonus)
            allowed, total_used, bonus_left = await check_user_download_limit(user.id, user.username)
            if not allowed:
                await update.effective_message.reply_text(
                    text=get_limit_reached_message(total_used),
                    reply_markup=get_limit_reached_keyboard(),
                    parse_mode=ParseMode.HTML
                )
                return

            await update.effective_message.reply_text("⏳ <i>Sending your requested movie file...</i>", parse_mode=ParseMode.HTML)
            success = await deliver_movie_file(context.bot, chat.id, movie)
            if success:
                await record_user_download(user.id, movie["id"])
                total_after = await get_user_total_downloads(user.id)
                if total_after > FREE_MOVIE_LIMIT:
                    await consume_user_bonus_download(user.id)

                # Check if this user was invited by someone and reward the referrer now that they used the bot!
                reward_info = await check_and_reward_referral(user.id)
                if reward_info:
                    referrer_id = reward_info["referrer_id"]
                    active_count = reward_info["active_count"]
                    try:
                        if reward_info["is_milestone_10"]:
                            ref_notice = (
                                "🏆 <b>MILESTONE UNLOCKED: 1-WEEK VIP PASS!</b>\n\n"
                                "10 of your invited friends are actively using Movie World!\n"
                                "🌟 You have been awarded <b>7 Days of Free VIP Membership</b> (Unlimited Downloads)!\n\n"
                                "Enjoy your movies without any limits! 🍿"
                            )
                        else:
                            ref_notice = (
                                "🎉 <b>Active Friend Verified!</b>\n\n"
                                "Your invited friend just downloaded a movie and is actively using Movie World!\n"
                                "🎁 You received <b>+1 Extra Movie Download Pass</b>!\n\n"
                                f"📊 Active Friends: <b>{active_count}/10</b> towards a <b>1-Week Free VIP Pass</b>!"
                            )
                        await context.bot.send_message(chat_id=referrer_id, text=ref_notice, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass

                # Force/prompt user to take VIP subscription with conversion notices
                if not await is_user_premium(user.id):
                    if total_after == 1:
                        notice = (
                            "🍿 <b>Enjoy your movie!</b>\n"
                            f"ℹ️ <i>Notice: You have used 1 of your {FREE_MOVIE_LIMIT} Free Welcome Movies.</i>\n\n"
                            "⚡ <b>Want unlimited downloads without limits or ads?</b>\n"
                            "👉 Tap /vip to view our VIP passes (starting at only ₹39)!"
                        )
                        await update.effective_message.reply_text(notice, parse_mode=ParseMode.HTML)
                    elif total_after == FREE_MOVIE_LIMIT:
                        notice = (
                            "🍿 <b>Enjoy your movie!</b>\n"
                            f"⚠️ <b>You have now used all {FREE_MOVIE_LIMIT} of your Free Welcome Movies!</b>\n\n"
                            "🔥 <b>Unlock Unlimited HD Downloads Now:</b>\n"
                            "• No waiting, zero download limits\n"
                            "• Direct instant download on all new releases\n"
                            "• Full VIP priority access\n\n"
                            "👉 Tap below to upgrade to VIP or invite friends to earn free passes!"
                        )
                        markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton("💎 Upgrade to VIP (Unlimited)", callback_data="buy_premium")],
                            [InlineKeyboardButton("🎁 Invite Friends", callback_data="show_referral_info")]
                        ])
                        await update.effective_message.reply_text(notice, reply_markup=markup, parse_mode=ParseMode.HTML)
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

    # Prompt user to subscribe if they already exhausted free quota
    used_count = await get_user_total_downloads(user.id)
    is_vip = await is_user_premium(user.id)
    if not is_vip and used_count >= FREE_MOVIE_LIMIT:
        welcome_text += (
            f"\n\n🔒 <b>Notice:</b> You have used your {FREE_MOVIE_LIMIT} free welcome movies.\n"
            "💎 Upgrade to <b>VIP</b> for unlimited downloads or invite friends to earn free passes!"
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
    active_refs = stats.get("active_referrals", 0)
    pending_refs = stats.get("pending_referrals", max(0, total_refs - active_refs))
    bonus_passes = stats["bonus_downloads"]
    progress_to_vip = active_refs % 10

    invite_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    share_text = quote(f"🎬 Watch & download HD movies for free on Movie World!\nJoin now: {invite_link}")
    share_url = f"https://t.me/share/url?url={invite_link}&text={share_text}"

    text = (
        "🎁 <b>Invite Friends & Earn Free VIP!</b>\n\n"
        "Share your personal invite link with friends or in Telegram groups:\n"
        f"🔗 <b>Your Personal Invite Link:</b>\n"
        f"<code>{invite_link}</code>\n\n"
        "💎 <b>How It Works:</b>\n"
        "• Friends must <b>use the bot (download at least 1 movie)</b> to count as active.\n"
        "• 🎟️ <b>Each Active Friend:</b> +1 Extra Free Movie Pass!\n"
        "• 🏆 <b>Invite 10 Active Friends:</b> <b>🌟 1-Week Free VIP Pass (7 Days Unlimited)!</b>\n\n"
        "📊 <b>Your Referral Status:</b>\n"
        f"• 👥 Active Friends (Using Bot): <b>{active_refs}</b>\n"
        f"• ⏳ Pending Friends (Joined, not used yet): <b>{pending_refs}</b>\n"
        f"• 🎟️ Available Bonus Passes: <b>{bonus_passes}</b>\n"
        f"• 🎯 Progress to 1-Week VIP: <b>{progress_to_vip}/10</b> active friends\n\n"
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
