import logging
from typing import List, Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.lib.model import get_model
from src.lib.state import AgentState

logger = logging.getLogger(__name__)

class CriticEvaluation(BaseModel):
    is_pass: bool = Field(description="True if the report perfectly answers the research question using solid data. False if it lacks data, misses the point, or hallucinates.")
    feedback: str = Field(description="If is_pass is False, provide strict feedback and a specific Search Query the agent should use to find the missing data. If True, just say 'Approved'.")

class FollowUpQuestions(BaseModel):
    questions: List[str] = Field(description="Exactly 3 follow-up research questions the user might want to explore next, written in the same language as the research question.")

async def critic_node(state: AgentState, config: RunnableConfig) -> Command[Literal["chat_node", "__end__"]]:
    """
    Critic Node: Evaluates the drafted report against the research question.
    """
    logger.info("=== CRITIC_NODE: Evaluating Report ===")
    
    state["critic_retry_count"] = state.get("critic_retry_count", 0)
    
    if state["critic_retry_count"] >= 2:
        logger.info("Critic retry limit reached. Forcing approval.")
        return Command(goto="__end__")
        
    research_question = state.get("research_question", "")
    report = state.get("report", "")
    
    if not report:
        # No report to evaluate, let chat_node handle it
        return Command(goto="chat_node")
        
    state["logs"] = state.get("logs", [])
    retry = state.get("critic_retry_count", 0)
    attempt_label = f" (attempt {retry + 1}/3)" if retry > 0 else ""
    state["logs"].append({"message": f"Quality-checking report{attempt_label}…", "done": False})

    model = get_model(state)
    
    eval_prompt = f"""You are a strict QA Critic Agent.
Your job is to evaluate the following Research Report against the User's Research Question.

Research Question:
{research_question}

Research Report:
{report}

Rules for Passing:
1. The report MUST directly answer the core of the research question.
2. If the user asked for statistics, market shares, or specific numbers, the report MUST contain them.
3. If the report says 'I cannot find data' or 'Data is unavailable', you MUST REJECT IT and instruct the agent on what to search for.
4. If the question implies comparison or statistics, the report MUST contain a chart.
5. If the report contains an iframe, the src attribute MUST start with "/charts/". If it points to "plotly.com", "chart-url.com", or ANY other domain, you MUST REJECT IT and instruct the agent to use the GeneratePlotlyChart tool to get a real chart.

Output your evaluation using the CriticEvaluation tool."""

    from src.lib.sanitize import sanitize_messages
    sanitized_messages = sanitize_messages(state["messages"])
    
    response = await model.with_structured_output(CriticEvaluation).ainvoke(
        [
            SystemMessage(content=eval_prompt),
            *sanitized_messages,
        ],
    )
    
    evaluation = cast(CriticEvaluation, response)
    
    state["logs"][-1]["done"] = True

    if evaluation.is_pass:
        logger.info("Critic APPROVED the report.")
        last_ai_msg = state["messages"][-1]
        tool_messages = []
        if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
            for call in last_ai_msg.tool_calls:
                content = "Report accepted and delivered to user." if call["name"] == "WriteReport" else "Tool call ignored."
                tool_messages.append(ToolMessage(tool_call_id=call["id"], content=content))

        # Generate follow-up question suggestions
        suggested_questions: List[str] = []
        try:
            research_question = state.get("research_question", "")
            report_snippet = state.get("report", "")[:2000]
            followup_response = await model.with_structured_output(FollowUpQuestions).ainvoke(
                [
                    SystemMessage(content=(
                        "คุณคือผู้ช่วยวิจัยที่ช่วยแนะนำคำถามติดตาม "
                        "จากรายงานวิจัยที่เพิ่งเสร็จ สร้างคำถาม 3 ข้อ "
                        "เป็นภาษาเดียวกับคำถามวิจัยหลัก "
                        "ที่น่าสนใจและต่อยอดจากรายงานนี้ได้ดี "
                        "แต่ละคำถามควรเจาะจงและนำไปวิจัยต่อได้ทันที"
                    )),
                    HumanMessage(content=(
                        f"คำถามวิจัยหลัก: {research_question}\n\n"
                        f"รายงาน (ส่วนต้น):\n{report_snippet}\n\n"
                        "สร้างคำถามติดตาม 3 ข้อที่ผู้ใช้น่าจะอยากรู้ต่อจากรายงานนี้"
                    )),
                ],
            )
            suggested_questions = followup_response.questions[:3]
            logger.info(f"Generated {len(suggested_questions)} follow-up questions")
        except Exception as e:
            logger.warning(f"Failed to generate follow-up questions: {e}")

        return Command(
            goto="__end__",
            update={"messages": tool_messages, "suggested_questions": suggested_questions},
        )
    else:
        logger.info(f"Critic REJECTED the report. Feedback: {evaluation.feedback}")
        state["critic_retry_count"] += 1
        
        # We need to append a ToolMessage for EVERY tool call to satisfy OpenAI's requirements
        last_ai_msg = state["messages"][-1]
        tool_messages = []
        if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
            for i, call in enumerate(last_ai_msg.tool_calls):
                if call["name"] == "WriteReport":
                    content = (
                        f"CRITIC REJECTED YOUR REPORT. Reason: {evaluation.feedback}\n\n"
                        "You MUST use GeneratePlotlyChart or Search to fix this and rewrite the report.\n"
                        "When rewriting, you MUST keep every [CHART:id] marker and every [N] citation marker "
                        "from the previous version in place, and keep the report in the same language as the user's question."
                    )
                else:
                    content = "Tool call ignored because WriteReport was rejected."
                tool_messages.append(ToolMessage(tool_call_id=call["id"], content=content))
        else:
            # Fallback (shouldn't happen)
            tool_messages.append(ToolMessage(tool_call_id="unknown", content="Rejected"))
        
        state["logs"].append({"message": f"Report needs improvement — searching for more data…", "done": True})

        return Command(
            goto="chat_node",
            update={
                "critic_retry_count": state["critic_retry_count"],
                "messages": tool_messages
            }
        )
