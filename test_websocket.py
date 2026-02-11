"""Simple WebSocket client test for nanobot."""

import asyncio
import json
import sys


async def test_websocket_client(
    host: str = "localhost",
    port: int = 8765,
    token: str | None = None,
    user_id: str = "test_user",
):
    """
    Test the WebSocket channel connection.

    Args:
        host: WebSocket server host.
        port: WebSocket server port.
        token: Optional authentication token.
        user_id: User ID to authenticate with.
    """
    import websockets

    uri = f"ws://{host}:{port}"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            # Authenticate
            auth_msg = {"type": "auth", "user_id": user_id}
            if token:
                auth_msg["token"] = token

            await ws.send(json.dumps(auth_msg))
            print(f"Sent authentication: {auth_msg}")

            # Receive connected confirmation
            response = await ws.recv()
            data = json.loads(response)
            print(f"Received: {data}")

            if data.get("type") == "error":
                print(f"Authentication failed: {data.get('message')}")
                return

            print(f"Connected as client {data.get('client_id')} (user: {data.get('user_id')})")

            # Send a test message
            test_msg = {"type": "message", "content": "Hello nanobot!"}
            await ws.send(json.dumps(test_msg))
            print(f"Sent: {test_msg}")

            # Receive response
            while True:
                response = await ws.recv()
                data = json.loads(response)
                print(f"Received: {data.get('type', 'unknown')}")

                if data.get("type") == "message":
                    print(f"Response: {data.get('content', '')[:200]}")
                    break

    except websockets.exceptions.ConnectionRefused:
        print("Error: Connection refused. Is the WebSocket server running?")
        print("Start it with: nanobot gateway")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run the WebSocket client test."""
    import argparse

    parser = argparse.ArgumentParser(description="Test nanobot WebSocket channel")
    parser.add_argument("--host", default="localhost", help="WebSocket server host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port")
    parser.add_argument("--token", help="Authentication token (if required)")
    parser.add_argument("--user-id", default="test_user", help="User ID")

    args = parser.parse_args()

    asyncio.run(test_websocket_client(args.host, args.port, args.token, args.user_id))


if __name__ == "__main__":
    main()
