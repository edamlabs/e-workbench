"""infra/config/app: process-level knobs — APP_ENV."""

from enum import StrEnum

from pydantic_settings import SettingsConfigDict

from infra.config.base import BaseSettings


##### ENUMS #####
class Env(StrEnum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"


class AppSettings(BaseSettings):
    """APP_ENV (dev | local | prod) drives the logger.

    The env is validated on decode: a typo (`deV`) fails the load, it never reaches runtime."""

    model_config = SettingsConfigDict(env_prefix="APP_")

    env: Env = Env.DEV
