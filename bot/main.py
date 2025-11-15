import os
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO

import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from bot.config import TELEGRAM_TOKEN, PROJECTS_BASE, ALLOWED_USER_IDS
from bot.logs import log
from bot.util import check_auth

from bot.config import TELEGRAM_TOKEN, PROJECTS_BASE, ALLOWED_USER_IDS
from bot.logs import log
from bot.util import check_auth

# Podman connection settings for Windows
PODMAN_URL = os.getenv('PODMAN_URL', '')  # e.g., tcp://host.containers.internal:8888


def run_command(cmd):
    """Execute shell command and return output"""
    try:
        # Add Podman URL if set and command starts with 'podman'
        if PODMAN_URL and cmd.strip().startswith('podman'):
            cmd = cmd.replace('podman', f'podman --url {PODMAN_URL}', 1)

        log.debug(f"Executing command: {cmd}")

        # On Windows, use shell=True, on Unix use bash
        if os.name == 'nt':
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                executable='/bin/bash'
            )

        if result.returncode != 0:
            log.error(f"Command failed with return code {result.returncode}: {result.stderr}")
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        log.error(f"Command timed out: {cmd}")
        return "Command timed out"
    except Exception as e:
        log.error(f"Command execution error: {str(e)}")
        return f"Error: {str(e)}"


def get_podman_containers():
    """Get list of Podman containers with their status"""
    # Use double quotes for Windows compatibility
    if os.name == 'nt':
        cmd = 'podman ps -a --format "{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}"'
    else:
        cmd = "podman ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'"

    output = run_command(cmd)

    containers = []
    for line in output.strip().split('\n'):
        if line and '|' in line:
            parts = line.split('|')
            if len(parts) == 4:
                containers.append({
                    'id': parts[0][:12],
                    'name': parts[1],
                    'status': parts[2],
                    'image': parts[3]
                })
    return containers


def get_container_logs(container_id, lines=50):
    """Get logs from a specific container"""
    cmd = f"podman logs --tail {lines} {container_id}"
    return run_command(cmd)


def get_full_container_logs(container_id):
    """Get full logs from a specific container"""
    cmd = f"podman logs {container_id}"
    return run_command(cmd)


def restart_container(container_id):
    """Restart a container"""
    cmd = f"podman restart {container_id}"
    return run_command(cmd)


def stop_container(container_id):
    """Stop a container"""
    cmd = f"podman stop {container_id}"
    return run_command(cmd)


def start_container(container_id):
    """Start a container"""
    cmd = f"podman start {container_id}"
    return run_command(cmd)


def get_system_stats():
    """Get system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        # Get disk usage - try multiple methods for Windows compatibility
        disk_display = 'System'
        try:
            if os.name == 'nt':
                # Try different Windows paths
                for path in ['C:/', 'C:', os.path.expanduser('~')]:
                    try:
                        disk = psutil.disk_usage(path)
                        disk_display = path
                        break
                    except:
                        continue
                else:
                    # If all fail, get first partition
                    partitions = psutil.disk_partitions()
                    if partitions:
                        disk = psutil.disk_usage(partitions[0].mountpoint)
                        disk_display = partitions[0].mountpoint
                    else:
                        raise Exception("No disk partitions found")
            else:
                disk = psutil.disk_usage('/')
                disk_display = '/'
        except Exception as disk_error:
            # If disk check fails, set dummy values
            log.warning(f"Could not get disk usage: {disk_error}")

            class DummyDisk:
                percent = 0
                used = 0
                total = 0

            disk = DummyDisk()
            disk_display = 'N/A'

        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        stats = f"""
🖥 <b>System Resources</b>

