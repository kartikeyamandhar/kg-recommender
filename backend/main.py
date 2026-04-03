import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.extraction_agent import run_extraction_agent
from backend.agents.graph_agent import run_graph_agent, get_store
from backend.agents.recommendation_agent import run_recommendation_agent
from backend.graph.embeddings import EmbeddingStore
from backend.ingest.pdf_parser import extract_pdf_text
from backend.ingest.image_parser import extract_image_triples
from backend.ingest.audio_parser import transcribe_audio
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
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_AUDIO_TYPES = {"audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a", "audio/m4a"}

_embed_store: EmbeddingStore | None = None


def get_embed_store() -> EmbeddingStore:
    global _embed_store
    if _embed_store is None:
        _embed_store = EmbeddingStore()
        _embed_store.rebuild_from_store(get_store())
    return _embed_store


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _index_new_entities():
    """Index any new graph nodes into the embedding store."""
    store = get_store()
    embed_store = get_embed_store()
    for node_id, data in store.graph.nodes(data=True):
        embed_store.add_entity(Entity(
            id=node_id,
            label=data.get("label", node_id),
            type=data.get("type", "other"),
            properties={},
        ))


async def _run_pipeline(triples: list[Triple]):
    """Run graph agent on triples and index new entities. Yields SSE events."""
    async for event in run_graph_agent(triples):
        yield event
    await _index_new_entities()


class TextIngestRequest(BaseModel):
    text: str


class RecommendRequest(BaseModel):
    entity_id: str
    k: int = 5


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

@app.post("/ingest/text")
async def ingest_text(request: TextIngestRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    if len(request.text) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=422, detail=f"text exceeds {MAX_TEXT_LENGTH} chars")

    async def event_generator():
        triples = []
        async for event in run_extraction_agent(request.text):
            yield _sse_line(event)
            if event.get("type") == "triples":
                triples = [Triple(**t) for t in event["triples"]]
        async for event in _run_pipeline(triples):
            yield _sse_line(event)
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@app.post("/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds 10MB limit")

    async def event_generator():
        text, truncated = extract_pdf_text(contents)

        if truncated:
            yield _sse_line({
                "type": "step",
                "step": {
                    "step": 0,
                    "agent": "extraction",
                    "message": "PDF exceeded 6000 chars — truncated to first 6000 characters",
                    "data": {"truncated": True},
                },
            })

        if not text.strip():
            yield _sse_line({"type": "triples", "triples": []})
            yield _sse_line({"type": "done"})
            return

        triples = []
        async for event in run_extraction_agent(text):
            yield _sse_line(event)
            if event.get("type") == "triples":
                triples = [Triple(**t) for t in event["triples"]]
        async for event in _run_pipeline(triples):
            yield _sse_line(event)
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

@app.post("/ingest/image")
async def ingest_image(file: UploadFile = File(...)):
    media_type = file.content_type or ""
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported image type: {media_type}. Use jpeg, png, or webp.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds 10MB limit")

    async def event_generator():
        yield _sse_line({
            "type": "step",
            "step": {
                "step": 1,
                "agent": "extraction",
                "message": f"Sending image to Claude vision ({len(contents) // 1024} KB)",
                "data": None,
            },
        })

        try:
            triples = extract_image_triples(contents, media_type)
        except Exception as e:
            yield _sse_line({"type": "step", "step": {
                "step": 2, "agent": "extraction",
                "message": f"Vision extraction error: {e}", "data": None,
            }})
            yield _sse_line({"type": "triples", "triples": []})
            yield _sse_line({"type": "done"})
            return

        yield _sse_line({
            "type": "step",
            "step": {
                "step": 2,
                "agent": "extraction",
                "message": f"Vision extracted {len(triples)} triples",
                "data": {"triple_count": len(triples)},
            },
        })
        yield _sse_line({"type": "triples", "triples": [t.model_dump() for t in triples]})

        async for event in _run_pipeline(triples):
            yield _sse_line(event)
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

@app.post("/ingest/audio")
async def ingest_audio(file: UploadFile = File(...)):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds 10MB limit")

    filename = file.filename or "audio.mp3"

    async def event_generator():
        transcribed_text = ""

        async for event in transcribe_audio(contents, filename):
            if event.get("type") == "transcription":
                transcribed_text = event["text"]
            else:
                yield _sse_line(event)

        if not transcribed_text.strip():
            yield _sse_line({"type": "triples", "triples": []})
            yield _sse_line({"type": "done"})
            return

        triples = []
        async for event in run_extraction_agent(transcribed_text):
            yield _sse_line(event)
            if event.get("type") == "triples":
                triples = [Triple(**t) for t in event["triples"]]
        async for event in _run_pipeline(triples):
            yield _sse_line(event)
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Graph + Recommend
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: list = []


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    from backend.agents.chat_agent import run_chat_agent

    async def event_generator():
        try:
            async for chunk in run_chat_agent(get_store(), request.message, request.history):
                yield _sse_line({"type": "chunk", "text": chunk})
        except Exception as e:
            yield _sse_line({"type": "error", "message": str(e)})
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.delete("/graph")
async def reset_graph():
    import sqlite3
    store = get_store()
    store.graph.clear()
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")
        conn.commit()
    global _embed_store
    _embed_store = None
    return {"status": "reset"}
