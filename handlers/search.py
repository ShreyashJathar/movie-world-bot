import math
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from database import add_user, search_movies
from services.fsub import is_user_subscribed, get_fsub_keyboard, get_fsub_message
from services.metadata import (
    fetch_movie_metadata,
    format_file_size,
    clean_movie_title,
    extract_year,
    parse_search_query
)
from handlers.payment import handle_user_payment_text, display_storefront
from config import logger

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

    # Share link button
    keyboard.append([InlineKeyboardButton("🔗 Share Bot", switch_inline_query="")])

    return InlineKeyboardMarkup(keyboard)

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
            await update.effective_message.reply_text(msg, reply_markup=alt_markup, parse_mode=ParseMode.HTML)
            return

    # TIER 4: Completely not found
    if total_count == 0:
        if year and not clean_title:
            # User only typed a year like "2001"
            await update.effective_message.reply_text(
                f"❌ <b>Not Available:</b> No movies from year <code>{year}</code> found in our library.",
                parse_mode=ParseMode.HTML
            )
            return

        if clean_title and year:
            not_found_msg = (
                f"❌ <b>Not Available:</b>\n\n"
                f"Movie <b>{clean_title}</b> ({year}) is currently not available in our library.\n\n"
                f"💡 <b>Tips:</b>\n"
                f"• Verify the movie title and release year.\n"
                f"• Try searching with only the main title (e.g. <code>{clean_title}</code>).\n"
                f"• Contact the admin to request this movie!"
            )
        else:
            not_found_msg = (
                f"❌ <b>No results found for:</b> <code>{text}</code>\n\n"
                f"💡 <b>Tips to find what you want:</b>\n"
                f"• Check the spelling of the title.\n"
                f"• Search with only the main name (e.g. <code>Inception</code> instead of <code>Inception 2010 1080p BluRay</code>).\n"
                f"• Our library is updated regularly by administrators!"
            )
        await update.effective_message.reply_text(not_found_msg, parse_mode=ParseMode.HTML)
        return

    # MATCH FOUND!
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
