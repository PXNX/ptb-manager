import os
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import QUADLETS_DIR
from logs import log
from shell import run_command
from util import check_auth


def get_quadlet_files():
    """Get list of quadlet files with their modification times"""
    try:
        if not os.path.exists(QUADLETS_DIR):
            return []

        quadlets = []
        for file in Path(QUADLETS_DIR).glob("*.container"):
            stat = file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)
            quadlets.append({
                'name': file.name,
                'path': str(file),
                'modified': mtime.strftime("%Y-%m-%d %H:%M:%S")
            })

        # Sort by modification time (newest first)
        quadlets.sort(key=lambda x: x['modified'], reverse=True)
        return quadlets
    except Exception as e:
        log.error(f"Error getting quadlet files: {str(e)}")
        return []


def update_quadlets_repo():
    """Sync quadlets repository from GitHub"""
    try:
        cmd = f"cd {QUADLETS_DIR} && gh repo sync"
        output = run_command(cmd, timeout=60)
        return output
    except Exception as e:
        log.error(f"Error updating quadlets repo: {str(e)}")
        return f"Error: {str(e)}"


def reload_systemd_quadlets():
    """Reload systemd daemon after quadlet changes"""
    try:
        # We don't do 'gh repo sync' here anymore as it's a separate step now
        cmd = "systemctl --user daemon-reload"
        output = run_command(cmd)
        return output
    except Exception as e:
        log.error(f"Error reloading quadlets: {str(e)}")
        return f"Error: {str(e)}"


@check_auth
async def quadlets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quadlets management menu"""
    try:
        if os.name == 'nt':
            await update.message.reply_text(
                "❌ Quadlets management is not supported on Windows."
            )
            return

        keyboard = [
            [InlineKeyboardButton("📥 Update from GitHub", callback_data="quadlets_update")],
            [InlineKeyboardButton("🔄 Reload Systemd", callback_data="quadlets_reload")],
            [InlineKeyboardButton("📋 List Quadlet Files", callback_data="quadlets_list")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔧 <b>Quadlets Management</b>\n\nWhat would you like to do?",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in quadlets_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
