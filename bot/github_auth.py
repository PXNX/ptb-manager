import json
import os
import stat
import urllib.error
import urllib.request

from config import GITHUB_TOKENS_FILE
from logs import log


def _load_tokens():
    if not os.path.exists(GITHUB_TOKENS_FILE):
        return {}
    try:
        with open(GITHUB_TOKENS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading GitHub tokens: {e}")
        return {}


def _save_tokens(tokens):
    os.makedirs(os.path.dirname(GITHUB_TOKENS_FILE), exist_ok=True)
    with open(GITHUB_TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)
    try:
        os.chmod(GITHUB_TOKENS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def set_token(user_id, token):
    """Save (or replace) the GitHub token for a Telegram user"""
    tokens = _load_tokens()
    tokens[str(user_id)] = token
    _save_tokens(tokens)


def get_token(user_id):
    """Return the GitHub token for a Telegram user, or None if not set"""
    return _load_tokens().get(str(user_id))


def remove_token(user_id):
    """Remove a stored token, returns True if one existed"""
    tokens = _load_tokens()
    if str(user_id) in tokens:
        del tokens[str(user_id)]
        _save_tokens(tokens)
        return True
    return False


def verify_github_token(token):
    """Check a token against the GitHub API. Returns (ok, login_or_error)."""
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ptb-manager",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return True, data.get("login", "unknown")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def gh_env(token):
    """Env override to make `gh` (and `git` via gh's credential helper) use a
    specific user's token for a single subprocess call, without ever touching
    global/shared credentials."""
    return {'GH_TOKEN': token, 'GITHUB_TOKEN': token}
