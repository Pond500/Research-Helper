"""Chat Node"""

import logging
import re
from datetime import date
from typing import Dict, List, Literal, Tuple, cast

from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.lib.download import get_resource
from src.lib.model import get_model
from src.lib.state import AgentState, DataQuestion
from src.lib.chart_tool import GeneratePlotlyChart, run_chart_tool
from src.lib.state import ChartSpec
from src.lib.a2ui_tool import GenerateA2UIComponent

logger = logging.getLogger(__name__)


# Feature toggles
ENABLE_DEEP_QUERIES = False


@tool
def Search(queries: List[str]):  # pylint: disable=invalid-name,unused-argument
    """A list of one or more search queries to find good resources to support the research."""


@tool
def WriteReport(report: str):  # pylint: disable=invalid-name,unused-argument
    """Write the research report."""


@tool
def WriteResearchQuestion(research_question: str):  # pylint: disable=invalid-name,unused-argument
    """Write the research question."""


@tool
def DeleteResources(urls: List[str]):  # pylint: disable=invalid-name,unused-argument
    """Delete the URLs from the resources."""

@tool
def DeepScrapeWebsite(url: str):  # pylint: disable=invalid-name,unused-argument
    """Use this tool to bypass search engine snippets and download the FULL text content of a specific URL (up to 50,000 characters). Use this when you need deep insights from a specific page."""





_NUM_RE = re.compile(r'\d+\.?\d*')

def _nums_from_text(text: str) -> List[str]:
    """Extract all numeric strings (stripped of %, $, commas) from text."""
    return [m.group(0) for m in _NUM_RE.finditer(re.sub(r"[%$,]", " ", text))]


def _auto_inject_citations(
    report: str, extracted_facts: List[dict], resources: List[dict]
) -> Tuple[str, Dict[str, dict]]:
    """
    Match numbers from resources against the report, inject [N] markers inline.
    Two strategies in order: extracted facts → content numerics. Both verify the
    cited resource actually contains the number. Returns (annotated_report, citations_dict).
    """
    report_lower = report.lower()
    value_to_n: Dict[str, int] = {}  # display_string → 1-based resource index

    # ── Strategy A: match extracted_numerics fact values against resource content ──
    for i, resource in enumerate(resources[:25]):
        content = (resource.get("content", "") or resource.get("description", "")).lower()
        for fact in extracted_facts:
            val = fact.get("value", "").strip()
            if val and len(val) >= 3 and val not in value_to_n:
                core = re.sub(r"[%$,]", "", val).strip()
                if core and core.lower() in content:
                    value_to_n[val] = i + 1

    # ── Strategy B: extract numbers FROM each resource, find them IN the report ──
    if not value_to_n:
        for i, resource in enumerate(resources[:20]):
            content_raw = resource.get("content", "") or resource.get("description", "")
            if not content_raw:
                continue
            content_nums = set(_nums_from_text(content_raw))
            for num in content_nums:
                # skip trivial numbers (years, single digits, etc.)
                if not num or len(num) < 2 or (len(num) == 4 and num.startswith("20")):
                    continue
                # find this number with word boundaries in the report
                pat = re.compile(rf'(?<!\d){re.escape(num)}(?!\d)')
                if not pat.search(report_lower):
                    continue
                # use the widest match in the report (num% preferred over bare num)
                wide = re.search(rf'(?<!\d){re.escape(num)}\s*%', report)
                val_display = wide.group(0).strip() if wide else num
                if val_display not in value_to_n:
                    value_to_n[val_display] = i + 1

    # Strategies that guessed attributions without verifying the source actually
    # contains the number (title-keyword proximity, forced pairing) were removed:
    # a wrong citation is worse than no citation.

    if not value_to_n:
        return report, {}

    logger.info(f"[citations] value_to_n has {len(value_to_n)} entries: {list(value_to_n.items())[:5]}")

    citations: Dict[str, dict] = {}
    annotated = report
    used: set = set()

    # Longest values first to avoid partial-match collisions
    for val in sorted(value_to_n, key=len, reverse=True):
        if val in used:
            continue
        n = value_to_n[val]
        marker = f"[{n}]"
        escaped = re.escape(val)
        # Inject marker after the FIRST occurrence of val not already followed by [N]
        pattern = re.compile(rf"({escaped})(?!\s*\[\d+\])")
        new_annotated, count = pattern.subn(rf"\1{marker}", annotated, count=1)
        if count:
            annotated = new_annotated
            used.add(val)
            if str(n) not in citations:
                r = resources[n - 1]
                raw = r.get("content", "") or r.get("description", "")
                citations[str(n)] = {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": raw[:300].strip(),
                }

    return annotated, citations


# ── Chart grounding guard ────────────────────────────────────────────────────
# Charts must be drawn from numbers that actually exist in the gathered
# sources — the model otherwise interpolates smooth fakes (e.g. revenue
# "10, 20, 30, 50, 100" instead of the real figures).

