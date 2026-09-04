import os
import subprocess

from config import IS_CONTAINER, PODMAN_SOCK
from logs import log


def run_command(cmd, timeout=30, force_local=False, env=None):
    """Execute shell command and return output.

    `env`, if given, is a dict of extra environment variables merged over the
    current process environment for this call only (e.g. a per-user GH_TOKEN)
    - it's never written to the log, unlike `cmd`.
    """
    try:
        # For podman commands in container, use socket connection
        if cmd.strip().startswith('podman') and IS_CONTAINER and not force_local:
            # Use podman with remote socket connection
            cmd = cmd.replace('podman', f'podman --remote --url unix://{PODMAN_SOCK}', 1)

        log.debug(f"Executing command: {cmd}")

        run_env = {**os.environ, **env} if env else None

        # On Windows, use shell=True, on Unix use bash
        if os.name == 'nt':
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                executable='/bin/bash',
                env=run_env
            )

        if result.returncode != 0:
            log.error(f"Command failed with return code {result.returncode}: {result.stderr}")
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        log.error(f"Command timed out: {cmd}")
        return "Command timed out"
    except Exception as e:
        log.error(f"Command execution error: {str(e)}")
        return f"Error: {str(e)}"
