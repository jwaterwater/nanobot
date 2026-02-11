# WebSocket Channel - Multi-User Support

## Overview

The WebSocket channel enables real-time bidirectional communication between nanobot and multiple clients. It supports per-user workspace isolation, allowing each user to have their own independent workspace, memory, and conversation history.

## Features

- **Real-time Communication**: WebSocket-based low-latency messaging
- **Multi-User Support**: Multiple concurrent client connections
- **Token Authentication**: Secure token-based user verification
- **Workspace Isolation**: Each user has their own independent workspace
- **Heartbeat Monitoring**: Automatic connection health monitoring
- **JSON Message Protocol**: Simple, structured message format

## Installation

The WebSocket channel requires the `websockets` package:

```bash
pip install websockets
```

## Configuration

Add the WebSocket configuration to `~/.nanobot/config.json`:

```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.nanobot/workspace",
      "multi_workspace": true,
      "model": "anthropic/claude-opus-4-5"
    }
  },
  "channels": {
    "websocket": {
      "enabled": true,
      "host": "0.0.0.0",
      "port": 8765,
      "auth_required": true,
      "auth_tokens": {
        "secret-token-1": "user_001",
        "secret-token-2": "user_002"
      },
      "allow_from": [],
      "heartbeat_interval": 30,
      "max_message_size": 1048576
    }
  }
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable WebSocket channel |
| `host` | string | `"0.0.0.0"` | Server host address |
| `port` | integer | `8765` | Server port |
| `auth_required` | boolean | `true` | Require authentication |
| `auth_tokens` | object | `{}` | Token → user_id mapping |
| `allow_from` | array | `[]` | Allowed user IDs (empty = allow all) |
| `heartbeat_interval` | integer | `30` | Heartbeat interval in seconds |
| `max_message_size` | integer | `1048576` | Max message size in bytes |

### Multi-Workspace Mode

Set `multi_workspace: true` to enable per-user workspace isolation:

- **Single workspace mode** (`multi_workspace: false`): All users share the same workspace at `~/.nanobot/workspace`
- **Multi workspace mode** (`multi_workspace: true`): Each user gets their own workspace at `~/.nanobot/users/{user_id}/workspace`

## Starting the Server

Start the nanobot gateway with WebSocket enabled:

```bash
nanobot gateway
```

The WebSocket server will start on `ws://0.0.0.0:8765` (or your configured host/port).

## Message Protocol

### Client → Server Messages

#### Authentication
```json
{
  "type": "auth",
  "token": "optional-token",
  "user_id": "user-123"
}
```
The first message must be an authentication message.

#### Chat Message
```json
{
  "type": "message",
  "content": "Hello nanobot!"
}
```

#### Heartbeat
```json
{
  "type": "ping"
}
```

#### Reset Conversation
```json
{
  "type": "reset"
}
```

### Server → Client Messages

#### Connected Confirmation
```json
{
  "type": "connected",
  "client_id": "abc12345",
  "user_id": "user-123",
  "timestamp": "2026-02-09T12:00:00"
}
```

#### Chat Response
```json
{
  "type": "message",
  "content": "Hi! How can I help you?",
  "timestamp": "2026-02-09T12:00:01"
}
```

#### Heartbeat Response
```json
{
  "type": "pong",
  "timestamp": "2026-02-09T12:00:00"
}
```

#### Error
```json
{
  "type": "error",
  "message": "Authentication failed"
}
```

## Python Client Example

```python
import asyncio
import json
import websockets

async def chat():
    uri = "ws://localhost:8765"

    async with websockets.connect(uri) as ws:
        # Authenticate
        await ws.send(json.dumps({
            "type": "auth",
            "token": "secret-token-1",
            "user_id": "user_001"
        }))

        # Check connection
        response = await ws.recv()
        data = json.loads(response)

        if data.get("type") == "error":
            print(f"Error: {data['message']}")
            return

        print(f"Connected: {data}")

        # Send message
        await ws.send(json.dumps({
            "type": "message",
            "content": "What files are in my workspace?"
        }))

        # Receive response
        response = await ws.recv()
        data = json.loads(response)
        print(f"Response: {data['content']}")

asyncio.run(chat())
```

