from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import (
    get_movie_by_id,
    get_movie_by_code,
    search_movies,
    get_total_movies,
    get_total_users,
    record_user_download
)
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.delivery import deliver_movie_file
from services.ratelimit import (
    check_daily_limit,
    get_daily_limit_message,
    get_daily_limit_keyboard
)
from services.premium import get_premium_plans_card
from handlers.search import build_search_keyboard, PER_PAGE
from handlers.payment import (
    display_storefront,
    handle_plan_selection,
    handle_payment_approval,
    handle_payment_rejection
)
from config import is_admin, logger

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline button clicks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    user = update.effective_user

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

    # Buy / Premium storefront button
    if data in ["buy_premium", "buy"]:
        await query.answer()
        await display_storefront(update, context)
        return

    # Plan Selection: select_plan:<plan_id>
    if data.startswith("select_plan:"):
        await handle_plan_selection(update, context)
        return

    # Plan Confirmation after photo upload: confirm_plan:<plan_id>
    if data.startswith("confirm_plan:"):
        await handle_plan_confirmation(update, context)
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

        # Check 1 Movie Per Day Limit
        allowed, hours_left, mins_left = await check_daily_limit(user.id, user.username)
        if not allowed:
            await query.answer("⏳ Daily limit reached (1 movie per day)!", show_alert=True)
            await query.message.reply_text(
                text=get_daily_limit_message(hours_left, mins_left),
                reply_markup=get_daily_limit_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return

        await query.answer("🎬 Sending file to you now...")
        success = await deliver_movie_file(context.bot, update.effective_chat.id, movie)
        if success:
            await record_user_download(user.id, movie_id)
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
