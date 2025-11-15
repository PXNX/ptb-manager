import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS = [int(uid) for uid in os.environ.get('ALLOWED_USER_IDS', '').split(',') if uid]
PROJECTS_BASE = os.path.expanduser('~/projects')