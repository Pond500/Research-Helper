"""
A2UI Tool — lets the agent generate declarative structured UI components
following the A2UI standard (https://github.com/google/a2ui).

Components are stored in AgentState["pending_a2ui"] and streamed to the
frontend via AG-UI StateDeltaEvent automatically by ag_ui_langgraph.
"""

import json
from typing import Any, Dict, List, Literal, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field


class SeriesData(BaseModel):
    name: str
    values: List[Any]


class A2UIComponentInput(BaseModel):
    type: Literal["stat_card", "comparison_table", "data_grid", "timeline", "kpi_row"] = Field(
        description=(
            "Component type. Choose: "
            "'stat_card' for a single highlighted metric; "
            "'kpi_row' for a row of 2-5 KPI values side by side; "
            "'comparison_table' for comparing multiple entities across attributes; "
            "'data_grid' for tabular data with column headers and rows; "
            "'timeline' for chronological events."
        )
    )
    title: str = Field(description="Short descriptive title shown above the component.")
    data: Dict[str, Any] = Field(
        description=(
            "Structured data for the component. Schema per type:\n"
            "stat_card:        {value, unit?, change?, change_label?}\n"
            "kpi_row:          {items: [{label, value, unit?, change?}]}\n"
            "comparison_table: {columns: [str], rows: [{label: str, values: [any]}]}\n"
            "data_grid:        {headers: [str], rows: [[any]]}\n"
            "timeline:         {events: [{date: str, title: str, description?: str}]}"
        )
    )
    source: Optional[str] = Field(default=None, description="Data source attribution (e.g. 'World Bank 2024').")


@tool(args_schema=A2UIComponentInput)
def GenerateA2UIComponent(
    type: str,
    title: str,
    data: Dict[str, Any],
    source: Optional[str] = None,
) -> str:
    """
    Generate a structured interactive UI component for the research report.
    Use this instead of plain markdown tables or lists when presenting:
    - key statistics (stat_card, kpi_row)
    - entity comparisons (comparison_table)
    - tabular datasets (data_grid)
    - chronological events (timeline)
    The component will be rendered visually in the frontend.
    """
    component = {"type": type, "title": title, "data": data}
    if source:
        component["source"] = source
    return json.dumps(component)
