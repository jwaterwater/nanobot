"""Session management for conversation history."""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename

try:
    from nanobot.workspace.resolver import WorkspaceResolver
except ImportError:
    WorkspaceResolver = None  # type: ignore[misc, assignment]


@dataclass
class Session:
    """
    A conversation session.
    
    Stores messages in JSONL format for easy reading and persistence.
    """
    
    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        Get message history for LLM context.
        
        Args:
            max_messages: Maximum messages to return.
        
        Returns:
            List of messages in LLM format.
        """
        # Get recent messages
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # Convert to LLM format (just role and content)
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """Clear all messages in the session."""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored as JSONL files in the sessions directory.
    Supports multi-workspace mode through WorkspaceResolver.
    """

    def __init__(self, workspace: Path, workspace_resolver: "WorkspaceResolver | None" = None):
        self.workspace = workspace
        self.workspace_resolver = workspace_resolver
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str, user_id: str | None = None) -> Path:
        """Get the file path for a session."""
        if self.workspace_resolver and user_id:
            sessions_dir = self.workspace_resolver.get_sessions_dir(user_id)
        else:
            sessions_dir = self.sessions_dir
        safe_key = safe_filename(key.replace(":", "_"))
        return sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str, user_id: str | None = None) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).
            user_id: Optional user ID for multi-workspace mode.

        Returns:
            The session.
        """
        # Create a cache key that includes user_id if in multi-workspace mode
        cache_key = f"{user_id}:{key}" if user_id else key

        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try to load from disk
        session = self._load(key, user_id)
        if session is None:
            session = Session(key=key)

        self._cache[cache_key] = session
        return session

    def _load(self, key: str, user_id: str | None = None) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key, user_id)
        
        if not path.exists():
            return None
        
        try:
            messages = []
            metadata = {}
            created_at = None
            
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                    else:
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)
        
        with open(path, "w") as f:
            # Write metadata first
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata
            }
            f.write(json.dumps(metadata_line) + "\n")
            
            # Write messages
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        
        self._cache[session.key] = session
    
    def delete(self, key: str) -> bool:
        """
        Delete a session.
        
        Args:
            key: Session key.
        
        Returns:
            True if deleted, False if not found.
        """
        # Remove from cache
        self._cache.pop(key, None)
        
        # Remove file
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.
        
        Returns:
            List of session info dicts.
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception:
                continue
        
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
