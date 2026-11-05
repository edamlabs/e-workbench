"""ports/agent: a roster made runnable — one framework's build of an entry agent and the subagents it names.

The build resolves every name a roster carries against what the system has: `tools` and `middleware` by name (a
middleware is a factory: each agent gets its own instance), `models` by tier. A name with nothing behind it is the
build's refusal, never a missing tool at run time."""

from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from ports.harness import Roster, Tier
from ports.provider import Provider


@runtime_checkable
class AgentPort(Provider, Protocol):
    """Build the entry agent of a roster with the system's tools, middleware and models."""

    def build(
        self,
        roster: Roster,
        entry: str,
        *,
        tools: Mapping[str, Any],
        middleware: Mapping[str, Callable[[], Any]],
        models: Mapping[Tier, Any],
        schema: type | None = None,
    ) -> Any: ...
