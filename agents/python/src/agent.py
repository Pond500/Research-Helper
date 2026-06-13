"""
Research Agent Workflow

Defines the LangGraph workflow for the research agent, including nodes
for chat, search, download, and resource management.
"""

import os

from langgraph.graph import StateGraph

from src.lib.chat import chat_node
from src.lib.delete import delete_node, perform_delete_node
from src.lib.download import download_node
from src.lib.search import search_node
from src.lib.critic import critic_node
from src.lib.state import AgentState

# Define a new graph
workflow = StateGraph(AgentState)
workflow.add_node("download", download_node)
workflow.add_node("chat_node", chat_node)
workflow.add_node("search_node", search_node)
workflow.add_node("delete_node", delete_node)
workflow.add_node("perform_delete_node", perform_delete_node)
workflow.add_node("critic_node", critic_node)


workflow.set_entry_point("download")
workflow.add_edge("download", "chat_node")
workflow.add_edge("delete_node", "perform_delete_node")
workflow.add_edge("perform_delete_node", "chat_node")
workflow.add_edge("search_node", "download")
# chat_node routes to critic_node conditionally via Command
# critic_node routes to chat_node or __end__ conditionally via Command

# Conditionally use a checkpointer based on the environment
# This allows compatibility with both LangGraph API and CopilotKit
# (delete confirmation uses a dynamic interrupt() inside delete_node,
#  resumed via forwarded_props.command.resume — no static breakpoint needed)
compile_kwargs = {}


# Check if we're running in LangGraph API mode
if os.environ.get("LANGGRAPH_FASTAPI", "false").lower() == "false":
    # When running in LangGraph API, don't use a custom checkpointer
    graph = workflow.compile(**compile_kwargs)
else:
    # For CopilotKit and other contexts, use an in-memory checkpointer.
    # The frontend rotates the thread id every turn, so threads would otherwise
    # accumulate in RAM forever. Cap the number of retained threads (LRU) — a
    # turn only needs its own thread alive (incl. the delete interrupt/resume).
    from collections import OrderedDict

    from langgraph.checkpoint.memory import MemorySaver

    MAX_THREADS = int(os.environ.get("CHECKPOINT_MAX_THREADS", "200"))

    class BoundedMemorySaver(MemorySaver):
        """MemorySaver that evicts least-recently-written threads past a cap."""

        def __init__(self, max_threads: int):
            super().__init__()
            self._max_threads = max_threads
            self._seen: "OrderedDict[str, None]" = OrderedDict()

        def put(self, config, checkpoint, metadata, new_versions):
            result = super().put(config, checkpoint, metadata, new_versions)
            thread_id = (config.get("configurable") or {}).get("thread_id")
            if thread_id is not None:
                self._seen.pop(thread_id, None)
                self._seen[thread_id] = None
                while len(self._seen) > self._max_threads:
                    old, _ = self._seen.popitem(last=False)
                    try:
                        self.delete_thread(old)
                    except Exception:  # noqa: BLE001 — eviction is best-effort
                        pass
            return result

    memory = BoundedMemorySaver(MAX_THREADS)
    compile_kwargs["checkpointer"] = memory
    graph = workflow.compile(**compile_kwargs)
