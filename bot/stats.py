import os
from datetime import datetime

import psutil
from telegram import Update
from telegram.ext import ContextTypes

from bot.logs import log
from bot.util import check_auth


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


@check_auth
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system statistics"""
    try:
        stats = get_system_stats()
        await update.message.reply_text(stats)
    except Exception as e:
        log.error(f"Error in stats_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
