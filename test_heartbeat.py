"""Test script to manually trigger heartbeat for multi-user testing."""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanobot.config.loader import load_config
from nanobot.bus.queue import MessageBus
from nanobot.agent.loop import AgentLoop
from nanobot.workspace.resolver import WorkspaceResolver
from nanobot.heartbeat.service import HeartbeatService, HEARTBEAT_PROMPT


def _make_provider(config):
    """Create LiteLLMProvider from config."""
    from nanobot.providers.litellm_provider import LiteLLMProvider
    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        print(f"Error: No API key configured for provider: {config.get_provider_name()}")
        sys.exit(1)
    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


async def test_heartbeat():
    """Test heartbeat for all users."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    console.print("[cyan]Testing Multi-User Heartbeat[/cyan]\n")

    # Load config
    config = load_config()
    bus = MessageBus()
    provider = _make_provider(config)

    # Create workspace resolver
    workspace_resolver = WorkspaceResolver(
        default_workspace=config.workspace_path,
        multi_workspace=config.agents.defaults.multi_workspace,
    )

    console.print(f"Multi-workspace mode: [yellow]{workspace_resolver.is_multi_workspace}[/yellow]")
    console.print(f"Default workspace: {config.workspace_path}\n")

    # List all users
    if workspace_resolver.is_multi_workspace:
        users = workspace_resolver.list_users()
        console.print(f"Found [cyan]{len(users)}[/cyan] users: {users}\n")
    else:
        console.print("[yellow]Single-user mode[/yellow]\n")
        users = [None]

    # Create agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        workspace_resolver=workspace_resolver,
    )

    # Create heartbeat service
    async def on_heartbeat(prompt: str, user_id: str | None = None) -> str:
        """Execute heartbeat through the agent for a specific user."""
        user_label = user_id or "default"
        console.print(f"\n[yellow]Executing heartbeat for:[/yellow] [cyan]{user_label}[/cyan]")

        session_key = f"heartbeat:{user_id}" if user_id else "heartbeat"
        response = await agent.process_direct(
            prompt,
            session_key=session_key,
            metadata={"user_id": user_id} if user_id else {}
        )

        console.print(Panel(response, title=f"Response from {user_label}", border_style="green"))
        return response

    heartbeat = HeartbeatService(
        workspace=workspace_resolver,
        on_heartbeat=on_heartbeat,
        enabled=True
    )

    # Check heartbeat files for each user
    console.print("\n[cyan]Checking HEARTBEAT.md files:[/cyan]\n")
    for user_id in users:
        user_label = user_id or "default"
        heartbeat_file = heartbeat.get_heartbeat_file(user_id)

        if heartbeat_file.exists():
            content = heartbeat_file.read_text()
            console.print(f"[green][+][/green] {user_label}: {heartbeat_file}")
            console.print(f"[dim]{content[:100]}...[/dim]\n")
        else:
            console.print(f"[red][-][/red] {user_label}: No HEARTBEAT.md found\n")

    # Trigger heartbeat for all users
    console.print("[cyan]Triggering heartbeat for all users...[/cyan]\n")
    console.print("=" * 60)

    if workspace_resolver.is_multi_workspace:
        for user_id in users:
            await heartbeat._check_user_tasks(user_id)
    else:
        await heartbeat._check_user_tasks(None)

    console.print("\n" + "=" * 60)
    console.print("[green][+] Test complete![/green]")

    # Check if memory files were updated
    console.print("\n[cyan]Checking memory files for updates:[/cyan]\n")
    for user_id in users:
        user_label = user_id or "default"
        workspace = workspace_resolver.get_workspace(user_id)
        memory_file = workspace / "memory" / "MEMORY.md"

        if memory_file.exists():
            content = memory_file.read_text()
            lines = content.split("\n")
            console.print(f"[green][+][/green] {user_label} memory: {memory_file}")
            console.print(f"[dim]Last 5 lines:[/dim]")
            for line in lines[-5:]:
                console.print(f"  [dim]{line}[/dim]")
        else:
            console.print(f"[yellow][o][/yellow] {user_label}: No memory file yet")
        console.print()


if __name__ == "__main__":
    asyncio.run(test_heartbeat())
