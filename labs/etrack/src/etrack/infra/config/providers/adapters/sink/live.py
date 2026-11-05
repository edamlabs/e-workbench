"""infra/config/providers/adapters/sink/live: how much of each thread the live buffer keeps, for how many threads."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from etrack.infra.config.base import BaseSettings


class LiveSettings(BaseSettings):
    """ETRACK_LIVE_BUFFER — frames kept per thread for a reconnect to replay; ETRACK_LIVE_THREADS — threads kept, the
    least recently written evicted first; ETRACK_LIVE_BACKLOG — frames a subscriber may lag before it is cut off."""

    model_config = SettingsConfigDict(env_prefix="ETRACK_LIVE_")

    buffer: int = Field(default=2000, ge=1)
    threads: int = Field(default=256, ge=1)
    backlog: int = Field(default=1000, ge=1)
