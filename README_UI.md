# TradingAgents Web UI

A dark-themed Bloomberg-style terminal UI for the [TradingAgents](https://github.com/TauricResearch/TradingAgents) framework — streams each agent's progress in real time via Server-Sent Events.

## Architecture

```
/                   ← TradingAgents repo root
├── api.py          ← FastAPI backend (port 8000)
├── .venv/          ← Python 3.13 virtual environment
├── web/            ← React + Vite frontend (port 5173)
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── Header.jsx
│           ├── ConfigPanel.jsx
│           ├── AgentFeed.jsx
│           ├── DecisionPanel.jsx
│           └── HistorySidebar.jsx
└── .env            ← API keys (copy from .env.example)
```

## Setup

### 1. Copy env file and add your API keys

```bash
cp .env.example .env
# Edit .env and set at least one LLM provider key, e.g.:
# OPENAI_API_KEY=sk-...
```

### 2. Install Python dependencies (already done if you ran the setup)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install fastapi "uvicorn[standard]" python-dotenv sse-starlette
```

### 3. Install frontend dependencies (already done if you ran the setup)

```bash
cd web && npm install
```

## Running

Open **two terminal windows** in the project root:

### Terminal 1 — Backend (FastAPI)

```bash
source .venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Frontend (Vite dev server)

```bash
cd web
npm run dev
```

Then open **http://localhost:5173** in your browser.

The Vite dev server proxies `/analyze` and `/health` to the backend at port 8000, so no CORS issues during development.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyze` | Streams analysis via SSE. Body: `{ ticker, date, llm_provider, deep_think_llm, quick_think_llm, max_debate_rounds }` |
| `GET`  | `/health`  | Returns `{ status: "ok" }` |

### SSE Event Types

| Event | Payload |
|-------|---------|
| `status` | `{ message }` — initialisation / progress messages |
| `agent_complete` | `{ agent, node, snippet }` — fired as each agent finishes |
| `final_decision` | `{ signal, reasoning, ticker, date }` — the final trade signal |
| `error` | `{ message, detail }` — if something goes wrong |

### Signals

`Buy` · `Overweight` · `Hold` · `Underweight` · `Sell`

## UI Features

- **Config panel** — ticker, date, LLM provider, deep/quick model selectors, debate rounds slider
- **Agent feed** — 12 agent cards that glow/animate as each agent completes; shows a text snippet from the report
- **Decision panel** — BUY / SELL / HOLD badge with expandable full reasoning
- **History sidebar** — last 50 runs stored in `localStorage`; persists across page reloads

## LLM Providers

| Provider | Key env var | Example models |
|----------|-------------|----------------|
| OpenAI   | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-opus-4-7`, `claude-sonnet-4-6` |
| Google   | `GOOGLE_API_KEY` | `gemini-2.5-pro`, `gemini-2.0-flash` |
| xAI      | `XAI_API_KEY` | `grok-3`, `grok-3-mini` |
