"""
Error Logger Module for PTB-MANAGER: Posts errors to Telegram group topics and console.
"""

import logging
import traceback
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
from config import LOG_GROUP_ID, THREAD_ID, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)


class ErrorLogger:
    """Handles error logging to both Telegram topics and console logs."""
    
    def __init__(self):
        self.log_group_id = LOG_GROUP_ID
        self.thread_id = THREAD_ID
        self.bot = Bot(token=TELEGRAM_TOKEN)
    
    async def log_error(self, error: Exception, context_msg: Optional[str] = None) -> None:
        """Log an error to both Telegram group topic and console logs."""
        error_trace = traceback.format_exc()
        logger.error(f"[ERROR] {context_msg or 'Unhandled exception'}\n{error_trace}")
        
        if self.log_group_id and self.thread_id:
            try:
                error_msg = self._format_error_message(error, context_msg, error_trace)
                await self.bot.send_message(
                    chat_id=self.log_group_id,
                    message_thread_id=self.thread_id,
                    text=error_msg,
                    parse_mode="HTML"
                )
            except TelegramError as tg_error:
                logger.error(f"Failed to post error to Telegram group topic: {tg_error}")
            except Exception as e:
                logger.error(f"Unexpected error while logging to Telegram: {e}")
    
    def _format_error_message(self, error: Exception, context_msg: Optional[str], trace: str) -> str:
        """Format error message for Telegram."""
        msg = "🚨 <b>Bot Error (PTB-MANAGER)</b>\n\n"
        if context_msg:
            msg += f"<b>Context:</b> {context_msg}\n\n"
        msg += f"<b>Error Type:</b> <code>{type(error).__name__}</code>\n"
        msg += f"<b>Message:</b> <code>{str(error)}</code>\n\n"
        trace_lines = trace.split('\n')[-5:]
        trace_text = '\n'.join(trace_lines)
        msg += f"<b>Traceback (last lines):</b>\n<pre>{trace_text}</pre>"
        return msg


_error_logger: Optional[ErrorLogger] = None


def get_error_logger() -> ErrorLogger:
    """Get or create the global error logger instance."""
    global _error_logger
    if _error_logger is None:
        _error_logger = ErrorLogger()
    return _error_logger
