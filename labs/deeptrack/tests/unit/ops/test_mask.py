"""CUITs never leave the process: bare, hyphenated, nested."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ops.mask import LIMIT, MASK, mask_clip, mask_data


async def test_mask_nested() -> None:
    masked = mask_data(data={"a": ["CUIT 20-11111111-2", 7], "b": "27222222223"})
    assert masked == {"a": [f"CUIT {MASK}", 7], "b": MASK}


async def test_mask_clip_limit() -> None:
    assert len(mask_clip("x" * (LIMIT * 2))) == LIMIT


async def test_mask_chat_messages() -> None:
    masked = mask_data(data={"messages": [HumanMessage("CUIT 20-11111111-2"), AIMessage("tu CUIT 20111111112")]})
    assert [each["content"] for each in masked["messages"]] == [f"CUIT {MASK}", f"tu CUIT {MASK}"]


async def test_mask_graph_commands_and_tool_calls() -> None:
    command = Command(update={"messages": [ToolMessage("CUIT 20-11111111-2", tool_call_id="c")]})
    call = AIMessage("", tool_calls=[{"name": "task", "args": {"description": "CUIT 20111111112"}, "id": "c"}])
    masked = str(mask_data(data={"out": command, "call": call}))
    assert "20-11111111-2" not in masked
    assert "20111111112" not in masked
    assert masked.count(MASK) == 2


async def test_mask_opaque_objects_as_text() -> None:
    class Opaque:
        def __str__(self) -> str:
            return "CUIT 20-11111111-2"

    assert mask_data(data=Opaque()) == f"CUIT {MASK}"
    assert mask_data(data=[1, 2.5, True, None]) == [1, 2.5, True, None]
