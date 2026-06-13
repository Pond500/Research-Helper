"""
Research Agent Server

FastAPI server that exposes a LangGraph research agent via CopilotKit.
"""

import asyncio
import logging
import os

import uvicorn
from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import tempfile
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env.local")
load_dotenv(env_path, override=True)
os.environ["LANGGRAPH_FASTAPI"] = "true"
from src.agent import graph  # noqa: E402

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("research_agent")

agent = LangGraphAgent(
    name="research_agent",
    description="AI research assistant for gathering and analyzing information.",
    graph=graph,
)

HEARTBEAT_SECONDS = 15
_STREAM_DONE = object()


@app.post("/copilotkit/agents/research_agent")
async def research_agent_endpoint(input_data: RunAgentInput, request: Request):
    """
    Same contract as ag_ui_langgraph.add_langgraph_fastapi_endpoint, plus:
    - SSE keepalive comments while the agent is silent (proxies/clients kill
      idle streams — undici/Next.js default is 300s)
    - agent exceptions become a RUN_ERROR event instead of crashing the
      response mid-stream, so the frontend can show the failure
    """
    accept_header = request.headers.get("accept")
    encoder = EventEncoder(accept=accept_header)
    is_sse = "text/event-stream" in (accept_header or "text/event-stream")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def pump():
            try:
                async for event in agent.run(input_data):
                    # RAW events echo every LangGraph internal step (thousands per
                    # run) and the frontend ignores them — drop to save bandwidth.
                    if getattr(event, "type", None) == EventType.RAW:
                        continue
                    await queue.put(encoder.encode(event))
            except Exception as exc:  # noqa: BLE001 — surface every failure to the client
                logger.exception("Agent run failed")
                await queue.put(encoder.encode(RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=f"Agent error: {exc}",
                )))
            finally:
                await queue.put(_STREAM_DONE)

        task = asyncio.create_task(pump())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    if is_sse:
                        yield ": keepalive\n\n"
                    continue
                if item is _STREAM_DONE:
                    break
                yield item
        finally:
            task.cancel()

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


from src.lib.qdrant import add_documents_to_qdrant

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document and index it into the Qdrant Knowledge Base."""
    try:
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        documents = []
        if file.filename.lower().endswith(".pdf"):
            loader = PyPDFLoader(tmp_path)
            documents = loader.load()
        elif file.filename.lower().endswith(".txt"):
            loader = TextLoader(tmp_path)
            documents = loader.load()
        elif file.filename.lower().endswith(".docx"):
            loader = Docx2txtLoader(tmp_path)
            documents = loader.load()
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Only PDF, TXT, DOCX allowed.")

        # Chunk the document — larger chunks preserve tables/numerical context better
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=400)
        chunks = text_splitter.split_documents(documents)
        
        # Add metadata source
        for chunk in chunks:
            chunk.metadata["source"] = file.filename

        # Ingest into Qdrant
        add_documents_to_qdrant(chunks)
        
        # Clean up
        os.remove(tmp_path)

        return {"filename": file.filename, "status": "success", "chunks_indexed": len(chunks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def main():
    """Run the uvicorn server."""
    port = int(os.getenv("PORT", "10236"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=(
            ["."]
            + (
                ["../../../../sdk-python/copilotkit"]
                if os.path.exists("../../../../sdk-python/copilotkit")
                else []
            )
        ),
    )


if __name__ == "__main__":
    main()
