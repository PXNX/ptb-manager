import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DOCKERFILE_TEMPLATE = """FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set environment variables
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "main.py"]
"""

QUADLET_TEMPLATE = """[Unit]
Description="{project_name}"
Wants=network-online.target
After=network-online.target

[Container]
ContainerName={project_name}
Image=ghcr.io/{github_org}/{project_name}:master
AutoUpdate=registry
EnvironmentFile=%h/projects/{project_name}/.env
WorkingDir=/app
Exec=python main.py

[Service]
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""

def generate_project_files(project_path, project_name, github_org="PXNX"):
    """Generate Dockerfile and Quadlet file for a new project"""
    try:
        # 1. Create Dockerfile if it doesn't exist
        dockerfile_path = os.path.join(project_path, 'Dockerfile')
        if not os.path.exists(dockerfile_path):
            with open(dockerfile_path, 'w') as f:
                f.write(DOCKERFILE_TEMPLATE)
            log.info(f"Created Dockerfile for {project_name}")
        
        # 2. Generate Quadlet content
        quadlet_content = QUADLET_TEMPLATE.format(
            project_name=project_name,
            github_org=github_org
        )
        
        return True, quadlet_content
    except Exception as e:
        log.error(f"Error generating project files: {str(e)}")
        return False, str(e)
