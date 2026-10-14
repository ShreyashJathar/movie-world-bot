import asyncio
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config import ADMIN_CONTACT_USERNAME, FSUB_INVITE_LINK, logger
from database import (
    get_expiring_vip_subscriptions,
    mark_vip_reminded,
    get_expired_vip_subscriptions,
    mark_vip_expired_notified,
    find_pending_movie_requests,
    mark_movie_request_fulfilled
)
from services.fsub import is_user_subscribed

async def check_and_send_vip_reminders(bot: Bot) -> None:
    """
    Checks for subscriptions expiring within 24h and sends friendly renewal reminders.
    Also notifies users whose VIP has expired.
    """
    # 1. Check subscriptions expiring in < 24 hours
    try:
        expiring = await get_expiring_vip_subscriptions(hours_ahead=24)
        for sub in expiring:
            user_id = sub["user_id"]
            name = sub.get("first_name") or "there"
            exp_str = sub["expires_at"]

            reminder_text = (
                f"⏰ <b>VIP Subscription Expiring Soon!</b>\n\n"
                f"Hello <b>{name}</b>, your Movie World VIP membership will expire in "
                f"<b>less than 24 hours</b> (on <code>{exp_str}</code>).\n\n"
                f"🚀 <b>Don't lose your unlimited benefits:</b>\n"
                f"• Unlimited daily movie downloads with zero limits\n"
                f"• High-speed direct storage delivery\n"
                f"• Priority requests to admin\n\n"
                f"👇 <i>Renew your plan now to keep unlimited streaming active without interruption:</i>"
            )

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Renew VIP Subscription", callback_data="buy_premium")],
                [InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")]
            ])

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=reminder_text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent 24h VIP expiry reminder to user {user_id}")
            except TelegramError as e:
                logger.info(f"Could not deliver expiry reminder to user {user_id}: {e}")

            await mark_vip_reminded(user_id)
            await asyncio.sleep(0.05)
    except Exception as e:
        logger.warning(f"Error checking expiring VIP subscriptions: {e}")

    # 2. Check subscriptions that expired today
    try:
        expired = await get_expired_vip_subscriptions()
        for sub in expired:
            user_id = sub["user_id"]
            name = sub.get("first_name") or "there"
            exp_str = sub["expires_at"]

            expired_text = (
                f"⚠️ <b>Your VIP Subscription Has Ended</b>\n\n"
                f"Hello <b>{name}</b>, your VIP subscription expired on <code>{exp_str}</code>.\n\n"
                f"Your account has now returned to the standard free tier (1 movie per day).\n\n"
                f"👇 <i>You can reactivate your VIP access anytime to resume unlimited downloads:</i>"
            )

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Reactivate VIP Access", callback_data="buy_premium")],
                [InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")]
            ])

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=expired_text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent VIP expired notice to user {user_id}")
            except TelegramError as e:
                logger.info(f"Could not deliver expired notice to user {user_id}: {e}")

            await mark_vip_expired_notified(user_id)
            await asyncio.sleep(0.05)
    except Exception as e:
        logger.warning(f"Error checking expired VIP subscriptions: {e}")

async def notify_requesters_of_new_movie(
    bot: Bot,
    movie_name: str,
    share_code: str
) -> None:
    """
    Checks if an uploaded movie matches any user requests in the database.
    Verifies that the user has joined the main movie channel before sending.
    """
    try:
        matches = await find_pending_movie_requests(movie_name)
        if not matches:
            return

        bot_info = await bot.get_me()
        bot_username = bot_info.username

        for req in matches:
            user_id = req["user_id"]
            req_id = req["id"]
            name = req.get("user_name") or "there"

            # Check if user has joined the main movie channel
            is_member = await is_user_subscribed(bot, user_id)

            if is_member:
                # User has joined main channel: send direct download notice
                notice = (
                    f"🎉 <b>Good News {name}!</b>\n\n"
                    f"The movie you requested — 🎬 <b>{movie_name}</b> — has just been uploaded to our library!\n\n"
                    f"💡 <i>VIP members enjoy unlimited instant downloads with zero waiting time!</i>\n\n"
                    f"👇 <i>Tap below to download your movie now:</i>"
                )
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Download Movie Now", url=f"https://t.me/{bot_username}?start=file_{share_code}")],
                    [InlineKeyboardButton("💎 Upgrade to VIP (Unlimited)", url=f"https://t.me/{bot_username}?start=buy")],
                    [InlineKeyboardButton("🔍 Search Other Movies", url=f"https://t.me/{bot_username}")]
                ])
            else:
                # User has NOT joined the main movie channel: require channel join
                join_link = FSUB_INVITE_LINK or f"https://t.me/{bot_username}"
                notice = (
                    f"🎬 <b>Good News {name}!</b>\n\n"
                    f"The movie you previously requested — <b>{movie_name}</b> — has just been uploaded to Movie World!\n\n"
                    f"⚠️ <b>Channel Membership Required:</b>\n"
                    f"You must join our official Movie Channel before downloading.\n\n"
                    f"👇 <i>Join the channel below, then tap Download:</i>"
                )
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Main Movie Channel", url=join_link)],
                    [InlineKeyboardButton("▶️ Download Movie", url=f"https://t.me/{bot_username}?start=file_{share_code}")]
                ])

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=notice,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Notified user {user_id} that requested movie '{movie_name}' is available (channel member: {is_member})")
            except TelegramError as e:
                logger.info(f"Could not deliver movie request notification to user {user_id}: {e}")

            # Mark request as fulfilled so they aren't spammed
            await mark_movie_request_fulfilled(req_id)
            await asyncio.sleep(0.05)
    except Exception as e:
        logger.warning(f"Error in notify_requesters_of_new_movie: {e}")

async def send_daily_report_to_admins(bot: Bot) -> None:
    """Compile and broadcast daily analytics report to ADMIN_IDS and ADMIN_GROUP_ID."""
    try:
        from database import get_daily_analytics, get_effective_admin_group_id, get_admin_user_ids
        from handlers.admin import format_daily_report, get_daily_report_keyboard
        
        data = await get_daily_analytics()
        report_text = "📢 <b>AUTOMATIC DAILY SUMMARY RECAP</b>\n\n" + format_daily_report(data)
        markup = get_daily_report_keyboard()

        admin_group_id = await get_effective_admin_group_id()
        admin_ids = await get_admin_user_ids()

        targets = set()
        if admin_group_id:
            targets.add(admin_group_id)
        for aid in admin_ids:
            targets.add(aid)

        for target_id in targets:
            try:
                await bot.send_message(
                    chat_id=target_id,
                    text=report_text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.info(f"Could not send automatic daily report to {target_id}: {e}")
    except Exception as e:
        logger.warning(f"Error in send_daily_report_to_admins: {e}")
