"""Heartbeat service - periodic agent wake-up to check for tasks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

try:
    from nanobot.workspace.resolver import WorkspaceResolver
except ImportError:
    WorkspaceResolver = None  # type: ignore[misc, assignment]

# Default interval: 30 minutes
DEFAULT_HEARTBEAT_INTERVAL_S = 30 * 60

# The prompt sent to agent during heartbeat
HEARTBEAT_PROMPT = """Read HEARTBEAT.md in your workspace (if it exists).
Follow any instructions or tasks listed there.
If nothing needs attention, reply with just: HEARTBEAT_OK"""

# Token that indicates "nothing to do"
HEARTBEAT_OK_TOKEN = "HEARTBEAT_OK"


def _is_heartbeat_empty(content: str | None) -> bool:
    """Check if HEARTBEAT.md has no actionable content."""
    if not content:
        return True
    
    # Lines to skip: empty, headers, HTML comments, empty checkboxes
    skip_patterns = {"- [ ]", "* [ ]", "- [x]", "* [x]"}
    
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--") or line in skip_patterns:
            continue
        return False  # Found actionable content
    
    return True


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    The agent reads HEARTBEAT.md from the workspace and executes any
    tasks listed there. If nothing needs attention, it replies HEARTBEAT_OK.

    Supports both single-user and multi-user modes via WorkspaceResolver.
    """

    def __init__(
        self,
        workspace: Path | "WorkspaceResolver",
        on_heartbeat: Callable[[str, str | None], Coroutine[Any, Any, str]] | None = None,
        interval_s: int = DEFAULT_HEARTBEAT_INTERVAL_S,
        enabled: bool = True,
    ):
        # Support both Path and WorkspaceResolver for backward compatibility
        if isinstance(workspace, Path):
            if WorkspaceResolver is None:
                raise ImportError("WorkspaceResolver not available")
            self.workspace_resolver = WorkspaceResolver(
                default_workspace=workspace,
                multi_workspace=False
            )
        else:
            self.workspace_resolver = workspace

        self.on_heartbeat = on_heartbeat
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    def get_heartbeat_file(self, user_id: str | None = None) -> Path:
        """Get the heartbeat file path for a user."""
        workspace = self.workspace_resolver.get_workspace(user_id)
        return workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self, heartbeat_file: Path) -> str | None:
        """Read HEARTBEAT.md content from a specific path."""
        if heartbeat_file.exists():
            try:
                return heartbeat_file.read_text()
            except Exception:
                return None
        return None
    
    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Heartbeat started (every {self.interval_s}s)")
    
    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
    
    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _tick(self) -> None:
        """Execute a single heartbeat tick for all users."""
        if self.workspace_resolver.is_multi_workspace:
            # Multi-user mode: iterate through all users
            users = self.workspace_resolver.list_users()
            logger.debug(f"Heartbeat: checking {len(users)} users")

            for user_id in users:
                try:
                    await self._check_user_tasks(user_id)
                except Exception as e:
                    logger.error(f"Heartbeat error for user {user_id}: {e}")
        else:
            # Single-user mode
            await self._check_user_tasks(None)

    async def _check_user_tasks(self, user_id: str | None) -> None:
        """Check and execute tasks for a specific user."""
        heartbeat_file = self.get_heartbeat_file(user_id)
        content = self._read_heartbeat_file(heartbeat_file)

        # Skip if empty or doesn't exist
        if _is_heartbeat_empty(content):
            logger.debug(f"Heartbeat: no tasks for user {user_id or 'default'}")
            return

        logger.info(f"Heartbeat: executing tasks for user {user_id or 'default'}")

        if self.on_heartbeat:
            try:
                response = await self.on_heartbeat(HEARTBEAT_PROMPT, user_id)

                if HEARTBEAT_OK_TOKEN.replace("_", "") in response.upper().replace("_", ""):
                    logger.info(f"Heartbeat: OK for user {user_id or 'default'}")
                else:
                    logger.info(f"Heartbeat: completed task for user {user_id or 'default'}")
            except Exception as e:
                logger.error(f"Heartbeat execution failed for user {user_id}: {e}")
    
    async def trigger_now(self, user_id: str | None = None) -> str | None:
        """Manually trigger a heartbeat for a specific user or all users."""
        if self.on_heartbeat:
            return await self.on_heartbeat(HEARTBEAT_PROMPT, user_id)
        return None
