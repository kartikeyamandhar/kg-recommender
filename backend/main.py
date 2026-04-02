import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.extraction_agent import run_extraction_agent

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


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


class TextIngestRequest(BaseModel):
    text: str


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
        async for event in run_extraction_agent(request.text):
            yield _sse_line(event)
        yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
