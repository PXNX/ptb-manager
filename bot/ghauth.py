from telegram import Update
from telegram.ext import ContextTypes

from github_auth import get_token, remove_token, set_token, verify_github_token
from logs import log
from util import check_auth


async def _try_delete(update: Update):
    """Best-effort: remove the message that carried the raw token from the
    chat. Telegram bots can't delete arbitrary user messages in private
    chats, so this often silently fails - that's fine."""
    try:
        await update.message.delete()
    except Exception:
        pass


@check_auth
async def ghauth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link, inspect, or remove the caller's personal GitHub token"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        token = get_token(user_id)
        if not token:
            await update.message.reply_text(
                "🔑 You haven't linked a GitHub token yet.\n\n"
                "1. Go to https://github.com/settings/tokens/new to create one\n"
                "2. Give it the <code>repo</code> scope (clone/sync repos) and "
                "<code>gist</code> scope (needed for /dbbackup uploads) — a classic "
                "token with just those two is simplest\n"
                "3. Send it here as:\n"
                "<code>/ghauth ghp_xxxxxxxx</code>\n\n"
                "⚠️ Only send it in a private chat with the bot."
            )
            return

        ok, info = verify_github_token(token)
        status = f"✅ authenticated as <code>{info}</code>" if ok else f"⚠️ stored token is no longer valid ({info})"
        await update.message.reply_text(
            f"🔑 You have a GitHub token on file.\n{status}\n\n"
            f"Send <code>/ghauth &lt;token&gt;</code> to replace it, or <code>/ghauth revoke</code> to remove it."
        )
        return

    if args[0].lower() in ('revoke', 'remove', 'clear'):
        removed = remove_token(user_id)
        await update.message.reply_text("🗑 GitHub token removed." if removed else "You had no token on file.")
        return

    token = args[0].strip()
    await _try_delete(update)

    ok, info = verify_github_token(token)
    if not ok:
        await update.message.reply_text(f"❌ That token doesn't look valid: {info}\nPlease try again.")
        return

    set_token(user_id, token)
    log.info(f"Stored GitHub token for user_id={user_id} (github user: {info})")
    await update.message.reply_text(
        f"✅ GitHub token saved and linked to your account (GitHub user: <code>{info}</code>).\n\n"
        f"⚠️ If this chat isn't private, delete your message with the token now."
    )


async def require_token(message_target, user_id):
    """Fetch the caller's token, or tell them to link one first.

    `message_target` is anything with a reply_text/edit_message_text
    coroutine - i.e. update.message or a callback query's message.
    Returns the token, or None if the caller needs to /ghauth first.
    """
    token = get_token(user_id)
    if not token:
        await message_target(
            "🔑 You need to link a GitHub token first.\n"
            "Create one at https://github.com/settings/tokens/new (with the "
            "<code>repo</code> and <code>gist</code> scopes), then send it here as "
            "<code>/ghauth &lt;token&gt;</code> in a private chat, then try again."
        )
        return None
    return token
