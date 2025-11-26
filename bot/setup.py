import os

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import PROJECTS_BASE, QUADLETS_DIR, DEFAULT_GITHUB_ORG
from logs import log
from shell import run_command
from util import check_auth


def clone_github_repo(project_name, github_source=None):
    """Clone GitHub repository into project directory"""
    try:
        project_path = os.path.join(PROJECTS_BASE, project_name)

        # If no source provided, use default org
        if not github_source:
            github_source = f"{DEFAULT_GITHUB_ORG}/{project_name}"

        # Construct GitHub URL
        repo_url = f"https://github.com/{github_source}.git"

        # Clone the repository
        cmd = f"cd {PROJECTS_BASE} && gh repo clone {repo_url}"
        output = run_command(cmd)

        if "fatal" in output.lower() or "error" in output.lower():
            log.error(f"Error cloning repo: {output}")
            return False, output

        log.info(f"Cloned repository: {github_source} to {project_path}")
        return True, output
    except Exception as e:
        log.error(f"Error cloning GitHub repo: {str(e)}")
        return False, f"Error: {str(e)}"


def create_project_directory(project_name):
    """Create a new project directory"""
    try:
        project_path = os.path.join(PROJECTS_BASE, project_name)

        if os.path.exists(project_path):
            return False, f"Project directory already exists: {project_name}"

        os.makedirs(project_path, exist_ok=True)
        log.info(f"Created project directory: {project_path}")
        return True, project_path
    except Exception as e:
        log.error(f"Error creating project directory: {str(e)}")
        return False, f"Error: {str(e)}"


def create_env_file(project_name, env_content):
    """Create .env file for a project"""
    try:
        project_path = os.path.join(PROJECTS_BASE, project_name)
        env_path = os.path.join(project_path, '.env')

        with open(env_path, 'w') as f:
            f.write(env_content)

        log.info(f"Created .env file for project: {project_name}")
        return True, env_path
    except Exception as e:
        log.error(f"Error creating .env file: {str(e)}")
        return False, f"Error: {str(e)}"


def setup_and_start_project(project_name):
    """Setup project with gh repo sync, daemon reload, and container start"""
    try:
        project_path = os.path.join(PROJECTS_BASE, project_name)

        steps = [
            f"cd {QUADLETS_DIR}",
            "gh repo sync",
            "systemctl --user daemon-reload",
            f"systemctl --user start {project_name}"
        ]

        full_cmd = " && ".join(steps)
        output = run_command(full_cmd)
        return output
    except Exception as e:
        log.error(f"Error setting up project: {str(e)}")
        return f"Error: {str(e)}"


