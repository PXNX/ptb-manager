from datetime import datetime
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

from bot.logs import log
from bot.shell import run_command
from bot.util import check_auth


def backup_postgres_database(container_name='pg'):
    """Create PostgreSQL database backup"""
    try:
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"postgres_backup_{timestamp}.sql"

        # Create backup using pg_dumpall
        cmd = f"podman exec {container_name} pg_dumpall -U postgres"
        backup_data = run_command(cmd)

        if backup_data and not backup_data.startswith("Error"):
            return backup_data, backup_filename
        else:
            return None, None
    except Exception as e:
        log.error(f"Error creating database backup: {str(e)}")
        return None, None


@check_auth
async def dbbackup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create and send PostgreSQL database backup"""
    try:
        await update.message.reply_text("📦 Creating database backup... This may take a moment.")

        backup_data, filename = backup_postgres_database()

        if backup_data and filename:
            # Send as document
            backup_bytes = BytesIO(backup_data.encode('utf-8'))
            backup_bytes.name = filename

            await update.message.reply_document(
                document=backup_bytes,
                filename=filename,
                caption=f"🗄 PostgreSQL Database Backup\n🕐 Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await update.message.reply_text("✅ Database backup created successfully!")
        else:
            await update.message.reply_text(
                "❌ Failed to create database backup. Check if the PostgreSQL container is running.")
    except Exception as e:
        log.error(f"Error in dbbackup_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error creating backup: {str(e)}")
