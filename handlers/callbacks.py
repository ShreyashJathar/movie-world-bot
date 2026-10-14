import asyncio
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import (
    get_movie_by_id,
    get_movie_by_code,
    search_movies,
    get_total_movies,
    get_total_users,
    record_user_download,
    get_referral_stats,
    consume_user_bonus_download,
    get_user_downloads_today,
    get_user_total_downloads,
    check_and_reward_referral,
    is_user_premium,
    get_daily_analytics,
    get_search_history_today,
    get_active_users_today,
    get_new_users_today,
    update_user_activity
)
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.delivery import deliver_movie_file
from services.ratelimit import (
    check_user_download_limit,
    get_limit_reached_message,
    get_limit_reached_keyboard
)
from handlers.search import build_search_keyboard, PER_PAGE
from handlers.payment import (
    display_storefront,
    handle_plan_selection,
    handle_payment_approval,
    handle_payment_rejection
)
from handlers.admin import format_daily_report, get_daily_report_keyboard
from config import is_admin, FREE_MOVIE_LIMIT, logger

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline button clicks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    user = update.effective_user
    if user:
        asyncio.create_task(update_user_activity(user.id, user.username, user.first_name))

    # No-op button
    if data == "noop":
        await query.answer()
        return

    # Help search button
    if data == "help_search":
        context.user_data["awaiting_payment_proof"] = False
        help_text = (
            "💡 <b>Search Tips & Tricks:</b>\n\n"
            "1. <b>Simple is better:</b> Just type the movie name (e.g. <code>Interstellar</code>).\n"
            "2. <b>Specific resolutions:</b> You can search with quality like <code>720p</code> or <code>1080p</code>.\n"
            "3. <b>Multi-word titles:</b> Punctuation doesn't matter (e.g. <code>Spider Man</code> matches <code>Spider-Man</code>).\n"
            "4. <b>Saved Messages:</b> Always forward the sent movie to your Telegram 'Saved Messages' before the auto-delete timer expires!"
        )
        await query.answer()
        await query.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return

    # Stats button (Admin only)
    if data == "show_stats":
        if not is_admin(user.id, user.username):
            await query.answer("🔒 Only administrators can view bot statistics.", show_alert=True)
            return

        total_movies = await get_total_movies()
        total_users = await get_total_users()
        stats_text = (
            f"📊 <b>Bot Statistics (Admin Only)</b>\n\n"
            f"🎬 Total Movies Indexed: <b>{total_movies}</b>\n"
            f"👥 Total Users: <b>{total_users}</b>\n\n"
            f"⚡ Powered by High-Speed Telegram Delivery"
        )
        await query.answer()
        await query.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
        return

    # Daily Admin Report Callbacks (Admin only)
    if data.startswith("daily_"):
        if not is_admin(user.id, user.username):
            await query.answer("🔒 Only administrators can access daily analytics.", show_alert=True)
            return

        await query.answer()
        if data in ["daily_refresh", "daily_back"]:
            data_report = await get_daily_analytics()
            text = format_daily_report(data_report)
            markup = get_daily_report_keyboard()
            try:
                await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return

        if data == "daily_searches":
            searches = await get_search_history_today(limit=40)
            if not searches:
                msg = "🔍 <b>Today's Search History</b>\n\n<i>No user searches recorded yet today.</i>"
            else:
                msg_lines = [f"🔍 <b>Today's Search History ({len(searches)} queries)</b>\n"]
                for s in searches:
                    u_label = f"@{s['current_username']}" if s.get('current_username') else (s.get('user_name') or f"ID:{s['user_id']}")
                    res = s.get('results_count', 0)
                    time_str = s['searched_at'].split(" ")[1][:5] if " " in s['searched_at'] else ""
                    time_tag = f"[{time_str}] " if time_str else ""
                    status = f"✅ ({res})" if res > 0 else "❌ (not found)"
                    msg_lines.append(f"• {time_tag}<b>{u_label}</b>: \"<code>{s['query']}</code>\" → {status}")
                msg = "\n".join(msg_lines)

            back_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Summary", callback_data="daily_back")]
            ])
            try:
                await query.edit_message_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            except Exception:
                await query.message.reply_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            return

        if data == "daily_active":
            active_users = await get_active_users_today()
            if not active_users:
                msg = "👥 <b>Active Users Today</b>\n\n<i>No users active today yet.</i>"
            else:
                msg_lines = [f"👥 <b>Active Users Today ({len(active_users)} users)</b>\n"]
                for u in active_users[:35]:
                    handle = f"@{u['username']}" if u.get('username') else f"ID: <code>{u['user_id']}</code>"
                    name = u.get('first_name') or "User"
                    s_c = u.get('search_count', 0)
                    d_c = u.get('download_count', 0)
                    msg_lines.append(f"• <b>{name}</b> ({handle}) — 🔍 {s_c} | 📥 {d_c}")
                msg = "\n".join(msg_lines)

            back_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Summary", callback_data="daily_back")]
            ])
            try:
                await query.edit_message_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            except Exception:
                await query.message.reply_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            return

        if data == "daily_new":
            new_users = await get_new_users_today()
            if not new_users:
                msg = "🆕 <b>New Users Joined Today</b>\n\n<i>No new users connected today yet.</i>"
            else:
                msg_lines = [f"🆕 <b>New Users Joined Today ({len(new_users)} users)</b>\n"]
                for u in new_users[:35]:
                    handle = f"@{u['username']}" if u.get('username') else f"ID: <code>{u['user_id']}</code>"
                    name = u.get('first_name') or "User"
                    joined_time = u['joined_at'].split(" ")[1][:5] if " " in u['joined_at'] else ""
                    time_tag = f"[{joined_time}] " if joined_time else ""
                    msg_lines.append(f"• {time_tag}<b>{name}</b> ({handle})")
                msg = "\n".join(msg_lines)

            back_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Summary", callback_data="daily_back")]
            ])
            try:
                await query.edit_message_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            except Exception:
                await query.message.reply_text(msg, reply_markup=back_markup, parse_mode=ParseMode.HTML)
            return

    # Buy / Premium storefront button
    if data in ["buy_premium", "buy"]:
        await query.answer()
        await display_storefront(update, context)
        return

    # Show Personal Referral Link & Stats
    if data == "show_referral_info":
        await query.answer()
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

        ref_card = (
            "🎁 <b>Invite Friends & Earn Free VIP!</b>\n\n"
            "Share your personal invite link with your friends or in Telegram groups:\n"
            f"🔗 <b>Your Personal Invite Link:</b>\n"
            f"<code>{invite_link}</code>\n\n"
            "💎 <b>How It Works:</b>\n"
            "• Your friends must <b>use the bot (download at least 1 movie)</b> to count as active.\n"
            "• 🎟️ <b>Each Active Friend:</b> +1 Extra Free Movie Pass!\n"
            "• 🏆 <b>Invite 10 Active Friends:</b> <b>🌟 1-Week Free VIP Pass (7 Days Unlimited)!</b>\n\n"
            "📊 <b>Your Referral Status:</b>\n"
            f"• 👥 Active Friends (Using Bot): <b>{active_refs}</b>\n"
            f"• ⏳ Pending Friends (Joined, not used yet): <b>{pending_refs}</b>\n"
            f"• 🎟️ Available Bonus Passes: <b>{bonus_passes}</b>\n"
            f"• 🎯 Progress to 1-Week VIP: <b>{progress_to_vip}/10</b> active friends\n\n"
            "👇 <i>Tap below to share your link directly with friends:</i>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📲 Share with Friends", url=share_url)],
            [InlineKeyboardButton("💎 View VIP Plans", callback_data="buy_premium")],
            [InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")]
        ])
        await query.message.reply_text(ref_card, reply_markup=markup, parse_mode=ParseMode.HTML)
        return

    # Plan Selection: select_plan:<plan_id>
    if data.startswith("select_plan:"):
        await handle_plan_selection(update, context)
        return

    # Plan Confirmation fallback: confirm_plan:<plan_id>
    if data.startswith("confirm_plan:"):
        await query.answer("Please send your 12-digit UTR or payment screenshot directly in chat.", show_alert=True)
        return

    # Admin Payment Approval: pay_appr:<req_id>
    if data.startswith("pay_appr:"):
        await handle_payment_approval(update, context)
        return

    # Admin Payment Rejection: pay_rej:<req_id>
    if data.startswith("pay_rej:"):
        await handle_payment_rejection(update, context)
        return

    # FSUB Verification button: check_fsub:<type>:<param>
    if data.startswith("check_fsub:"):
        parts = data.split(":", 2)
        action_type = parts[1] if len(parts) > 1 else "home"
        param = parts[2] if len(parts) > 2 else ""

        subscribed = await is_user_subscribed(context.bot, user.id)
        if not subscribed:
            await query.answer("❌ You still haven't joined the channel. Please join first!", show_alert=True)
            return

        await query.answer("✅ Verification successful!", show_alert=False)
        try:
            await query.message.delete()
        except Exception:
            pass

        if action_type == "file" and param:
            movie = await get_movie_by_code(param)
            if movie:
                allowed, hours_left, mins_left = await check_daily_limit(user.id, user.username)
                if not allowed:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=get_daily_limit_message(hours_left, mins_left),
                        reply_markup=get_daily_limit_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
                    return
                success = await deliver_movie_file(context.bot, update.effective_chat.id, movie)
                if success:
                    await record_user_download(user.id, movie["id"])
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ File not found or expired.",
                    parse_mode=ParseMode.HTML
                )
        elif action_type == "id" and param:
            movie_id = int(param) if param.isdigit() else 0
            movie = await get_movie_by_id(movie_id)
            if movie:
                allowed, hours_left, mins_left = await check_daily_limit(user.id, user.username)
                if not allowed:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=get_daily_limit_message(hours_left, mins_left),
                        reply_markup=get_daily_limit_keyboard(),
                        parse_mode=ParseMode.HTML
                    )
                    return
                success = await deliver_movie_file(context.bot, update.effective_chat.id, movie)
                if success:
                    await record_user_download(user.id, movie["id"])
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ File not found or expired.",
                    parse_mode=ParseMode.HTML
                )
        elif action_type == "q" and param:
            movies, total_count = await search_movies(param, offset=0, limit=PER_PAGE)
            if movies:
                markup = build_search_keyboard(movies, total_count, param, page=1)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"🎬 <b>Results for:</b> <code>{param}</code>",
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ No movies found for <code>{param}</code>",
                    parse_mode=ParseMode.HTML
                )
        return

    # Deliver movie: get_file:<movie_id>
    if data.startswith("get_file:"):
        movie_id_str = data.split(":", 1)[1]
        if not movie_id_str.isdigit():
            await query.answer("Invalid file ID.", show_alert=True)
            return

        movie_id = int(movie_id_str)
        # Check FSUB
        subscribed = await is_user_subscribed(context.bot, user.id)
        if not subscribed:
            await query.answer("🔒 Please join the required channel first!", show_alert=True)
            await query.message.reply_text(
                text=get_fsub_message(),
                reply_markup=get_fsub_keyboard(callback_data=f"check_fsub:id:{movie_id}"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        movie = await get_movie_by_id(movie_id)
        if not movie:
            await query.answer("❌ This file is no longer available in the database.", show_alert=True)
            return

        # Check Movie Download Limit (2 Free Movies Lifetime, VIP, or Active Referral Bonus)
        allowed, total_used, bonus_left = await check_user_download_limit(user.id, user.username)
        if not allowed:
            await query.answer(f"⏳ Free limit reached ({FREE_MOVIE_LIMIT}/{FREE_MOVIE_LIMIT} movies used)!", show_alert=True)
            await query.message.reply_text(
                text=get_limit_reached_message(total_used),
                reply_markup=get_limit_reached_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        await query.answer("🎬 Sending file to you now...")
        success = await deliver_movie_file(context.bot, update.effective_chat.id, movie)
        if success:
            await record_user_download(user.id, movie_id)
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

            # Force/prompt user to take VIP subscription with high-converting notices
            if not await is_user_premium(user.id):
                if total_after == 1:
                    notice = (
                        "🍿 <b>Enjoy your movie!</b>\n"
                        f"ℹ️ <i>Notice: You have used 1 of your {FREE_MOVIE_LIMIT} Free Welcome Movies.</i>\n\n"
                        "⚡ <b>Want unlimited downloads without any limits or ads?</b>\n"
                        "👉 Tap /vip to view our VIP passes (starting at only ₹39)!"
                    )
                    await query.message.reply_text(notice, parse_mode=ParseMode.HTML)
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
                    await query.message.reply_text(notice, reply_markup=markup, parse_mode=ParseMode.HTML)
        return

    # Pagination: sp:<query>:<page>
    if data.startswith("sp:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.answer()
            return

        search_query = parts[1]
        try:
            page = int(parts[2])
        except ValueError:
            page = 1

        offset = (page - 1) * PER_PAGE
        movies, total_count = await search_movies(search_query, offset=offset, limit=PER_PAGE)
        if not movies:
            await query.answer("No more pages available.", show_alert=True)
            return

        new_markup = build_search_keyboard(movies, total_count, search_query, page)
        try:
            await query.edit_message_reply_markup(reply_markup=new_markup)
            await query.answer()
        except Exception as e:
            logger.warning(f"Error editing pagination markup: {e}")
            await query.answer()
        return