@check_auth
async def newproject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start new project setup wizard"""
    try:
        if os.name == 'nt':
            await update.message.reply_text(
                "❌ New project setup is not supported on Windows."
            )
            return

        await update.message.reply_text(
            "🆕 <b>New Project Setup</b>\n\n"
            "Please send the GitHub source in one of these formats:\n\n"
            "1. Just project name (e.g., <code>ptb-manager</code>)\n"
            f"   → Will clone from {DEFAULT_GITHUB_ORG}/ptb-manager\n\n"
            "2. Full source (e.g., <code>PXNX/ptb-manager</code>)\n"
            "   → Will clone from specified org/user\n\n"
            "3. Full URL (e.g., <code>https://github.com/PXNX/ptb-manager.git</code>)\n"
            "   → Will clone from URL"

        )

        # Store state to track we're waiting for GitHub source
        context.user_data['awaiting_github_source'] = True

    except Exception as e:
        log.error(f"Error in newproject_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


def clone_github_repo(project_name, github_source=None):
    """Clone GitHub repository into project directory"""
    try:
        project_path = os.path.join(PROJECTS_BASE, project_name)

        # Check if directory already exists
        if os.path.exists(project_path):
            log.error(f"Project directory already exists: {project_path}")
            return False, f"Project directory already exists: {project_name}"

        # If no source provided, use default org
        if not github_source:
            github_source = f"{DEFAULT_GITHUB_ORG}/{project_name}"

        # Construct GitHub URL if not already a full URL
        if not github_source.startswith('http'):
            repo_url = f"https://github.com/{github_source}.git"
        else:
            repo_url = github_source

        # Clone the repository - gh repo clone automatically creates the directory
        # We need to specify the target directory name
        # Use absolute path to ensure it goes to the right place
        cmd = f"cd {PROJECTS_BASE} && gh repo clone {repo_url} {project_name}"
        log.info(f"Executing clone command: {cmd}")
        log.info(f"PROJECTS_BASE: {PROJECTS_BASE}")
        log.info(f"Target project_path: {project_path}")

        output = run_command(cmd, timeout=60)  # Increase timeout for cloning

        if "fatal" in output.lower() or "error" in output.lower():
            log.error(f"Error cloning repo: {output}")
            return False, output

        # Give filesystem a moment to sync
        import time
        time.sleep(1)

        # Verify the directory was created
        if not os.path.exists(project_path):
            # List what's actually in PROJECTS_BASE to debug
            try:
                contents = os.listdir(PROJECTS_BASE)
                log.error(f"Project directory was not created at: {project_path}")
                log.error(f"Contents of {PROJECTS_BASE}: {contents}")
            except Exception as list_err:
                log.error(f"Could not list {PROJECTS_BASE}: {list_err}")
            return False, f"Project directory was not created at expected path: {project_path}"

        log.info(f"Cloned repository: {github_source} to {project_path}")
        return True, output
    except Exception as e:
        log.error(f"Error cloning GitHub repo: {str(e)}", exc_info=True)
        return False, f"Error: {str(e)}"


@check_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for new project setup"""
    try:
        # Check if we're waiting for GitHub source
        if context.user_data.get('awaiting_github_source'):
            user_input = update.message.text.strip()

            # Parse the input
            github_source = None
            project_name = None

            # Case 1: Full GitHub URL
            if user_input.startswith('http'):
                # Extract org/repo from URL
                # https://github.com/PXNX/ptb-manager.git -> PXNX/ptb-manager
                parts = user_input.replace('.git', '').split('/')
                if len(parts) >= 2:
                    github_source = f"{parts[-2]}/{parts[-1]}"
                    project_name = parts[-1]
                else:
                    await update.message.reply_text(
                        "❌ Invalid GitHub URL format. Please try again."
                    )
                    return

            # Case 2: org/repo format
            elif '/' in user_input:
                github_source = user_input
                project_name = user_input.split('/')[-1]

            # Case 3: Just project name
            else:
                project_name = user_input
                github_source = f"{DEFAULT_GITHUB_ORG}/{project_name}"

            # Validate project name
            if not project_name or not all(c.isalnum() or c in '-_' for c in project_name):
                await update.message.reply_text(
                    "❌ Invalid project name. Use only letters, numbers, hyphens, and underscores.\n"
                    "Please try again:"
                )
                return

            # Check if project already exists
            project_path = os.path.join(PROJECTS_BASE, project_name)
            if os.path.exists(project_path):
                await update.message.reply_text(
                    f"❌ Project directory already exists: {project_name}\n"
                    "Please choose a different name or remove the existing directory."
                )
                context.user_data.clear()
                return

            # Clone the repository
            await update.message.reply_text(
                f"📥 Cloning repository: <code>{github_source}</code>\n"
                f"Target: <code>{project_path}</code>\n"
                f"Please wait..."
            )

            success, result = clone_github_repo(project_name, github_source)

            if not success:
                await update.message.reply_text(
                    f"❌ Failed to clone repository:\n\n<code>{result}</code>\n\n"
                    f"Please check:\n"
                    f"• Repository exists and is accessible\n"
                    f"• You have gh CLI installed and authenticated\n"
                    f"• The repository name is correct\n\n"
                    f"Debug info:\n"
                    f"• PROJECTS_BASE: <code>{PROJECTS_BASE}</code>\n"
                    f"• IS_CONTAINER: <code>{os.getenv('CONTAINER', 'false')}</code>"
                )
                context.user_data.clear()
                return

            # Verify directory exists after cloning
            if not os.path.exists(project_path):
                # Show what directories DO exist
                try:
                    existing = os.listdir(PROJECTS_BASE)
                    existing_str = ", ".join(existing) if existing else "(empty)"
                except Exception as e:
                    existing_str = f"Error listing: {e}"

                await update.message.reply_text(
                    f"❌ Error: Project directory was not created at:\n"
                    f"<code>{project_path}</code>\n\n"
                    f"Existing directories in <code>{PROJECTS_BASE}</code>:\n"
                    f"<code>{existing_str}</code>\n\n"
                    f"Clone output:\n<code>{result}</code>"
                )
                context.user_data.clear()
                return

            # Store project name and move to next step
            context.user_data['project_name'] = project_name
            context.user_data['github_source'] = github_source
            context.user_data['awaiting_github_source'] = False
            context.user_data['awaiting_env_content'] = True

            await update.message.reply_text(
                f"✅ Repository cloned successfully!\n\n"
                f"📁 Project: <code>{project_name}</code>\n"
                f"📦 Source: <code>{github_source}</code>\n"
                f"📂 Path: <code>{project_path}</code>\n\n"
                f"📝 Now send the contents of the .env file.\n"
                f"Send each environment variable on a new line, for example:\n\n"
                f"<code>TELEGRAM_TOKEN=your_token_here\n"
                f"API_KEY=your_api_key\n"
                f"DATABASE_URL=postgres://...</code>\n\n"
                f"Or send 'skip' to skip creating a .env file."
            )

        # Check if we're waiting for env content
        elif context.user_data.get('awaiting_env_content'):
            project_name = context.user_data.get('project_name')
            env_content = update.message.text.strip()

            # Verify project directory exists before creating .env
            project_path = os.path.join(PROJECTS_BASE, project_name)
            if not os.path.exists(project_path):
                await update.message.reply_text(
                    f"❌ Error: Project directory not found at {project_path}\n"
                    f"Please start over with /newproject"
                )
                context.user_data.clear()
                return

            if env_content.lower() == 'skip':
                # Skip .env creation
                context.user_data['awaiting_env_content'] = False

                keyboard = [
                    [InlineKeyboardButton("🔄 Setup & Start Project", callback_data=f"setup_{project_name}")],
                    [InlineKeyboardButton("✅ Done (Manual Setup)", callback_data="setup_done")]
                ]

                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"⏭ Skipped .env file creation.\n\n"
                    f"🚀 <b>Next Steps:</b>\n\n"
                    f"<b>Setup & Start Project</b> will:\n"
                    f"1. Run systemctl --user daemon-reload\n"
                    f"2. Start the container: systemctl --user start {project_name}\n\n"
                    f"Or choose 'Done' to set up manually later.",
                    reply_markup=reply_markup
                )
                return

            # Create .env file
            success, result = create_env_file(project_name, env_content)

            if not success:
                await update.message.reply_text(f"❌ {result}")
                context.user_data.clear()
                return

            # Clear state
            context.user_data['awaiting_env_content'] = False

            # Show next steps menu
            keyboard = [
                [InlineKeyboardButton("🔄 Setup & Start Project", callback_data=f"setup_{project_name}")],
                [InlineKeyboardButton("✅ Done (Manual Setup)", callback_data="setup_done")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ .env file created: <code>{result}</code>\n\n"
                f"🚀 <b>Next Steps:</b>\n\n"
                f"<b>Setup & Start Project</b> will:\n"
                f"1. Run systemctl --user daemon-reload\n"
                f"2. Start the container: systemctl --user start {project_name}\n\n"
                f"Or choose 'Done' to set up manually later.",
                reply_markup=reply_markup
            )

        else:
            # No active wizard, ignore message
            pass

    except Exception as e:
        log.error(f"Error in handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data.clear()