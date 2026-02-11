# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**nanobot** is an ultra-lightweight personal AI assistant framework (~4,000 lines of core agent code). It provides multi-channel chat integration (Telegram, Discord, WhatsApp, Feishu, DingTalk, Email), extensible skills, scheduled tasks, and tool execution.

**Python**: 3.11+
**Package**: `nanobot-ai`
**Config location**: `~/.nanobot/config.json`
**Workspace**: `~/.nanobot/workspace/`

## Common Commands

### Development
```bash
# Install from source (editable)
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"

# Linting
ruff check .
ruff format .

# Testing
pytest
pytest tests/          # Run specific tests

# Run agent
nanobot agent -m "Hello"           # Single message
nanobot agent                      # Interactive mode
nanobot agent --logs               # Show runtime logs
nanobot agent --no-markdown        # Plain text output

# Gateway (runs all enabled channels)
nanobot gateway

# Utility
nanobot onboard                    # Initialize config
nanobot status                     # Show configuration status
nanobot channels login             # WhatsApp QR linking
nanobot channels status            # Show channel status

# Scheduled tasks
nanobot cron add --name "daily" --message "Good morning!" --cron "0 9 * * *"
nanobot cron list
nanobot cron remove <job_id>
```

### Node.js Bridge (bridge/)
WhatsApp integration requires a separate Node.js bridge server:
```bash
cd bridge
npm install
npm run build    # Build TypeScript
npm start        # Run bridge server
```

## Architecture

The codebase follows a message-bus architecture with clear separation of concerns:

```
Channels → MessageBus → AgentLoop → Tools/Providers
   ↓            ↓           ↓            ↓
 (TG/Disc/   (events)   (LLM +      (File, Shell,
  WA/FT/DT)              tools)       Web, etc.)
```

### Key Components

**nanobot/agent/** - Core agent logic
- `loop.py` - AgentLoop: LLM chat ↔ tool execution loop
- `context.py` - ContextBuilder: builds prompts from history/memory/skills
- `memory.py` - Persistent memory via workspace files
- `skills.py` - Skills loader (progressive loading)
- `subagent.py` - Background task execution

**nanobot/channels/** - Chat app integrations
- All inherit from `BaseChannel` with `start()`, `stop()`, `send()` methods
- Publish inbound messages to bus, consume outbound from bus
- Each channel handles its own authentication/connection logic

**nanobot/bus/** - Message routing
- `events.py` - InboundMessage, OutboundMessage dataclasses
- `queue.py` - MessageBus: async queue for channel ↔ agent communication

**nanobot/providers/** - LLM provider registry
- `registry.py` - **PROVIDERS tuple** is the single source of truth
- `litellm_provider.py` - LiteLLM-based provider implementation
- `base.py` - LLMProvider base class

**nanobot/agent/tools/** - Built-in tools
- All inherit from `Tool` ABC with `name`, `description`, `parameters`, `execute()`
- `ToolRegistry` manages registration and execution
- Tools: filesystem (read/write/edit/list), shell, web (search/fetch), message, spawn, cron

**nanobot/skills/** - Bundled skills
- Each skill is a directory with `SKILL.md` (YAML frontmatter + content)
- Loaded progressively: "always" skills at startup, others on-demand

**nanobot/config/** - Configuration
- `schema.py` - Pydantic models for all config sections
- `loader.py` - ConfigLoader with environment variable support

**nanobot/session/** - Session management
- JSONL-based persistence in `~/.nanobot/sessions/`
- Session key format: `{channel}:{chat_id}`
- History limited to 50 messages by default

## Adding a New LLM Provider

The provider registry eliminates if-elif chains. Adding a provider takes 2 steps:

**Step 1**: Add `ProviderSpec` to `PROVIDERS` in `nanobot/providers/registry.py`:
```python
ProviderSpec(
    name="myprovider",                   # config field name
    keywords=("myprovider", "mymodel"),  # model-name keywords for auto-matching
    env_key="MYPROVIDER_API_KEY",        # env var for LiteLLM
    display_name="My Provider",
    litellm_prefix="myprovider",         # auto-prefix: model → myprovider/model
    skip_prefixes=("myprovider/",),      # don't double-prefix
)
```

**Step 2**: Add field to `ProvidersConfig` in `nanobot/config/schema.py`:
```python
class ProvidersConfig(BaseModel):
    ...
    myprovider: ProviderConfig = ProviderConfig()
```

That's it! Environment variables, model prefixing, config matching, and `nanobot status` display all derive from the registry.

## Code Conventions

- **Async-first**: All I/O operations use `asyncio`
- **Type hints**: Extensive use of Python type hints (Pydantic for config)
- **File naming**: `snake_case.py` for modules, `PascalCase` for classes
- **Line length**: 100 characters (ruff configured)
- **Sessions**: JSONL format, one message per line
- **Tools**: Return `str` results (JSON for structured data)

## Security Features

- `restrict_to_workspace`: When `true`, all file/shell tools are sandboxed to workspace directory
- `allowFrom`: Whitelist for channel users (empty = allow all)
- `consent_granted`: Explicit permission required for email channel access

## Bridge Architecture

The WhatsApp bridge (`bridge/`) is a separate Node.js process:
- Uses Baileys library for WhatsApp Web protocol
- WebSocket connection between bridge and Python backend
- Build with `npm run build` before running
- Start with `nanobot channels login` (scan QR) + `nanobot gateway`

## Workspace Files

The agent reads/writes these files in `~/.nanobot/workspace/`:
- `AGENTS.md` - Agent instructions/system prompt
- `SOUL.md` - Personality and values
- `USER.md` - User preferences
- `MEMORY.md` - Long-term memory
- `HEARTBEAT.md` - Periodic/proactive tasks
- `memory/YYYY-MM-DD.md` - Daily notes
- `skills/{name}/SKILL.md` - Custom skills

## Interactive Mode Exits

Type: `exit`, `quit`, `/exit`, `/quit`, `:q`, or `Ctrl+D`
