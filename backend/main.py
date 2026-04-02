import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.extraction_agent import run_extraction_agent
from backend.agents.graph_agent import run_graph_agent, get_store
from backend.agents.recommendation_agent import run_recommendation_agent
from backend.graph.embeddings import EmbeddingStore
from backend.models.schemas import Entity, Triple

load_dotenv()

app = FastAPI(title="KG Recommender API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_TEXT_LENGTH = 10_000

_embed_store: EmbeddingStore | None = None


def get_embed_store() -> EmbeddingStore:
    global _embed_store
    if _embed_store is None:
        _embed_store = EmbeddingStore()
        _embed_store.rebuild_from_store(get_store())
    return _embed_store


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


class TextIngestRequest(BaseModel):
    text: str


class RecommendRequest(BaseModel):
    entity_id: str
    k: int = 5


@app.post("/ingest/text")
async def ingest_text(request: TextIngestRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    if len(request.text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"text exceeds maximum length of {MAX_TEXT_LENGTH} characters",
        )

    async def event_generator():
        triples = []

        async for event in run_extraction_agent(request.text):
            yield _sse_line(event)
            if event.get("type") == "triples":
                triples = [Triple(**t) for t in event["triples"]]

        async for event in run_graph_agent(triples):
            yield _sse_line(event)

        store = get_store()
        embed_store = get_embed_store()
        for node_id, data in store.graph.nodes(data=True):
            embed_store.add_entity(Entity(
                id=node_id,
                label=data.get("label", node_id),
                type=data.get("type", "other"),
                properties={},
            ))

        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/graph")
async def get_graph():
    return get_store().get_graph()


@app.post("/recommend")
async def recommend(request: RecommendRequest):
    store = get_store()
    if request.entity_id not in store.graph:
        raise HTTPException(status_code=404, detail=f"Entity '{request.entity_id}' not found")

    embed_store = get_embed_store()

    async def event_generator():
        try:
            async for event in run_recommendation_agent(store, embed_store, request.entity_id, request.k):
                yield _sse_line(event)
        except ValueError as e:
            yield _sse_line({"type": "error", "message": str(e)})
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")