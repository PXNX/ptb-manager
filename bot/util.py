from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ALLOWED_USER_IDS
from bot.logs import log


def check_auth(func):
    """Decorator to check if user is authorized"""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"

        if user_id not in ALLOWED_USER_IDS:
            log.warning(f"Unauthorized access attempt by user_id={user_id} username={username}")
            message = update.message or update.callback_query.message
            if update.callback_query:
                await update.callback_query.answer("❌ Unauthorized access", show_alert=True)
                await update.callback_query.edit_message_text("❌ Unauthorized access")
            else:
                await message.reply_text("❌ Unauthorized access")
            return None

        log.info(f"Command '{func.__name__}' executed by user_id={user_id} username={username}")
        return await func(update, context)

    return wrapper