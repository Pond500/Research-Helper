import re

with open("src/lib/search.py", "r") as f:
    content = f.read()

# Add imports if not present
if "from src.lib.searxng import search_searxng" not in content:
    content = content.replace("from tavily import TavilyClient", "from tavily import TavilyClient\nfrom src.lib.searxng import search_searxng\nfrom src.lib.qdrant import search_qdrant")

# We will rewrite search_node
new_search_node = """
async def search_node(state: AgentState, config: RunnableConfig):
    \"\"\"
    The search node is responsible for searching the internet for resources.
    Performs Tavily web search, SearxNG API search, and Qdrant vector search according to state toggles.
    \"\"\"
    logger.info("=== SEARCH_NODE: Starting execution ===")
    
    # Force initial state emission to ensure CopilotKit registers the step as started
    await copilotkit_emit_state(config, state)
    
    try:
        # Find the last AIMessage (not ToolMessage) in the messages
        ai_message = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage):
                ai_message = msg
                break

        if not ai_message:
            logger.warning("No AIMessage found in search_node - returning state unchanged")
            return state

        state["resources"] = state.get("resources", [])
        state["logs"] = state.get("logs", [])
        
        # Get selected sources
        search_sources = state.get("search_sources", ["tavily"])
        if not search_sources:
            search_sources = ["tavily"]

        if ai_message.tool_calls and ai_message.tool_calls[0]["name"] == "Search":
            queries = ai_message.tool_calls[0]["args"].get("queries", [])[:MAX_WEB_SEARCHES]
        else:
            research_question = state.get("research_question", "")
            queries = [research_question] if research_question else []
            queries = queries[:MAX_WEB_SEARCHES]

        search_results = []

        for query in queries:
            state["logs"].append({"message": f"Deep Search across {len(search_sources)} engines: {query}", "done": False})
        
        if queries:
            await copilotkit_emit_state(config, state)

        # Launch parallel searches
        tavily_tasks = []
        searxng_tasks = []
        qdrant_tasks = []
        
        for query in queries:
            if "tavily" in search_sources:
                tavily_tasks.append(async_tavily_search(query))
            if "searxng" in search_sources:
                searxng_tasks.append(search_searxng(query))
            if "qdrant" in search_sources:
                qdrant_tasks.append(search_qdrant(query))

        # Gather Tavily
        if tavily_tasks:
            tavily_results = await asyncio.gather(*tavily_tasks, return_exceptions=True)
            for res in tavily_results:
                if not isinstance(res, Exception):
                    search_results.append(res)
        
        # Gather Searxng and format into Dict similar to tavily so model understands
        if searxng_tasks:
            searxng_results = await asyncio.gather(*searxng_tasks, return_exceptions=True)
            for res in searxng_results:
                if not isinstance(res, Exception):
                    search_results.append({"results": [{"title": r["title"], "url": r["url"], "content": r["description"]} for r in res]})

        # Gather Qdrant
        if qdrant_tasks:
            qdrant_results = await asyncio.gather(*qdrant_tasks, return_exceptions=True)
            for res in qdrant_results:
                if not isinstance(res, Exception):
                    search_results.append({"results": [{"title": r["title"], "url": r["url"], "content": r["description"]} for r in res]})

        if queries and state["logs"]:
            state["logs"][-1]["done"] = True
            await copilotkit_emit_state(config, state)

        model = get_model(state)
        ainvoke_kwargs = {}
        if model.__class__.__name__ in ["ChatOpenAI"]:
            ainvoke_kwargs["parallel_tool_calls"] = False

        # Prepare search results message
        search_message = f"Web/Data search results: {search_results}"

        extract_messages = [
            SystemMessage(
                content=\"\"\"
            You need to extract the 3-5 most relevant resources from the following search results.
            Focus on resources that contain solid numerical data, metrics, or factual statements.
            \"\"\"
            ),
            *state["messages"],
        ]

        if ai_message.tool_calls and ai_message.tool_calls[0]["name"] == "Search":
            extract_messages.extend([
                ToolMessage(
                    tool_call_id=call["id"],
                    content=search_message if i == 0 else "Tool ignored."
                )
                for i, call in enumerate(ai_message.tool_calls)
            ])
        else:
            extract_messages.append(
                SystemMessage(content=f"Search results:\\n{search_message}")
            )

        state["logs"].append({"message": "Selecting most relevant resources...", "done": False})
        await copilotkit_emit_state(config, state)

        # Extract relevant resources using ExtractResources tool
        response = await model.bind_tools(
            [ExtractResources], tool_choice="ExtractResources", **ainvoke_kwargs
        ).ainvoke(extract_messages, config)

        state["logs"][-1]["done"] = True
        state["logs"] = []
        await copilotkit_emit_state(config, state)

        ai_message_response = cast(AIMessage, response)
        resources = ai_message_response.tool_calls[0]["args"]["resources"]

        # Tag resources with resource_type and attach content
        for resource in resources:
            resource["resource_type"] = "web"
            resource["source"] = "Tri-Modal Search"
            for search_result in search_results:
                if isinstance(search_result, dict) and "results" in search_result:
                    for tavily_item in search_result["results"]:
                        if tavily_item.get("url") == resource.get("url"):
                            resource["content"] = tavily_item.get("content", "")
                            resource["source"] = tavily_item.get("title", "Tri-Modal Search")
                            break

        current_count = len(state["resources"])
        remaining_slots = MAX_TOTAL_RESOURCES - current_count

        existing_urls = {r.get("url") for r in state["resources"]}

        unique_resources = []
        for r in resources:
            if r.get("url") not in existing_urls:
                unique_resources.append(r)
                existing_urls.add(r.get("url"))

        if remaining_slots > 0:
            resources_to_add = unique_resources[:remaining_slots]
            state["resources"].extend(resources_to_add)
        else:
            resources_to_add = []

        return state
        
    except Exception as e:
        logger.error(f"Error in search_node: {e}", exc_info=True)
        return state
"""

import ast

class RewriteSearchNode(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if node.name == 'search_node':
            return ast.parse(new_search_node).body[0]
        return node

tree = ast.parse(content)
tree = RewriteSearchNode().visit(tree)
ast.fix_missing_locations(tree)
new_search_node_code = ast.unparse(tree)

# Because unparse formatting can be a bit weird sometimes and strips comments,
# it's usually safer to use regex to replace the function.
start_idx = content.find("async def search_node")
end_idx = content.find("def ", start_idx + 1)
if end_idx == -1:
    end_idx = len(content)

final_code = content[:start_idx] + new_search_node + "\n"
with open("src/lib/search.py", "w") as f:
    f.write(final_code)

print("Patch applied to search.py")
