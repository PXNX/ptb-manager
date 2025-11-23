import os
import subprocess

from config import PODMAN_URL
from logs import log


def run_command(cmd):
    """Execute shell command and return output"""
    try:
        # Add Podman URL if set and command starts with 'podman'
        if PODMAN_URL and cmd.strip().startswith('podman'):
            cmd = cmd.replace('podman', f'podman --url {PODMAN_URL}', 1)

        log.debug(f"Executing command: {cmd}")

        # On Windows, use shell=True, on Unix use bash
        if os.name == 'nt':
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                executable='/bin/bash'
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
