import math
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from database import (
    add_user,
    search_movies,
    log_movie_request,
    get_effective_admin_group_id,
    get_admin_user_ids,
    log_user_search,
    update_user_activity
)
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.metadata import (
    fetch_movie_metadata,
    format_file_size,
    parse_search_query
)
from handlers.payment import handle_user_payment_text, display_storefront
from config import logger, ADMIN_CONTACT_USERNAME

PER_PAGE = 6

def build_search_keyboard(movies: list, total_count: int, query: str, page: int) -> InlineKeyboardMarkup:
    """Build keyboard with movie file selection and pagination."""
    keyboard = []
    
    # Movie buttons
    for movie in movies:
        size_str = format_file_size(movie.get("file_size", 0))
        # Shorten filename if needed to fit on Telegram button
        name = movie.get("file_name", "Movie")
        display_name = name if len(name) <= 38 else f"{name[:35]}..."
        button_text = f"▶️ {display_name} ({size_str})"
        keyboard.append([
            InlineKeyboardButton(text=button_text, callback_data=f"get_file:{movie['id']}")
        ])

    # Pagination buttons
    total_pages = max(1, math.ceil(total_count / PER_PAGE))
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"sp:{query[:15]}:{page - 1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"sp:{query[:15]}:{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # VIP Upgrade Button (Pushes users to subscribe for unlimited downloads)
    keyboard.append([InlineKeyboardButton("💎 VIP: Unlimited Downloads & Fast Speed", callback_data="buy_premium")])

    # Share link button
    keyboard.append([InlineKeyboardButton("🔗 Share Bot with Friends", switch_inline_query="")])

    return InlineKeyboardMarkup(keyboard)

async def notify_admins_missing_movie(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    query_text: str
) -> None:
    """
    Notify Admin & Admin Group when a user searches for a movie not in database.
    Includes rate-limiting cache to avoid spamming admins for identical searches within 10 minutes.
    """
    if not user or not query_text:
        return

    # Anti-spam cache in bot_data
    if "recent_missing_requests" not in context.bot_data:
        context.bot_data["recent_missing_requests"] = {}

    cache = context.bot_data["recent_missing_requests"]
    now = datetime.now()
    cache_key = f"{user.id}:{query_text.lower().strip()}"

    # Don't send duplicate admin alerts if user re-searches the same title within 10 minutes
    last_time = cache.get(cache_key)
    if last_time and (now - last_time).total_seconds() < 600:
        return

    cache[cache_key] = now

    # Log request to database
    try:
        await log_movie_request(
            user_id=user.id,
            user_name=user.first_name,
            user_handle=user.username,
            query=query_text
        )
    except Exception as e:
        logger.warning(f"Could not log movie request to database: {e}")

    admin_group_id = await get_effective_admin_group_id()
    admin_ids = await get_admin_user_ids()

    targets = set()
    if admin_group_id:
        targets.add(admin_group_id)
    for aid in admin_ids:
        targets.add(aid)

    if not targets:
        logger.warning("No admin group or admin IDs configured to receive missing movie alerts.")
        return

    user_username = f"@{user.username}" if user.username else "No Username"
    user_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    admin_caption = (
        "📢 <b>NEW MOVIE REQUEST (Not in Database)</b>\n\n"
        f"🎬 <b>Requested Movie:</b> <code>{query_text}</code>\n"
        f"👤 <b>Requested By:</b> {user.first_name} ({user_username})\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"⏰ <b>Time:</b> {now_str}\n\n"
        "💡 <i>Action: Please upload or forward this movie file to your storage channel to index it!</i>"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Message {user.first_name}", url=user_url)]
    ])

    for target_id in targets:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=admin_caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to deliver missing movie alert to chat {target_id}: {e}")

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process search text sent by the user."""
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    if text.startswith("/"):
        return  # Ignore commands here

    # Intercept payment proof (12-digit UTR or messages while awaiting payment proof)
    if await handle_user_payment_text(update, context):
        return

    # If user asks for plans or pricing in chat, display all plans with QR code
    lower_text = text.lower().strip()
    plan_keywords = {"plan", "plans", "buy", "price", "prices", "pricing", "subscription", "vip", "qr", "qr code", "payment"}
    if lower_text in plan_keywords:
        await display_storefront(update, context)
        return

    user = update.effective_user
    chat = update.effective_chat
    if user:
        await add_user(user.id, user.username, user.first_name)

    # In private chats, check FSUB
    if chat.type == ChatType.PRIVATE and user:
        subscribed = await is_user_subscribed(context.bot, user.id)
        if not subscribed:
            await update.effective_message.reply_text(
                text=get_fsub_message(),
                reply_markup=get_fsub_keyboard(callback_data=f"check_fsub:q:{text[:20]}"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Parse complex queries (e.g. "Spider-Man 2 2004 1080p Hindi" or "Inception 2010 1080p")
    parsed = parse_search_query(text)
    clean_title = parsed["clean_title"]
    year = parsed["year"]

    page = 1
    offset = 0
    tier_note = ""

    # TIER 1: Exact search with all terms (Title + Year + Quality + Language)
    movies, total_count = await search_movies(text, offset=offset, limit=PER_PAGE)

    # TIER 2: If Tier 1 returned 0, search for Core Title + Year (e.g. "Spider Man 2 2004")
    # This helps when user specifies "1080p Hindi" but the database has "720p Dual Audio" or "1080p"
    if total_count == 0 and clean_title and year:
        core_query_with_year = f"{clean_title} {year}"
        movies, total_count = await search_movies(core_query_with_year, offset=offset, limit=PER_PAGE)
        if total_count > 0:
            tier_note = (
                f"ℹ️ <i>Exact audio/resolution tags not matched, "
                f"showing all available <b>{year}</b> versions:</i>\n\n"
            )

    # TIER 3: If still 0, check if Core Title exists without the year (across any release)
    if total_count == 0 and clean_title:
        alt_movies, alt_count = await search_movies(clean_title, offset=offset, limit=PER_PAGE)
        if alt_count > 0:
            alt_markup = build_search_keyboard(alt_movies, alt_count, clean_title, 1)
            if year:
                msg = (
                    f"❌ <b>Movie Not Available for Year {year}:</b>\n\n"
                    f"We could not find <b>{clean_title}</b> for release year <code>{year}</code>.\n\n"
                    f"💡 <b>However, {alt_count} other release(s) of '{clean_title}' are available:</b>\n"
                    f"👇 <i>Tap below to download an available release:</i>"
                )
            else:
                msg = (
                    f"💡 <b>Found {alt_count} release(s) for '{clean_title}':</b>\n"
                    f"👇 <i>Tap below to download:</i>"
                )
            if user:
                await log_user_search(user.id, user.first_name, user.username, text, alt_count)
            await update.effective_message.reply_text(msg, reply_markup=alt_markup, parse_mode=ParseMode.HTML)
            return

    # TIER 4: Completely not found
    if total_count == 0:
        if user:
            await log_user_search(user.id, user.first_name, user.username, text, 0)

        if year and not clean_title:
            # User only typed a year like "2001"
            await update.effective_message.reply_text(
                f"❌ <b>Not Available:</b> No movies from year <code>{year}</code> found in our library.",
                parse_mode=ParseMode.HTML
            )
            return

        display_query = f"{clean_title} ({year})" if (clean_title and year) else (clean_title or text)

        # Notify admin team immediately that user asked for this movie and it's not in the database!
        if user and len(display_query.strip()) >= 2:
            await notify_admins_missing_movie(context, user, display_query)

        not_found_msg = (
            f"❌ <b>Movie Not in Database:</b> <code>{display_query}</code>\n\n"
            "📢 <b>Admin Notified!</b>\n"
            f"We have automatically forwarded your request to our Admin team to add <b>{display_query}</b> as soon as possible.\n\n"
            "💡 <b>Tips:</b>\n"
            "• Double check spelling (e.g. <code>Interstellar</code>).\n"
            "• Once the admin uploads it, you'll be able to download it here!"
        )

        user_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 Contact Admin (@{ADMIN_CONTACT_USERNAME})", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")],
            [InlineKeyboardButton("🔍 Search Tips", callback_data="help_search")]
        ])

        await update.effective_message.reply_text(
            not_found_msg,
            reply_markup=user_markup,
            parse_mode=ParseMode.HTML
        )
        return

    # MATCH FOUND!
    if user:
        await log_user_search(user.id, user.first_name, user.username, text, total_count)
    # Fetch movie metadata & IMDb poster
    meta = await fetch_movie_metadata(clean_title or text, year=year)
    markup = build_search_keyboard(movies, total_count, text, page)

    year_str = f" ({year})" if year else ""
    display_title = (
        f"{meta['title']} ({meta['year']})"
        if meta and meta.get("year") != "N/A"
        else f"{clean_title or text}{year_str}"
    )

    if meta and meta.get("poster"):
        caption = (
            f"🎬 <b>{display_title}</b> - <b>Available!</b>\n"
            f"⭐ <b>IMDb:</b> {meta['rating']}/10 | 🎭 <b>Genre:</b> {meta['genre']}\n\n"
            f"📖 <i>{meta['plot'][:220]}...</i>\n\n"
            f"{tier_note}"
            f"📦 <b>Available Downloads:</b> ({total_count} files found)"
        )
        try:
            await update.effective_message.reply_photo(
                photo=meta["poster"],
                caption=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
            return
        except Exception as e:
            logger.warning(f"Failed to send poster: {e}. Falling back to text.")

    # Text fallback card
    text_card = (
        f"🎬 <b>{display_title}</b> - <b>Available!</b>\n\n"
        f"{tier_note}"
        f"📦 Found <b>{total_count}</b> file(s) for your search.\n"
        f"👇 <i>Tap your desired version below to download:</i>"
    )
    await update.effective_message.reply_text(text_card, reply_markup=markup, parse_mode=ParseMode.HTML)