<b>CPU Usage:</b> {cpu_percent}%
<b>Memory:</b> {memory.percent}% ({memory.used // (1024 ** 3)}GB / {memory.total // (1024 ** 3)}GB)
<b>Disk ({disk_display}):</b> {disk.percent}% ({disk.used // (1024 ** 3)}GB / {disk.total // (1024 ** 3)}GB)
<b>Uptime:</b> {uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m
"""
        return stats
    except Exception as e:
        log.error(f"Error getting system stats: {str(e)}", exc_info=True)
        # Escape any HTML-like characters in error message
        error_msg = str(e).replace('<', '&lt;').replace('>', '&gt;')
        return f"❌ Error getting system stats: {error_msg}"


def format_containers_list(containers):
    """Format containers list for display"""
    if not containers:
        return "No containers found."

    text = "🐳 <b>Podman Containers</b>\n\n"
    for c in containers:
        status_emoji = "🟢" if "Up" in c['status'] else "🔴"
        text += f"{status_emoji} <b>{c['name']}</b>\n"
        text += f"  ID: <code>{c['id']}</code>\n"
        text += f"  Status: {c['status']}\n"
        text += f"  Image: {c['image']}\n\n"

    return text


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
/help - Show this message
"""
    await update.message.reply_text(welcome_text, parse_mode='HTML')


@check_auth
async def containers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all containers"""
    try:
        containers = get_podman_containers()
        text = format_containers_list(containers)
        await update.message.reply_text(text, parse_mode='HTML')
    except Exception as e:
        log.error(f"Error in containers_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system statistics"""
    try:
        stats = get_system_stats()
        await update.message.reply_text(stats, parse_mode='HTML')
    except Exception as e:
        log.error(f"Error in stats_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


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
                    callback_data=f"dlogs_{c['id']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container:\n📄 View last 100 lines | 💾 Download full log",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in logs_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show restart menu"""
    try:
        containers = get_podman_containers()

        if not containers:
            await update.message.reply_text("No containers found.")
            return

        keyboard = []
        for c in containers:
            keyboard.append([InlineKeyboardButton(
                f"{c['name']} ({c['id'][:8]})",
                callback_data=f"restart_{c['id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container to restart:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in restart_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stop menu"""
    try:
        containers = get_podman_containers()

        if not containers:
            await update.message.reply_text("No containers found.")
            return

        # Only show running containers
        running_containers = [c for c in containers if "Up" in c['status']]

        if not running_containers:
            await update.message.reply_text("No running containers found.")
            return

        keyboard = []
        for c in running_containers:
            keyboard.append([InlineKeyboardButton(
                f"{c['name']} ({c['id'][:8]})",
                callback_data=f"stop_{c['id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container to stop:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in stop_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def start_container_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show start menu"""
    try:
        containers = get_podman_containers()

        if not containers:
            await update.message.reply_text("No containers found.")
            return

        # Only show stopped containers
        stopped_containers = [c for c in containers if "Up" not in c['status']]

        if not stopped_containers:
            await update.message.reply_text("No stopped containers found.")
            return

        keyboard = []
        for c in stopped_containers:
            keyboard.append([InlineKeyboardButton(
                f"{c['name']} ({c['id'][:8]})",
                callback_data=f"start_{c['id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container to start:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in start_container_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def redeploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show redeploy menu (Linux/systemd only)"""
    try:
        if os.name == 'nt':
            await update.message.reply_text(
                "❌ Redeploy command is not supported on Windows.\n"
                "Use /restart to restart containers instead."
            )
            return

        containers = get_podman_containers()

        if not containers:
            await update.message.reply_text("No containers found.")
            return

        keyboard = []
        for c in containers:
            keyboard.append([InlineKeyboardButton(
                c['name'],
                callback_data=f"redeploy_{c['name']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a project to redeploy:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in redeploy_command: {str(e)}", exc_info=True)
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

        elif data.startswith('redeploy_'):
            service = data.replace('redeploy_', '')
            log.info(f"Redeploying service: {service}")

            if not service:
                await query.edit_message_text(f"❌ Project {service} not found")
                return

            await query.edit_message_text(f"🔄 Redeploying {service}...")

            project_path = os.path.join(PROJECTS_BASE, service)

            # Execute redeploy steps (Linux/systemd only)
            steps = [
                f"cd {project_path}",
                "gh repo sync",
                f"systemctl --user restart {service}"
            ]

            full_cmd = " && ".join(steps)
            output = run_command(full_cmd)

            result_text = f"✅ *Redeploy completed for {service}*\n\n"
            result_text += f"```\n{output}\n```"

            log.info(f"Redeploy completed for {service}")
            await query.edit_message_text(result_text, parse_mode='Markdown')

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

    application = Application.builder().token(TELEGRAM_TOKEN).build()

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