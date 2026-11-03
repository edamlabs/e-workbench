"""The config tree mirrors the module tree: each provider's settings sit at its module path."""

from infra.settings import settings as st


def test_settings_mirror_tree() -> None:
    trace = st.providers.drivers.trace.langfuse
    servers = st.providers.drivers.ontology.openontologies
    assert trace.url == f"http://{trace.host}:{trace.port}"
    assert servers.ref_url == f"http://{servers.host}:{servers.ref_port}/mcp"
    assert st.providers.drivers.chat.vertex.kwargs["vertexai"] is True


def test_settings_ontology_texts() -> None:
    assert len(st.ontology.texts) == len(st.ontology.files)
    assert "sh:NodeShape" in st.ontology.shapes_text
