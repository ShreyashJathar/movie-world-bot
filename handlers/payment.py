import os
import re
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import (
    SUBSCRIPTION_PLANS,
    get_plan_by_id,
    ADMIN_CONTACT_USERNAME,
    is_admin,
    logger
)
from database import (
    create_payment_request,
    get_payment_request,
    update_payment_request_status,
    add_user_subscription,
    get_admin_user_ids,
    is_utr_already_submitted,
    get_effective_admin_group_id,
    set_bot_setting
)
from services.premium import (
    get_plan_checkout_card,
    get_storefront_payment_card
)

async def display_storefront(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: Optional[str] = None) -> None:
    """
    Display plans overview text with plan selection buttons (No QR code sent here).
    QR code is sent after the user taps/selects a specific plan.
    """
    user = update.effective_user
    if not user:
        return

    text, markup = get_storefront_payment_card(user.id)

    if update.effective_message:
        await update.effective_message.reply_text(
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plan selection button: select_plan:<plan_id>"""
    query = update.callback_query
    if not query or not query.data:
        return

    plan_id = query.data.split(":", 1)[1]
    plan = get_plan_by_id(plan_id)
    if not plan:
        await query.answer("Plan not found.", show_alert=True)
        return

    context.user_data["selected_plan_id"] = plan_id
    context.user_data["awaiting_payment_proof"] = True
    user = update.effective_user

    text, markup, qr_url = get_plan_checkout_card(plan, user.id)
    await query.answer()

    if qr_url:
        try:
            if os.path.exists(qr_url):
                with open(qr_url, "rb") as f:
                    await query.message.reply_photo(
                        photo=f,
                        caption=text,
                        reply_markup=markup,
                        parse_mode=ParseMode.HTML
                    )
            else:
                await query.message.reply_photo(
                    photo=qr_url,
                    caption=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
            return
        except Exception as e:
            logger.warning(f"Failed to send QR image ({qr_url}): {e}. Falling back to text.")

    await query.message.reply_text(
        text=text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

async def handle_user_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle user uploaded photo (screenshot).
    Guarantees:
    - Never auto-approves.
    - Checks for duplicate UTR in caption if provided.
    - Sends exact required pending message.
    - Sends structured summary to admins with user details & proof.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("image/") or mime == "application/pdf":
            file_id = message.document.file_id

    if not file_id:
        return

    caption = message.caption or ""

    # Check for 12-digit UTR in caption
    utr_match = re.search(r'\b\d{12}\b', caption)
    extracted_utr = utr_match.group(0) if utr_match else None

    # Check for duplicate UTR submissions
    if extracted_utr and await is_utr_already_submitted(extracted_utr):
        await message.reply_text("This reference number has already been submitted for verification.")
        return

    selected_plan_id = context.user_data.get("selected_plan_id") or "plan_1month"
    plan = get_plan_by_id(selected_plan_id) or SUBSCRIPTION_PLANS[1]

    # Save pending request in database (Never auto-approve)
    req_id = await create_payment_request(
        user_id=user.id,
        user_name=user.first_name,
        user_handle=user.username,
        plan_id=plan["id"],
        plan_name=plan["name"],
        plan_days=plan["days"],
        amount=plan["price"],
        proof_file_id=file_id,
        utr_or_note=caption,
        utr_number=extracted_utr
    )

    context.user_data["awaiting_payment_proof"] = False

    # Send exact prompt acknowledgment
    await message.reply_text(
        "⏳ Proof submitted successfully! Our team is currently validating your transfer. You will receive an automated notification here as soon as it is verified."
    )

    # Send structured summary to Admin
    await notify_admins_structured_summary(
        context=context,
        req_id=req_id,
        user=user,
        plan=plan,
        proof_type="Payment Screenshot",
        submitted_proof=extracted_utr or "Screenshot Image Attached",
        note=caption,
        photo_file_id=file_id
    )

async def handle_user_payment_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle user text when awaiting payment proof or submitting a 12-digit UTR.
    Returns True if handled, False if regular search query.
    """
    message = update.effective_message
    if not message or not message.text:
        return False

    text = message.text.strip()
    if text.startswith("/"):
        return False

    user = update.effective_user
    if not user:
        return False

    is_awaiting = context.user_data.get("awaiting_payment_proof", False)
    utr_match = re.search(r'\b\d{12}\b', text)

    # If user is in payment mode:
    if is_awaiting:
        lower = text.lower().strip()
        if lower in ["cancel", "exit", "back"]:
            context.user_data["awaiting_payment_proof"] = False
            await message.reply_text("✅ Payment mode closed. You can now search for movies directly!")
            return True

        if lower in ["plan", "plans", "buy", "price", "prices", "pricing", "subscription", "vip", "qr", "qr code", "payment"]:
            await display_storefront(update, context)
            return True

        # User MUST send either 12-digit UTR or screenshot
        if not utr_match:
            await message.reply_text(
                "I can only process your order if you send a valid payment screenshot or a 12-digit UTR transaction number. Please try again."
            )
            return True

        utr = utr_match.group(0)

        # Check duplicate UTR
        if await is_utr_already_submitted(utr):
            await message.reply_text("This reference number has already been submitted for verification.")
            return True

        selected_plan_id = context.user_data.get("selected_plan_id") or "plan_1month"
        plan = get_plan_by_id(selected_plan_id) or SUBSCRIPTION_PLANS[1]

        req_id = await create_payment_request(
            user_id=user.id,
            user_name=user.first_name,
            user_handle=user.username,
            plan_id=plan["id"],
            plan_name=plan["name"],
            plan_days=plan["days"],
            amount=plan["price"],
            proof_file_id=None,
            utr_or_note=text,
            utr_number=utr
        )

        context.user_data["awaiting_payment_proof"] = False

        # Exact confirmation message
        await message.reply_text(
            "⏳ Proof submitted successfully! Our team is currently validating your transfer. You will receive an automated notification here as soon as it is verified."
        )

        # Send structured summary to Admin
        await notify_admins_structured_summary(
            context=context,
            req_id=req_id,
            user=user,
            plan=plan,
            proof_type="12-Digit UTR Number",
            submitted_proof=utr,
            note=text,
            photo_file_id=None
        )
        return True

    # If NOT in payment mode but message is an exact 12-digit numeric string:
    if re.fullmatch(r'\d{12}', text):
        utr = text
        if await is_utr_already_submitted(utr):
            await message.reply_text("This reference number has already been submitted for verification.")
            return True

        plan = SUBSCRIPTION_PLANS[1]  # Default 1 Month
        req_id = await create_payment_request(
            user_id=user.id,
            user_name=user.first_name,
            user_handle=user.username,
            plan_id=plan["id"],
            plan_name=plan["name"],
            plan_days=plan["days"],
            amount=plan["price"],
            proof_file_id=None,
            utr_or_note=text,
            utr_number=utr
        )

        await message.reply_text(
            "⏳ Proof submitted successfully! Our team is currently validating your transfer. You will receive an automated notification here as soon as it is verified."
        )

        await notify_admins_structured_summary(
            context=context,
            req_id=req_id,
            user=user,
            plan=plan,
            proof_type="12-Digit UTR Number",
            submitted_proof=utr,
            note=text,
            photo_file_id=None
        )
        return True

    return False

async def check_admin_permission(user, chat, bot) -> bool:
    """Check if user is admin globally or an admin in the current group/supergroup."""
    if is_admin(user.id, user.username):
        return True
    if chat and chat.type in ["group", "supergroup"]:
        try:
            member = await bot.get_chat_member(chat.id, user.id)
            if member.status in ["administrator", "creator"]:
                return True
        except Exception:
            pass
    return False

async def notify_admins_structured_summary(
    context: ContextTypes.DEFAULT_TYPE,
    req_id: int,
    user,
    plan: dict,
    proof_type: str,
    submitted_proof: str,
    note: str,
    photo_file_id: Optional[str] = None
) -> None:
    """
    Send structured summary containing User's Telegram ID, Name, Username,
    and submitted proof to Private Admin Chat Group (https://t.me/+lgLJDd4mfZw5M2U1)
    for human review with instant APPROVES and REJECTS.
    """
    admin_group_id = await get_effective_admin_group_id()
    admin_ids = await get_admin_user_ids()

    targets = set()
    if admin_group_id:
        targets.add(admin_group_id)
    for aid in admin_ids:
        targets.add(aid)

    if not targets:
        logger.warning("No admin user IDs or admin group available to receive payment submission.")
        return

    user_username = f"@{user.username}" if user.username else "No Username"
    user_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    caption = (
        f"🔔 <b>NEW PAYMENT SUBMISSION FOR VERIFICATION</b> (Request #{req_id})\n\n"
        f"👤 <b>Name:</b> {user.first_name}\n"
        f"🏷 <b>Username:</b> {user_username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"📦 <b>Selected Plan:</b> {plan['badge']} {plan['name']} ({plan['days']} Days) — ₹{plan['price']}\n"
        f"🔢 <b>Proof Type:</b> {proof_type}\n"
        f"📄 <b>Submitted Proof:</b> <code>{submitted_proof}</code>\n"
        f"📝 <b>Raw Notes:</b> {note or '<i>None</i>'}\n"
        f"⏰ <b>Time:</b> {now_str}"
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ Approve ({plan['days']}d)", callback_data=f"pay_appr:{req_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"pay_rej:{req_id}")
        ],
        [InlineKeyboardButton(f"💬 Message {user.first_name}", url=user_url)]
    ])

    for target_id in targets:
        try:
            if photo_file_id:
                await context.bot.send_photo(
                    chat_id=target_id,
                    photo=photo_file_id,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=caption,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Failed to deliver admin payment notification to chat {target_id}: {e}")

async def handle_payment_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin clicking Approve button."""
    query = update.callback_query
    if not query or not query.data:
        return

    admin = update.effective_user
    chat = update.effective_chat
    if not await check_admin_permission(admin, chat, context.bot):
        await query.answer("🔒 Only administrators can approve payments.", show_alert=True)
        return

    req_id_str = query.data.split(":", 1)[1]
    if not req_id_str.isdigit():
        await query.answer("Invalid Request ID.", show_alert=True)
        return

    req_id = int(req_id_str)
    req = await get_payment_request(req_id)
    if not req:
        await query.answer("Payment request not found.", show_alert=True)
        return

    if req["status"] != "PENDING":
        await query.answer(f"This request has already been {req['status']}.", show_alert=True)
        return

    # Grant VIP access (Access only granted when admin pushes Approve)
    expiry_str = await add_user_subscription(req["user_id"], req["plan_days"])
    await update_payment_request_status(
        request_id=req_id,
        status="APPROVED",
        admin_message_id=query.message.message_id if query.message else None,
        admin_chat_id=query.message.chat_id if query.message else None
    )

    admin_tag = f"@{admin.username}" if admin.username else admin.first_name
    admin_update_text = (
        f"\n\n━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>APPROVED</b> by {admin_tag}\n"
        f"⏰ <b>VIP Active Until:</b> <code>{expiry_str}</code>"
    )

    user_url = f"https://t.me/{req['user_handle']}" if req["user_handle"] else f"tg://user?id={req['user_id']}"
    updated_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Message User", url=user_url)]
    ])

    try:
        if query.message.caption:
            await query.edit_message_caption(
                caption=query.message.caption + admin_update_text,
                reply_markup=updated_markup,
                parse_mode=ParseMode.HTML
            )
        elif query.message.text:
            await query.edit_message_text(
                text=query.message.text + admin_update_text,
                reply_markup=updated_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.warning(f"Could not edit admin payment message: {e}")

    await query.answer("✅ VIP Subscription Activated Successfully!")

    # POST-VERIFICATION ACTION (IF ADMIN APPROVES): Celebratory message with digital delivery/access
    try:
        celebration_text = (
            f"🎉 <b>Congratulations! Your payment has been approved and verified!</b>\n\n"
            f"📦 <b>Plan:</b> <b>{req['plan_name']}</b> ({req['plan_days']} Days)\n"
            f"🚀 <b>Perks Unlocked:</b>\n"
            f"• <b>UNLIMITED Movie Downloads</b> with ZERO daily limits\n"
            f"• High-speed direct storage delivery\n"
            f"• Priority requests to admin\n\n"
            f"⏰ <b>VIP Valid Until:</b> <code>{expiry_str}</code>\n\n"
            f"🍿 <i>Enjoy your unlimited streaming on Movie World! Tap below to search:</i>"
        )
        user_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Search & Download Movies", callback_data="help_search")]
        ])
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=celebration_text,
            reply_markup=user_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Failed to notify approved user {req['user_id']}: {e}")

async def handle_payment_rejection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin clicking Reject button."""
    query = update.callback_query
    if not query or not query.data:
        return

    admin = update.effective_user
    chat = update.effective_chat
    if not await check_admin_permission(admin, chat, context.bot):
        await query.answer("🔒 Only administrators can reject payments.", show_alert=True)
        return

    req_id_str = query.data.split(":", 1)[1]
    if not req_id_str.isdigit():
        await query.answer("Invalid Request ID.", show_alert=True)
        return

    req_id = int(req_id_str)
    req = await get_payment_request(req_id)
    if not req:
        await query.answer("Payment request not found.", show_alert=True)
        return

    if req["status"] != "PENDING":
        await query.answer(f"This request has already been {req['status']}.", show_alert=True)
        return

    await update_payment_request_status(
        request_id=req_id,
        status="REJECTED",
        admin_message_id=query.message.message_id if query.message else None,
        admin_chat_id=query.message.chat_id if query.message else None
    )

    admin_tag = f"@{admin.username}" if admin.username else admin.first_name
    admin_update_text = (
        f"\n\n━━━━━━━━━━━━━━━━━━\n"
        f"❌ <b>REJECTED</b> by {admin_tag}"
    )

    user_url = f"https://t.me/{req['user_handle']}" if req["user_handle"] else f"tg://user?id={req['user_id']}"
    updated_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Message User", url=user_url)]
    ])

    try:
        if query.message.caption:
            await query.edit_message_caption(
                caption=query.message.caption + admin_update_text,
                reply_markup=updated_markup,
                parse_mode=ParseMode.HTML
            )
        elif query.message.text:
            await query.edit_message_text(
                text=query.message.text + admin_update_text,
                reply_markup=updated_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.warning(f"Could not edit admin payment message: {e}")

    await query.answer("❌ Request Rejected.")

    # POST-VERIFICATION ACTION (IF ADMIN REJECTS): Polite exact rejection message
    try:
        rejection_text = (
            "Verification Failed. We could not match this proof with our bank statement records. "
            "Please contact support if you believe this is an error."
        )
        user_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{ADMIN_CONTACT_USERNAME}")]
        ])
        await context.bot.send_message(
            chat_id=req["user_id"],
            text=rejection_text,
            reply_markup=user_markup
        )
    except Exception as e:
        logger.warning(f"Failed to notify rejected user {req['user_id']}: {e}")

