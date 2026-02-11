"""WebSocket channel for real-time multi-user chat."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel

try:
    import websockets
    from websockets.server import ServerConnection, State
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    ServerConnection = Any  # type: ignore[misc, assignment]
    State = Any  # type: ignore[misc, assignment]


class WebSocketChannel(BaseChannel):
    """
    WebSocket channel for real-time bidirectional communication.

    Supports multiple concurrent client connections with token-based authentication
    and per-user workspace isolation in multi-workspace mode.
    """

    name = "websocket"

    def __init__(self, config: Any, bus: MessageBus):
        super().__init__(config, bus)

        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets package is required for WebSocket channel. "
                "Install it with: pip install websockets"
            )

        self.host = config.host
        self.port = config.port
        self.auth_required = config.auth_required
        self.auth_tokens = config.auth_tokens or {}
        self.allow_from = config.allow_from or []
        self.heartbeat_interval = config.heartbeat_interval
        self.max_message_size = config.max_message_size

        # Client management
        self._clients: dict[str, "WebSocketClient"] = {}
        self._server: Any = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._shutdown.clear()

        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        try:
            self._server = await websockets.serve(
                self._handle_connection,
                self.host,
                self.port,
                max_size=self.max_message_size,
                ping_interval=self.heartbeat_interval,
                ping_timeout=self.heartbeat_interval * 2,
            )
            logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")

            # Wait for shutdown
            await self._shutdown.wait()

        except OSError as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the WebSocket server and disconnect all clients."""
        logger.info("Stopping WebSocket server...")
        self._shutdown.set()

        # Disconnect all clients
        for client_id, client in list(self._clients.items()):
            try:
                await client.ws.close()
            except Exception:
                pass
        self._clients.clear()

        # Close server
        if self._server:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass

        logger.info("WebSocket server stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message to a WebSocket client.

        The chat_id should be the client_id for WebSocket connections.

        Supports different message types via metadata:
        - type: "message" (default), "thinking", "tool_call", "tool_result", "error"
        - streaming: bool - whether this is a streaming chunk
        - done: bool - whether streaming is complete
        """
        client = self._clients.get(msg.chat_id)
        if not client:
            logger.warning(f"Client {msg.chat_id} not found")
            return

        # Check if connection is still open (websockets >= 16.0)
        if client.ws.state != State.OPEN:
            logger.warning(f"Client {msg.chat_id} connection is not open (state: {client.ws.state})")
            return

        try:
            # Get message type from metadata (default: "message")
            msg_type = msg.metadata.get("type", "message")

            response = {
                "type": msg_type,
                "content": msg.content,
                "timestamp": datetime.now().isoformat(),
            }

            # Add streaming-specific fields
            if msg.metadata.get("streaming"):
                response["streaming"] = True
                if "done" in msg.metadata:
                    response["done"] = msg.metadata["done"]

            # Add tool call information
            if msg_type == "tool_call":
                response["tool_name"] = msg.metadata.get("tool_name", "")
                response["tool_args"] = msg.metadata.get("tool_args", {})

            # Add tool result information
            if msg_type == "tool_result":
                response["tool_name"] = msg.metadata.get("tool_name", "")
                response["success"] = msg.metadata.get("success", True)

            await client.ws.send(json.dumps(response))
            logger.debug(f"Sent {msg_type} to client {client.user_id}:{msg.chat_id}")
        except Exception as e:
            logger.error(f"Error sending to client {msg.chat_id}: {e}")

    async def _handle_connection(self, ws: "ServerConnection") -> None:
        """Handle a new WebSocket connection."""
        client_id = str(uuid.uuid4())[:8]
        client = WebSocketClient(client_id, ws)
        self._clients[client_id] = client

        logger.info(f"New WebSocket connection: {client_id}")

        try:
            # Wait for authentication first
            auth_msg = await ws.recv()
            try:
                auth_data = json.loads(auth_msg)
            except json.JSONDecodeError:
                await self._send_error(ws, "Invalid JSON format")
                return

            user_id = await self._authenticate(auth_data)
            if not user_id:
                await self._send_error(ws, "Authentication failed")
                return

            client.user_id = user_id
            client.authenticated = True

            # Send connected confirmation
            await self._send_connected(ws, client_id, user_id)
            logger.info(f"Client authenticated: {client_id} -> user: {user_id}")

            # Check authorization
            if not self._is_user_allowed(user_id):
                await self._send_error(ws, f"User {user_id} is not authorized")
                logger.warning(f"Unauthorized user access denied: {user_id}")
                return

            # Handle messages
            async for raw_msg in ws:
                try:
                    data = json.loads(raw_msg)
                    await self._handle_client_message(client, data)
                except json.JSONDecodeError:
                    await self._send_error(ws, "Invalid JSON format")
                except Exception as e:
                    logger.error(f"Error handling message from {client_id}: {e}")
                    await self._send_error(ws, f"Error: {str(e)}")

        except websockets.exceptions.ConnectionClosed:
            logger.debug(f"Connection closed: {client_id}")
        except Exception as e:
            logger.error(f"Error in connection handler for {client_id}: {e}")
        finally:
            self._clients.pop(client_id, None)
            logger.debug(f"Client removed: {client_id}")

    async def _authenticate(self, auth_data: dict[str, Any]) -> str | None:
        """
        Authenticate a client connection.

        Returns:
            The user_id if authentication succeeds, None otherwise.
        """
        msg_type = auth_data.get("type")

        if msg_type != "auth":
            return None

        # Get user_id from auth data
        user_id = auth_data.get("user_id")

        if not user_id:
            return None

        # Check if authentication is required
        if self.auth_required:
            token = auth_data.get("token")
            if not token:
                return None

            # Verify token
            expected_user_id = self.auth_tokens.get(token)
            if expected_user_id and expected_user_id != user_id:
                # Token maps to a different user
                return None

            # If token exists in mapping, use its user_id
            if expected_user_id:
                user_id = expected_user_id

        return user_id

    def _is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to connect."""
        if not self.allow_from:
            return True
        return user_id in self.allow_from

    async def _handle_client_message(self, client: "WebSocketClient", data: dict[str, Any]) -> None:
        """Handle a message from a client."""
        msg_type = data.get("type")

        if msg_type == "message":
            content = data.get("content", "")
            if not content:
                return

            await self._handle_message(
                sender_id=client.user_id,
                chat_id=client.client_id,  # Use client_id as chat_id for routing
                content=content,
                metadata={"user_id": client.user_id, "client_id": client.client_id},
            )

        elif msg_type == "ping":
            await self._send_pong(client.ws)

        elif msg_type == "reset":
            # Reset conversation for this user
            # This is a no-op for now, but could trigger session reset
            await client.ws.send(json.dumps({"type": "reset", "status": "ok"}))

        elif msg_type == "preferences":
            # Store client preferences
            client.preferences = {
                "show_thinking": data.get("show_thinking", True)
            }
            logger.info(f"Client {client.client_id} preferences updated: {client.preferences}")
            await client.ws.send(json.dumps({
                "type": "preferences_ack",
                "preferences": client.preferences
            }))

        else:
            await self._send_error(client.ws, f"Unknown message type: {msg_type}")

    async def _send_connected(self, ws: "ServerConnection", client_id: str, user_id: str) -> None:
        """Send a connected confirmation to the client."""
        msg = {
            "type": "connected",
            "client_id": client_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
        }
        await ws.send(json.dumps(msg))

    async def _send_pong(self, ws: "ServerConnection") -> None:
        """Send a pong response to the client."""
        msg = {"type": "pong", "timestamp": datetime.now().isoformat()}
        await ws.send(json.dumps(msg))

    async def _send_error(self, ws: "ServerConnection", message: str) -> None:
        """Send an error message to the client."""
        msg = {"type": "error", "message": message}
        try:
            await ws.send(json.dumps(msg))
        except Exception:
            pass


class WebSocketClient:
    """Represents a connected WebSocket client."""

    def __init__(self, client_id: str, ws: "ServerConnection"):
        self.client_id = client_id
        self.ws = ws
        self.user_id: str | None = None
        self.authenticated = False
        self.preferences: dict[str, Any] = {
            "show_thinking": True
        }
