import asyncio
from typing import Optional, Tuple
from telegram import Update, Message
from telegram.constants import ParseMode, ChatType
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from config import is_admin, STORAGE_CHANNEL_ID, SUBSCRIPTION_PLANS, ADMIN_CONTACT_USERNAME, logger
from database import (
    save_movie,
    get_movie_by_id,
    delete_movie,
    get_total_movies,
    get_total_users,
    get_all_user_ids,
    get_total_downloads_today,
    reset_user_downloads,
    add_user_subscription,
    remove_user_subscription,
    get_total_premium_users,
    get_pending_payment_requests,
    get_payment_request,
    update_payment_request_status
)
from services.metadata import format_file_size


def extract_media_info(message: Message) -> Optional[Tuple[str, str, str, int, Optional[str], Optional[str]]]:
    """
    Extracts file_id, file_unique_id, file_name, file_size, caption, mime_type from a message.
    Returns None if message has no video/document.
    """
    if message.video:
        file = message.video
        file_name = file.file_name or f"Video_{file.file_unique_id[:6]}.mp4"
        return (
            file.file_id,
            file.file_unique_id,
            file_name,
            file.file_size or 0,
            message.caption,
            file.mime_type or "video/mp4"
        )
    elif message.document:
        doc = message.document
        file_name = doc.file_name or f"File_{doc.file_unique_id[:6]}"
        return (
            doc.file_id,
            doc.file_unique_id,
            file_name,
            doc.file_size or 0,
            message.caption,
            doc.mime_type or "application/octet-stream"
        )
    return None

