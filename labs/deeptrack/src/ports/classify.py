"""ports/classify: a text sorted into one of a closed set of labels — the answer is always one of them."""

from typing import Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig

from ports.provider import Provider


@runtime_checkable
class ClassifyPort(Provider, Protocol):
    """`classify` answers exactly one of `labels` for `text` under the `system` instruction, or raises `ModelError`."""

    async def classify(
        self, system: str, text: str, labels: tuple[str, ...], config: RunnableConfig | None = None
    ) -> str: ...
