"""cli/session: ChatSession — the terminal side of a conversation on one thread.

A turn's outcome is shown with its trace; an approval stop asks the operator and resumes until the turn settles. With
no message, the session reads lines until an empty one or `/salir`."""

import json

from beartype import beartype
from rich.console import Console
from rich.prompt import Confirm, Prompt

from models.proposal import Decision
from models.turn import ChatTurn
from services.chat import ChatService


@beartype
class ChatSession:
    """A chat service, the thread it talks on, and the console it talks through."""

    __slots__ = ("_chat", "_console", "_thread")

    def __init__(self, chat: ChatService, thread: str, console: Console) -> None:
        self._chat = chat
        self._thread = thread
        self._console = console

    async def _run_settle(self, turn: ChatTurn) -> None:
        self._console.print(f"\n[bold]>[/] {turn.reply}\n[dim]{turn.url}[/]")
        match turn.interrupt:
            case None:
                return
            case stop:
                self._console.print(f"[bold red]Aprobación requerida:[/] {json.dumps(stop, ensure_ascii=False)}")
                approved = Confirm.ask("¿Aprobar?", console=self._console)
                decision = Decision.APROBAR if approved else Decision.RECHAZAR
                await self._run_settle(await self._chat.turn(self._thread, decision))

    async def _run_loop(self) -> None:
        match Prompt.ask("\n[bold]tú[/]", console=self._console).strip():
            case "" | "/salir":
                return
            case message:
                await self._run_settle(await self._chat.turn(self._thread, message))
                await self._run_loop()

    ############################################################

    async def run(self, message: str = "") -> None:
        """One turn on `message`; with none, the conversation until an empty line or `/salir`."""
        match message:
            case "":
                await self._run_loop()
            case _:
                await self._run_settle(await self._chat.turn(self._thread, message))
