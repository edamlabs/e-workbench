"""main: the `deeptrack` script — the command tree by explicit registration; importing this module builds nothing.

`chat` talks to the agents, `tools` shows what each server offers; each is a plain handler under `cli/commands/`."""

from cyclopts import App

from cli.commands.chat import chat
from cli.commands.tools import tools
from infra.logger import ELogger
from infra.settings import settings as st


def build() -> App:
    """The command tree: one registration per command."""
    ELogger.setup(env=st.APP_ENV)
    app = App(name="deeptrack", help="Insurance deep agent over an ontology MCP, traced live and in Langfuse.")
    app.command(chat)
    app.command(tools)
    return app


def main() -> None:
    """Entry point of the `deeptrack` script."""
    build()()


main() if __name__ == "__main__" else None
