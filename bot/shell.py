import os
import subprocess

from config import IS_CONTAINER, PODMAN_SOCK
from logs import log



def run_command(cmd, timeout=30):
    """Execute shell command and return output"""
    try:
        # For podman commands in container, use socket connection
        if cmd.strip().startswith('podman') and IS_CONTAINER:
            # Use podman with remote socket connection
            cmd = cmd.replace('podman', f'podman --remote --url unix://{PODMAN_SOCK}', 1)

        log.debug(f"Executing command: {cmd}")

        # On Windows, use shell=True, on Unix use bash
        if os.name == 'nt':
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
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
