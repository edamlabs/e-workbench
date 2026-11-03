"""The e-workbench command line: the only module that knows the app; every command is registered here."""

import sys

from cyclopts import App

from e_workbench.cli.commands.fleet import fleet
from e_workbench.cli.commands.run import run
from e_workbench.core.logger import setup_logger
from e_workbench.core.settings import settings as st

app = App(name="e-workbench", help="Self-maintenance engine of EDamLabs projects.")
app.command(fleet)
app.command(run)


def main() -> None:
    """Entry point: configure logging once, then dispatch the command."""
    setup_logger(st.env, st.log_level)
    app(sys.argv[1:])
