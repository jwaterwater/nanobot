"""Workspace resolver for multi-user and single-workspace modes."""

from pathlib import Path
from typing import Any

from loguru import logger


class WorkspaceResolver:
    """
    Resolves workspace and session paths for multi-user or single-workspace modes.

    In single-workspace mode (default):
    - workspace: ~/.nanobot/workspace
    - sessions: ~/.nanobot/sessions

    In multi-workspace mode:
    - workspace: ~/.nanobot/users/{user_id}/workspace
    - sessions: ~/.nanobot/users/{user_id}/sessions
    """

    def __init__(
        self,
        default_workspace: Path,
        multi_workspace: bool = False,
        base_dir: Path | None = None,
    ):
        """
        Initialize the workspace resolver.

        Args:
            default_workspace: The default workspace path (usually ~/.nanobot/workspace).
            multi_workspace: If True, enable per-user workspace isolation.
            base_dir: Base directory for nanobot data (defaults to ~/.nanobot).
        """
        self.default_workspace = Path(default_workspace).expanduser()
        self.multi_workspace = multi_workspace
        self.base_dir = Path(base_dir) if base_dir else Path.home() / ".nanobot"

    @property
    def is_multi_workspace(self) -> bool:
        """Check if multi-workspace mode is enabled."""
        return self.multi_workspace

    def get_workspace(self, user_id: str | None = None) -> Path:
        """
        Get the workspace path for a user.

        Args:
            user_id: Optional user identifier. In multi-workspace mode,
                    this determines which workspace to use.

        Returns:
            Path to the workspace directory.
        """
        if self.multi_workspace and user_id:
            workspace = self.base_dir / "users" / self._sanitize_user_id(user_id) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            self._initialize_user_workspace(workspace)
            return workspace
        return self.default_workspace

    def get_sessions_dir(self, user_id: str | None = None) -> Path:
        """
        Get the sessions directory for a user.

        Args:
            user_id: Optional user identifier. In multi-workspace mode,
                    this determines which sessions directory to use.

        Returns:
            Path to the sessions directory.
        """
        if self.multi_workspace and user_id:
            sessions_dir = self.base_dir / "users" / self._sanitize_user_id(user_id) / "sessions"
        else:
            sessions_dir = self.base_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    def get_user_base_dir(self, user_id: str) -> Path:
        """
        Get the base directory for a specific user.

        Args:
            user_id: User identifier.

        Returns:
            Path to the user's base directory (contains workspace and sessions).
        """
        return self.base_dir / "users" / self._sanitize_user_id(user_id)

    def _sanitize_user_id(self, user_id: str) -> str:
        """
        Sanitize user_id for use in file paths.

        Args:
            user_id: Raw user identifier.

        Returns:
            Sanitized user ID safe for use in file paths.
        """
        # Replace potentially dangerous characters
        sanitized = user_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized

    def _initialize_user_workspace(self, workspace: Path) -> None:
        """
        Initialize a user workspace with default template files.

        Creates AGENTS.md, SOUL.md, USER.md, and memory/MEMORY.md
        if they don't already exist.

        Args:
            workspace: Path to the user's workspace directory.
        """
        # Check if already initialized
        if (workspace / "AGENTS.md").exists():
            return

        # Create memory directory
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        # Default template files
        templates = {
            "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in your memory files
""",
            "SOUL.md": """# Soul

I am nanobot, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
            "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
        }

        # Create template files
        for filename, content in templates.items():
            file_path = workspace / filename
            if not file_path.exists():
                file_path.write_text(content)
                logger.info(f"Created {filename} for user workspace")

        # Create MEMORY.md in memory directory
        memory_file = memory_dir / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
            logger.info(f"Created memory/MEMORY.md for user workspace")

    def list_users(self) -> list[str]:
        """
        List all users with workspaces in multi-workspace mode.

        Returns:
            List of user IDs.
        """
        if not self.multi_workspace:
            return []

        users_dir = self.base_dir / "users"
        if not users_dir.exists():
            return []

        return [d.name for d in users_dir.iterdir() if d.is_dir()]

    def delete_user_workspace(self, user_id: str) -> bool:
        """
        Delete a user's workspace and sessions.

        Args:
            user_id: User identifier.

        Returns:
            True if deleted, False if not found.
        """
        if not self.multi_workspace:
            return False

        user_dir = self.get_user_base_dir(user_id)
        if user_dir.exists():
            import shutil
            shutil.rmtree(user_dir)
            logger.info(f"Deleted workspace for user: {user_id}")
            return True
        return False

    def get_workspace_info(self, user_id: str | None = None) -> dict[str, Any]:
        """
        Get information about the current workspace configuration.

        Args:
            user_id: Optional user identifier.

        Returns:
            Dictionary with workspace information.
        """
        workspace = self.get_workspace(user_id)
        sessions = self.get_sessions_dir(user_id)

        info = {
            "mode": "multi-workspace" if self.multi_workspace else "single-workspace",
            "workspace": str(workspace),
            "sessions": str(sessions),
            "workspace_exists": workspace.exists(),
            "sessions_exists": sessions.exists(),
        }

        if self.multi_workspace and user_id:
            info["user_id"] = user_id

        return info
