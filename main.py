#Code by yori [python session generator]
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

# configuration
BOT_TOKEN = "8746937266:AAFenYn3ASCjjEyRGptMCXaWdbXIYMvE4mA"
SESSION_TIMEOUT = 600
MAX_ATTEMPTS = 3

#  logging 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

(
    API_ID,
    API_HASH,
    PHONE,
    OTP_CODE,
    TWOFA_PASSWORD,
) = range(5)

# helpers
async def update_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
) -> None:
    user_data = context.user_data
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return
    
    msg_id = user_data.get("bot_message_id")

    try:
        if msg_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        else:
            raise BadRequest("No previous message")
    except (BadRequest, Forbidden, TelegramError):
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        user_data["bot_message_id"] = sent.message_id
        return

    user_data["bot_message_id"] = msg_id


async def cleanup_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    client: Optional[TelegramClient] = user_data.get("client")
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    file_path: Optional[str] = user_data.get("file_path")
    if file_path and os.path.isfile(file_path):
        try:
            os.unlink(file_path)
        except Exception:
            pass
    user_data.clear()


async def cancel_conv(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "❌ Operation cancelled.",
) -> int:
    await update_message(update, context, text)
    await cleanup_user(update, context)
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await cancel_conv(update, context)


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    return await cancel_conv(update, context)


async def timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update_message(
        update, context, "⏰ Session timed out due to inactivity."
    )
    await cleanup_user(update, context)
    return ConversationHandler.END


