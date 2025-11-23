import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS = [int(uid) for uid in os.environ.get('ALLOWED_USER_IDS', '').split(',') if uid]
PROJECTS_BASE = os.path.expanduser('~/projects')
QUADLETS_DIR = os.path.expanduser("~/.config/containers/systemd")
PODMAN_URL = os.getenv('PODMAN_URL', '')  # e.g., tcp://host.containers.internal:8888
