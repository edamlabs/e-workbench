"""engines/shacl: ShaclEngine — a validation round against an ontology server: clear, reload, add the proposal, judge.

The server holds one store, so rounds are serialized behind a lock; the engine keeps only the reference, the base
texts and the shapes. Every call carries the caller's config, so each step is a span under whoever asked."""

import asyncio
from typing import Protocol

import msgspec
from langchain_core.runnables import RunnableConfig

from infra.errors import ShaclError
from ports.ontology import OntologyPort, ShaclReport


class ShaclValidation(Protocol):
    """What the gate needs from an engine: a candidate in, a report out."""

    async def validate(self, turtle: str, config: RunnableConfig | None = None) -> ShaclReport: ...


class ShaclEngine:
    """SHACL over a fresh copy of the ontology plus one candidate graph."""

    __slots__ = ("_base", "_lock", "_server", "_shapes")

    def __init__(self, server: OntologyPort, base: tuple[str, ...], shapes: str) -> None:
        self._server = server
        self._base = base
        self._shapes = shapes
        self._lock = asyncio.Lock()

    async def validate(self, turtle: str, config: RunnableConfig | None = None) -> ShaclReport:
        """The candidate judged against the shapes, over the base ontology alone — one round at a time."""
        async with self._lock:
            await self._server.call("onto_clear", {}, config)
            [await self._server.call("onto_load", {"turtle": text}, config) for text in self._base]
            await self._server.call("onto_load", {"turtle": turtle}, config)
            raw = await self._server.call("onto_shacl", {"shapes": self._shapes, "inline": True}, config)
        try:
            return msgspec.json.decode(raw, type=ShaclReport)
        except msgspec.DecodeError as error:
            msg = f"shacl: the server's answer is not a SHACL report ({raw[:200]})"
            raise ShaclError(msg) from error


class PassShaclEngine:
    """The engine of the arm without ontology: it judges nothing — every candidate conforms. Same port, same node."""

    __slots__ = ()

    async def validate(self, turtle: str, config: RunnableConfig | None = None) -> ShaclReport:  # noqa: ARG002 — the port's signature
        """Conforms, always."""
        return ShaclReport(conforms=True)
