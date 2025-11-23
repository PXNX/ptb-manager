import logging
import os
import sys


def setup_logging():
    """Configure logging for both file and container environments"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Format for log messages
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Always log to stdout (for containers and systemd)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # If not in container (no /.dockerenv or /run/.containerenv), also log to file
    is_container = os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')

    if not is_container:
        try:
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'bot.log')

            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            logging.info(f"Logging to file: {log_file}")
        except Exception as e:
            logging.warning(f"Could not setup file logging: {e}")
    else:
        logging.info("Running in container - logging to stdout only")

    return logger


log = setup_logging()