async def set_admin_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Link private group as the verification group."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    if chat.type in ["group", "supergroup"]:
        await set_bot_setting("admin_group_id", str(chat.id))
        await update.effective_message.reply_text(
            f"✅ <b>Private Verification Group Linked!</b>\n\n"
            f"👥 <b>Group Title:</b> {chat.title}\n"
            f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n\n"
            f"All customer payment proofs (screenshots & 12-digit UTRs) will now be forwarded here for <b>APPROVES</b> and <b>REJECTS</b>!",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.effective_message.reply_text(
            "ℹ️ <b>How to link your Private Group:</b>\n\n"
            "1. Add this bot to your private group (https://t.me/+lgLJDd4mfZw5M2U1) as an <b>Admin</b>.\n"
            "2. Send <code>/setadmingroup</code> inside that group.\n"
            "3. The bot will automatically link it and forward all payment submissions there!",
            parse_mode=ParseMode.HTML
        )

async def handle_chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Automatically detect when bot is added to the private group and link it."""
    my_chat_member = update.my_chat_member
    if not my_chat_member:
        return

    new_status = my_chat_member.new_chat_member.status
    chat = update.effective_chat
    if chat and chat.type in ["group", "supergroup"] and new_status in ["administrator", "member"]:
        await set_bot_setting("admin_group_id", str(chat.id))
        logger.info(f"Bot joined group {chat.title} ({chat.id}). Configured as Admin Verification Group!")
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"✅ <b>Admin Verification Group Linked!</b>\n\n"
                    f"👥 <b>Group:</b> {chat.title}\n"
                    f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n\n"
                    f"All customer subscription payment submissions (screenshots & UTR numbers) will now be automatically forwarded here for instant <b>APPROVE / REJECT</b> human review!"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Could not send welcome message to group {chat.id}: {e}")

