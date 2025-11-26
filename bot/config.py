import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS = [int(uid) for uid in os.environ.get('ALLOWED_USER_IDS', '').split(',') if uid]

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