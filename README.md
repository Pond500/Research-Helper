# Research Canvas with MCP Integration

https://github.com/user-attachments/assets/bc32adb4-e4a7-492d-b5d6-34177cd1c216

An AI-powered research assistant that combines data visualization with web search capabilities. Built with [LangGraph](https://langchain-ai.github.io/langgraph/), the [AG-UI protocol](https://docs.ag-ui.com/), and the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

The Next.js frontend talks directly to a Python LangGraph agent over AG-UI server-sent events — streaming chat, shared agent state, interactive charts, and human-in-the-loop confirmations.

## ✨ Features

- **AI Research Agent**: Automatically generates relevant search queries and gathers resources
- **Multi-source Search**: Web search (Tavily), SearXNG, and a local Qdrant knowledge base — toggleable per query
- **Interactive Charts**: The agent generates ECharts visualizations rendered natively in the UI, with source-grounding verification
- **Report Generation**: Compiles findings into a cited research report (citations verified against source content)
- **Quality Critic**: A critic node reviews each report and sends it back for revision when data is missing
- **Document Upload**: PDF/TXT/DOCX indexing into Qdrant for retrieval (requires Docker)
- **Human-in-the-loop**: Resource deletion requires explicit user confirmation via a LangGraph interrupt

## 🚀 Quick Start

### Prerequisites

1. **OpenAI API Key** (or OpenRouter) — [platform.openai.com](https://platform.openai.com)
2. **Tavily API Key** — [tavily.com](https://tavily.com)
3. **uv** — Python package manager ([astral.sh/uv](https://docs.astral.sh/uv/))
4. **Data Source** — your MCP server endpoint (optional)

## 📋 Installation

```bash
# Install dependencies
npm install
npm run install:agent      # installs the Python agent with uv

# Copy environment template
cp .env.example .env.local

# Add your API keys to .env.local
# OPENAI_API_KEY=your-openai-key   (or OPENROUTER_API_KEY)
# TAVILY_API_KEY=your-tavily-key

# Start frontend + agent together
npm run dev
```

The application will be available at:
- **Frontend**: http://localhost:10235
- **Agent Backend**: http://localhost:10236

## 🏗️ Project Structure

```
tako-copilotkit/
├── src/                    # Next.js frontend
│   ├── app/                # App router pages
│   ├── components/         # React components (canvas, chat, charts)
│   └── lib/                # AG-UI stream client, types
├── agents/python/          # LangGraph agent (FastAPI)
│   ├── main.py             # Server entry + /upload endpoint
│   └── src/lib/            # Graph nodes: chat, search, critic, delete
├── tests/e2e/              # End-to-end test suite
└── docker-compose.yml      # Full stack: Qdrant + agent + frontend
```

## 🌐 Environment Variables

Create a `.env.local` file based on `.env.example`:

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for LLM | Yes* |
| `OPENROUTER_API_KEY` | Routes the default model through OpenRouter | Yes* |
| `TAVILY_API_KEY` | Tavily API key for web search | Yes |
| `TAKO_API_TOKEN` | API token for data source | Optional |
| `TAKO_MCP_URL` | MCP server endpoint URL | Optional |
| `TAKO_URL` | Base URL for data source | Optional |
| `QDRANT_URL` | Vector DB for uploaded docs (default `http://localhost:10237`) | Optional |

*One of `OPENAI_API_KEY` / `OPENROUTER_API_KEY` is required.

## 💬 Usage

1. **Start a Research Session**: Enter a research question or topic (Thai or English — the agent answers in your language)
2. **AI Generates Queries**: The agent creates data-focused search queries
3. **Resource Discovery**: Watch sources stream into the canvas in real time
4. **Charts & Data**: Generated charts and structured components appear in the Data tab and inline in the report
5. **Report**: A cited, critic-reviewed research draft you can edit in place

## 🏗️ Architecture

```
┌─────────────────┐
│  Next.js App    │  src/lib/useAgentStream.ts
│  (Frontend UI)  │
└────────┬────────┘
         │  AG-UI protocol (SSE) via Next.js rewrites
         ▼
┌─────────────────┐
│  LangGraph      │  download → chat ⇄ search / critic / delete
│  Agent (FastAPI)│
└────────┬────────┘
         ├─→ OpenAI / OpenRouter (LLM)
         ├─→ Tavily / SearXNG (web search)
         ├─→ Qdrant (uploaded documents)
         └─→ MCP Server (optional data source)
```

## 🔧 Key Technologies

- **[LangGraph](https://langchain-ai.github.io/langgraph/)**: Stateful agent workflow with interrupts and a critic loop
- **[AG-UI protocol](https://docs.ag-ui.com/)**: Streaming agent↔UI events (text, tool calls, state deltas)
- **[Next.js](https://nextjs.org)** + **[Apache ECharts](https://echarts.apache.org/)**: Frontend and interactive charts
- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)**: Standard for connecting AI systems to data sources
- **[Tavily](https://tavily.com)** / **[Qdrant](https://qdrant.tech/)**: Web search and vector retrieval

## 🧪 Testing

```bash
# E2E suite (requires the app running — see tests/e2e/README.md)
node tests/e2e/delete_flow.test.mjs
node tests/e2e/edge_cases.test.mjs
node tests/e2e/battery/runner.mjs     # full research-quality battery
```

## 🐛 Troubleshooting

### Agent won't start

```bash
npm run install:agent      # re-sync the Python environment
npm run dev:agent          # run the agent alone to see errors
```

### API rate limits

- Check your OpenAI/OpenRouter quota
- Verify Tavily API subscription level

### Resources not loading

- Verify all API keys are set in `.env.local`
- Check browser console for errors
- Ensure the agent backend is running on port 10236 (`curl localhost:10236/health`)

## 🔐 Security

**Important**: Never commit API keys to version control

1. Always use `.env.local` for sensitive values (already gitignored)
2. Rotate API keys regularly
3. Use environment-specific keys for dev/production

## 🚢 Deployment

- **Self-hosted (Docker)**: `docker-compose up -d` runs Qdrant + agent + frontend — see [DEPLOY.md](./DEPLOY.md)
- **Cloud (Vercel + Railway)**: push to the `production` branch auto-deploys — see [DEPLOYMENT.md](./DEPLOYMENT.md)

### Branch Strategy

- **`main`** — development branch (CI runs, no auto-deploy)
- **`production`** — auto-deploys to production (protected branch)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the E2E suite against your change
5. Submit a pull request

## 💡 Extending This Project

### Adding Custom MCP Data Sources

1. Implement an MCP server for your data source
2. Update environment variables with your MCP endpoint
3. Extend `agents/python/src/lib/mcp_integration.py`

### Customizing the Agent

The LangGraph agent lives in `agents/python/src/`:
- `agent.py` — graph definition and routing
- `lib/chat.py` — main LLM node, tools, system prompt, citation verification
- `lib/search.py` — multi-source search node
- `lib/critic.py` — report quality review loop
- `lib/chart_tool.py` — ECharts option builder

### UI Customization

The Next.js frontend is in `src/`:
- `components/ResearchCanvas.tsx` — main research interface
- `components/ChatUI.tsx` — chat panel and delete confirmation
- `lib/useAgentStream.ts` — AG-UI stream client

## 📄 License

MIT License — see LICENSE file for details

---

**Built as a demonstration of LangGraph + AG-UI + MCP integration**
