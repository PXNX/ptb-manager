import os
import subprocess
from datetime import datetime

import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from bot.config import TELEGRAM_TOKEN, PROJECTS_BASE, ALLOWED_USER_IDS
from bot.logs import log
from bot.util import check_auth


def run_command(cmd):
    """Execute shell command and return output"""
    try:
        log.debug(f"Executing command: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
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
    cmd = "podman ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'"
    output = run_command(cmd)

    containers = []
    for line in output.strip().split('\n'):
        if line:
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


def get_system_stats():
    """Get system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()

        # Get disk usage - use C: on Windows, / on Unix
        disk_path = r'C:\\' if os.name == 'nt' else '/'

        disk = psutil.disk_usage(disk_path)

        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        stats = f"""
🖥 <b>System Resources</b>

<b>CPU Usage:</b> {cpu_percent}%
<b>Memory:</b> {memory.percent}% ({memory.used // (1024 ** 3)}GB / {memory.total // (1024 ** 3)}GB)
<b>Disk ({disk_path}):</b> {disk.percent}% ({disk.used // (1024 ** 3)}GB / {disk.total // (1024 ** 3)}GB)
<b>Uptime:</b> {uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m
"""
        return stats
    except Exception as e:
        log.error(f"Error getting system stats: {str(e)}", exc_info=True)
        return f"❌ Error getting system stats: {str(e)}"


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
/redeploy - Redeploy a project
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
            keyboard.append([InlineKeyboardButton(
                f"{c['name']} ({c['id'][:8]})",
                callback_data=f"logs_{c['id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select a container to view logs:",
            reply_markup=reply_markup
        )
    except Exception as e:
        log.error(f"Error in logs_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def redeploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show redeploy menu"""
    try:
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
            await query.edit_message_text("Fetching logs... ⏳")

            logs = get_container_logs(container_id)

            # Split logs if too long
            max_length = 4000
            if len(logs) > max_length:
                logs = logs[-max_length:]
                logs = "... (truncated)\n\n" + logs

            await query.edit_message_text(f"```\n{logs}\n```", parse_mode='Markdown')

        elif data.startswith('redeploy_'):
            service = data.replace('redeploy_', '')
            log.info(f"Redeploying service: {service}")

            if not service:
                await query.edit_message_text(f"❌ Project {service} not found")
                return

            await query.edit_message_text(f"🔄 Redeploying {service}...")

            project_path = os.path.join(PROJECTS_BASE, service)

            # Execute redeploy steps
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

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("containers", containers_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("logs", logs_command))
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