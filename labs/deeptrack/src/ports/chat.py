"""ports/chat: a tool-calling chat model an agent runs on — the LangChain model itself, opened and owned by a provider.

The agent framework (deepagents over LangGraph) consumes a `BaseChatModel`; the port hands exactly that, so the
provider decides vendor, credentials and streaming, and the agent never learns which."""

from typing import Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel

from ports.provider import Provider


@runtime_checkable
class ChatPort(Provider, Protocol):
    """`model` is the chat model, built and authenticated when the provider opened."""

    @property
    def model(self) -> BaseChatModel: ...
