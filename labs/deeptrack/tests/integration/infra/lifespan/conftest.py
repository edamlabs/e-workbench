"""Fixtures of the lifespan tests: the walk over the sealed tree and what parity counts as placed or atomic."""

import dataclasses
import itertools
from collections.abc import Callable, Iterator

import pytest

from infra.state import State

type Nodes = Callable[..., Iterator[tuple[str, object]]]


@pytest.fixture
def strata() -> tuple[str, ...]:
    """The packages the project owns: a node of these classes lives where its chain says."""
    return ("services.", "logic.")


@pytest.fixture
def atoms() -> tuple[type, ...]:
    """The value types that may legitimately be shared between paths."""
    return (str, bytes, int, float, bool, type(None), frozenset, tuple)


@pytest.fixture
def nodes() -> Nodes:
    """`nodes(root)`: every node under a node — branches and leaves alike — at its dotted path."""

    def children(node: object) -> list[tuple[str, object]]:
        match node:
            case State():
                return list(node.items())
            case _ if dataclasses.is_dataclass(node) and not isinstance(node, type):
                return [(each.name, getattr(node, each.name)) for each in dataclasses.fields(node)]
            case _:
                return []

    def walk(node: object, chain: tuple[str, ...] = ()) -> Iterator[tuple[str, object]]:
        return itertools.chain.from_iterable(
            itertools.chain([(".".join((*chain, name)), child)], walk(child, (*chain, name)))
            for name, child in children(node)
        )

    return walk
