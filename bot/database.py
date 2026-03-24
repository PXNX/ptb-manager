import os
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from logs import log
from shell import run_command
from util import check_auth
from podman import get_podman_containers


def backup_postgres_database(container_name='pg', db_user='postgres'):
    """Create PostgreSQL database backup"""
    try:
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{container_name}_backup_{timestamp}.sql"

        # Create backup using pg_dumpall
        # We use -U to specify the user, defaults to postgres
        cmd = f"podman exec {container_name} pg_dumpall -U {db_user}"
        backup_data = run_command(cmd, timeout=300) # Increased timeout for large DBs

        if backup_data and not any(x in backup_data.lower() for x in ["error", "failed", "denied", "not found"]):
            return backup_data, backup_filename
        else:
            log.error(f"Backup failed or returned error: {backup_data}")
            return None, None
    except Exception as e:
        log.error(f"Error creating database backup: {str(e)}")
        return None, None


@check_auth
async def dbbackup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show database backup selection menu"""
    try:
        containers = get_podman_containers()
        
        # Filter for containers that might be databases (containing 'pg', 'db', 'postgres')
        db_containers = [c for c in containers if any(x in c['name'].lower() for x in ['pg', 'db', 'postgres'])]
        
        if not db_containers:
            # Fallback to show all containers if no obvious DB found
            db_containers = containers

        if not db_containers:
            await update.message.reply_text("No containers found.")
            return

        keyboard = []
        for c in db_containers:
            keyboard.append([
                InlineKeyboardButton(
                    f"📦 Backup {c['name']}",
                    callback_data=f"dbbackup_{c['name']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container to backup its PostgreSQL database:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in dbbackup_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def handle_db_backup(query, container_name):
    """Execute the actual backup and send to user"""
    try:
        await query.edit_message_text(f"📦 Creating database backup for {container_name}... ⏳")
        
        # Determine user - default to postgres, but could be customized
        db_user = 'postgres'
        if 'ptb-' in container_name:
            db_user = 'ptb_user'
            
        backup_data, filename = backup_postgres_database(container_name, db_user)

        if backup_data and filename:
            # Send as document
            backup_bytes = BytesIO(backup_data.encode('utf-8'))
            backup_bytes.name = filename

            await query.message.reply_document(
                document=backup_bytes,
                filename=filename,
                caption=f"🗄 PostgreSQL Backup: {container_name}\n🕐 Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await query.edit_message_text(f"✅ Backup for {container_name} completed!")
        else:
            # If backup_postgres_database returns None, it means it failed
            # We should have logged the error in backup_postgres_database
            await query.edit_message_text(
                f"❌ Failed to create backup for {container_name}.\n"
                f"Possible reasons: container not running, wrong DB user, or pg_dumpall not available.")
    except Exception as e:
        log.error(f"Error in handle_db_backup: {str(e)}", exc_info=True)
        await query.edit_message_text(f"❌ Error: {str(e)}")


async def handle_db_upload(query, container_name):
    """Upload database dump to a remote destination (e.g. via gh or s3)"""
    # This is a placeholder for actual upload logic
    # For now, we can implement an upload to a GitHub gist or similar if gh is configured
    try:
        await query.edit_message_text(f"🚀 Preparing upload for {container_name}... ⏳")
        
        db_user = 'postgres'
        if 'ptb-' in container_name:
            db_user = 'ptb_user'
            
        backup_data, filename = backup_postgres_database(container_name, db_user)
        
        if not backup_data:
            await query.edit_message_text(f"❌ Failed to create dump for upload.")
            return

        # Save temporarily to disk for upload
        temp_path = f"/tmp/{filename}"
        with open(temp_path, "w") as f:
            f.write(backup_data)
            
        # Example: Upload using GitHub CLI as a secret gist
        await query.edit_message_text(f"📤 Uploading {filename} to GitHub Gist... ⏳")
        cmd = f"gh gist create {temp_path} -d 'Database Backup {container_name} {datetime.now()}'"
        gist_url = run_command(cmd)
        
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if gist_url and gist_url.startswith("https://"):
            await query.edit_message_text(f"✅ Uploaded successfully!\n🔗 {gist_url.strip()}")
        else:
            await query.edit_message_text(f"❌ Upload failed: {gist_url}")
            
    except Exception as e:
        log.error(f"Error in handle_db_upload: {str(e)}", exc_info=True)
        await query.edit_message_text(f"❌ Error during upload: {str(e)}")
