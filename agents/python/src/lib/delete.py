"""Delete Resources"""

from typing import cast

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.lib.state import AgentState


def _find_delete_call(state: AgentState):
    """Locate the most recent DeleteResources tool call in the message history."""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "DeleteResources":
                    return tc
    return None


async def delete_node(state: AgentState, config: RunnableConfig):  # pylint: disable=unused-argument
    """
    Pause the graph (dynamic interrupt) and wait for the user to confirm the
    deletion. The frontend resumes the run with forwarded_props.command.resume
    set to "YES" or "NO".
    """
    tool_call = _find_delete_call(state)
    urls = tool_call["args"].get("urls", []) if tool_call else []
    answer = interrupt({"action": "confirm_delete", "urls": urls})
    return {"delete_confirmation": str(answer)}


async def perform_delete_node(state: AgentState, config: RunnableConfig):  # pylint: disable=unused-argument
    """
    Apply (or skip) the deletion the user answered in delete_node, and close
    the pending DeleteResources tool call so the next LLM turn is valid.
    """
    tool_call = _find_delete_call(state)
    if tool_call is None:
        return state

    urls = tool_call["args"].get("urls", [])
    confirmed = str(state.get("delete_confirmation", "")).strip().upper() == "YES"

    resources = state.get("resources", [])
    if confirmed:
        resources = [r for r in resources if r["url"] not in urls]
        result = f"Deleted {len(urls)} resource(s) as confirmed by the user. Tell the user the deletion is done."
    else:
        result = "The user declined the deletion. Resources were kept unchanged. Tell the user nothing was deleted."

    return {
        "resources": resources,
        "messages": [ToolMessage(tool_call_id=tool_call["id"], content=result)],
    }
