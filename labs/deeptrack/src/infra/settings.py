"""infra/settings: the one `Settings` — every cluster of `infra/config`, read once, at import.

The environment, the `.env` files, the secrets and the config file are read here, validated, and frozen. Only the
composition root imports `settings` (`from infra.settings import settings as st`) and hands each provider, engine and
service its typed values; everything below takes plain keyword arguments."""

from infra.config.infra import InfraSettings
from infra.config.ontology import OntologySettings
from infra.config.providers import ProviderSettings
from infra.config.services import ServiceSettings


##### SETTINGS #####
class Settings(InfraSettings, ProviderSettings, OntologySettings, ServiceSettings):
    """Every cluster, one contract."""


settings = Settings()
