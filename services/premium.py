import os
from urllib.parse import quote
from typing import Tuple, Optional, Dict, Any
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user_subscription
from config import (
    SUBSCRIPTION_PLANS,
    UPI_ID,
    UPI_NAME,
    ADMIN_CONTACT_USERNAME,
    PAYMENT_QR_IMAGE
)

async def get_premium_plans_card(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Return marketing plans card or active VIP subscription info with plan selection buttons.
    """
    sub = await get_user_subscription(user_id)
    header = ""
    if sub:
        header = (
            "👑 <b>VIP Premium Member</b>\n\n"
            f"✅ <b>Status:</b> Active\n"
            f"⏰ <b>Expires On:</b> <code>{sub['expires_at']}</code> ({sub['days_left']} days left)\n"
            f"🚀 <b>Perks:</b> Unlimited Movie Downloads with zero daily limits!\n\n"
            "✨ <i>Want to extend your VIP membership? Select a plan below:</i>\n\n"
        )
    else:
        header = (
            "💎 <b>Movie World VIP Subscription</b>\n\n"
            "Unlock <b>UNLIMITED MOVIE DOWNLOADS</b> with zero daily limits!\n\n"
            "<b>✨ VIP Benefits:</b>\n"
            "⚡ <b>Unlimited Downloads:</b> No 1-movie-per-day restriction\n"
            "🎬 <b>High Speed:</b> Instant direct file dispatch\n"
            "🍿 <b>Direct Requests:</b> Priority movie requests to admin\n\n"
            "<b>Select a plan below to activate:</b>\n\n"
        )

    lines = []
    for p in SUBSCRIPTION_PLANS:
        lines.append(f"• {p['badge']} <b>{p['name']}</b> ({p['days']} Days) — <b>{p['currency']}{p['price']}</b>")

    text = header + "\n".join(lines) + "\n\n👇 <i>Tap a plan button below to view payment details & instant activation:</i>"

    # Build keyboard with 2 buttons per row, then 1 button for 1-year
    keyboard = [
        [
            InlineKeyboardButton("🌟 Weekly (₹39)", callback_data="select_plan:plan_weekly"),
            InlineKeyboardButton("🌟 1 Month (₹89)", callback_data="select_plan:plan_1month")
        ],
        [
            InlineKeyboardButton("🔥 3 Months (₹219)", callback_data="select_plan:plan_3months"),
            InlineKeyboardButton("👑 6 Months (₹349)", callback_data="select_plan:plan_6months")
        ],
        [
            InlineKeyboardButton("⚡ One Year (₹649)", callback_data="select_plan:plan_1year")
        ],
        [
            InlineKeyboardButton(f"💬 Contact Admin (@{ADMIN_CONTACT_USERNAME})", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}"),
            InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)

def get_plan_checkout_card(plan: Dict[str, Any], user_id: int) -> Tuple[str, InlineKeyboardMarkup, Optional[str]]:
    """
    Generate checkout message, keyboard, and optional QR code image URL for a selected plan.
    Returns: (caption_text, keyboard, qr_code_url_or_none)
    """
    price = plan["price"]
    days = plan["days"]
    name = plan["name"]
    badge = plan["badge"]

    # UPI URL and QR Code
    encoded_name = quote(UPI_NAME)
    encoded_note = quote(f"{name} VIP User {user_id}")
    upi_uri = f"upi://pay?pa={UPI_ID}&pn={encoded_name}&am={price}&cu=INR&tn={encoded_note}"
    if plan.get("qr_image") and os.path.exists(plan["qr_image"]):
        qr_url = plan["qr_image"]
    else:
        qr_url = PAYMENT_QR_IMAGE or f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={quote(upi_uri)}"

    text = (
        f"💎 <b>Storefront VIP Checkout — {badge} {name}</b>\n\n"
        f"💰 <b>Exact Amount:</b> <code>₹{price}</code>\n"
        f"⏳ <b>Duration:</b> <b>{days} Days</b>\n"
        f"⚡ <b>Perks:</b> Unlimited Movie Downloads with zero daily limits\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📸 <b>How to Pay via QR Code:</b>\n"
        f"1. Scan the QR code image above using any UPI App (Google Pay, PhonePe, Paytm, BHIM).\n"
        f"2. Complete the payment of <b>₹{price}</b>.\n"
        f"3. After payment, reply directly to this bot with either:\n"
        f"   • Your <b>12-digit UTR/Reference number</b>, or\n"
        f"   • A clear <b>screenshot of the payment confirmation page</b>."
    )

    buttons = [
        [
            InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}"),
            InlineKeyboardButton("🔙 Back to Plans", callback_data="buy_premium")
        ]
    ]

    return text, InlineKeyboardMarkup(buttons), qr_url

def get_storefront_payment_card(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Generate payment storefront card displaying exact pricing and plan selection buttons.
    (No QR code is sent with this message; QR code is sent once user selects a plan).
    """
    text = (
        "💎 <b>Movie World — VIP Subscription</b>\n\n"
        "Unlock <b>UNLIMITED MOVIE DOWNLOADS</b> with zero daily limits!\n\n"
        "<b>Exact Pricing:</b>\n"
        "• 🌟 <b>Weekly:</b> 7 Days — <b>₹39</b>\n"
        "• 🌟 <b>1 Month:</b> 30 Days — <b>₹89</b>\n"
        "• 🔥 <b>3 Months:</b> 90 Days — <b>₹219</b>\n"
        "• 👑 <b>6 Months:</b> 180 Days — <b>₹349</b>\n"
        "• ⚡ <b>One Year:</b> 365 Days — <b>₹649</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Select a plan below to view its QR code & payment instructions:</b>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🌟 Weekly (₹39)", callback_data="select_plan:plan_weekly"),
            InlineKeyboardButton("🌟 1 Month (₹89)", callback_data="select_plan:plan_1month")
        ],
        [
            InlineKeyboardButton("🔥 3 Months (₹219)", callback_data="select_plan:plan_3months"),
            InlineKeyboardButton("👑 6 Months (₹349)", callback_data="select_plan:plan_6months")
        ],
        [
            InlineKeyboardButton("⚡ One Year (₹649)", callback_data="select_plan:plan_1year")
        ],
        [
            InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}"),
            InlineKeyboardButton("🔍 Search Movies", callback_data="help_search")
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)


