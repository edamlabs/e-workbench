"""infra/config/providers/adapters/bus/anyio: how many events may wait for each sink before the next is dropped."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from etrack.infra.config.base import BaseSettings


class AnyioSettings(BaseSettings):
    """ETRACK_BUS_CAPACITY — events queued per sink; past it, a slow sink loses the newest and the drop is counted."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_BUS_")

    capacity: int = Field(default=1000, ge=1)
