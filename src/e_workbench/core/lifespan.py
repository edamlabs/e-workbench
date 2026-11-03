"""The engine's resources: one HTTP client for the run, the adapters bound to the core's ports."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType

import wreq

from e_workbench.adapters.crates import CratesAdapter
from e_workbench.adapters.github import GithubAdapter
from e_workbench.adapters.osv import OsvAdapter
from e_workbench.adapters.pypi import PypiAdapter
from e_workbench.adapters.site import SiteAdapter
from e_workbench.adapters.workspace import WorkspaceAdapter
from e_workbench.core.settings import Settings
from e_workbench.logic.ports import RegistryPort


@dataclass(frozen=True, slots=True)
class RuntimeLifespan:
    """The wired adapters of one run: the code host and tracker, the registries by host, the advisory database,
    and the workspace where the act stage solves bumps."""

    github: GithubAdapter
    registries: Mapping[str, RegistryPort]
    advisories: OsvAdapter
    workspace: WorkspaceAdapter
    site: SiteAdapter


@asynccontextmanager
async def lifespan(settings: Settings) -> AsyncGenerator[RuntimeLifespan]:
    """Open the HTTP client, bind every adapter to it, close it when the run ends."""
    client = wreq.Client(timeout=settings.http_timeout)
    token = settings.github_token.get_secret_value() if settings.github_token else None
    try:
        yield RuntimeLifespan(
            github=GithubAdapter(client, settings.github_api, token, settings.user_agent),
            registries=MappingProxyType(
                {
                    "pypi.org": PypiAdapter(client, settings.pypi_url, settings.user_agent),
                    "crates.io": CratesAdapter(client, settings.crates_api, settings.user_agent),
                }
            ),
            advisories=OsvAdapter(client, settings.osv_api, settings.user_agent, settings.concurrency),
            workspace=WorkspaceAdapter(settings.work_dir, settings.git_remote, token, settings.act_timeout),
            site=SiteAdapter(client, settings.user_agent),
        )
    finally:
        client.close()