_GROUNDING_SCALES = (1.0, 1e3, 1e6, 1e-3, 1e-6)  # tolerate unit conversions
_GROUNDING_TOLERANCE = 0.02
_MAX_CHART_REJECTS = 2


def _corpus_numbers(resources: List[dict], extracted_facts: List[dict], chart_datasets: List[dict]) -> List[float]:
    """Every number available from sources/extraction, as floats."""
    texts = [
        (r.get("content", "") or "") + " " + (r.get("description", "") or "")
        for r in resources
    ]
    texts.extend(str(f.get("value", "")) for f in extracted_facts or [])
    for ds in chart_datasets or []:
        for s in ds.get("series", []):
            texts.append(" ".join(str(v) for v in (s.get("values") or [])))
    nums: set = set()
    for t in texts:
        for m in re.finditer(r"-?\d[\d,]*\.?\d*", t):
            try:
                nums.add(float(m.group(0).replace(",", "")))
            except ValueError:
                continue
    return list(nums)


_METRIC_LABEL_RE = re.compile(
    r"(growth|inflation|current prices|percent of|share of|balance|net lending"
    r"|gross debt|\brate\b|\bindex\b|per capita|unemployment|account)",
    re.I,
)


def _x_axis_is_metric_list(x_axis) -> bool:
    """True when x categories are metric names (a table copied sideways),
    e.g. ['Real GDP growth', 'Inflation rate', ...] instead of entities/years."""
    labels = [str(x) for x in (x_axis or [])]
    if len(labels) < 3:
        return False
    hits = sum(1 for x in labels if _METRIC_LABEL_RE.search(x))
    return hits >= max(3, len(labels) // 2)


def _chart_grounding(series: List[dict], corpus: List[float]) -> Tuple[int, int]:
    """Return (grounded, checked) chart values matched against source numbers
    within tolerance at common unit scales (millions vs billions etc.)."""
    grounded = checked = 0
    for s in series or []:
        for v in (s or {}).get("values") or []:
            vals = [x for x in v if isinstance(x, (int, float))] if isinstance(v, list) \
                else ([v] if isinstance(v, (int, float)) else [])
            for x in vals:
                if abs(x) < 1:  # tiny values match too easily to verify
                    continue
                checked += 1
                if any(
                    abs(c - x * sc) <= _GROUNDING_TOLERANCE * abs(x * sc)
                    for sc in _GROUNDING_SCALES
                    for c in corpus
                ):
                    grounded += 1
    return grounded, checked


def _detect_user_language(messages) -> str:
    """Language of the last non-empty human message: Thai script → Thai, else English."""
    for m in reversed(messages):
        if getattr(m, "type", "") == "human":
            text = str(getattr(m, "content", "") or "").strip()
            if text:
                return "Thai" if re.search(r"[\u0e00-\u0e7f]", text) else "English"
    return "Thai"


_MARKER_RE = re.compile(r"\[(\d+)\]")


def _normalize_num(s: str) -> str:
    return re.sub(r"[%$,\s]", "", s)


def _verify_llm_citations(
    report: str, resources: List[dict]
) -> Tuple[str, Dict[str, dict]]:
    """
    Validate [N] markers the LLM wrote. For each marker preceded (on the same line)
    by a number, the cited resource's content must actually contain that number —
    otherwise remap the marker to a resource that does, or drop it entirely.
    Markers without a preceding number (e.g. the source-index footer) are left alone.
    Returns (cleaned_report, citations_dict).
    """
    contents = [
        _normalize_num(r.get("content", "") or r.get("description", ""))
        for r in resources
    ]

    out: List[str] = []
    last = 0
    for m in _MARKER_RE.finditer(report):
        n = int(m.group(1))
        # Number candidates on the same line, just before the marker
        context = report[max(0, m.start() - 60):m.start()].split("\n")[-1]
        nums = re.findall(r"[\$]?\d[\d,\.]*\s*%?", context)
        cand = None
        for s in reversed(nums):
            core = _normalize_num(s).rstrip(".")
            if re.fullmatch(r"(?:19|20)\d\d", core):  # bare years prove nothing
                continue
            cand = core
            break

        out.append(report[last:m.start()])
        if cand is None:
            out.append(m.group(0))  # nothing to verify against → keep as-is
        elif 0 <= n - 1 < len(contents) and cand in contents[n - 1]:
            out.append(m.group(0))  # attribution verified
        else:
            j = next((k for k, c in enumerate(contents) if cand in c), None)
            out.append(f"[{j + 1}]" if j is not None else "")  # remap or drop
        last = m.end()
    out.append(report[last:])
    cleaned = "".join(out)

    citations: Dict[str, dict] = {}
    for m in _MARKER_RE.finditer(cleaned):
        n = int(m.group(1))
        if 0 <= n - 1 < len(resources) and str(n) not in citations:
            r = resources[n - 1]
            raw = r.get("content", "") or r.get("description", "")
            citations[str(n)] = {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": raw[:300].strip(),
            }
    return cleaned, citations


async def chat_node(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["search_node", "chat_node", "delete_node", "__end__"]]:
    """
    Chat Node
    """
    logger.info("=== CHAT_NODE: Starting execution ===")

    # Guard: no actual user input → ask what to research instead of self-driving a run
    has_user_input = any(
        getattr(m, "type", "") == "human" and str(getattr(m, "content", "") or "").strip()
        for m in state.get("messages", [])
    )
    if not has_user_input:
        return Command(goto="__end__", update={"messages": [AIMessage(
            content="สวัสดีครับ อยากให้ช่วยค้นคว้าเรื่องอะไรดีครับ? / Hi! What would you like me to research?"
        )]})

    state["resources"] = state.get("resources", [])
    research_question = state.get("research_question", "")
    report = state.get("report", "")

    resources = []

    for resource in state["resources"]:
        if resource.get("resource_type") == "tako_chart":
            resources.append({**resource, "content": resource.get("description", "")})
        else:
            content = resource.get("content", "")
            if not content:
                content = get_resource(resource["url"])
                if content == "ERROR":
                    continue
            resources.append({**resource, "content": content})

    model = get_model(state)
    # Prepare the kwargs for the ainvoke method
    ainvoke_kwargs = {}
    if model.__class__.__name__ in ["ChatOpenAI"]:
        ainvoke_kwargs["parallel_tool_calls"] = False

    state["logs"] = state.get("logs", [])
    has_resources = len(resources) > 0
    log_msg = f"Synthesizing {len(resources)} source(s) for your query…" if has_resources else "Analyzing your research query…"
    state["logs"].append({"message": log_msg, "done": False})

    from src.lib.sanitize import sanitize_messages
    sanitized_messages = sanitize_messages(state["messages"])

    # Build extracted data context for system prompt
    extracted_facts = state.get("extracted_numerics", [])
    chart_datasets = state.get("chart_datasets", [])

    data_context = ""
    if chart_datasets or extracted_facts:
        data_context = "\n══════════════════════════════════════\n"
        data_context += "📊 ข้อมูลจริงที่สกัดได้จากการค้นหา — ใช้สร้างกราฟได้ทันที\n"
        data_context += "══════════════════════════════════════\n"

        if chart_datasets:
            data_context += "🎯 CHART-READY DATASETS (ใช้ค่าเหล่านี้โดยตรงใน GeneratePlotlyChart — ห้าม hallucinate ตัวเลขเพิ่ม):\n"
            for ds in chart_datasets[-6:]:
                data_context += f"\n  ชื่อกราฟ: {ds.get('chart_title')} [type: {ds.get('chart_type')}]\n"
                data_context += f"  x_axis: {ds.get('x_axis', [])}\n"
                for s in ds.get("series", []):
                    data_context += f"  series → {s.get('name')}: {s.get('values')}\n"

        if extracted_facts:
            data_context += "\n📈 NUMERICAL FACTS:\n"
            for f in extracted_facts[-40:]:
                period = f" ({f.get('period')})" if f.get("period") else ""
                data_context += f"  • {f.get('entity')}: {f.get('metric')} = {f.get('value')}{period}\n"

    user_language = _detect_user_language(state["messages"])
    today = date.today()

    system_prompt = f"""MANDATORY OUTPUT LANGUAGE: {user_language}
Every reply, every section of the report, all headings and chart explanations MUST be written in {user_language}. This overrides everything below.

TODAY'S DATE: {today.isoformat()} (พ.ศ. {today.year + 543}) — the current year is {today.year}.

คุณคือนักวิจัยอัจฉริยะและนักวิทยาศาสตร์ข้อมูลระดับเชี่ยวชาญ มีหน้าที่สร้างรายงานวิจัยเชิงลึกพร้อมการวิเคราะห์เชิงตัวเลขและภาพข้อมูลที่น่าประทับใจ

══════════════════════════════════════
ภาษา / LANGUAGE
══════════════════════════════════════
- ตอบ สื่อสาร และเขียนรายงาน: เป็นภาษา {user_language} เท่านั้น (ภาษาของผู้ใช้)
- Search queries และ tool arguments: ภาษาอังกฤษเท่านั้น (เพื่อให้ได้ผลลัพธ์ที่ดีที่สุด)

══════════════════════════════════════
ขั้นตอนการวิจัย (ทำตามลำดับนี้เสมอ)
══════════════════════════════════════
1. WRITE RESEARCH QUESTION — เรียก WriteResearchQuestion เพื่อกำหนดคำถามวิจัยหลักก่อน ถ้ามีคำถามแล้วข้ามขั้นนี้
2. PLAN & SEARCH — แตกคำถามใหญ่เป็น sub-queries ภาษาอังกฤษหลายๆ อัน (สูงสุด 10) แล้วส่งทั้งหมดพร้อมกันใน Search ครั้งเดียว

   ⚠️ ถ้าคำถามเกี่ยวกับ market share, ranking, การเปรียบเทียบ, หรือ top N — กฎบังคับ:
   • ต้องมี query ระดับ entity เสมอ (ระบุ "by brand", "by manufacturer", "by company")
     เช่น "EV market share by brand Thailand 2025"
   • ต้องมี query ที่ระบุชื่อ entity ที่รู้จัก
     เช่น "BYD Tesla MG Neta ORA EV sales Thailand 2025"
   • ต้องมี query หา top list / ranking
     เช่น "top selling EV brands Thailand 2025 ranking list"
   • ห้ามส่งแค่ query ระดับรวม (aggregate) เช่น "EV market share Thailand" โดยไม่มี breakdown query คู่

   ⚠️ คำถามอิงเวลาปัจจุบัน ("ตอนนี้", "ช่วงนี้", "ล่าสุด", "current", "now", "today") — กฎบังคับ:
   • ต้องใส่ปี {today.year} ใน search queries เสมอ (เช่น "gold price {today.year}")
   • ตรวจวันที่ของข้อมูลที่ได้ — ถ้าข้อมูลล่าสุดที่หาได้เก่ากว่าปัจจุบันมาก ต้องบอกผู้อ่านชัดเจนว่าเป็นข้อมูล ณ วันที่ใด ห้ามนำเสนอข้อมูลเก่าราวกับเป็นข้อมูลปัจจุบัน
   • ระบุวันที่/ช่วงเวลาของข้อมูลในรายงานและชื่อกราฟเสมอ

   ⚠️ ถ้าคำถามระบุช่วงปี (เช่น 2018–2024) — กฎบังคับ:
   • ต้องใส่ปีทุกปีในช่วงนั้นใน query เสมอ เช่น "G7 GDP growth 2018 2019 2020 2021 2022 2023 2024"
   • ต้องเพิ่ม query ที่เจาะ historical data โดยตรง เช่น:
     "G7 GDP annual growth rate historical data worldbank"
     "list of countries by real GDP growth rate wikipedia 2018 2024"
   • ห้ามส่ง query ที่ระบุแค่ปีล่าสุด (เช่น "2024 only") เมื่อผู้ใช้ขอข้อมูลหลายปี

3. DEEP SCRAPE (สำคัญมากสำหรับข้อมูล historical) — เรียก DeepScrapeWebsite ทันทีเมื่อ:
   • search results ไม่ครอบคลุมทุกปีที่ผู้ใช้ถาม
   • พบ URL ของ Wikipedia, WorldBank, IMF, OECD ที่น่าจะมีตาราง historical
   • ตัวอย่าง URL ที่มีข้อมูลครบ: Wikipedia "GDP by country", WorldBank "data.worldbank.org"
   ❌ ห้าม WriteReport ถ้ายังขาดข้อมูลปีใดปีหนึ่งในช่วงที่ผู้ใช้ถาม

4. VISUALIZE DATA — หลังได้ข้อมูลตัวเลขแล้ว ต้องเรียก GeneratePlotlyChart อย่างน้อย 1 ครั้ง (ดูกฎด้านล่าง)
5. STRUCTURED COMPONENTS — เรียก GenerateA2UIComponent เพื่อแสดงตัวเลขสำคัญและตารางเปรียบเทียบ
6. WRITE REPORT — เรียก WriteReport เพื่อเขียนรายงานฉบับสมบูรณ์เป็นภาษาเดียวกับผู้ใช้ ใช้เฉพาะตัวเลขที่ได้จาก search/scrape เท่านั้น ห้าม hallucinate ปีที่ไม่มีข้อมูล
7. FOLLOW UP — ส่งข้อความสั้น 1-2 ประโยค ถามว่าอยากให้ปรับอะไรเพิ่มเติม

══════════════════════════════════════
กฎการสร้างกราฟ (CHART RULES — บังคับ)
══════════════════════════════════════
▸ MANDATORY: ถ้าหัวข้อมีสถิติ, ตัวเลข, การเปรียบเทียบ, หรือแนวโน้ม → ต้องสร้างกราฟเสมอ ห้ามรอให้ผู้ใช้ขอ
▸ ถ้ามี CHART-READY DATASETS ใน "📊 ข้อมูลจริง" ด้านล่าง → ต้องใช้ค่าเหล่านั้นโดยตรงใน GeneratePlotlyChart ห้าม hallucinate ตัวเลข
▸ ตัวเลขทุกตัวในกราฟต้องมาจาก search results เป๊ะ ๆ — ห้ามปัดเป็นเลขกลม ห้าม interpolate เติมปีที่ไม่มีข้อมูล (ระบบจะตรวจและปฏิเสธกราฟที่ตัวเลขไม่ตรงแหล่ง)
▸ ใส่เฉพาะ entity ที่ผู้ใช้ถามเท่านั้น — ถ้าคำถามระบุกลุ่ม (เช่น ASEAN, G7, EU) ให้กรองข้อมูลเหลือเฉพาะสมาชิกของกลุ่มนั้น ห้ามลอกทั้งตารางจากแหล่งมาทั้งดุ้น
▸ แกน x ต้องเป็นชื่อ entity (ประเทศ/บริษัท/แบรนด์) หรือช่วงเวลา (ปี/เดือน) เท่านั้น — หนึ่งกราฟต่อหนึ่ง metric ห้ามเอาชื่อ metric หลายตัว (เช่น "Real GDP growth", "Inflation rate") มาเรียงเป็นแกน x ในกราฟเดียว
▸ ค่าของปีอนาคตหรือค่าคาดการณ์ ต้องระบุในชื่อกราฟหรือชื่อ series ว่า "(คาดการณ์)" / "(forecast)" ให้ชัดเจน
▸ สร้างกราฟแต่ละเรื่องเพียงครั้งเดียว — ห้ามสร้างกราฟชื่อเดิมหรือข้อมูลเดิมซ้ำ ถ้า tool บอกว่ากราฟมีอยู่แล้วให้ใช้ marker เดิม
▸ หลังเรียก GeneratePlotlyChart แล้ว tool จะคืน marker เช่น [CHART:abc12345] → ต้องวาง marker นั้นในรายงานตรงตำแหน่งที่ต้องการแสดงกราฟทุกครั้ง ห้ามแต่งหรือเดา chart ID เอง

เลือกประเภทกราฟตามข้อมูล:
| ข้อมูล | chart_type |
|--------|-----------|
| แนวโน้มตามเวลา/ปี | `line` หรือ `area` |
| ส่วนแบ่ง/เปอร์เซ็นต์ | `donut` หรือ `pie` |
| เปรียบเทียบหมวดหมู่ | `bar` |
| ชื่อหมวดหมู่ยาว | `horizontal_bar` |
| เปรียบเทียบหลายมิติ (3+ metrics) | `radar` |
| ราคาหุ้น/crypto OHLC | `candlestick` |
| ความสัมพันธ์ 2 ตัวแปร | `scatter` |
| ข้อมูลไหล/ลำดับขั้น | `funnel` |
| กำไร-ขาดทุน running total | `waterfall` |
| ความเข้มข้น matrix | `heatmap` |

รูปแบบ series สำหรับกราฟแต่ละประเภท:
- bar/line/area: x_axis=["ม.ค.","ก.พ.",...], series=[{{name:"ชุดข้อมูล", values:[1,2,3,...]}}]
- donut/pie (แนะนำ): series=[{{name:"Tesla",values:[23.5]}}, {{name:"BYD",values:[18.3]}}, ...] (แต่ละ entity เป็น series แยก)
- radar: x_axis=["ราคา","แบตเตอรี่","ความเร็ว"], series=[{{name:"Tesla",values:[80,95,90]}}, ...]
- เปรียบเทียบหลาย series: series=[{{name:"ปี 2023",values:[...]}}, {{name:"ปี 2024",values:[...]}}]

══════════════════════════════════════
กฎ A2UI Components
══════════════════════════════════════
ใช้ GenerateA2UIComponent ควบคู่กับกราฟเสมอ:
- stat_card: ตัวเลขพาดหัวเดียว เช่น GDP $500B (+3.2% YoY)
- kpi_row: KPI หลายตัวเรียงแนวนอน เช่น GDP + เงินเฟ้อ + การว่างงาน
- comparison_table: เปรียบเทียบหลาย entity ข้ามหลาย attribute
- data_grid: ตารางข้อมูลที่มี header และ row ชัดเจน
- timeline: เหตุการณ์สำคัญตามลำดับเวลา
▸ ถ้าต้องการตารางเปรียบเทียบใน report ให้ใช้ markdown table ปกติได้เลย (| col | col |)
▸ GenerateA2UIComponent สร้าง component ใน Data tab (แยกจาก report) — ไม่ต้องเขียน placeholder ใดๆ ใน report

══════════════════════════════════════
แนวทางการเขียนรายงาน
══════════════════════════════════════
- เขียนรายงานเชิงวิเคราะห์เชิงลึก ไม่ใช่แค่สรุปข้อมูล
- ทุกกราฟต้องมีย่อหน้าอธิบาย: ข้อมูลบอกว่าอะไร → ทำไมถึงสำคัญ → ผลกระทบคืออะไร
- วาง [CHART:id] ไว้ในเนื้อหาตรงจุดที่เหมาะสม ไม่ใช่รวมกันท้ายรายงาน
- ใช้ตัวเลขจริงจาก search results เสมอ ห้าม hallucinate ตัวเลข
- ห้ามใช้ ![image](url) หรือ link ภายนอก
- โครงสร้างรายงาน: บทนำ → วิเคราะห์ข้อมูล (พร้อมกราฟ) → สรุปและข้อเสนอแนะ
{state.get("explore_context", "")}
══════════════════════════════════════
การอ้างอิงแหล่งข้อมูล (INLINE CITATIONS — บังคับทำทุกครั้ง)
══════════════════════════════════════
▸ ใส่ [N] ต่อท้ายตัวเลขและสถิติในรายงาน — ทุกย่อหน้าหรือบูลเล็ตที่มีตัวเลขสำคัญ ต้องมี [N] กำกับอย่างน้อยหนึ่งจุด
▸ N คือหมายเลขใน "ดัชนีแหล่งข้อมูล" ด้านล่าง — ใช้ [N] เฉพาะเมื่อ source หมายเลขนั้นมีตัวเลข/ข้อเท็จจริงนั้นอยู่จริง
▸ ถ้าไม่แน่ใจว่าตัวเลขมาจาก source ไหน → ห้ามเดาหมายเลข ให้ละ [N] ไว้เฉพาะตัวเลขนั้นแล้วอ้างตัวเลขอื่นที่แน่ใจตามปกติ
▸ ไม่ต้องมีช่องว่างก่อน [N] เช่น: "เติบโต 2.5%[1]" หรือ "มูลค่า 500 พันล้าน[2]"
▸ ตัวอย่าง: "GDP เติบโต 2.5%[1] ขณะที่ CPI อยู่ที่ 3.2%[2] และ FDI รวม $45B[1]"

══════════════════════════════════════
บริบทปัจจุบัน
══════════════════════════════════════
คำถามวิจัย: {research_question or "(ยังไม่ได้กำหนด)"}

รายงานปัจจุบัน: {report or "(ยังไม่มี)"}

ดัชนีแหล่งข้อมูล ({len(resources)} แหล่ง):
{chr(10).join(
    f"[{i+1}] {r.get('title', r.get('source', 'Unknown'))[:80]} — {r.get('url', '')}"
    + (f"\n     ↳ {(r.get('content','') or r.get('description',''))[:180].strip()}" if (r.get('content','') or r.get('description','')) else "")
    for i, r in enumerate(resources[:25])
)}
{data_context}"""

    response = await model.bind_tools(
        [
            Search,
            WriteReport,
            WriteResearchQuestion,
            GeneratePlotlyChart,
            GenerateA2UIComponent,
            DeepScrapeWebsite,
            DeleteResources,
        ],
        **ainvoke_kwargs,
    ).ainvoke(
        [SystemMessage(content=system_prompt), *sanitized_messages],
        config,
    )

    state["logs"][-1]["done"] = True

    ai_message = cast(AIMessage, response)
    if ai_message.tool_calls:
        tool_messages = []
        goto_node = "chat_node"
        
        # Check if AI called WriteReport in parallel with data gathering tools
        has_chart_or_search = any(tc["name"] in ["GeneratePlotlyChart", "GenerateA2UIComponent", "Search", "DeepScrapeWebsite"] for tc in ai_message.tool_calls)
        
        for i, call in enumerate(ai_message.tool_calls):
            name = call["name"]
            
            if name == "WriteResearchQuestion":
                rq = call["args"].get("research_question", "")
                state["research_question"] = rq
                state["logs"].append({"message": f"Research question: {rq[:80]}{'…' if len(rq) > 80 else ''}", "done": True})
                tool_messages.append(ToolMessage(tool_call_id=call["id"], content="Research question written."))
                
            elif name == "GeneratePlotlyChart":
                try:
                    import json as _json_chart

                    # ── Structure guard: x-axis must be entities/periods, not metric names ──
                    rejects = state.get("chart_reject_count", 0)
                    if rejects < _MAX_CHART_REJECTS and _x_axis_is_metric_list(call["args"].get("x_axis")):
                        state["chart_reject_count"] = rejects + 1
                        title_preview = str(call["args"].get("title", ""))[:60]
                        state["logs"].append({"message": f"Chart rejected — x-axis is a list of metrics: {title_preview}", "done": True})
                        tool_messages.append(ToolMessage(
                            tool_call_id=call["id"],
                            content=(
                                f"REJECTED: chart '{title_preview}' uses metric names as x-axis categories. "
                                "A chart must show ONE metric: x_axis must be entity names (countries/companies) "
                                "or time periods (years/months). Pick the single most relevant metric for the "
                                "user's question (e.g. 'Real GDP growth') and plot it per entity instead."
                            ),
                        ))
                        continue

                    # ── Grounding guard: reject charts whose numbers aren't in any source ──
                    rejects = state.get("chart_reject_count", 0)
                    if rejects < _MAX_CHART_REJECTS:
                        corpus = _corpus_numbers(
                            resources,
                            state.get("extracted_numerics", []),
                            state.get("chart_datasets", []),
                        )
                        grounded, checked = _chart_grounding(call["args"].get("series") or [], corpus)
                        if checked >= 3 and grounded / checked < 0.5:
                            state["chart_reject_count"] = rejects + 1
                            title_preview = str(call["args"].get("title", ""))[:60]
                            state["logs"].append({"message": f"Chart rejected — data not found in sources: {title_preview}", "done": True})
                            tool_messages.append(ToolMessage(
                                tool_call_id=call["id"],
                                content=(
                                    f"REJECTED: chart '{title_preview}' uses numbers that do not appear in any search result "
                                    f"(only {grounded}/{checked} values verified against sources). Do NOT invent, round off, or "
                                    "interpolate values. Use ONLY the exact figures from the CHART-READY DATASETS / NUMERICAL FACTS "
                                    "in your context, or call Search/DeepScrapeWebsite to find the real figures first. "
                                    "If the exact data cannot be found, skip this chart entirely."
                                ),
                            ))
                            continue

                    result = run_chart_tool(call["args"])
                    if result.startswith("CHART_READY:"):
                        rest = result[len("CHART_READY:"):]
                        pipe_idx = rest.index("|OPTION:")
                        meta = rest[:pipe_idx]
                        option_json = rest[pipe_idx + len("|OPTION:"):]
                        colon_idx = meta.index(":")
                        chart_id = meta[:colon_idx]
                        chart_title = meta[colon_idx + 1:]
                        option = _json_chart.loads(option_json)

                        # ── Dedupe: same title (ignoring year-range suffixes) → reuse/update ──
                        def _title_key(t: str) -> str:
                            return re.sub(r"\s*\([^)]*\)\s*", " ", t or "").strip().lower()

                        norm_title = _title_key(chart_title)
                        existing = next(
                            (c for c in state.get("charts", []) if _title_key(c.get("title", "")) == norm_title),
                            None,
                        )
                        if existing is not None:
                            if existing.get("option", {}).get("series") != option.get("series"):
                                existing["option"] = option  # refresh data; keep id so report markers stay valid
                                if call["args"].get("source_attribution"):
                                    existing["source"] = call["args"]["source_attribution"]
                            state["logs"].append({"message": f"Chart reused: {chart_title}", "done": True})
                            tool_messages.append(ToolMessage(
                                tool_call_id=call["id"],
                                content=(
                                    f"Chart '{chart_title}' already exists with ID {existing['id']} (data refreshed). "
                                    f"Reuse the marker [CHART:{existing['id']}] in your report — do NOT generate this chart again."
                                ),
                            ))
                            continue

                        chart_spec: ChartSpec = {"id": chart_id, "title": chart_title, "option": option}
                        if call["args"].get("source_attribution"):
                            chart_spec["source"] = call["args"]["source_attribution"]
                        state.setdefault("charts", []).append(chart_spec)
                        state["logs"].append({"message": f"Chart generated: {chart_title}", "done": True})
                        tool_messages.append(ToolMessage(
                            tool_call_id=call["id"],
                            content=f"Chart '{chart_title}' generated with ID {chart_id}. You MUST insert the marker [CHART:{chart_id}] exactly at the appropriate position in your report using WriteReport."
                        ))
                    else:
                        tool_messages.append(ToolMessage(tool_call_id=call["id"], content=result))
                except Exception as e:
                    tool_messages.append(ToolMessage(tool_call_id=call["id"], content=f"Failed to generate chart: {str(e)}"))
                    
            elif name == "GenerateA2UIComponent":
                import json as _json
                try:
                    component = {
                        "type": call["args"].get("type"),
                        "title": call["args"].get("title"),
                        "data": call["args"].get("data", {}),
                    }
                    if call["args"].get("source"):
                        component["source"] = call["args"]["source"]
                    state.setdefault("pending_a2ui", []).append(component)
                    state["logs"].append({"message": f"A2UI component generated: {component['title']}", "done": True})
                    tool_messages.append(ToolMessage(
                        tool_call_id=call["id"],
                        content=f"A2UI component '{component['title']}' ({component['type']}) generated and queued for display."
                    ))
                except Exception as e:
                    tool_messages.append(ToolMessage(tool_call_id=call["id"], content=f"Failed to generate A2UI component: {e}"))

            elif name == "DeepScrapeWebsite":
                url = call["args"].get("url", "")
                state["logs"].append({"message": f"Deep Scraping {url}...", "done": False})
                try:
                    import aiohttp
                    import html2text
                    import asyncio
                    async def fetch_and_parse():
                        async with aiohttp.ClientSession() as session:
                            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15) as response:
                                response.raise_for_status()
                                html_content = await response.text()
                                return html2text.html2text(html_content)[:50000]
                    # We have to await it, but we are inside an async function so it's fine.
                    # Wait, chat_node is an async function, we can just await directly here!
                    # Actually, the original loop wasn't async-friendly if I use await inside it.
                    # Yes it was, the loop is inside `async def chat_node`.
                    content = await fetch_and_parse()
                    scrape_res = f"DEEP SCRAPE RESULTS for {url}:\n\n{content}"
                    tool_messages.append(ToolMessage(tool_call_id=call["id"], content=scrape_res))
                except Exception as e:
                    tool_messages.append(ToolMessage(tool_call_id=call["id"], content=f"Scrape failed: {str(e)}"))
                state["logs"][-1]["done"] = True
                    
            elif name == "Search":
                goto_node = "search_node"
                queries_preview = call["args"].get("queries", [])
                n = len(queries_preview)
                state["logs"].append({"message": f"Dispatching {n} search quer{'y' if n == 1 else 'ies'}…", "done": True})
                # For Search, we do not append ToolMessage here. search_node handles it.
                
            elif name == "DeleteResources":
                goto_node = "delete_node"
                
            elif name == "WriteReport":
                if has_chart_or_search:
                    tool_messages.append(ToolMessage(tool_call_id=call["id"], content="ERROR: You called WriteReport at the same time as generating a chart or searching. You must wait for the chart URL or search results first! I have generated the chart/search for you. Please use WriteReport in the NEXT turn using the newly provided data and URLs."))
                else:
                    state["report"] = call["args"].get("report", "")

                    external_domains = r"(tradingeconomics|worldbank|imf|fred|ourworldindata|statista)"
                    state["report"] = re.sub(rf"\!\[([^\]]+)\]\(https?://[^)]*{external_domains}[^)]*\)", r"", state["report"], flags=re.IGNORECASE)
                    state["report"] = re.sub(r"\!\[[^\]]*\]\([^)]+\)", "", state["report"])
                    state["report"] = re.sub(r"\[TAKO_CHART:[^\]]+\]", "", state["report"])
                    # Strip unfilled template placeholders: {comparison_table} {} { }
                    state["report"] = re.sub(r'\{[a-z][a-z_0-9]*\}|\{\s*\}', "", state["report"])

                    resources_list = resources  # use content-enriched local var
                    extracted_facts = state.get("extracted_numerics", [])

                    verified: Dict[str, dict] = {}
                    if _MARKER_RE.search(state["report"]):
                        # LLM added its own [N] markers — verify each against source content
                        state["report"], verified = _verify_llm_citations(
                            state["report"], resources_list
                        )
                    # Supplement: inject markers for numbers the LLM left uncited
                    # (only values verifiably present in a source get a marker)
                    state["report"], auto_cit = _auto_inject_citations(
                        state["report"], extracted_facts, resources_list
                    )
                    state["citations"] = {**auto_cit, **verified}

                    # Charts must survive report rewrites (critic retries tended to
                    # drop the inline markers) — re-append any chart not referenced.
                    charts = state.get("charts", [])
                    missing_markers = [
                        f"[CHART:{c['id']}]" for c in charts
                        if f"[CHART:{c['id']}]" not in state["report"]
                    ]
                    if missing_markers:
                        state["report"] += "\n\n" + "\n\n".join(missing_markers)

                    goto_node = "critic_node"
                    
        if goto_node == "chat_node":
            return Command(
                goto="chat_node",
                update={
                    "messages": [ai_message] + tool_messages,
                    "research_question": state.get("research_question", ""),
                    "pending_a2ui": state.get("pending_a2ui", []),
                    "charts": state.get("charts", []),
                    "logs": state.get("logs", []),
                    "extracted_numerics": state.get("extracted_numerics", []),
                    "chart_datasets": state.get("chart_datasets", []),
                    "citations": state.get("citations", {}),
                    "chart_reject_count": state.get("chart_reject_count", 0),
                }
            )
        else:
            return Command(
                goto=goto_node,
                update={
                    "messages": [ai_message] + tool_messages,
                    "report": state.get("report", ""),
                    "resources": state.get("resources", []),
                    "pending_a2ui": state.get("pending_a2ui", []),
                    "charts": state.get("charts", []),
                    "logs": state.get("logs", []),
                    "extracted_numerics": state.get("extracted_numerics", []),
                    "chart_datasets": state.get("chart_datasets", []),
                    "citations": state.get("citations", {}),
                    "chart_reject_count": state.get("chart_reject_count", 0),
                }
            )
            
    if len(ai_message.content) > 500:
        return Command(
            goto="chat_node",
            update={
                "messages": [
                    ai_message,
                    HumanMessage(content="SYSTEM ERROR: You wrote the report as plain text. You MUST use the WriteReport tool to submit the report! Please rewrite it using the WriteReport tool.")
                ]
            }
        )

    logger.info("=== CHAT_NODE: Routing to __end__ ===")
    return Command(goto="__end__", update={"messages": [ai_message], "resources": state.get("resources", [])})
