# KG Recommender

Upload text, PDFs, images, or audio. Extract a live knowledge graph. Get explainable recommendations and chat with your content.

---

## Screenshots

### Knowledge Graph
![Knowledge Graph](docs/images/graph-view.png)

### Chat
![Chat View](docs/images/chat-view.png)

---

## Architecture

![Architecture](docs/images/architecture.svg)

---

## Agent Loop
---

## Agent Loop

**Extraction Agent** receives raw content — plain text, PDF-extracted text, a base64 image, or a Whisper transcription — and calls Claude to extract named entities and relations as JSON triples. Each triple has a head entity, relation type in snake_case, tail entity, and confidence score. Text is chunked to 2000 characters per LLM call. Images use Claude Sonnet vision and do extraction in one pass.

**Graph Agent** merges extracted triples into a live NetworkX directed graph backed by SQLite. Before inserting any entity it slugifies the label and checks for an existing node, preventing duplicates from case variation. Every insertion writes to SQLite first so the graph survives server restarts. Step events stream to the frontend in real time.

**Recommendation Agent** sends the full graph as structured context to Claude Haiku with a prompt asking for specific, grounded recommendations related to the clicked entity. Results include a reasoning path and confidence score.

**Chat Agent** receives every user message along with the full extracted graph serialized as `Entity --[relation]--> Entity` triples. Claude uses this structured context to answer questions, surface non-obvious connections, and ask clarifying questions when intent is ambiguous. Conversation history persists for the session.

---

## Stack

| Layer | Technology | Cost |
|---|---|---|
| Frontend | React 18, Vite, TailwindCSS, D3.js v7 | Free |
| API | FastAPI, Python 3.11 | Free |
| LLM extraction | Claude Haiku (`claude-haiku-4-5-20251001`) | ~$0.04 / 100 calls |
| LLM vision | Claude Sonnet (`claude-sonnet-4-20250514`) | ~$0.30 / 20 calls |
| LLM chat + reco | Claude Haiku | ~$0.02 / 100 calls |
| Embeddings | `all-MiniLM-L6-v2` via sentence-transformers | Free (local) |
| Vector search | FAISS flat index | Free (local) |
| Graph engine | NetworkX | Free |
| Graph persistence | SQLite | Free |
| Audio transcription | OpenAI Whisper base | Free (local) |

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/kartikeyamandhar/kg-recommender.git
cd kg-recommender

# 2. Python environment
python3.11 -m venv kg_rec
source kg_rec/bin/activate
pip install -r backend/requirements.txt

# 3. Environment variables
# Edit .env — set ANTHROPIC_API_KEY=sk-ant-...

# 4. Start backend
uvicorn backend.main:app --reload
# → http://localhost:8000

# 5. Start frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key — required | — |
| `DB_PATH` | Path to SQLite database file | `./kg_store.db` |
| `VITE_API_BASE_URL` | Backend URL for deployed frontend | `''` (Vite proxy) |

---

## API Reference

### `POST /ingest/text`
```json
{ "text": "string (max 10,000 chars)" }
```
Response: `text/event-stream`
```
data: {"type": "step", "step": {"agent": "extraction", "message": "..."}}
data: {"type": "triples", "triples": [...]}
data: {"type": "graph_updated", "node_count": 12, "edge_count": 8}
data: {"type": "done"}
```

### `POST /ingest/pdf` · `POST /ingest/image` · `POST /ingest/audio`
```
Content-Type: multipart/form-data
Body: file (max 10MB)
Response: same SSE stream
```

### `GET /graph`
```json
{
  "nodes": [{"id": "christopher_nolan", "label": "Christopher Nolan", "type": "person"}],
  "edges": [{"source": "christopher_nolan", "target": "inception", "relation": "directed", "confidence": 0.95}]
}
```

### `DELETE /graph`
Wipes all nodes, edges, and embeddings. Returns `{"status": "reset"}`.

### `POST /recommend`
```json
{ "entity_id": "christopher_nolan", "k": 5 }
```
Response: `text/event-stream` with `recommendations` event containing ranked results with paths and explanations.

### `POST /chat`
```json
{ "message": "string", "history": [{"role": "user"|"assistant", "content": "..."}] }
```
Response: `text/event-stream` with `chunk` events streamed token by token.

---

## Roadmap

- **Neo4j migration** — replace NetworkX + SQLite with Neo4j for graphs exceeding 10,000 nodes, enabling Cypher queries and native graph algorithms at scale
- **Pre-seeded domain knowledge** — ship with a base layer of 10,000 books, films, tools, and people so user entities immediately connect to a rich topology
- **Real-time collaborative graph building** — WebSocket-based multi-user sessions where multiple users ingest content simultaneously and watch the shared graph update live