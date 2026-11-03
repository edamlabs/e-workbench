"""deeptrack: the only module that knows the app — `chat` talks to the agents, `tools` shows what each server offers.

Every command opens the lifespan, so a missing service fails at startup, not mid-turn."""

import json

from cyclopts import App
from rich.console import Console
from rich.prompt import Confirm, Prompt

from deeptrack.adapters.onto import OntoAdapter
from deeptrack.infra.lifespan import lifespan
from deeptrack.infra.settings import settings as st
from deeptrack.instrument.chat import TracedChat
from deeptrack.instrument.console import EventConsole
from deeptrack.models.proposal import Decision
from deeptrack.models.turn import ChatTurn

console = Console(highlight=False)
app = App(name="deeptrack", help="Insurance deep agent over an ontology MCP, traced live and in Langfuse.")


async def _chat_settle(chat: TracedChat, thread: str, turn: ChatTurn) -> None:
    """Show a turn's outcome; an approval stop asks the operator and resumes until the turn settles."""
    console.print(f"\n[bold]>[/] {turn.reply}\n[dim]{turn.url}[/]")
    match turn.interrupt:
        case None:
            return
        case stop:
            console.print(f"[bold red]Aprobación requerida:[/] {json.dumps(stop, ensure_ascii=False)}")
            decision = Decision.APROBAR if Confirm.ask("¿Aprobar?", console=console) else Decision.RECHAZAR
            await _chat_settle(chat, thread, await chat.turn(thread, decision))


async def _chat_loop(chat: TracedChat, thread: str) -> None:
    match Prompt.ask("\n[bold]tú[/]", console=console).strip():
        case "" | "/salir":
            return
        case message:
            await _chat_settle(chat, thread, await chat.turn(thread, message))
            await _chat_loop(chat, thread)


async def chat(thread: str = "default", message: str = "") -> None:
    """Talk to the agents; `--message` runs one turn and exits."""
    async with lifespan(EventConsole(console).show) as runtime:
        match message:
            case "":
                await _chat_loop(runtime.chat, thread)
            case _:
                await _chat_settle(runtime.chat, thread, await runtime.chat.turn(thread, message))


async def tools() -> None:
    """Each ontology server's advertised tools and their input schemas, and the agent's whitelist."""
    async with OntoAdapter(st.onto) as onto:
        console.print_json(json.dumps({"agent": [tool.name for tool in onto.tools], **onto.schemas}))


app.command(chat)
app.command(tools)


def main() -> None:
    """Entry point of `deeptrack` and `python -m deeptrack`."""
    app()


main() if __name__ == "__main__" else None
