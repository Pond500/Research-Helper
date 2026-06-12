"""
Chart Tool — generates ECharts JSON option specs for the frontend to render natively.
Charts are stored in AgentState["charts"] and rendered as interactive React components.
"""

import uuid
from typing import Any, List, Literal, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

BRAND_COLORS = [
    "#6766FC", "#34D399", "#F59E0B", "#EF4444",
    "#8B5CF6", "#06B6D4", "#EC4899", "#F97316",
    "#10B981", "#3B82F6", "#A78BFA", "#FCD34D",
]


def _grad(color: str, opacity_start: str = "99", opacity_end: str = "00") -> dict:
    return {
        "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
        "colorStops": [
            {"offset": 0, "color": f"{color}{opacity_start}"},
            {"offset": 1, "color": f"{color}{opacity_end}"},
        ],
    }


def _hgrad(color: str) -> dict:
    return {
        "type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
        "colorStops": [
            {"offset": 0, "color": f"{color}CC"},
            {"offset": 1, "color": color},
        ],
    }


def _base(title: str, source: Optional[str]) -> dict:
    base: dict = {
        "animation": True,
        "animationDuration": 900,
        "animationEasing": "cubicOut",
        "animationDurationUpdate": 400,
        "color": BRAND_COLORS,
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": "Inter, ui-sans-serif, sans-serif", "color": "#374151"},
        "title": {
            "text": title,
            "textStyle": {"fontSize": 14, "fontWeight": "600", "color": "#111827"},
            "left": 0, "top": 4,
        },
        "tooltip": {
            "trigger": "axis",
            "confine": True,
            "axisPointer": {
                "type": "cross",
                "crossStyle": {"color": "#CBD5E1", "width": 1, "type": "dashed"},
                "label": {"backgroundColor": "#6766FC", "fontSize": 11, "padding": [4, 8]},
            },
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": "#E5E7EB",
            "borderWidth": 1,
            "textStyle": {"color": "#111827", "fontSize": 12},
            "padding": [10, 14],
            "extraCssText": "box-shadow: 0 8px 24px rgba(0,0,0,0.12); border-radius: 10px;",
        },
        "grid": {"left": 16, "right": 24, "top": 56, "bottom": 40, "containLabel": True},
        "toolbox": {
            "show": True,
            "right": 4,
            "top": 2,
            "feature": {
                "saveAsImage": {
                    "title": "Save PNG",
                    "pixelRatio": 2,
                    "backgroundColor": "#FFFFFF",
                },
                "restore": {"title": "Reset"},
                "dataZoom": {"title": {"zoom": "Zoom", "back": "Reset zoom"}},
            },
            "iconStyle": {"borderColor": "#9CA3AF"},
            "emphasis": {"iconStyle": {"borderColor": "#6766FC", "color": "#6766FC"}},
        },
    }
    if source:
        base["graphic"] = [{
            "type": "text", "right": 4, "bottom": -2,
            "style": {"text": f"Source: {source}", "fontSize": 9, "fill": "#9CA3AF"},
        }]
    return base


def _numeric_max(values: List[Any]) -> float:
    nums = [abs(v) for v in values if isinstance(v, (int, float))]
    return float(max(nums)) if nums else 0.0


def _maybe_dual_axis(
    opt: dict, series: List[Any], y_axis_secondary_name: Optional[str]
) -> dict:
    """
    Series with wildly different scales (e.g. GDP in $B vs GDP per capita in $)
    flatten the smaller one when sharing a y-axis — move outliers (≥8× scale
    difference vs the first series) onto an auto-added secondary axis.
    """
    SCALE_RATIO = 8
    y_axis = opt.get("yAxis")
    if len(series) < 2 or not isinstance(y_axis, dict) or y_axis.get("type") != "value":
        return opt
    maxes = [_numeric_max(s.values) for s in series]
    nonzero = [m for m in maxes if m > 0]
    if len(nonzero) < 2 or max(nonzero) / min(nonzero) < SCALE_RATIO:
        return opt

    ref = next((m for m in maxes if m > 0), 0.0)
    base_axis = opt["yAxis"]
    secondary = {
        **base_axis,
        "name": y_axis_secondary_name or "",
        "splitLine": {"show": False},
    }
    opt["yAxis"] = [base_axis, secondary]
    for i, ser_cfg in enumerate(opt.get("series", [])):
        m = maxes[i] if i < len(maxes) else 0.0
        if m > 0 and (m / ref >= SCALE_RATIO or ref / m >= SCALE_RATIO):
            ser_cfg["yAxisIndex"] = 1
    return opt


