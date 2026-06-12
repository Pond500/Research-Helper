import asyncio
import uuid
import sys
import os
from dotenv import load_dotenv
load_dotenv("../../.env.local")

from langchain_core.messages import HumanMessage
from src.agent import graph

async def main():
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    inputs = {
        "messages": [HumanMessage(content="หาข้อมูลสรุปหุ้น AAPL ในปี 2023 ให้หน่อย แล้ววาดกราฟเปรียบเทียบกำไรกับ MSFT")]
    }
    print("Starting agent...")
    try:
        async for event in graph.astream(inputs, config=config, stream_mode="values"):
            if "messages" in event:
                msg = event["messages"][-1]
                print(f"[{msg.type.upper()}]: {msg.content}")
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    print(f"  TOOL_CALLS: {[tc['name'] for tc in msg.tool_calls]}")
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