## JavaScript Client Example (Browser)

```javascript
const ws = new WebSocket('ws://localhost:8765');

ws.onopen = () => {
    // Authenticate
    ws.send(JSON.stringify({
        type: 'auth',
        token: 'secret-token-1',
        user_id: 'user_001'
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'connected':
            console.log('Connected as', data.user_id);
            break;
        case 'message':
            console.log('Response:', data.content);
            break;
        case 'error':
            console.error('Error:', data.message);
            break;
    }
};

function sendMessage(content) {
    ws.send(JSON.stringify({
        type: 'message',
        content: content
    }));
}
```

## Testing

Use the included test client:

```bash
# Basic connection test
python test_websocket.py

# With custom host/port
python test_websocket.py --host localhost --port 8765

# With authentication token
python test_websocket.py --token secret-token-1 --user-id user_001
```

## Workspace Directory Structure

### Single Workspace Mode (`multi_workspace: false`)

```
~/.nanobot/
├── config.json
├── workspace/
│   ├── AGENTS.md
│   ├── MEMORY.md
│   ├── memory/
│   └── skills/
└── sessions/
    ├── cli_default.jsonl
    └── websocket_*.jsonl
```

### Multi Workspace Mode (`multi_workspace: true`)

```
~/.nanobot/
├── config.json
├── workspace/              # Fallback workspace
├── sessions/               # Fallback sessions
└── users/
    ├── user_001/
    │   ├── workspace/
    │   │   ├── AGENTS.md
    │   │   ├── MEMORY.md
    │   │   ├── memory/
    │   │   └── skills/
    │   └── sessions/
    │       └── websocket_*.jsonl
    └── user_002/
        ├── workspace/
        └── sessions/
```

## Security Considerations

1. **Authentication**: Always enable `auth_required` in production
2. **Authorization**: Use `allow_from` to restrict access to specific users
3. **TLS/SSL**: Use a reverse proxy (nginx, Traefik) to handle HTTPS/WSS
4. **Token Management**: Rotate tokens regularly and use strong, random values
5. **Network Security**: Bind to specific interfaces instead of `0.0.0.0` when possible

### Example nginx Reverse Proxy Configuration

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /ws {
        proxy_pass http://localhost:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Then connect via secure WebSocket: `wss://your-domain.com/ws`

## Troubleshooting

### Connection Refused
- Ensure the gateway is running: `nanobot gateway`
- Check that the port is not in use by another service
- Verify firewall settings

### Authentication Failed
- Check that the token is correctly configured in `auth_tokens`
- Ensure the user_id matches the token mapping
- Verify `auth_required` setting

### Workspace Not Found
- Ensure `multi_workspace` is set correctly in config
- Check directory permissions for `~/.nanobot/users/`
- Run `nanobot onboard` to create initial workspace

### High Memory Usage
- Each user maintains their own session history
- Consider implementing session cleanup for inactive users
- Adjust `max_tool_iterations` if needed

## Status Command

Check WebSocket channel status:

```bash
nanobot channels status
```

Output example:
```
┏━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Channel ┃ Enabled ┃ Configuration    ┃
┡━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ WhatsApp│ ✓       │ ws://localhost:3 │
│ Discord │ ✗       │ wss://gateway... │
│ Telegram│ ✓       │ token: 123456... │
│ WebSocket│ ✓      │ ws://0.0.0.0:8765│
└────────┴─────────┴──────────────────┘
```

## Backward Compatibility

The WebSocket channel is fully backward compatible:
- When `multi_workspace: false` (default), all users share the same workspace
- Existing channels (Telegram, Discord, etc.) continue to work unchanged
- Session format remains JSONL across all modes
