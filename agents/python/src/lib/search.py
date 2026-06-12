"""
The search node is responsible for searching the internet for information.
"""

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional, cast

from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from tavily import TavilyClient
from src.lib.searxng import search_searxng
from src.lib.qdrant import search_qdrant

from src.lib.model import get_model
from src.lib.state import AgentState

logger = logging.getLogger(__name__)


MAX_WEB_SEARCHES = 10
MAX_TOTAL_RESOURCES = 30

# Keywords that indicate the query is data/chart-worthy → trigger augmentation
_DATA_TRIGGERS = {
    "market", "share", "growth", "economy", "gdp", "price", "rate", "percent",
    "compare", "vs", "trend", "forecast", "index", "revenue", "profit", "sales",
    "largest", "statistics", "population", "export", "import", "production",
    "consumption", "investment", "inflation", "ranking", "analysis", "sector",
    "performance", "output", "capacity", "supply", "demand", "volume", "yield",
}

# Queries likely to have structured Wikipedia tables
_WIKIPEDIA_TRIGGERS = {
    "market", "share", "gdp", "economy", "population", "statistics", "ranking",
    "largest", "comparison", "history", "list", "country", "world", "global",
}

# Phrases that signal a market share / ranking / comparison query needing entity breakdown
_BREAKDOWN_TRIGGERS = {
    "market share", "market cap", "sales share",
    "top selling", "best selling", "best-selling",
    "ranking", "ranked", "top brand", "leading brand",
    "compare", "comparison", "versus",
    "largest", "biggest", "leading",
}

# If these already appear → query is already entity-level, skip adding twin
_ENTITY_ALREADY_PRESENT = {
    "by brand", "by company", "by manufacturer", "by maker", "by model",
    "per brand", "each brand", "breakdown", "brand list",
}


# ── Pydantic models ──────────────────────────────────────────────────────────

class ResourceInput(BaseModel):
    url: str = Field(description="The URL of the resource")
    title: str = Field(description="The title of the resource")
    description: str = Field(description="A short description of the resource")


class NumericFact(BaseModel):
    entity: str = Field(description="Subject being measured (company, country, product, sector)")
    metric: str = Field(description="What is measured (market share, GDP, revenue, growth rate, price, rank, etc.)")
    value: str = Field(description="The number with unit, e.g. 23.5%, $500B, 12.4M units, #3 rank")
    period: Optional[str] = Field(default=None, description="Time period: 2024, Q3 2023, YoY, CAGR, etc.")


class SeriesData(BaseModel):
    name: str = Field(description="Series label, e.g. 'Tesla', 'GDP Growth', '2023'")
    values: List[float] = Field(description="Numeric values matching each x_axis position. Must be real numbers from sources.")


class ChartDataset(BaseModel):
    chart_title: str = Field(description="Descriptive chart title")
    chart_type: str = Field(description="Recommended type: bar | line | area | donut | pie | radar | horizontal_bar")
    x_axis: List[str] = Field(description="Category labels, years, or time periods as strings")
    series: List[SeriesData] = Field(description="One or more data series with real numeric values")


class ExtractNumericsInput(BaseModel):
    facts: List[NumericFact] = Field(
        description="All important numerical facts from the search results. Extract 5–25 key data points."
    )
    markdown_table: str = Field(
        default="",
        description="A concise markdown comparison table if data warrants it (entity vs. metrics). Empty string if not applicable.",
    )
    chart_datasets: List[ChartDataset] = Field(
        default_factory=list,
        description=(
            "1–3 chart-ready datasets using ONLY real numbers found in the sources. "
            "For time-series: x_axis=[years], series=[{name, values}]. "
            "For comparisons: x_axis=[categories], one series per metric. "
            "For market share (pie/donut): x_axis=[], series=[{name:entity, values:[single_%]}]. "
            "Leave empty if no reliable numeric data was found."
        ),
    )


# ── LangChain tools ──────────────────────────────────────────────────────────

@tool
def ExtractResources(resources: List[ResourceInput]):  # pylint: disable=invalid-name,unused-argument
    """Extract the 3-5 most relevant resources from a search result."""


