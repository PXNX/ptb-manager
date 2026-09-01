"""
Health Monitoring for PTB-MANAGER: watches the fleet's systemd units for
failures and crash-restart loops, and proactively alerts admins instead of
requiring someone to notice manually.
"""

import os

from telegram import Update
from telegram.ext import ContextTypes

from config import ALLOWED_USER_IDS
from logs import log
from shell import run_command
from util import check_auth

# Unit name globs to watch. systemd resolves these against installed units.
WATCHED_UNIT_GLOBS = ["ptb-*", "pg*", "tg-*"]

# A unit counts as "in trouble" if its ACTIVE/SUB state matches one of these -
# either a hard failure, or systemd currently mid-crash-loop restarting it.
TROUBLED_SUB_STATES = {"failed", "auto-restart"}


def get_unit_states():
    """Return a list of {unit, active, sub} for all watched systemd user units."""
    if os.name == 'nt':
        return []

    globs = " ".join(f"'{g}'" for g in WATCHED_UNIT_GLOBS)
    cmd = f"systemctl --user list-units --all {globs} --no-legend --plain --no-pager"
    output = run_command(cmd, timeout=30)

    units = []
    for line in output.strip().split('\n'):
        parts = line.split()
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        if not unit.endswith(".service"):
            continue
        units.append({"unit": unit, "load": load, "active": active, "sub": sub})
    return units


def format_health(units) -> str:
    """Format a full health overview for /health."""
    if not units:
        return "⚠️ No matching systemd units found (or unsupported on this OS)."

    troubled = [u for u in units if u["sub"] in TROUBLED_SUB_STATES]
    healthy = [u for u in units if u["sub"] not in TROUBLED_SUB_STATES]

    lines = ["🩺 <b>Fleet Health</b>\n"]

    if troubled:
        lines.append("🔴 <b>Needs attention:</b>")
        for u in troubled:
            lines.append(f"  • <code>{u['unit']}</code>: {u['active']} ({u['sub']})")
        lines.append("")

    lines.append(f"🟢 <b>Healthy:</b> {len(healthy)}/{len(units)} units")
    for u in healthy:
        lines.append(f"  • <code>{u['unit']}</code>: {u['active']} ({u['sub']})")

    return "\n".join(lines)


@check_auth
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current systemd health for all watched units."""
    try:
        if os.name == 'nt':
            await update.message.reply_text("❌ Health monitoring is not supported on Windows.")
            return

        units = get_unit_states()
        await update.message.reply_text(format_health(units))
    except Exception as e:
        log.error(f"Error in health_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def check_health_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Scheduled job: alert admins the moment a unit starts failing or
    crash-looping, and again once it recovers. Only fires on state
    *changes* - a still-broken unit doesn't re-alert every cycle.
    """
    if os.name == 'nt':
        return

    try:
        units = get_unit_states()
    except Exception as e:
        log.error(f"[health] Failed to fetch unit states: {e}", exc_info=True)
        return

    troubled_now = {u["unit"] for u in units if u["sub"] in TROUBLED_SUB_STATES}
    troubled_before = context.bot_data.get("troubled_units", set())

    newly_troubled = troubled_now - troubled_before
    recovered = troubled_before - troubled_now

    if not newly_troubled and not recovered:
        context.bot_data["troubled_units"] = troubled_now
        return

    lines = []
    if newly_troubled:
        lines.append("🚨 <b>Service trouble detected:</b>")
        for unit in sorted(newly_troubled):
            state = next((u for u in units if u["unit"] == unit), None)
            detail = f"{state['active']} ({state['sub']})" if state else "unknown"
            lines.append(f"  • <code>{unit}</code>: {detail}")

    if recovered:
        if lines:
            lines.append("")
        lines.append("✅ <b>Recovered:</b>")
        for unit in sorted(recovered):
            lines.append(f"  • <code>{unit}</code>")

    message = "\n".join(lines)
    log.info(f"[health] State change - {message}")

    for admin_id in ALLOWED_USER_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message)
        except Exception as e:
            log.error(f"[health] Failed to alert admin {admin_id}: {e}")

    context.bot_data["troubled_units"] = troubled_now
