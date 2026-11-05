"""tests/unit/infra/settings: one `Settings` of category clusters, and the law's gates read from the tree.

Every field UPPERCASE and named as its environment variable; no field in two clusters; the names held against the
snapshot taken from the old composer; `infra.settings` read only by the composition root; nothing but enums and value
types taken from `infra.config` below it."""

from infra.config.base import BaseSettings
from infra.settings import Settings, settings
from tests.unit.infra.conftest import Imports, Names


async def test_settings_one_instance_of_every_cluster() -> None:
    assert isinstance(settings, Settings)
    assert all(issubclass(base, BaseSettings) for base in Settings.__bases__)


async def test_settings_every_field_uppercase() -> None:
    assert [name for name in Settings.model_fields if name != name.upper()] == []


async def test_settings_no_field_in_two_clusters() -> None:
    owners = [name for base in Settings.__bases__ for name in base.__annotations__ if name.isupper()]
    assert sorted({name for name in owners if owners.count(name) > 1}) == []


async def test_settings_environment_names_held(names: Names, snapshot: list[str]) -> None:
    assert sorted(names(Settings)) == snapshot


async def test_settings_read_by_the_root_alone(below: Imports) -> None:
    assert sorted({path for path, module, _ in below if module == "infra.settings"}) == []


async def test_settings_below_the_root_config_gives_only_types(below: Imports) -> None:
    assert (
        sorted(
            {
                f"{path}:{name}"
                for path, module, name in below
                if module.startswith("infra.config") and name.endswith("Settings")
            }
        )
        == []
    )


async def test_settings_derived_values() -> None:
    assert settings.onto_ref_url == f"http://{settings.LABS_ONTO_HOST}:{settings.LABS_ONTOREF_PORT}/mcp"
    assert settings.langfuse_traces.startswith(settings.langfuse_url)
    assert settings.langfuse_authorization.get_secret_value().startswith("Basic ")
    assert len(settings.ontology_texts) == len(settings.DEEPTRACK_ONTOLOGY_FILES)
    assert "sh:NodeShape" in settings.ontology_shapes
