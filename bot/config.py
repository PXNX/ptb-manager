import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS = [int(uid) for uid in os.environ.get('ALLOWED_USER_IDS', '').split(',') if uid]

PODMAN_URL = os.getenv('PODMAN_URL', '')  # e.g., tcp://host.containers.internal:8888
DEFAULT_GITHUB_ORG = os.getenv('DEFAULT_GITHUB_ORG', 'PXNX')
PODMAN_CMD = os.getenv('PODMAN_CMD', '/usr/bin/podman')

# Use containerized paths if running in container, otherwise use host paths
if os.getenv('CONTAINER') == 'true':
    PROJECTS_BASE = os.getenv('PROJECTS_BASE', '/host/projects')
    QUADLETS_DIR = os.getenv('QUADLETS_DIR', '/host/quadlets')
else:
    PROJECTS_BASE = os.path.expanduser(os.getenv('PROJECTS_BASE', '~/projects'))
    QUADLETS_DIR = os.path.expanduser('~/.config/containers/systemd')
