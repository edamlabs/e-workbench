"""infra/config/infra: the process — the environment it runs in."""

from enum import StrEnum

from infra.config.base import BaseSettings


##### ENUMS #####
class Env(StrEnum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"


##### SETTINGS #####
class InfraSettings(BaseSettings):
    """The process: APP_ENV (dev | local | prod) drives the logger; a typo (`deV`) fails the load, never runtime."""

    ### APP
    APP_ENV: Env = Env.DEV
