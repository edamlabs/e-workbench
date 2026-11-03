"""deeptrack: the only module that knows the app — `chat` talks to the agents, `tools` shows what each server offers.

`chat` opens the whole lifespan, so a missing service or credential fails at startup, not mid-turn."""

import json
from contextlib import AsyncExitStack

from cyclopts import App
from rich.console import Console
from rich.prompt import Confirm, Prompt

from deeptrack.cli.console import EventConsole
from deeptrack.lifespan.providers import ontology
from deeptrack.lifespan.sealed import lifespan
from deeptrack.logic.agent import READ_TOOLS
from deeptrack.models.proposal import Decision
from deeptrack.models.turn import ChatTurn
from deeptrack.services.chat import ChatService
from deeptrack.state import ServicesState

console = Console(highlight=False)
app = App(name="deeptrack", help="Insurance deep agent over an ontology MCP, traced live and in Langfuse.")


async def _chat_settle(chat: ChatService, thread: str, turn: ChatTurn, view: EventConsole) -> None:
    """Show a turn's outcome; an approval stop asks the operator and resumes until the turn settles."""
    console.print(f"\n[bold]>[/] {turn.reply}\n[dim]{turn.url}[/]")
    match turn.interrupt:
        case None:
            return
        case stop:
            console.print(f"[bold red]Aprobación requerida:[/] {json.dumps(stop, ensure_ascii=False)}")
            decision = Decision.APROBAR if Confirm.ask("¿Aprobar?", console=console) else Decision.RECHAZAR
            await _chat_settle(chat, thread, await chat.turn(thread, decision, view.show), view)


async def _chat_loop(chat: ChatService, thread: str, view: EventConsole) -> None:
    match Prompt.ask("\n[bold]tú[/]", console=console).strip():
        case "" | "/salir":
            return
        case message:
            await _chat_settle(chat, thread, await chat.turn(thread, message, view.show), view)
            await _chat_loop(chat, thread, view)


async def chat(thread: str = "default", message: str = "") -> None:
    """Talk to the agents; `--message` runs one turn and exits."""
    view = EventConsole(console)
    async with lifespan() as state:
        services: ServicesState = state.services
        match message:
            case "":
                await _chat_loop(services.chat, thread, view)
            case _:
                await _chat_settle(services.chat, thread, await services.chat.turn(thread, message, view.show), view)


async def tools() -> None:
    """Each ontology server's advertised tools and input schemas, and the ontologist's read-only whitelist."""
    async with AsyncExitStack() as stack:
        servers = await ontology(stack)
        shown = {
            "ontologo": list(READ_TOOLS),
            "reference": {name: tool.args for name, tool in servers.reference.tools.items()},
            "validation": {name: tool.args for name, tool in servers.validation.tools.items()},
        }
        console.print_json(json.dumps(shown))


app.command(chat)
app.command(tools)


def main() -> None:
    """Entry point of `deeptrack` and `python -m deeptrack`."""
    app()


main() if __name__ == "__main__" else None
