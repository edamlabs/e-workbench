"""infra/config/base: pydantic-settings — frozen, typed, layered config.

This module wires the five layers every cluster shares: config file < secrets < .env < environment < kwargs. The
`.env` files are the repository's (shared by every lab) and the lab's own, the lab's winning. A key a cluster pins
(`PINNED`) reads the `.env` files before the environment: a shell can carry a stale `GEMINI_API_KEY`, and a lab that
silently picks it up fails on a key nobody chose. `Secret` is pydantic's `SecretStr`: masked through repr, str and
f-strings, readable only via `.get_secret_value()`. Every cluster inherits from here."""

from pathlib import Path
from typing import Any, ClassVar, Final

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings as SettingsBase,
)
from pydantic_settings import (
    DotEnvSettingsSource,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
    YamlConfigSettingsSource,
)

Secret = SecretStr

LAB: Final[Path] = Path(__file__).resolve().parents[3]
### the repository's `.env` first, the lab's after: a later file wins.
ENV_FILES: Final[tuple[Path, ...]] = (LAB.parents[1] / ".env", LAB / ".env")

FILE_SOURCES: Final = (
    ("toml_file", TomlConfigSettingsSource),
    ("yaml_file", YamlConfigSettingsSource),
    ("json_file", JsonConfigSettingsSource),
)


class PinnedDotEnvSource(DotEnvSettingsSource):
    """The `.env` files, narrowed to the pinned keys: what must beat the environment, and nothing else."""

    def __init__(self, settings_cls: type[SettingsBase], pinned: frozenset[str]) -> None:
        super().__init__(settings_cls)
        self._pinned = pinned

    def __call__(self) -> dict[str, Any]:
        return {key: value for key, value in super().__call__().items() if key in self._pinned}


class BaseSettings(SettingsBase):
    """Subclass and declare typed UPPERCASE fields, each the name of its environment variable; the constructor merges
    every layer in one pass.

    A cluster narrows its sources through ``model_config``: ``toml_file`` / ``yaml_file`` / ``json_file``,
    ``secrets_dir`` (set ``/run/secrets`` there when it is containerized). Complex values in env or .env are
    JSON-decoded; enums, paths and timedeltas validate on load, never at runtime."""

    ### the keys the `.env` files give before the environment; a cluster names its own.
    PINNED: ClassVar[frozenset[str]] = frozenset()

    model_config = SettingsConfigDict(
        frozen=True,
        ### the one Settings reads the shared .env files: a foreign key in them must not abort the load.
        extra="ignore",
        env_file=ENV_FILES,
        env_nested_delimiter="__",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[SettingsBase],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        ### pydantic-settings reads these first-to-highest: kwargs beat env, the config file is the floor; a pinned key
        ### reads the .env files before the environment.
        pinned = getattr(settings_cls, "PINNED", frozenset())
        return (
            init_settings,
            *((PinnedDotEnvSource(settings_cls, pinned),) if pinned else ()),
            env_settings,
            dotenv_settings,
            file_secret_settings,
            *cls._settings_customise_files(settings_cls),
        )

    @staticmethod
    def _settings_customise_files(settings_cls: type[SettingsBase]) -> tuple[PydanticBaseSettingsSource, ...]:
        """The configured config-file sources only: absent format, absent source."""
        return tuple(source(settings_cls) for key, source in FILE_SOURCES if settings_cls.model_config.get(key))
