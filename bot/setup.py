import os

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from bot.config import PROJECTS_BASE, QUADLETS_DIR
from bot.logs import log
from bot.shell import run_command
from bot.util import check_auth


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
            f"cd {project_path}",
            "gh repo sync",
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
            "Please send the project name (this will be used as the directory name and service name).",
            parse_mode='HTML'
        )

        # Store state to track we're waiting for project name
        context.user_data['awaiting_project_name'] = True

    except Exception as e:
        log.error(f"Error in newproject_command: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


@check_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for new project setup"""
    try:
        # Check if we're waiting for project name
        if context.user_data.get('awaiting_project_name'):
            project_name = update.message.text.strip()

            # Validate project name (alphanumeric, hyphens, underscores only)
            if not project_name or not all(c.isalnum() or c in '-_' for c in project_name):
                await update.message.reply_text(
                    "❌ Invalid project name. Use only letters, numbers, hyphens, and underscores.\n"
                    "Please try again:"
                )
                return

            # Create project directory
            success, result = create_project_directory(project_name)

            if not success:
                await update.message.reply_text(f"❌ {result}")
                context.user_data.clear()
                return

            # Store project name and move to next step
            context.user_data['project_name'] = project_name
            context.user_data['awaiting_project_name'] = False
            context.user_data['awaiting_env_content'] = True

            await update.message.reply_text(
                f"✅ Project directory created: <code>{result}</code>\n\n"
                f"📝 Now send the contents of the .env file.\n"
                f"Send each environment variable on a new line, for example:\n\n"
                f"<code>TELEGRAM_TOKEN=your_token_here\n"
                f"API_KEY=your_api_key\n"
                f"DATABASE_URL=postgres://...</code>\n\n"
                f"Or send 'skip' to create an empty .env file.",
                parse_mode='HTML'
            )

        # Check if we're waiting for env content
        elif context.user_data.get('awaiting_env_content'):
            project_name = context.user_data.get('project_name')
            env_content = update.message.text.strip()

            if env_content.lower() == 'skip':
                env_content = "# Add your environment variables here\n"

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
                f"1. Run gh repo sync in project directory\n"
                f"2. Run gh repo sync in quadlets directory\n"
                f"3. Run systemctl --user daemon-reload\n"
                f"4. Start the container: systemctl --user start {project_name}\n\n"
                f"Or choose 'Done' to set up manually later.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        else:
            # No active wizard, ignore message
            pass

    except Exception as e:
        log.error(f"Error in handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
        context.user_data.clear()