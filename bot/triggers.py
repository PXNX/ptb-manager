import os
import time
import uuid

from config import PROJECTS_BASE
from logs import log

# Watched by a host-native systemd --user path unit (see
# quadlets/host-units/ptb-redeploy-watcher.{path,service,sh}). This exists
# because systemctl --user cannot be called directly from inside the
# ptb-manager container (its D-Bus EXTERNAL auth handshake fails against the
# bind-mounted host session bus - confirmed even after dropping privileges to
# the host's own uid, so it needs a real fix on the host side instead of a
# container-side workaround).
TRIGGER_DIR = os.path.join(PROJECTS_BASE, '.triggers')


def write_trigger(kind, name=""):
    """Drop a trigger file for the host-side watcher to act on.

    `kind` is 'restart', 'setup', or 'reload'. `name` is the systemd
    unit/project name for 'restart'/'setup' (ignored for 'reload'). Only the
    *filename* is meaningful - the watcher never executes file content, and
    independently validates `name` against a strict allowlist before acting.
    """
    os.makedirs(TRIGGER_DIR, exist_ok=True)
    uniq = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    filename = f"{kind}__{name}__{uniq}.trigger" if name else f"{kind}__{uniq}.trigger"
    path = os.path.join(TRIGGER_DIR, filename)
    open(path, 'w').close()
    log.info(f"Wrote trigger file for host-side watcher: {filename}")
    return path
