import os

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes

from logs import log
from shell import run_command
from util import check_auth


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
async def containers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all containers"""
    try:
        containers = get_podman_containers()
        text = format_containers_list(containers)
        await update.message.reply_text(text)
    except Exception as e:
        log.error(f"Error in containers_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
