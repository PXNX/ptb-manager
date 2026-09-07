import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
# Tolerate both `1,2,3` and a Python/JSON-list-looking `[1,2,3]` in the .env,
# since a restart (e.g. via /redeploy) previously never actually happened in
# practice, letting a bracketed value sit unnoticed until it crash-looped
# the bot on the next real restart.
ALLOWED_USER_IDS = [
    int(uid.strip().strip('[]').strip('"\''))
    for uid in os.environ.get('ALLOWED_USER_IDS', '').split(',')
    if uid.strip().strip('[]').strip('"\'')
]

LOG_GROUP_ID = int(os.environ.get('LOG_GROUP_ID', -1001338514957))
THREAD_ID = int(os.environ.get('THREAD_ID', 490))  # PTB-MANAGER topic

PODMAN_URL = os.getenv('PODMAN_URL', '')  # e.g., tcp://host.containers.internal:8888
DEFAULT_GITHUB_ORG = os.getenv('DEFAULT_GITHUB_ORG', 'PXNX')
PODMAN_CMD = os.getenv('PODMAN_CMD', '/usr/bin/podman')
HOST_USER = os.getenv('HOST_USER', 'nyx')  # Username on the host system

IS_CONTAINER = os.getenv('CONTAINER') == 'true' or os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')
PODMAN_SOCK = os.getenv('PODMAN_SOCK', '/run/podman/podman.sock')

# Use containerized paths if running in container, otherwise use host paths
if IS_CONTAINER:
    PROJECTS_BASE = os.getenv('PROJECTS_BASE', '/host/projects')
    QUADLETS_DIR = os.getenv('QUADLETS_DIR', '/host/quadlets')
else:
    PROJECTS_BASE = os.path.expanduser(os.getenv('PROJECTS_BASE', '~/projects'))
    QUADLETS_DIR = os.path.expanduser('~/.config/containers/systemd')

# Per-Telegram-user GitHub tokens, stored outside any git-managed project
# directory (PROJECTS_BASE is a sibling of the ptb-manager repo checkout).
GITHUB_TOKENS_FILE = os.path.join(PROJECTS_BASE, '.ptb-manager-data', 'github_tokens.json')