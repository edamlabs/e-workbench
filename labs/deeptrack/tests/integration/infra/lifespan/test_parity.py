"""tests/integration/infra/lifespan/parity: law 22, checked — the attribute chain of the sealed tree is the module path.

The real lifespan chain fills and seals the tree; the whole tree is walked. Every node whose class belongs to a stratum
the project owns (`services`, `logic`) lives in the package its chain names: `state.services.chat` under
`services.chat`. Infrastructure branches (providers, engines) are walked, their brands never placed. And one object, one
path: nothing the tree holds lives at two."""

from collections import defaultdict

import pytest

from infra.lifespan.sealed import lifespan
from tests.integration.infra.lifespan.conftest import Nodes
from tests.support.fake import FakeClassifier, ScriptedChat

pytestmark = pytest.mark.integration


async def test_parity_every_stratum_node_lives_where_its_chain_says(nodes: Nodes, strata: tuple[str, ...]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat()) as state:
        held = [(path, type(value).__module__) for path, value in nodes(state)]
    placed = [(path, module) for path, module in held if module.startswith(strata)]
    assert placed, "no stratum node was walked: the tree lost its services"
    assert [(path, module) for path, module in placed if not module.startswith(path)] == []


async def test_parity_no_object_lives_at_two_paths(nodes: Nodes, atoms: tuple[type, ...]) -> None:
    async with lifespan(classify=FakeClassifier(), chat=ScriptedChat()) as state:
        paths: defaultdict[int, list[str]] = defaultdict(list)
        _ = [paths[id(value)].append(path) for path, value in nodes(state) if not isinstance(value, atoms)]
    assert sorted(sorted(group) for group in paths.values() if len(group) > 1) == []
