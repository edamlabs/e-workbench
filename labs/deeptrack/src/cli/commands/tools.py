"""cli/commands/tools: `deeptrack tools` — each ontology server's advertised tools, and the tools every agent names.

Opens the two servers and the harness alone: no model, no credential."""

import json
from contextlib import AsyncExitStack

from rich.console import Console

from infra.lifespan import ontology
from infra.settings import settings as st
from providers.drivers.harness.files import FilesDriver


async def tools() -> None:
    """Each ontology server's advertised tools and input schemas, and the tools every agent names."""
    async with AsyncExitStack() as stack:
        servers = await stack.enter_async_context(ontology.lifespan())
        harness = await stack.enter_async_context(FilesDriver(directory=st.DEEPTRACK_AGENTS_DIRECTORY))
        shown = {
            "agents": {name: list(agent.spec.tools) for name, agent in harness.roster.agents.items()},
            "reference": {name: tool.args for name, tool in servers.reference.tools.items()},
            "validation": {name: tool.args for name, tool in servers.validation.tools.items()},
        }
        Console(highlight=False).print_json(json.dumps(shown))
