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

        # Check if we have a DATABASE_URL for this container in environment
        # Map container names to env var names
        env_map = {
            'ptb-mn': 'DATABASE_URL',
            'ptb-nn': 'DATABASE_URL_NN'
        }
        
        db_url = os.environ.get(env_map.get(container_name, ''))
        
        if db_url:
            log.info(f"Using DATABASE_URL for external backup of {container_name}")
            # Use pg_dump directly from the manager container for external databases
            # We use --no-owner and --no-privileges to make it more portable
            # IMPORTANT: We use pg_dump directly, NOT via podman exec
            # We use force_local=True to ensure it runs inside the manager container
            cmd = f"pg_dump \"{db_url}\" --no-owner --no-privileges"
            backup_data = run_command(cmd, timeout=300, force_local=True)
            
            # Check if pg_dump command was not found
            if "not found" in backup_data.lower() or "no such file" in backup_data.lower():
                log.error(f"pg_dump not found in manager container: {backup_data}")
                return f"ERROR: pg_dump is not installed in the manager container. Please ensure postgresql-client is installed in the container.", None
        else:
            # Fallback to podman exec for local containers
            log.info(f"Using podman exec for local backup of {container_name}")
            # We try pg_dumpall first, then pg_dump as fallback
            cmd = f"podman exec {container_name} pg_dumpall -U {db_user}"
            backup_data = run_command(cmd, timeout=300)
            
            if "not found" in backup_data.lower() or "no such file" in backup_data.lower():
                log.info(f"pg_dumpall not found in container {container_name}, trying pg_dump...")
                cmd = f"podman exec {container_name} pg_dump -U {db_user}"
                backup_data = run_command(cmd, timeout=300)

        if backup_data and not any(x in backup_data.lower() for x in ["error", "failed", "denied", "not found", "no such file"]):
            return backup_data, backup_filename
        else:
            log.error(f"Backup failed or returned error: {backup_data}")
            # Return the error message so it can be shown to the user
            return f"ERROR: {backup_data}", None
    except Exception as e:
        log.error(f"Error creating database backup: {str(e)}")
        return f"ERROR: {str(e)}", None


@check_auth
async def dbbackup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show database backup selection menu"""
    try:
        containers = get_podman_containers()
        
        # Filter for containers that might be databases (containing 'pg', 'db', 'postgres')
        db_containers = [c for c in containers if any(x in c['name'].lower() for x in ['pg', 'db', 'postgres'])]
        
        # Always add ptb-mn and ptb-nn if they are not in the list (since they are external)
        known_external = ['ptb-mn', 'ptb-nn']
        existing_names = [c['name'] for c in containers]
        
        for ext in known_external:
            if ext not in existing_names:
                db_containers.append({'name': ext, 'id': 'external', 'status': 'External'})

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
            "Select a container or database to backup:",
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

        if filename and backup_data:
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
            # backup_data contains the error message if filename is None
            error_msg = backup_data if backup_data else "Unknown error"
            await query.edit_message_text(
                f"❌ Failed to create backup for {container_name}.\n\n"
                f"Details: `{error_msg}`")
    except Exception as e:
        log.error(f"Error in handle_db_backup: {str(e)}", exc_info=True)
        await query.edit_message_text(f"❌ Error: {str(e)}")


async def handle_db_upload(query, container_name):
    """Upload database dump to a remote destination (e.g. via gh or s3)"""
    try:
        await query.edit_message_text(f"🚀 Preparing upload for {container_name}... ⏳")
        
        db_user = 'postgres'
        if 'ptb-' in container_name:
            db_user = 'ptb_user'
            
        backup_data, filename = backup_postgres_database(container_name, db_user)
        
        if not filename:
            await query.edit_message_text(f"❌ Failed to create dump for upload: {backup_data}")
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