@tool(args_schema=ExtractNumericsInput)
def ExtractNumerics(  # pylint: disable=invalid-name,unused-argument
    facts: List[NumericFact],
    markdown_table: str,
    chart_datasets: List[ChartDataset],
):
    """Extract numerical facts, comparison tables, and chart-ready datasets from search results."""


# ── Tavily client ────────────────────────────────────────────────────────────

_tavily_client = None

def get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY environment variable is not set")
        _tavily_client = TavilyClient(api_key=tavily_api_key)
    return _tavily_client


async def async_tavily_search(query: str) -> Dict[str, Any]:
    """Tavily search with full raw page content for richer numerical data."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: get_tavily_client().search(
                query=query,
                search_depth="advanced",
                include_answer=True,
                include_raw_content=True,
                max_results=5,
            ),
        )
        # raw_content never enters chat history (stripped before ToolMessage),
        # so we can keep 6 000 chars — enough for a full Wikipedia data table.
        for item in result.get("results", []):
            if item.get("raw_content"):
                item["raw_content"] = item["raw_content"][:6000]
        return result
    except Exception as e:
        raise Exception(f"Tavily search failed: {str(e)}")


# ── Query augmentation ───────────────────────────────────────────────────────

def _year_context(query: str) -> str:
    """
    Detect year range from query and return an expanded year list for twin queries.
    Handles:  "2018-2024", "2018–2024", "2018 to 2024", "2018 2019 ... 2024", "2018 2024"
    """
    # Explicit range with dash / em-dash / "to"
    m = re.search(r"(20\d\d)\s*[-–to]+\s*(20\d\d)", query)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        years = " ".join(str(y) for y in range(start, end + 1))
        return f"{years} historical time series"

    # Multiple years mentioned — infer range from min to max
    found = sorted(set(int(y) for y in re.findall(r"20\d\d", query)))
    if len(found) >= 2 and found[-1] - found[0] >= 2:
        years = " ".join(str(y) for y in range(found[0], found[-1] + 1))
        return f"{years} historical time series"

    # Two years with gap ≥ 2 (e.g. "2018 2024")
    if len(found) == 2 and found[-1] - found[0] >= 2:
        years = " ".join(str(y) for y in range(found[0], found[-1] + 1))
        return f"{years} historical time series"

    # Single year
    if found:
        return f"{found[0]} historical"

    return "historical data time series"


def augment_queries(queries: List[str], cap: int) -> List[str]:
    """
    For data-heavy queries inject targeted twins:
    1. Wikipedia table query (reliable structured data)
    2. Official statistics query — year range preserved from original query
    3. Entity breakdown query — forces brand/company-level results for market share / ranking queries
    Total queries capped at `cap`.
    """
    augmented = list(queries)
    budget = cap - len(queries)
    for q in queries:
        if budget <= 0:
            break
        lower_q = q.lower()
        if not any(kw in lower_q for kw in _DATA_TRIGGERS):
            continue

        year_hint = _year_context(q)

        # Twin 1 — Wikipedia (structured tables, reliable numbers)
        if any(kw in lower_q for kw in _WIKIPEDIA_TRIGGERS) and budget > 0:
            wiki_twin = f"{q} wikipedia statistics table"
            if wiki_twin not in augmented:
                augmented.append(wiki_twin)
                budget -= 1

        # Twin 2 — official data, year range from the original query
        if budget > 0:
            stats_twin = f"{q} official statistics data table {year_hint}"
            if stats_twin not in augmented:
                augmented.append(stats_twin)
                budget -= 1

        # Twin 3 — entity breakdown: force brand/company-level results
        is_breakdown_query = any(t in lower_q for t in _BREAKDOWN_TRIGGERS)
        already_entity_level = any(phrase in lower_q for phrase in _ENTITY_ALREADY_PRESENT)
        if is_breakdown_query and not already_entity_level and budget > 0:
            entity_twin = f"{q} by brand company manufacturer breakdown ranking list"
            if entity_twin not in augmented:
                augmented.append(entity_twin)
                budget -= 1

    return _dedupe_similar(augmented)[:cap]


def _dedupe_similar(queries: List[str], threshold: float = 0.8) -> List[str]:
    """Drop queries whose token set overlaps ≥ threshold (Jaccard) with an earlier one."""
    kept: List[str] = []
    seen: List[set] = []
    for q in queries:
        toks = set(re.findall(r"[a-z0-9]+", q.lower()))
        if toks and any(len(toks & s) / len(toks | s) >= threshold for s in seen):
            continue
        kept.append(q)
        seen.append(toks)
    return kept


# ── Numerical extraction helper ──────────────────────────────────────────────

def _build_raw_corpus(search_results: List[Dict]) -> str:
    """Concatenate raw_content from Tavily results for the numerical extraction pass."""
    parts = []
    for res in search_results:
        if not isinstance(res, dict):
            continue
        for item in res.get("results", []):
            body = item.get("raw_content") or item.get("content", "")
            if body:
                parts.append(f"SOURCE: {item.get('title', 'Unknown')}\n{body}")
        if len(parts) >= 12:  # cap at 12 sources — corpus limit handles the rest
            break
    corpus = "\n\n---\n\n".join(parts)
    return corpus[:30000]  # ≈ 7 500 tokens — safe for 128K-context models


def _strip_raw_content(search_results: List[Dict]) -> List[Dict]:
    """Return search results with raw_content removed — safe to put in ToolMessages."""
    stripped = []
    for res in search_results:
        if not isinstance(res, dict):
            stripped.append(res)
            continue
        clean_results = []
        for item in res.get("results", []):
            clean_results.append({k: v for k, v in item.items() if k != "raw_content"})
        stripped.append({**res, "results": clean_results})
    return stripped


def _format_numerics(facts: List[dict], table: str, chart_datasets: List[dict]) -> str:
    """Format extracted data into a clean block for ToolMessage context."""
    if not facts and not table and not chart_datasets:
        return ""
    lines = []

    if chart_datasets:
        lines.append("=== CHART-READY DATASETS (use these values directly in GeneratePlotlyChart) ===")
        for ds in chart_datasets:
            if not isinstance(ds, dict):
                continue
            lines.append(f"\n📊 {ds.get('chart_title')} [type: {ds.get('chart_type')}]")
            lines.append(f"   x_axis: {ds.get('x_axis', [])}")
            for s in ds.get("series", []):
                lines.append(f"   {s.get('name')}: {s.get('values')}")

    if facts:
        lines.append("\n=== EXTRACTED NUMERICAL FACTS ===")
        for f in facts:
            period = f" ({f['period']})" if f.get("period") else ""
            lines.append(f"  • {f['entity']}: {f['metric']} = {f['value']}{period}")

    if table:
        lines.append("\n=== COMPARISON TABLE ===")
        lines.append(table)

    return "\n".join(lines)


# ── Search node ──────────────────────────────────────────────────────────────

async def search_node(state: AgentState, config: RunnableConfig):
    """
    Searches the web with three improvements:
      1. Tavily raw_content (full page text, not just snippets)
      2. Query augmentation for data-heavy topics
      3. Parallel numerical extraction pass for chart-ready facts
    """
    logger.info("=== SEARCH_NODE: Starting execution ===")

    ai_message = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            ai_message = msg
            break

    if not ai_message:
        logger.warning("No AIMessage found in search_node")
        return state

    state["resources"] = state.get("resources", [])
    state["logs"] = state.get("logs", [])

    search_sources = state.get("search_sources", ["tavily"]) or ["tavily"]

    # Base queries from AI tool call
    if ai_message.tool_calls and ai_message.tool_calls[0]["name"] == "Search":
        base_queries = ai_message.tool_calls[0]["args"].get("queries", [])[:MAX_WEB_SEARCHES]
    else:
        rq = state.get("research_question", "")
        base_queries = [rq] if rq else []

    # ── Improvement 2: augment queries ──
    queries = augment_queries(base_queries, MAX_WEB_SEARCHES)

    search_results: List[Dict] = []

    source_label = " + ".join(s.capitalize() for s in search_sources)
    for q in queries:
        state["logs"].append({"message": f'Searching [{source_label}]: "{q}"', "done": False})

    # Launch parallel searches
    tavily_tasks = [async_tavily_search(q) for q in queries if "tavily" in search_sources]
    searxng_tasks = [search_searxng(q) for q in queries if "searxng" in search_sources]
    qdrant_tasks = [search_qdrant(q) for q in queries if "qdrant" in search_sources]

    if tavily_tasks:
        for res in await asyncio.gather(*tavily_tasks, return_exceptions=True):
            if not isinstance(res, Exception):
                search_results.append(res)

    if searxng_tasks:
        for res in await asyncio.gather(*searxng_tasks, return_exceptions=True):
            if not isinstance(res, Exception):
                search_results.append({
                    "results": [{"title": r["title"], "url": r["url"], "content": r["description"]} for r in res]
                })

    if qdrant_tasks:
        for res in await asyncio.gather(*qdrant_tasks, return_exceptions=True):
            if not isinstance(res, Exception):
                search_results.append({
                    "results": [{"title": r["title"], "url": r["url"], "content": r["description"]} for r in res]
                })

    # Mark search logs done
    total_raw = sum(len(r.get("results", [])) for r in search_results if isinstance(r, dict))
    for log in state["logs"]:
        if not log["done"]:
            log["done"] = True

    model = get_model(state)
    ainvoke_kwargs = {}
    if model.__class__.__name__ in ["ChatOpenAI"]:
        ainvoke_kwargs["parallel_tool_calls"] = False

    # Strip raw_content before putting into ToolMessage — only snippets go in conversation history
    snippet_message = f"Web/Data search results: {_strip_raw_content(search_results)}"

    # Build combined messages for ExtractResources
    combined_messages = list(state["messages"])
    if ai_message.tool_calls:
        for call in ai_message.tool_calls:
            if call["name"] == "Search":
                combined_messages.append(ToolMessage(tool_call_id=call["id"], content=snippet_message))

    from src.lib.sanitize import sanitize_messages
    sanitized = sanitize_messages(combined_messages)

    extract_messages = [
        SystemMessage(content=(
            "You are a research assistant. Extract the 3–5 most relevant and data-rich resources "
            "from the search results. Prefer sources with solid numerical data, statistics, and comparisons."
        )),
        *sanitized,
    ]
    if not ai_message.tool_calls or not any(tc["name"] == "Search" for tc in ai_message.tool_calls):
        extract_messages.append(SystemMessage(content=f"Search results:\n{snippet_message}"))

    # ── Numerical extraction ──
    corpus = _build_raw_corpus(search_results)
    research_question = state.get("research_question", "")

    # Detect if research question contains a year range so we can instruct extraction explicitly
    year_range_hint = ""
    yr_match = re.search(r"(20\d\d)\s*[-–to]+\s*(20\d\d)", research_question)
    if yr_match:
        start_yr, end_yr = int(yr_match.group(1)), int(yr_match.group(2))
        all_years = list(range(start_yr, end_yr + 1))
        year_range_hint = (
            f"\n⚠️ CRITICAL: The research question asks for a YEAR RANGE {start_yr}–{end_yr}. "
            f"You MUST extract data for EVERY year in this range: {all_years}. "
            f"Do NOT skip years or summarize to just the most recent 1-2 years. "
            f"If a year is missing from the sources, mark it as missing — do not fabricate."
        )

    numerics_messages = [
        SystemMessage(content=(
            "You are a data analyst and chart specialist. Your task:\n"
            "1. Extract ALL numerical facts (percentages, values, rankings, revenues, growth rates) from the sources.\n"
            "2. Build chart_datasets — pre-formatted datasets ready to pass directly to the chart tool:\n"
            "   • Time-series: x_axis=[years/quarters as strings], series=[{name, values:[...]}]\n"
            "   • Market share (pie/donut): series=[{name:'EntityA', values:[23.5]}, ...]\n"
            "   • Comparison (bar): x_axis=[categories], series=[{name:'Metric', values:[...]}]\n"
            "   • Multi-entity over time: one series per entity with values for every year\n"
            "3. For time-series data: populate EVERY year in the x_axis — do not skip years.\n"
            "IMPORTANT: Use ONLY real numbers found in the sources. Do not estimate or fabricate. "
            f"Research topic: {research_question}{year_range_hint}"
        )),
        HumanMessage(content=(
            f"SEARCH RESULTS (full text):\n\n{corpus}\n\n"
            "Extract all numerical facts and prepare 1–3 chart-ready datasets. "
            "For time-series data, include every year found — do not collapse to a summary."
        )),
    ]

    state["logs"].append({"message": f"Extracting chart data from {total_raw} results…", "done": False})

    # ── Run ExtractResources + ExtractNumerics in parallel ──
    resource_response, numerics_response = await asyncio.gather(
        model.bind_tools([ExtractResources], tool_choice="ExtractResources", **ainvoke_kwargs).ainvoke(extract_messages, config),
        model.bind_tools([ExtractNumerics], tool_choice="ExtractNumerics", **ainvoke_kwargs).ainvoke(numerics_messages, config),
    )

    state["logs"][-1]["done"] = True
    state["logs"] = []

    # Parse resources
    resource_response = cast(AIMessage, resource_response)
    resources = resource_response.tool_calls[0]["args"]["resources"] if resource_response.tool_calls else []

    # Attach raw_content as resource content
    for resource in resources:
        resource["resource_type"] = "web"
        resource["source"] = "Smart Search"
        for res in search_results:
            if not isinstance(res, dict):
                continue
            for item in res.get("results", []):
                if item.get("url") == resource.get("url"):
                    body = item.get("raw_content") or item.get("content", "")
                    resource["content"] = body[:5000]
                    resource["source"] = item.get("title", "Smart Search")
                    break

    # Deduplicate + cap
    existing_urls = {r.get("url") for r in state["resources"]}
    unique = [r for r in resources if r.get("url") not in existing_urls]
    slots = MAX_TOTAL_RESOURCES - len(state["resources"])
    state["resources"].extend(unique[:slots])

    # Parse numerical facts + chart datasets
    numerics_response = cast(AIMessage, numerics_response)
    new_facts: List[dict] = []
    new_chart_datasets: List[dict] = []
    formatted_numerics = ""

    if numerics_response.tool_calls:
        args = numerics_response.tool_calls[0]["args"]
        new_facts = args.get("facts", [])
        raw_table = args.get("markdown_table", "")
        # Drop table if it looks like an unfilled placeholder (e.g. "{comparison_table}")
        table = "" if re.search(r'^\{[a-z][a-z_0-9]*\}$', raw_table.strip()) else raw_table
        new_chart_datasets = [d for d in args.get("chart_datasets", []) if isinstance(d, dict)]

        formatted_numerics = _format_numerics(new_facts, table, new_chart_datasets)

        logger.info(
            f"Extracted {len(new_facts)} facts, {len(new_chart_datasets)} chart datasets"
        )

    # Accumulate in state (cap to avoid bloat)
    all_facts = (state.get("extracted_numerics", []) + new_facts)[-80:]
    all_datasets = [d for d in (state.get("chart_datasets", []) + new_chart_datasets) if isinstance(d, dict)][-8:]

    # Build ToolMessages with enriched numerical context
    tool_messages = []
    if ai_message.tool_calls:
        for call in ai_message.tool_calls:
            if call["name"] == "Search":
                content = f"Search completed. Found {len(unique[:slots])} new sources."
                if formatted_numerics:
                    content += f"\n\n{formatted_numerics}"
                tool_messages.append(ToolMessage(tool_call_id=call["id"], content=content))

    return {
        "resources": state["resources"],
        "messages": tool_messages,
        "extracted_numerics": all_facts,
        "chart_datasets": all_datasets,
    }