def _build_option(
    chart_type: str,
    title: str,
    x_axis: Optional[List[str]],
    series: List[Any],
    y_axis_name: Optional[str],
    y_axis_secondary_name: Optional[str],
    source_attribution: Optional[str],
    country_iso: Optional[List[str]],
    parent: Optional[List[str]],
) -> dict:
    base = _base(title, source_attribution)

    # LINE / AREA
    if chart_type in ("line", "area"):
        has_many_points = len(x_axis or []) > 12
        opt = {**base,
            "legend": {"show": True, "bottom": 28 if has_many_points else 0, "type": "scroll",
                       "textStyle": {"fontSize": 11, "color": "#6B7280"},
                       "inactiveColor": "#D1D5DB"},
            "xAxis": {
                "type": "category", "data": x_axis or [], "boundaryGap": False,
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
                "axisTick": {"lineStyle": {"color": "#E5E7EB"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "yAxis": {
                "type": "value", "name": y_axis_name or "",
                "nameTextStyle": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"show": False}, "axisTick": {"show": False},
                "splitLine": {"lineStyle": {"color": "#F3F4F6", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100, "zoomOnMouseWheel": True},
                {
                    "type": "slider", "start": 0, "end": 100,
                    "height": 20, "bottom": 0,
                    "borderColor": "#E5E7EB",
                    "backgroundColor": "#F3F4F6",
                    "fillerColor": "rgba(103,102,252,0.2)",
                    "handleStyle": {"color": "#6766FC", "borderColor": "#6766FC"},
                    "moveHandleStyle": {"color": "#6766FC"},
                    "textStyle": {"color": "#6B7280"},
                    "showDataShadow": False,
                    "showDetail": False,
                } if has_many_points else {"type": "inside", "disabled": True},
            ],
            "series": [],
        }
        for i, s in enumerate(series):
            color = BRAND_COLORS[i % len(BRAND_COLORS)]
            ser: dict = {
                "name": s.name, "type": "line", "data": s.values,
                "smooth": True, "symbol": "circle", "symbolSize": 6,
                "lineStyle": {"width": 2.5, "color": color},
                "itemStyle": {"color": color, "borderWidth": 2, "borderColor": "#FFFFFF"},
                "emphasis": {
                    "scale": True,
                    "itemStyle": {"shadowBlur": 12, "shadowColor": f"{color}66"},
                },
            }
            if chart_type == "area":
                ser["areaStyle"] = {"color": _grad(color, "55", "05")}
            opt["series"].append(ser)
        return _maybe_dual_axis(opt, series, y_axis_secondary_name)

    # BAR / HORIZONTAL_BAR
    if chart_type in ("bar", "horizontal_bar"):
        h = chart_type == "horizontal_bar"
        rotate = 30 if (not h and len(x_axis or []) > 7) else 0
        opt = {**base,
            "legend": {"show": len(series) > 1, "bottom": 0,
                       "textStyle": {"fontSize": 11, "color": "#6B7280"},
                       "inactiveColor": "#D1D5DB"},
            "series": [],
        }
        if h:
            opt["xAxis"] = {
                "type": "value", "name": y_axis_name or "",
                "splitLine": {"lineStyle": {"color": "#F3F4F6", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"show": False},
            }
            opt["yAxis"] = {
                "type": "category", "data": x_axis or [],
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
                "axisTick": {"show": False},
            }
        else:
            opt["xAxis"] = {
                "type": "category", "data": x_axis or [],
                "axisLabel": {"rotate": rotate, "color": "#6B7280", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
                "axisTick": {"show": False},
            }
            opt["yAxis"] = {
                "type": "value", "name": y_axis_name or "",
                "nameTextStyle": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"show": False}, "axisTick": {"show": False},
                "splitLine": {"lineStyle": {"color": "#F3F4F6", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            }
        for i, s in enumerate(series):
            color = BRAND_COLORS[i % len(BRAND_COLORS)]
            opt["series"].append({
                "name": s.name, "type": "bar", "data": s.values, "barMaxWidth": 52,
                "itemStyle": {
                    "color": _hgrad(color) if h else _grad(color, "EE", "88"),
                    "borderRadius": [0, 4, 4, 0] if h else [4, 4, 0, 0],
                },
                "label": {
                    "show": True,
                    "position": "right" if h else "top",
                    "fontSize": 10, "color": "#6B7280",
                    "formatter": "{c}",
                },
                "emphasis": {
                    "itemStyle": {"opacity": 0.9, "shadowBlur": 8, "shadowColor": f"{color}44"},
                    "label": {"color": "#111827"},
                },
            })
        return _maybe_dual_axis(opt, series, y_axis_secondary_name)

    # PIE / DONUT
    if chart_type in ("pie", "donut"):
        is_donut = chart_type == "donut"
        # Support two LLM calling patterns:
        # A) x_axis=["Tesla","BYD",...], series=[{name:"Share", values:[23,18,...]}]
        # B) series=[{name:"Tesla",values:[23]},{name:"BYD",values:[18]},...]  ← each entity as series
        if len(series) > 1 and all(len(s.values) == 1 for s in series):
            names = [s.name for s in series]
            values = [s.values[0] for s in series]
        else:
            names = x_axis or [s.name for s in series] or [f"Item {i+1}" for i in range(len(series[0].values if series else []))]
            values = series[0].values if series else []
        total = sum(float(v) for v in values if isinstance(v, (int, float)))
        pie_data = [
            {"name": n, "value": v, "itemStyle": {"color": BRAND_COLORS[i % len(BRAND_COLORS)]}}
            for i, (n, v) in enumerate(zip(names, values))
        ]
        series_cfg: dict = {
            "type": "pie",
            "radius": ["46%", "70%"] if is_donut else ["0%", "68%"],
            "center": ["40%", "54%"],
            "data": pie_data,
            "label": {
                "show": True,
                "formatter": "{b}\n{d}%",
                "fontSize": 11,
                "color": "#6B7280",
                "lineHeight": 16,
            },
            "labelLine": {"length": 10, "length2": 8, "lineStyle": {"color": "#D1D5DB"}},
            "emphasis": {
                "scale": True, "scaleSize": 8,
                "itemStyle": {"shadowBlur": 20, "shadowColor": "rgba(103,102,252,0.4)"},
                "label": {"fontSize": 13, "fontWeight": "bold", "color": "#111827"},
            },
            "selectedMode": "single",
            "selectedOffset": 8,
        }
        if is_donut:
            series_cfg["label"]["show"] = False
            series_cfg["labelLine"] = {"show": False}
            series_cfg["emphasis"]["label"] = {"show": False}
        opt = {**base,
            "tooltip": {
                "trigger": "item",
                "formatter": "<b>{b}</b><br/>Value: {c}<br/>Share: {d}%",
                "backgroundColor": "rgba(15,23,42,0.97)",
                "borderColor": "#E5E7EB",
                "borderWidth": 1,
                "textStyle": {"color": "#111827", "fontSize": 12},
                "extraCssText": "box-shadow: 0 8px 24px rgba(0,0,0,0.4); border-radius: 10px;",
            },
            "legend": {
                "orient": "vertical", "right": "2%", "top": "middle",
                "type": "scroll",
                "textStyle": {"fontSize": 11, "color": "#6B7280"},
                "inactiveColor": "#E5E7EB",
                "icon": "circle",
            },
            "series": [series_cfg],
        }
        if is_donut:
            top_item = max(zip(names, values), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 0, default=("", 0))
            opt["graphic"] = (base.get("graphic") or []) + [{
                "type": "group", "left": "center", "top": "center",
                "children": [
                    {
                        "type": "text", "left": "center", "top": -14,
                        "style": {"text": str(top_item[0]), "fontSize": 11, "fill": "#6B7280", "textAlign": "center"},
                    },
                    {
                        "type": "text", "left": "center", "top": 4,
                        "style": {"text": f"{float(top_item[1])/total*100:.1f}%" if total else "—", "fontSize": 20, "fontWeight": "bold", "fill": "#111827", "textAlign": "center"},
                    },
                ],
            }]
        return opt

    # SCATTER
    if chart_type == "scatter":
        opt = {**base,
            "tooltip": {"trigger": "item"},
            "xAxis": {
                "type": "value", "name": x_axis[0] if x_axis else "X",
                "splitLine": {"lineStyle": {"color": "#111827", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "yAxis": {
                "type": "value", "name": y_axis_name or "Y",
                "splitLine": {"lineStyle": {"color": "#111827", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "series": [],
        }
        for i, s in enumerate(series):
            color = BRAND_COLORS[i % len(BRAND_COLORS)]
            opt["series"].append({
                "name": s.name, "type": "scatter", "data": s.values,
                "symbolSize": 10, "itemStyle": {"color": color, "opacity": 0.8},
                "emphasis": {"itemStyle": {"opacity": 1, "shadowBlur": 8}},
            })
        return opt

    # CANDLESTICK
    if chart_type == "candlestick":
        opt = {**base,
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
            "xAxis": {
                "type": "category", "data": x_axis or [], "scale": True,
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
            },
            "yAxis": {
                "scale": True,
                "splitLine": {"lineStyle": {"color": "#111827", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "series": [{
                "type": "candlestick",
                "data": series[0].values if series else [],
                "itemStyle": {
                    "color": "#34D399", "color0": "#EF4444",
                    "borderColor": "#059669", "borderColor0": "#DC2626",
                },
            }],
        }
        if len(series) > 1:
            opt["series"].append({
                "name": series[1].name, "type": "line", "data": series[1].values,
                "smooth": True, "lineStyle": {"color": "#F59E0B", "width": 1.5},
                "itemStyle": {"color": "#F59E0B"}, "symbol": "none",
            })
        return opt

    # RADAR
    if chart_type == "radar":
        max_val = 100
        try:
            all_vals = [v for s in series for v in s.values if isinstance(v, (int, float))]
            if all_vals:
                max_val = round(max(all_vals) * 1.25)
        except Exception:
            pass
        indicators = [{"name": cat, "max": max_val} for cat in (x_axis or [])]
        opt = {**base,
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11, "color": "#6B7280"}},
            "radar": {
                "indicator": indicators,
                "splitArea": {"areaStyle": {"color": ["#FAFAFA", "#F3F4F6", "#E5E7EB"]}},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
                "splitLine": {"lineStyle": {"color": "#E5E7EB"}},
                "axisName": {"color": "#D1D5DB", "fontSize": 11},
            },
            "series": [],
        }
        for i, s in enumerate(series):
            color = BRAND_COLORS[i % len(BRAND_COLORS)]
            opt["series"].append({
                "type": "radar",
                "data": [{"value": s.values, "name": s.name,
                           "areaStyle": {"opacity": 0.25, "color": color},
                           "lineStyle": {"color": color, "width": 2},
                           "itemStyle": {"color": color}}],
            })
        return opt

    # HEATMAP
    if chart_type == "heatmap":
        row_names = [s.name for s in series]
        opt = {**base,
            "tooltip": {"position": "top"},
            "grid": {"left": 16, "right": 16, "top": 56, "bottom": 56, "containLabel": True},
            "xAxis": {
                "type": "category", "data": x_axis or [], "splitArea": {"show": True},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "yAxis": {
                "type": "category", "data": row_names, "splitArea": {"show": True},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "visualMap": {
                "show": True, "calculable": True, "orient": "horizontal",
                "left": "center", "bottom": 0,
                "inRange": {"color": ["#EEF2FF", "#6766FC"]},
                "textStyle": {"color": "#6B7280", "fontSize": 10},
            },
            "series": [{
                "type": "heatmap",
                "data": series[0].values if series else [],
                "label": {"show": True, "fontSize": 11},
                "emphasis": {"itemStyle": {"shadowBlur": 8}},
            }],
        }
        return opt

    # COMBINATION (bar + line dual-axis)
    if chart_type == "combination":
        has_secondary = bool(y_axis_secondary_name)
        opt = {**base,
            "legend": {"show": True, "bottom": 0,
                       "textStyle": {"fontSize": 11, "color": "#6B7280"}},
            "xAxis": {
                "type": "category", "data": x_axis or [],
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
            },
            "yAxis": [{
                "type": "value", "name": y_axis_name or "",
                "nameTextStyle": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"show": False}, "axisTick": {"show": False},
                "splitLine": {"lineStyle": {"color": "#111827", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            }],
            "series": [],
        }
        if has_secondary:
            opt["yAxis"].append({
                "type": "value", "name": y_axis_secondary_name,
                "nameTextStyle": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"show": False}, "axisTick": {"show": False},
                "splitLine": {"show": False},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            })
        half = max(1, len(series) // 2)
        for i, s in enumerate(series):
            color = BRAND_COLORS[i % len(BRAND_COLORS)]
            use_line = i >= half
            y_idx = 1 if (has_secondary and use_line) else 0
            if use_line:
                opt["series"].append({
                    "name": s.name, "type": "line", "data": s.values, "yAxisIndex": y_idx,
                    "smooth": True, "symbol": "circle", "symbolSize": 5,
                    "lineStyle": {"width": 2.5, "color": color},
                    "itemStyle": {"color": color, "borderWidth": 2, "borderColor": "#fff"},
                })
            else:
                opt["series"].append({
                    "name": s.name, "type": "bar", "data": s.values, "yAxisIndex": y_idx,
                    "barMaxWidth": 48,
                    "itemStyle": {"color": _grad(color, "EE", "AA"), "borderRadius": [4, 4, 0, 0]},
                })
        return opt

    # FUNNEL
    if chart_type == "funnel":
        names = x_axis or [s.name for s in series]
        values = series[0].values if series else []
        funnel_data = sorted(
            [{"name": n, "value": v} for n, v in zip(names, values)],
            key=lambda x: x["value"], reverse=True,
        )
        opt = {**base,
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)",
                        "backgroundColor": "#fff", "borderColor": "#E5E7EB"},
            "series": [{
                "type": "funnel", "left": "8%", "width": "84%",
                "label": {"show": True, "position": "inside",
                          "formatter": "{b}\n{d}%", "fontSize": 12},
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                "data": funnel_data,
                "emphasis": {"label": {"fontSize": 13}},
            }],
        }
        return opt

    # WATERFALL
    if chart_type == "waterfall":
        values = series[0].values if series else []
        labels = x_axis or [f"Item {i+1}" for i in range(len(values))]
        helpers, positives, negatives = [], [], []
        running = 0
        for v in values:
            if v >= 0:
                helpers.append(running)
                positives.append(v)
                negatives.append(0)
            else:
                helpers.append(running + v)
                positives.append(0)
                negatives.append(abs(v))
            running += v
        opt = {**base,
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11, "color": "#6B7280"}},
            "xAxis": {
                "type": "category", "data": labels,
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#E5E7EB"}},
            },
            "yAxis": {
                "type": "value", "name": y_axis_name or "",
                "splitLine": {"lineStyle": {"color": "#111827", "type": "dashed"}},
                "axisLabel": {"color": "#6B7280", "fontSize": 11},
            },
            "series": [
                {"name": "", "type": "bar", "stack": "wf", "data": helpers,
                 "itemStyle": {"color": "transparent", "borderColor": "transparent"},
                 "tooltip": {"show": False}},
                {"name": "Increase", "type": "bar", "stack": "wf", "data": positives,
                 "itemStyle": {"color": "#34D399", "borderRadius": [4, 4, 0, 0]}},
                {"name": "Decrease", "type": "bar", "stack": "wf", "data": negatives,
                 "itemStyle": {"color": "#EF4444", "borderRadius": [4, 4, 0, 0]}},
            ],
        }
        return opt

    # TREEMAP
    if chart_type == "treemap":
        names = x_axis or [s.name for s in series]
        values_list = series[0].values if series else []
        tree_data = [{"name": n, "value": v} for n, v in zip(names, values_list)]
        opt = {**base,
            "tooltip": {"formatter": "{b}: {c}"},
            "series": [{
                "type": "treemap",
                "data": tree_data,
                "width": "100%", "height": "85%",
                "label": {"show": True, "fontSize": 12},
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                "levels": [
                    {"itemStyle": {"borderColor": "#E5E7EB", "borderWidth": 3, "gapWidth": 3}},
                    {"itemStyle": {"borderColor": "#fff", "borderWidth": 2, "gapWidth": 2}},
                ],
            }],
        }
        return opt

    # Fallback
    return {**base,
        "xAxis": {"type": "category", "data": x_axis or []},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": series[0].values if series else []}],
    }


# ── Pydantic models ────────────────────────────────────────────────────────────

class SeriesData(BaseModel):
    name: str
    values: List[Any]


class GeneratePlotlyChartInput(BaseModel):
    chart_type: Literal[
        "line", "area", "bar", "horizontal_bar", "pie", "donut",
        "scatter", "candlestick", "radar", "heatmap", "combination",
        "funnel", "waterfall", "treemap",
    ] = Field(description=(
        "Chart type. Choose: "
        "'line'/'area' for time-series trends; "
        "'bar'/'horizontal_bar' for category comparisons (use horizontal when labels are long); "
        "'pie'/'donut' for proportions/market-share; "
        "'scatter' for correlations (values must be [[x,y], ...]); "
        "'candlestick' for OHLC price data (values must be [[open,close,low,high], ...]); "
        "'radar' for multi-dimension entity comparisons (normalise values to 0-100); "
        "'heatmap' for matrix intensity (values must be [[col_idx, row_idx, value], ...]); "
        "'combination' for bar+line dual-axis; "
        "'funnel' for conversion pipelines; "
        "'waterfall' for running totals / cash flow; "
        "'treemap' for hierarchical proportions."
    ))
    title: str = Field(description="Short descriptive chart title.")
    x_axis: Optional[List[str]] = Field(default=None, description="X-axis category labels or names.")
    series: List[SeriesData] = Field(description=(
        "Data series list. Each has a name and a values array. "
        "Use null (NOT 0) for periods with no data — a 0 draws a misleading plunge to zero, "
        "null leaves a gap. All series should align with x_axis positions."
    ))
    y_axis_name: Optional[str] = Field(default=None, description="Left Y-axis label.")
    y_axis_secondary_name: Optional[str] = Field(default=None,
        description="Right Y-axis label — only for combination charts with two scales.")
    source_attribution: str = Field(description="Data source citation shown on the chart.")
    country_iso: Optional[List[str]] = Field(default=None, description="ISO-3 codes for map charts.")
    parent: Optional[List[str]] = Field(default=None, description="Parent node names for treemap.")


def run_chart_tool(args: dict) -> str:
    """Call chart generation logic directly (bypasses LangChain tool invoke machinery)."""
    params = GeneratePlotlyChartInput(**args)
    chart_id = str(uuid.uuid4())[:8]
    option = _build_option(
        chart_type=params.chart_type, title=params.title, x_axis=params.x_axis,
        series=params.series, y_axis_name=params.y_axis_name,
        y_axis_secondary_name=params.y_axis_secondary_name,
        source_attribution=params.source_attribution,
        country_iso=params.country_iso, parent=params.parent,
    )
    import json
    return f"CHART_READY:{chart_id}:{params.title}|OPTION:{json.dumps(option, ensure_ascii=False)}"


@tool(args_schema=GeneratePlotlyChartInput)
def GeneratePlotlyChart(
    chart_type: str,
    title: str,
    series: List[SeriesData],
    source_attribution: str,
    x_axis: Optional[List[str]] = None,
    y_axis_name: Optional[str] = None,
    y_axis_secondary_name: Optional[str] = None,
    country_iso: Optional[List[str]] = None,
    parent: Optional[List[str]] = None,
) -> str:
    """
    Generate a beautiful interactive ECharts visualisation.
    Returns CHART_READY:{chart_id}:{title} — the chart_id is used in chat.py to store the spec.
    Insert [CHART:{chart_id}] in your report markdown exactly where the chart should appear.
    """
    chart_id = str(uuid.uuid4())[:8]
    option = _build_option(
        chart_type=chart_type, title=title, x_axis=x_axis, series=series,
        y_axis_name=y_axis_name, y_axis_secondary_name=y_axis_secondary_name,
        source_attribution=source_attribution, country_iso=country_iso, parent=parent,
    )
    # Return chart_id + serialised option separated by a sentinel so chat.py can parse it
    import json
    return f"CHART_READY:{chart_id}:{title}|OPTION:{json.dumps(option, ensure_ascii=False)}"