async def handle_admin_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct video/document uploads from admins in private chat."""
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not is_admin(user.id, user.username):
        return

    media_info = extract_media_info(message)
    if not media_info:
        return

    file_id, file_unique_id, file_name, file_size, caption, mime_type = media_info

    movie_id, share_code, is_new = await save_movie(
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        file_size=file_size,
        caption=caption,
        mime_type=mime_type,
        message_id=message.message_id,
        channel_id=None
    )

    bot_info = await context.bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=file_{share_code}"
    size_str = format_file_size(file_size)

    status_tag = "✅ <b>New Movie Indexed!</b>" if is_new else "ℹ️ <b>Movie Already Exists (Link Retrieved):</b>"

    response = (
        f"{status_tag}\n\n"
        f"📁 <b>Title:</b> <code>{file_name}</code>\n"
        f"📦 <b>Size:</b> <code>{size_str}</code>\n"
        f"🆔 <b>Database ID:</b> <code>{movie_id}</code>\n\n"
        f"🔗 <b>Shareable Link:</b>\n"
        f"<code>{share_link}</code>\n\n"
        f"💡 <i>Users can also search this movie by typing its title in chat.</i>"
    )

    await message.reply_text(response, parse_mode=ParseMode.HTML)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-index movies when files are posted/forwarded to the storage channel."""
    message = update.channel_post
    if not message:
        return

    # Check if this channel matches storage channel
    if STORAGE_CHANNEL_ID and message.chat.id != STORAGE_CHANNEL_ID:
        return

    media_info = extract_media_info(message)
    if not media_info:
        return

    file_id, file_unique_id, file_name, file_size, caption, mime_type = media_info

    movie_id, share_code, is_new = await save_movie(
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        file_size=file_size,
        caption=caption,
        mime_type=mime_type,
        message_id=message.message_id,
        channel_id=message.chat.id
    )

    if is_new:
        logger.info(f"Auto-indexed new channel post '{file_name}' (ID: {movie_id}, Code: {share_code})")

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin panel commands."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    text = (
        "👑 <b>Admin Control Panel</b>\n\n"
        "<b>Available Commands:</b>\n"
        "• <code>/stats</code> - View bot metrics & VIP members\n"
        "• <code>/plans</code> - View active VIP subscription plans & pricing\n"
        "• <code>/pending</code> - View pending VIP payment submissions\n"
        "• <code>/approve &lt;request_id&gt;</code> - Manually approve a payment request\n"
        "• <code>/reject &lt;request_id&gt;</code> - Manually reject a payment request\n"
        "• <code>/addpremium &lt;user_id&gt; [days]</code> - Grant VIP subscription (default: 30 days)\n"
        "• <code>/removepremium &lt;user_id&gt;</code> - Revoke VIP subscription\n"
        "• <code>/resetlimit [user_id]</code> - Reset daily limit for user or self\n"
        "• <code>/delete &lt;id&gt;</code> - Delete a movie from the database\n"
        "• <code>/link &lt;id&gt;</code> - Generate share link for a movie ID\n"
        "• <code>/setadmingroup</code> - Link private group (https://t.me/+lgLJDd4mfZw5M2U1) for payment approvals\n"
        "• <code>/broadcast &lt;message&gt;</code> - Broadcast text to all users\n\n"
        "<b>How to add movies:</b>\n"
        "1. Simply send or forward any video / file directly to this bot.\n"
        "2. Or add this bot as Admin in your Storage Channel — it will automatically index every movie posted there!"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed bot stats to admin."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        await update.effective_message.reply_text("🔒 <b>Access Denied:</b> Only administrators can view bot statistics.", parse_mode=ParseMode.HTML)
        return

    total_movies = await get_total_movies()
    total_users = await get_total_users()
    today_downloads = await get_total_downloads_today()
    premium_users = await get_total_premium_users()

    text = (
        "📊 <b>Detailed Bot Statistics</b>\n\n"
        f"👥 Total Registered Users: <b>{total_users}</b>\n"
        f"🎬 Total Indexed Movies: <b>{total_movies}</b>\n"
        f"👑 Active VIP Subscribers: <b>{premium_users}</b>\n"
        f"📥 Downloads in Last 24h: <b>{today_downloads}</b>\n"
        f"📁 Database Mode: <b>SQLite (Async)</b>\n"
        f"⚙️ Status: <b>Online & Running</b>"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Grant or extend VIP subscription: /addpremium <user_id> [days=30]"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: <code>/addpremium &lt;user_id&gt; [days]</code>\n"
            "Example: <code>/addpremium 123456789 30</code>",
            parse_mode=ParseMode.HTML
        )
        return

    target_id = int(context.args[0])
    days = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 30

    expiry_str = await add_user_subscription(target_id, days)
    await update.effective_message.reply_text(
        f"✅ <b>VIP Activated!</b>\n\n"
        f"👤 User: <code>{target_id}</code>\n"
        f"⏳ Granted: <b>{days} days</b>\n"
        f"⏰ Valid Until: <code>{expiry_str}</code>",
        parse_mode=ParseMode.HTML
    )

    # Attempt to notify the user
    try:
        notify_text = (
            "🎉 <b>VIP Premium Subscription Activated!</b>\n\n"
            f"You now have <b>UNLIMITED MOVIE DOWNLOADS</b> for <b>{days} days</b>!\n"
            f"⏰ Valid Until: <code>{expiry_str}</code>\n\n"
            "Enjoy streaming without daily limits! 🍿"
        )
        await context.bot.send_message(chat_id=target_id, text=notify_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.info(f"Could not notify user {target_id}: {e}")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Revoke VIP subscription: /removepremium <user_id>"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: <code>/removepremium &lt;user_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    target_id = int(context.args[0])
    success = await remove_user_subscription(target_id)
    if success:
        await update.effective_message.reply_text(f"✅ VIP subscription removed for <code>{target_id}</code>.", parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(f"❌ User <code>{target_id}</code> had no active subscription.", parse_mode=ParseMode.HTML)

async def reset_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the daily download limit for a user or self."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    target_id = user.id
    if context.args and context.args[0].isdigit():
        target_id = int(context.args[0])

    await reset_user_downloads(target_id)
    await update.effective_message.reply_text(
        f"✅ Daily download limit reset for user <code>{target_id}</code>.",
        parse_mode=ParseMode.HTML
    )

async def delete_movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a movie from database by ID."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: <code>/delete &lt;movie_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    movie_id = int(context.args[0])
    success = await delete_movie(movie_id)
    if success:
        await update.effective_message.reply_text(f"✅ Movie ID <code>{movie_id}</code> has been removed from database.", parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(f"❌ Movie ID <code>{movie_id}</code> was not found.", parse_mode=ParseMode.HTML)

async def get_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get shareable link by movie ID."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: <code>/link &lt;movie_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    movie_id = int(context.args[0])
    movie = await get_movie_by_id(movie_id)
    if not movie:
        await update.effective_message.reply_text(f"❌ Movie ID <code>{movie_id}</code> not found.", parse_mode=ParseMode.HTML)
        return

    bot_info = await context.bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start=file_{movie['share_code']}"
    size_str = format_file_size(movie.get("file_size", 0))

    response = (
        f"🎬 <b>{movie['file_name']}</b>\n"
        f"📦 Size: <code>{size_str}</code>\n"
        f"🔗 Link: <code>{share_link}</code>"
    )
    await update.effective_message.reply_text(response, parse_mode=ParseMode.HTML)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast an announcement message to all users."""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Usage: <code>/broadcast Your message here...</code>\n"
            "Or reply to a message with <code>/broadcast</code>",
            parse_mode=ParseMode.HTML
        )
        return

    reply_to = update.effective_message.reply_to_message
    broadcast_text = reply_to.text if reply_to and reply_to.text else " ".join(context.args)

    user_ids = await get_all_user_ids()
    total = len(user_ids)
    if total == 0:
        await update.effective_message.reply_text("No registered users to broadcast to.")
        return

    status_msg = await update.effective_message.reply_text(f"📢 Starting broadcast to {total} users...")

    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_text, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)  # Telegram rate limit compliance
        except TelegramError:
            failed += 1

    summary = (
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Delivered: <b>{sent}</b>\n"
        f"❌ Failed/Blocked: <b>{failed}</b>\n"
        f"👥 Total targeted: <b>{total}</b>"
    )
    await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current VIP plans configuration: /plans"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    text = "💎 <b>Configured VIP Subscription Plans:</b>\n\n"
    for p in SUBSCRIPTION_PLANS:
        text += (
            f"• {p['badge']} <b>{p['name']}</b> (ID: <code>{p['id']}</code>)\n"
            f"   ⏳ Duration: <b>{p['days']} Days</b>\n"
            f"   💰 Price: <b>{p['currency']}{p['price']}</b>\n"
            f"   📝 Info: {p['description']}\n\n"
        )
    text += f"💡 <i>Users can view and purchase these via /plan or VIP Plans button.</i>"
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

async def pending_payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View all pending payment requests: /pending"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    pending = await get_pending_payment_requests()
    if not pending:
        await update.effective_message.reply_text(
            "✅ <b>No pending payment submissions!</b>\nAll payment requests have been processed.",
            parse_mode=ParseMode.HTML
        )
        return

    text = f"📋 <b>Pending Payment Submissions ({len(pending)}):</b>\n\n"
    for req in pending[:10]:
        user_mention = f"@{req['user_handle']}" if req['user_handle'] else f"User {req['user_id']}"
        text += (
            f"🆔 <b>Request #{req['id']}</b>\n"
            f"👤 User: {req['user_name']} ({user_mention})\n"
            f"📦 Plan: <b>{req['plan_name']}</b> ({req['plan_days']}d) — ₹{req['amount']}\n"
            f"📝 Note: {req['utr_or_note'] or 'None'}\n"
            f"⏰ Time: <code>{req['created_at']}</code>\n"
            f"👉 Approve: <code>/approve {req['id']}</code> | Reject: <code>/reject {req['id']}</code>\n\n"
        )

    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

async def approve_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually approve a payment request: /approve <request_id>"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: <code>/approve &lt;request_id&gt;</code>\nExample: <code>/approve 1</code>",
            parse_mode=ParseMode.HTML
        )
        return

    req_id = int(context.args[0])
    req = await get_payment_request(req_id)
    if not req:
        await update.effective_message.reply_text(f"❌ Payment request #{req_id} not found.")
        return

    if req["status"] != "PENDING":
        await update.effective_message.reply_text(f"ℹ️ Request #{req_id} has already been {req['status']}.")
        return

    expiry_str = await add_user_subscription(req["user_id"], req["plan_days"])
    await update_payment_request_status(req_id, "APPROVED")

    await update.effective_message.reply_text(
        f"✅ <b>Request #{req_id} Approved!</b>\n\n"
        f"👤 User: <code>{req['user_id']}</code>\n"
        f"📦 Plan: <b>{req['plan_name']}</b> ({req['plan_days']} Days)\n"
        f"⏰ New Expiry: <code>{expiry_str}</code>",
        parse_mode=ParseMode.HTML
    )

    # Notify user (POST-VERIFICATION ACTION: IF ADMIN APPROVES)
    try:
        user_notify_text = (
            f"🎉 <b>Congratulations! Your payment has been approved and verified!</b>\n\n"
            f"📦 <b>Plan:</b> <b>{req['plan_name']}</b> ({req['plan_days']} Days)\n"
            f"🚀 <b>Perks Unlocked:</b>\n"
            f"• <b>UNLIMITED Movie Downloads</b> with ZERO daily limits\n"
            f"• High-speed direct storage delivery\n"
            f"• Priority requests to admin\n\n"
            f"⏰ <b>VIP Valid Until:</b> <code>{expiry_str}</code>\n\n"
            f"🍿 <i>Enjoy your unlimited streaming on Movie World! Tap below to search:</i>"
        )
        await context.bot.send_message(chat_id=req["user_id"], text=user_notify_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"Could not notify user {req['user_id']}: {e}")

async def reject_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually reject a payment request: /reject <request_id>"""
    user = update.effective_user
    if not user or not is_admin(user.id, user.username):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: <code>/reject &lt;request_id&gt;</code>\nExample: <code>/reject 1</code>",
            parse_mode=ParseMode.HTML
        )
        return

    req_id = int(context.args[0])
    req = await get_payment_request(req_id)
    if not req:
        await update.effective_message.reply_text(f"❌ Payment request #{req_id} not found.")
        return

    if req["status"] != "PENDING":
        await update.effective_message.reply_text(f"ℹ️ Request #{req_id} has already been {req['status']}.")
        return

    await update_payment_request_status(req_id, "REJECTED")
    await update.effective_message.reply_text(f"❌ <b>Request #{req_id} has been Rejected.</b>", parse_mode=ParseMode.HTML)

    # Notify user (POST-VERIFICATION ACTION: IF ADMIN REJECTS)
    try:
        user_notify_text = (
            "Verification Failed. We could not match this proof with our bank statement records. "
            "Please contact support if you believe this is an error."
        )
        await context.bot.send_message(chat_id=req["user_id"], text=user_notify_text)
    except Exception as e:
        logger.warning(f"Could not notify user {req['user_id']}: {e}")