async def entry_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.delete()
    text = (
        "🔄 <b>Generate Telethon Session String</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Step <b>1/5</b> – Send your <b>API ID</b> (numerical) from my.telegram.org.\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "ℹ️ Use /cancel to abort at any time."
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
    sent = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    context.user_data["bot_message_id"] = sent.message_id
    return API_ID


async def entry_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        text = (
            "🔄 <b>Generate Telethon Session String</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Step <b>1/5</b> – Send your <b>API ID</b> (numerical) from my.telegram.org.\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ℹ️ Use /cancel to abort at any time."
        )
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
        context.user_data["bot_message_id"] = query.message.message_id
    return API_ID


async def api_id_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return API_ID
        
    user_text = update.message.text.strip()
    user_data = context.user_data

    if not user_text.isdigit() or not (5 <= len(user_text) <= 9):
        await update.message.delete()
        attempts = user_data.get("api_id_attempts", 0) + 1
        user_data["api_id_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            return await cancel_conv(
                update, context,
                "❌ Too many invalid attempts. Operation cancelled."
            )
        await update_message(
            update, context,
            (
                "❌ Invalid API ID. It must be a number (5-9 digits).\n"
                "Try again or use /cancel."
            ),
        )
        return API_ID

    user_data["api_id"] = int(user_text)
    await update.message.delete()

    await update_message(
        update, context,
        (
            "🔑 <b>API ID accepted!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Step <b>2/5</b> – Send your <b>API Hash</b> (32 characters).\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    return API_HASH


async def api_hash_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return API_HASH
        
    user_text = update.message.text.strip()
    user_data = context.user_data

    if len(user_text) != 32 or not all(c in "0123456789abcdefABCDEF" for c in user_text):
        await update.message.delete()
        attempts = user_data.get("api_hash_attempts", 0) + 1
        user_data["api_hash_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            return await cancel_conv(
                update, context,
                "❌ Too many invalid attempts. Operation cancelled."
            )
        await update_message(
            update, context,
            (
                "❌ Invalid API Hash. It must be exactly 32 hexadecimal characters.\n"
                "Try again or use /cancel."
            ),
        )
        return API_HASH

    user_data["api_hash"] = user_text
    await update.message.delete()

    await update_message(update, context, "⏳ Checking credentials…")
    client = TelegramClient(
        StringSession(),
        user_data["api_id"],
        user_data["api_hash"],
    )
    try:
        await client.connect()
    except ApiIdInvalidError:
        await client.disconnect()
        return await cancel_conv(
            update, context,
            "❌ Invalid API credentials. Please check your API ID and Hash.",
        )
    except FloodWaitError as e:
        await client.disconnect()
        await update_message(
            update, context,
            f"⏳ Flood wait: please wait {e.seconds} seconds.\nRestart after the wait.",
        )
        return await cancel_conv(update, context)
    except Exception as e:
        await client.disconnect()
        return await cancel_conv(
            update, context,
            f"❌ Connection error: {e}",
        )

    user_data["client"] = client
    await update_message(
        update, context,
        (
            "✅ <b>Credentials valid!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Step <b>3/5</b> – Send your <b>phone number</b> in international format\n"
            "e.g. +1234567890\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    return PHONE


async def phone_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return PHONE
        
    user_text = update.message.text.strip()
    user_data = context.user_data

    if not (user_text.startswith("+") and user_text[1:].isdigit() and 10 <= len(user_text[1:]) <= 15):
        await update.message.delete()
        attempts = user_data.get("phone_attempts", 0) + 1
        user_data["phone_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            return await cancel_conv(
                update, context,
                "❌ Too many invalid attempts. Operation cancelled."
            )
        await update_message(
            update, context,
            (
                "❌ Invalid phone format. Use +countrycode and number, e.g. +1234567890.\n"
                "Try again or /cancel."
            ),
        )
        return PHONE

    user_data["phone"] = user_text
    await update.message.delete()

    client: TelegramClient = user_data["client"]
    await update_message(update, context, "⏳ Sending OTP…")
    try:
        sent_code = await client.send_code_request(user_text)
    except PhoneNumberInvalidError:
        return await cancel_conv(
            update, context,
            "❌ Invalid phone number. Please check and restart.",
        )
    except FloodWaitError as e:
        await update_message(
            update, context,
            f"⏳ Flood wait: {e.seconds} seconds.\nRestart later.",
        )
        return await cancel_conv(update, context)
    except Exception as e:
        return await cancel_conv(
            update, context,
            f"❌ Failed to send code: {e}",
        )

    user_data["phone_code_hash"] = sent_code.phone_code_hash
    await update_message(
        update, context,
        (
            "📱 <b>OTP sent!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Step <b>4/5</b> – Enter the <b>OTP code</b> you received.\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    return OTP_CODE


async def otp_code_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OTP_CODE
        
    user_text = update.message.text.strip()
    user_data = context.user_data

    if not (user_text.isdigit() and 5 <= len(user_text) <= 7):
        await update.message.delete()
        attempts = user_data.get("otp_attempts", 0) + 1
        user_data["otp_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            return await cancel_conv(
                update, context,
                "❌ Too many invalid OTP attempts. Operation cancelled."
            )
        await update_message(
            update, context,
            "❌ Invalid OTP. It should be 5-7 digits. Try again or /cancel.",
        )
        return OTP_CODE

    await update.message.delete()
    client: TelegramClient = user_data["client"]
    await update_message(update, context, "⏳ Verifying OTP…")

    try:
        user = await client.sign_in(
            phone=user_data["phone"],
            code=user_text,
            phone_code_hash=user_data["phone_code_hash"],
        )
    except SessionPasswordNeededError:
        await update_message(
            update, context,
            (
                "🔒 <b>2FA is enabled on this account.</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "Step <b>5/5</b> – Enter your <b>2FA password</b>.\n"
                "━━━━━━━━━━━━━━━━━━━━━"
            ),
        )
        return TWOFA_PASSWORD
    except FloodWaitError as e:
        await update_message(
            update, context,
            f"⏳ Flood wait: {e.seconds} seconds. Please wait and restart.",
        )
        return await cancel_conv(update, context)
    except Exception as e:
        return await cancel_conv(
            update, context,
            f"❌ OTP verification failed: {e}",
        )

    user_data["user_entity"] = user
    return await finish_generation(update, context)


async def twofa_password_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return TWOFA_PASSWORD
        
    user_password = update.message.text.strip()
    user_data = context.user_data
    client: TelegramClient = user_data["client"]

    await update.message.delete()
    await update_message(update, context, "⏳ Checking 2FA password…")

    try:
        user = await client.sign_in(password=user_password)
    except PasswordHashInvalidError:
        attempts = user_data.get("2fa_attempts", 0) + 1
        user_data["2fa_attempts"] = attempts
        if attempts >= MAX_ATTEMPTS:
            return await cancel_conv(
                update, context,
                "❌ Too many wrong 2FA passwords. Operation cancelled."
            )
        await update_message(
            update, context,
            "❌ Invalid 2FA password. Try again or /cancel.",
        )
        return TWOFA_PASSWORD
    except FloodWaitError as e:
        await update_message(
            update, context,
            f"⏳ Flood wait: {e.seconds} seconds. Please wait and restart.",
        )
        return await cancel_conv(update, context)
    except Exception as e:
        return await cancel_conv(
            update, context,
            f"❌ 2FA verification failed: {e}",
        )

    user_data["user_entity"] = user
    return await finish_generation(update, context)


async def finish_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    client: TelegramClient = user_data["client"]
    user = user_data["user_entity"]

    session_string = client.session.save()
    user_data["session_string"] = session_string

    os.makedirs("generated_sessions", exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"session_{user.id}_{timestamp}.txt"
    file_path = str(Path("generated_sessions") / filename)
    user_data["file_path"] = file_path

    file_content = (
        f"Telethon Session String\n"
        f"{'='*40}\n"
        f"User ID: {user.id}\n"
        f"Name: {user.first_name or ''} {user.last_name or ''}\n"
        f"Username: @{user.username if user.username else 'None'}\n"
        f"Phone: {user_data['phone']}\n"
        f"Generated at: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"Session String:\n{session_string}\n\n"
        f"{'='*40}\n"
        f"USAGE EXAMPLE (Python):\n"
        f"from telethon import TelegramClient\n"
        f"from telethon.sessions import StringSession\n\n"
        f"api_id = YOUR_API_ID\n"
        f"api_hash = 'YOUR_API_HASH'\n"
        f"session_str = '''{session_string}'''\n\n"
        f"client = TelegramClient(StringSession(session_str), api_id, api_hash)\n"
        f"await client.start()\n\n"
        f"{'='*40}\n"
        f"SECURITY WARNING:\n"
        f"NEVER share this session string with anyone.\n"
        f"Anyone with this string can control your Telegram account.\n\n"
        f"To revoke this session go to:\n"
        f"Telegram Settings → Privacy and Security → Active Sessions\n"
        f"and terminate the session.\n"
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(file_content)

    file_message = await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(file_path, "rb"),
        filename=filename,
        caption="📄 Your session file. Keep it safe!",
    )
    user_data["file_message_id"] = file_message.message_id

    preview = session_string[:50] + "..." if len(session_string) > 50 else session_string
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Download file again", callback_data="download_file"),
        ],
        [
            InlineKeyboardButton("🗑 Delete file from server", callback_data="delete_file"),
        ],
    ]
    session_text = (
        "✅ <b>Session generated successfully!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"User: {user.first_name} {user.last_name or ''}\n"
        f"ID: <code>{user.id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Session String:</b>\n"
        f"<code>{preview}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>Keep this string secret!</b>\n"
        "Use the button below to download the full .txt file."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=session_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )

    await update_message(
        update, context,
        "🎉 <b>All done!</b> Your session string is ready.\nCheck the messages above.",
    )
    await client.disconnect()
    for key in ("client", "phone_code_hash", "session_string", "user_entity"):
        user_data.pop(key, None)

    return ConversationHandler.END


# callbacks
async def download_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    user_data = context.user_data
    file_path = user_data.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        await query.edit_message_text("❌ File no longer available on the server.")
        return
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=open(file_path, "rb"),
        filename=os.path.basename(file_path),
        caption="📄 Your session file (re-sent).",
    )
    await query.edit_message_text(query.message.text + "\n\n📂 File re-sent.")


async def delete_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    user_data = context.user_data
    file_path = user_data.get("file_path")
    if file_path and os.path.isfile(file_path):
        os.unlink(file_path)
        user_data.pop("file_path", None)
        await query.edit_message_text(query.message.text + "\n\n🗑 File deleted from server.")
    else:
        await query.edit_message_text("❌ File already removed.")


#start menu & help
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🚀 Start Generation", callback_data="start_generation")],
        [
            InlineKeyboardButton("ℹ️ How to get API credentials", callback_data="help_credentials"),
            InlineKeyboardButton("📚 Help & Commands", callback_data="help_commands"),
        ],
    ]
    text = (
    "🚀 <b>Telethon Session Generator</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Welcome boss 👋\n\n"
    "This tool helps you generate a secure "
    "<b>Telethon StringSession</b> for your Telegram account.\n\n"
    "🔒 Your session data is processed securely.\n"
    "⚙️ Perfect for userbots, automation & Telegram projects.\n\n"
    "👇 Select an option to get started:"
)
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def help_credentials_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    text = (
        "🔑 <b>How to get API credentials</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ Go to <a href='https://my.telegram.org'>my.telegram.org</a> and log in.\n"
        "2️⃣ Click on <b>API Development Tools</b>.\n"
        "3️⃣ Create an app (choose any name and short description).\n"
        "4️⃣ You will receive an <b>API ID</b> and <b>API Hash</b>.\n\n"
        "ℹ️ These credentials are required for any Telegram client."
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def help_commands_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    text = (
        "📚 <b>Available Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start – Show the main menu\n"
        "/generate – Directly start session generation\n"
        "/cancel – Abort the current operation\n"
        "/help – Show this help message"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_start")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def back_to_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🚀 Start Generation", callback_data="start_generation")],
        [
            InlineKeyboardButton("ℹ️ How to get API credentials", callback_data="help_credentials"),
            InlineKeyboardButton("📚 Help & Commands", callback_data="help_commands"),
        ],
    ]
    text = (
        "👋 <b>Welcome to the Telethon Session Generator!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose an option below:"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


#file cleanup job {as i promised }
async def cleanup_old_files(context: ContextTypes.DEFAULT_TYPE) -> None:
    dir_path = Path("generated_sessions")
    if not dir_path.exists():
        return
    now = time.time()
    for file in dir_path.iterdir():
        if file.is_file() and (now - file.stat().st_mtime) > 3600:
            try:
                file.unlink()
                logger.info("Deleted old session file: %s", file)
            except Exception as e:
                logger.warning("Failed to delete %s: %s", file, e)


#main
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("generate", entry_from_command),
            CallbackQueryHandler(entry_from_callback, pattern="^start_generation$"),
        ],
        states={
            API_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, api_id_step),
                CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
            ],
            API_HASH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, api_hash_step),
                CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
            ],
            PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_step),
                CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
            ],
            OTP_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, otp_code_step),
                CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
            ],
            TWOFA_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, twofa_password_step),
                CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_handler),
            CallbackQueryHandler(cancel_callback, pattern="^cancel$"),
        ],
        conversation_timeout=SESSION_TIMEOUT,
        per_message=False,
    )

    application.add_handler(conv_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(help_credentials_callback, pattern="^help_credentials$"))
    application.add_handler(CallbackQueryHandler(help_commands_callback, pattern="^help_commands$"))
    application.add_handler(CallbackQueryHandler(back_to_start_callback, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(download_file_callback, pattern="^download_file$"))
    application.add_handler(CallbackQueryHandler(delete_file_callback, pattern="^delete_file$"))

    Path("generated_sessions").mkdir(exist_ok=True)

    async def periodic_cleanup():
        while True:
            await asyncio.sleep(600)
            await cleanup_old_files(None)

    loop = asyncio.get_event_loop()
    loop.create_task(periodic_cleanup())

    print("Bot by yori is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    