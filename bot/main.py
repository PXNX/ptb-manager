import os
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes, Defaults, MessageHandler, filters,
)

from config import TELEGRAM_TOKEN, PROJECTS_BASE, ALLOWED_USER_IDS, QUADLETS_DIR, PODMAN_URL, IS_CONTAINER
from database import dbbackup_command
from logs import log
from podman import restart_container, stop_container, start_container, redeploy_command, start_container_command, \
    stop_command, restart_command, get_podman_containers, containers_command
from quadlet import reload_systemd_quadlets, get_quadlet_files, quadlets_command
from setup import setup_and_start_project, newproject_command, handle_message
from shell import run_command
from stats import stats_command
from util import check_auth


@check_auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🤖 <b>Podman Monitoring Bot</b>

Available commands:

/containers - List all containers

/stats - Show system resources

/logs - Get container logs

/restart - Restart a container

/stop - Stop a container

/start - Start a container

/redeploy - Redeploy a project (Linux only)

/quadlets - Manage quadlet files (Linux only)

/envfiles - View project .env files

/dbbackup - Backup PostgreSQL database

/newproject - Setup a new project (Linux only)

/help - Show this message"""
    await update.message.reply_text(welcome_text)


def get_container_logs(container_id, lines=50):
    """Get logs from a specific container"""
    cmd = f"podman logs --tail {lines} {container_id}"
    return run_command(cmd, timeout=30)


def get_full_container_logs(container_id):
    """Get full logs from a specific container with extended timeout"""
    cmd = f"podman logs {container_id}"
    return run_command(cmd, timeout=300)  # 5 minutes timeout for large logs


def get_full_container_logs_since(container_id, since='24h'):
    """Get logs from a specific container since a time period"""
    cmd = f"podman logs --since {since} {container_id}"
    return run_command(cmd, timeout=120)  # 2 minutes timeout


@check_auth
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show logs selection menu"""
    try:
        containers = get_podman_containers()

        if not containers:
            await update.message.reply_text("No containers found.")
            return

        keyboard = []
        for c in containers:
            keyboard.append([
                InlineKeyboardButton(
                    f"📄 {c['name']} ({c['id'][:8]})",
                    callback_data=f"logs_{c['id']}"
                ),
                InlineKeyboardButton(
                    "💾 Download",
                    callback_data=f"dlogsmenu_{c['id']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container:\n📄 View last 100 lines | 💾 Download options",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in logs_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


def read_file_content(file_path):
    """Read and return file content"""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        log.error(f"Error reading file {file_path}: {str(e)}")
        return f"Error reading file: {str(e)}"


def get_project_env_files():
    """Get list of .env files in project directories"""
    try:
        if not os.path.exists(PROJECTS_BASE):
            return []

        env_files = []
        for project_dir in os.listdir(PROJECTS_BASE):
            project_path = os.path.join(PROJECTS_BASE, project_dir)
            env_path = os.path.join(project_path, '.env')

            if os.path.isfile(env_path):
                stat = os.stat(env_path)
                mtime = datetime.fromtimestamp(stat.st_mtime)
                env_files.append({
                    'project': project_dir,
                    'path': env_path,
                    'modified': mtime.strftime("%Y-%m-%d %H:%M:%S")
                })

        return sorted(env_files, key=lambda x: x['project'])
    except Exception as e:
        log.error(f"Error getting .env files: {str(e)}")
        return []


@check_auth
async def envfiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show .env files menu"""
    try:
        env_files = get_project_env_files()

        if not env_files:
            await update.message.reply_text("No .env files found in project directories.")
            return

        keyboard = []
        for env in env_files:
            keyboard.append([InlineKeyboardButton(
                f"📄 {env['project']} (Modified: {env['modified']})",
                callback_data=f"env_{env['project']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a project to view its .env file:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in envfiles_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        if data.startswith('logs_'):
            container_id = data.replace('logs_', '')
            log.info(f"Fetching logs for container: {container_id}")

            # Get container name for display
            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])

            await query.edit_message_text("📥 Fetching logs... ⏳")

            logs = get_container_logs(container_id, lines=100)

            # Check if logs are empty
            if not logs or logs.strip() == "":
                await query.edit_message_text(f"📄 No logs found for {container_name}")
                return

            # Escape special characters for Markdown
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            # Split logs if too long
            max_length = 4000
            if len(logs) > max_length:
                logs = logs[-max_length:]
                logs = "... (truncated)\n\n" + logs

            # Send logs
            await query.edit_message_text(
                f"📄 *Logs for {safe_container_name}* (last 100 lines)\n\n```\n{logs}\n```",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data.startswith('dlogs_'):
            container_id = data.replace('dlogs_', '')
            log.info(f"Downloading full logs for container: {container_id}")

            # Get container name for filename
            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])

            await query.edit_message_text("📥 Preparing full log file... ⏳")

            # Get full logs
            full_logs = get_full_container_logs(container_id)

            if not full_logs or full_logs.strip() == "":
                await query.edit_message_text(f"📄 No logs found for {container_name}")
                return

            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{container_name}_{timestamp}.log"

            # Escape special characters for Markdown
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            # Send as document
            log_bytes = BytesIO(full_logs.encode('utf-8'))
            log_bytes.name = filename

            await query.edit_message_text("📤 Uploading log file...")

            await query.message.reply_document(
                document=log_bytes,
                filename=filename,
                caption=f"📋 Full logs for *{safe_container_name}*\n🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text("✅ Log file sent successfully!")

        elif data.startswith('dlogsmenu_'):
            container_id = data.replace('dlogsmenu_', '')

            # Get container name for display
            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            keyboard = [
                [InlineKeyboardButton("📅 Last 24 hours", callback_data=f"dlogs24h_{container_id}")],
                [InlineKeyboardButton("📅 Last 1 hour", callback_data=f"dlogs1h_{container_id}")],
                [InlineKeyboardButton("📋 Full logs", callback_data=f"dlogs_{container_id}")],
                [InlineKeyboardButton("◀️ Back", callback_data="back_to_logs")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"📥 *Download logs for {safe_container_name}*\n\n"
                f"Choose time range:\n"
                f"⚠️ Full logs may take a while for large files",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

        elif data.startswith('dlogs24h_'):
            container_id = data.replace('dlogs24h_', '')
            log.info(f"Downloading 24h logs for container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])

            await query.edit_message_text("📥 Preparing log file (last 24 hours)... ⏳")

            logs = get_full_container_logs_since(container_id, '24h')

            if not logs or logs.strip() == "" or "Command timed out" in logs:
                await query.edit_message_text(
                    f"❌ Failed to retrieve logs: {logs if 'Command timed out' in logs else 'No logs found'}")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{container_name}_24h_{timestamp}.log"

            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            log_bytes = BytesIO(logs.encode('utf-8'))
            log_bytes.name = filename

            await query.edit_message_text("📤 Uploading log file...")

            await query.message.reply_document(
                document=log_bytes,
                filename=filename,
                caption=f"📋 Logs for *{safe_container_name}* (last 24h)\n🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text("✅ Log file sent successfully!")

        elif data.startswith('dlogs1h_'):
            container_id = data.replace('dlogs1h_', '')
            log.info(f"Downloading 1h logs for container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])

            await query.edit_message_text("📥 Preparing log file (last hour)... ⏳")

            logs = get_full_container_logs_since(container_id, '1h')

            if not logs or logs.strip() == "" or "Command timed out" in logs:
                await query.edit_message_text(
                    f"❌ Failed to retrieve logs: {logs if 'Command timed out' in logs else 'No logs found'}")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{container_name}_1h_{timestamp}.log"

            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            log_bytes = BytesIO(logs.encode('utf-8'))
            log_bytes.name = filename

            await query.edit_message_text("📤 Uploading log file...")

            await query.message.reply_document(
                document=log_bytes,
                filename=filename,
                caption=f"📋 Logs for *{safe_container_name}* (last hour)\n🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text("✅ Log file sent successfully!")

        elif data.startswith('dlogs_'):
            container_id = data.replace('dlogs_', '')
            log.info(f"Downloading full logs for container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])

            await query.edit_message_text(
                "📥 Preparing full log file... ⏳\n\n⚠️ This may take several minutes for large logs.")

            full_logs = get_full_container_logs(container_id)

            if not full_logs or full_logs.strip() == "" or "Command timed out" in full_logs:
                await query.edit_message_text(
                    f"❌ Failed to retrieve full logs.\n\n"
                    f"{'The operation timed out. ' if 'Command timed out' in full_logs else ''}"
                    f"Try using the 24h or 1h options instead for large log files."
                )
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{container_name}_full_{timestamp}.log"

            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            log_bytes = BytesIO(full_logs.encode('utf-8'))
            log_bytes.name = filename

            await query.edit_message_text("📤 Uploading log file...")

            await query.message.reply_document(
                document=log_bytes,
                filename=filename,
                caption=f"📋 Full logs for *{safe_container_name}*\n🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )

            await query.message.reply_text("✅ Log file sent successfully!")

        elif data == 'back_to_logs':
            await query.answer()
            # Re-trigger the logs command
            await logs_command(query, context)

        elif data.startswith('restart_'):
            container_id = data.replace('restart_', '')
            log.info(f"Restarting container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            await query.edit_message_text(f"🔄 Restarting {safe_container_name}...")

            output = restart_container(container_id)

            result_text = f"✅ *{safe_container_name}* restarted successfully\n\n```\n{output}\n```"
            log.info(f"Container restarted: {container_id}")
            await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)

        elif data.startswith('stop_'):
            container_id = data.replace('stop_', '')
            log.info(f"Stopping container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            await query.edit_message_text(f"⏸ Stopping {safe_container_name}...")

            output = stop_container(container_id)

            result_text = f"✅ *{safe_container_name}* stopped successfully\n\n```\n{output}\n```"
            log.info(f"Container stopped: {container_id}")
            await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)

        elif data.startswith('start_'):
            container_id = data.replace('start_', '')
            log.info(f"Starting container: {container_id}")

            containers = get_podman_containers()
            container_name = next((c['name'] for c in containers if c['id'] == container_id), container_id[:12])
            safe_container_name = container_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(
                '`', '\\`')

            await query.edit_message_text(f"▶️ Starting {safe_container_name}...")

            output = start_container(container_id)

            result_text = f"✅ *{safe_container_name}* started successfully\n\n```\n{output}\n```"
            log.info(f"Container started: {container_id}")
            await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)

            # In your main bot file, find the redeploy button callback and replace it with:



        elif data.startswith('redeploy_'):

            service = data.replace('redeploy_', '')

            log.info(f"Redeploying service: {service}")

            if not service:
                await query.edit_message_text(f"❌ Project {service} not found")

                return

            await query.edit_message_text(f"🔄 Redeploying {service}...")

            project_path = os.path.join(PROJECTS_BASE, service)

            # Check if project directory exists

            if not os.path.exists(project_path):
                await query.edit_message_text(f"❌ Project directory not found: {project_path}")

                return

            # Step 1: Sync the project repository

            sync_steps = [

                f"cd {project_path}",

                "gh repo sync"

            ]

            sync_cmd = " && ".join(sync_steps)

            sync_output = run_command(sync_cmd, timeout=60)

            result_text = f"✅ <b>Redeploy completed for {service}</b>\n\n"

            # Check if sync had errors

            if "fatal" in sync_output.lower() or "error" in sync_output.lower():

                result_text += f"❌ Repository sync failed:\n<code>{sync_output}</code>\n\n"

            elif sync_output.strip():

                result_text += f"📥 Repository sync:\n<code>{sync_output}</code>\n\n"

            else:

                result_text += f"📥 Repository sync: Already up to date ✓\n\n"

            # Step 2: Restart the service

            if IS_CONTAINER:

                # Create a trigger file for the systemd path watcher

                trigger_dir = os.path.join(PROJECTS_BASE, '.triggers')

                os.makedirs(trigger_dir, exist_ok=True)

                import time

                trigger_file = os.path.join(trigger_dir, f"restart-{service}-{int(time.time())}.trigger")

                try:

                    with open(trigger_file, 'w') as f:

                        f.write(f"systemctl --user restart {service}\n")

                    log.info(f"Created trigger file: {trigger_file}")

                    result_text += "✅ Restart command queued via trigger file\n"

                    result_text += f"🔄 The systemd path watcher will restart {service}\n\n"

                    result_text += "The container should restart automatically in a few seconds!"


                except Exception as e:

                    log.error(f"Error creating trigger file: {e}")

                    result_text += f"\n⚠️ Could not create trigger file: {e}\n\n"

                    result_text += "Please run this command manually on your host:\n\n"

                    result_text += f"<code>systemctl --user restart {service}</code>"

            else:

                # Running on host - execute normally

                restart_cmd = f"systemctl --user restart {service}"

                restart_output = run_command(restart_cmd, timeout=30)

                if restart_output.strip():

                    result_text += f"🔄 Service restart:\n<code>{restart_output}</code>"

                else:

                    result_text += f"🔄 Service restart: Completed successfully ✓"

            log.info(f"Redeploy completed for {service}")

            await query.edit_message_text(result_text)

        elif data == 'quadlets_reload':
            log.info("Reloading quadlets")
            await query.edit_message_text("🔄 Reloading quadlets and systemd daemon...")

            output = reload_systemd_quadlets()

            result_text = "✅ *Quadlets reloaded successfully*\n\n"
            result_text += f"```\n{output}\n```"

            log.info("Quadlets reloaded")
            await query.edit_message_text(result_text, parse_mode='Markdown')

        elif data == 'quadlets_list':
            log.info("Listing quadlet files")
            quadlets = get_quadlet_files()

            if not quadlets:
                await query.edit_message_text("No quadlet files found.")
                return

            keyboard = []
            for q in quadlets:
                keyboard.append([InlineKeyboardButton(
                    f"📝 {q['name']} (Modified: {q['modified']})",
                    callback_data=f"quadlet_{q['name']}"
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Select a quadlet file to inspect:",
                reply_markup=reply_markup
            )

        elif data.startswith('quadlet_'):
            filename = data.replace('quadlet_', '')
            log.info(f"Inspecting quadlet file: {filename}")

            file_path = os.path.join(QUADLETS_DIR, filename)
            content = read_file_content(file_path)

            # Escape special characters for Markdown
            safe_filename = filename.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            # Check length
            max_length = 4000
            if len(content) > max_length:
                content = content[:max_length] + "\n... (truncated)"

            await query.edit_message_text(
                f"📝 *Quadlet: {safe_filename}*\n\n```\n{content}\n```",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data.startswith('env_'):
            project = data.replace('env_', '')
            log.info(f"Viewing .env file for project: {project}")

            env_path = os.path.join(PROJECTS_BASE, project, '.env')

            if not os.path.exists(env_path):
                await query.edit_message_text(f"❌ .env file not found for project: {project}")
                return

            content = read_file_content(env_path)

            # Escape special characters for Markdown
            safe_project = project.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            # Check length
            max_length = 4000
            if len(content) > max_length:
                content = content[:max_length] + "\n... (truncated)"

            # Warning message about sensitive data
            warning = "⚠️ *Sensitive Data Warning*\n\n"

            await query.edit_message_text(
                f"{warning}📄 *.env file for {safe_project}*\n\n```\n{content}\n```",
                parse_mode=ParseMode.MARKDOWN
            )

        elif data.startswith('setup_'):
            project_name = data.replace('setup_', '')
            log.info(f"Setting up and starting project: {project_name}")

            await query.edit_message_text(f"🔄 Setting up {project_name}...\n\nThis may take a moment.")

            output = setup_and_start_project(project_name)

            result_text = f"✅ *Setup completed for {project_name}*\n\n"
            result_text += f"The container should now be starting.\n\n"
            result_text += f"```\n{output}\n```\n\n"
            result_text += f"Use /containers to check the status."

            log.info(f"Setup completed for {project_name}")
            await query.edit_message_text(result_text, parse_mode='Markdown')

        elif data == 'setup_done':
            await query.edit_message_text(
                "✅ Project setup complete!\n\n"
                "You can now manually configure your project or use the other bot commands to manage it."
            )

    except Exception as e:
        log.error(f"Error in button_callback: {str(e)}", exc_info=True)
        await query.edit_message_text(f"❌ Error: {str(e)}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    try:
        # Log the full error with traceback
        log.error(f"Update {update} caused error: {context.error}", exc_info=context.error)

        error_message = f"❌ An error occurred: {str(context.error)}"

        if update and update.effective_message:
            await update.effective_message.reply_text(error_message)

    except Exception as e:
        log.error(f"Error in error handler: {e}", exc_info=True)


def main():
    """Start the bot"""
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN environment variable not set")
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    log.info("Starting Podman Monitoring Bot...")
    log.info(f"Allowed user IDs: {ALLOWED_USER_IDS}")
    log.info(f"Operating System: {os.name}")
    if PODMAN_URL:
        log.info(f"Podman URL: {PODMAN_URL}")

    defaults = Defaults(parse_mode=ParseMode.HTML)
    application = Application.builder().token(TELEGRAM_TOKEN).defaults(defaults).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("containers", containers_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("start", start_container_command))
    application.add_handler(CommandHandler("redeploy", redeploy_command))
    application.add_handler(CommandHandler("quadlets", quadlets_command))
    application.add_handler(CommandHandler("envfiles", envfiles_command))
    application.add_handler(CommandHandler("dbbackup", dbbackup_command))
    application.add_handler(CommandHandler("newproject", newproject_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


    # Callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Error handler
    application.add_error_handler(error_handler)

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    except Exception as e:
        log.error(f"Bot crashed: {str(e)}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
