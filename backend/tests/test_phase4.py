"""Phase 4 tests — all 10 required by the build spec."""
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_PDF = os.path.join(FIXTURES, "sample.pdf")
SAMPLE_PNG = os.path.join(FIXTURES, "sample.png")
SAMPLE_WAV = os.path.join(FIXTURES, "sample.wav")

SAMPLE_TRIPLES_JSON = json.dumps([
    {"head": "Christopher Nolan", "relation": "directed", "tail": "Inception", "confidence": 0.95},
    {"head": "Inception", "relation": "stars", "tail": "Leonardo DiCaprio", "confidence": 0.9},
])


def _make_llm_mock(text=SAMPLE_TRIPLES_JSON):
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    return mock


def _make_st_mock():
    import numpy as np
    mock = MagicMock()
    def _encode(texts, normalize_embeddings=True):
        rng = np.random.default_rng(42)
        vec = rng.random((len(texts), 384)).astype(np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(vec, axis=1, keepdims=True)
            vec = vec / np.where(norms == 0, 1, norms)
        return vec
    mock.encode.side_effect = _encode
    return mock


ST_PATCHER = patch("backend.graph.embeddings.SentenceTransformer", return_value=_make_st_mock())


def _collect_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def _make_store():
    from backend.graph.kg_store import KGStore
    from backend.graph.embeddings import EmbeddingStore
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = KGStore(db_path=db_path)
    embed_store = EmbeddingStore()
    return store, embed_store


# ---------------------------------------------------------------------------
# PDF tests
# ---------------------------------------------------------------------------

@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
def test_pdf_endpoint_accepts_file(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post("/ingest/pdf", files={"file": ("sample.pdf", f, "application/pdf")})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
def test_pdf_extraction_yields_triples(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_PDF, "rb") as f:
            with client.stream("POST", "/ingest/pdf", files={"file": ("sample.pdf", f, "application/pdf")}) as r:
                events = _collect_events(r)
    triple_events = [e for e in events if e.get("type") == "triples"]
    assert len(triple_events) >= 1
    assert len(triple_events[0]["triples"]) > 0


@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
def test_pdf_oversized_truncates_gracefully(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()

    # Build a PDF whose extracted text exceeds 6000 chars
    import fitz
    doc = fitz.open()
    # Add multiple pages each with enough text to push total > 6000 chars
    sentence = "Christopher Nolan directed Inception in two thousand ten. "
    for _ in range(3):
        page = doc.new_page()
        y = 50
        for _ in range(40):  # ~40 lines per page, ~58 chars each = ~2320 chars/page -> 6960 total
            page.insert_text((50, y), sentence)
            y += 15
    pdf_bytes = doc.tobytes()
    doc.close()

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/ingest/pdf",
                           files={"file": ("big.pdf", pdf_bytes, "application/pdf")}) as r:
            events = _collect_events(r)

    # Should complete with 200 and contain a truncation notice step
    step_events = [e for e in events if e.get("type") == "step"]
    truncation_steps = [
        e for e in step_events
        if "truncat" in (e.get("step") or {}).get("message", "").lower()
    ]
    assert len(truncation_steps) >= 1
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------

@ST_PATCHER
@patch("backend.ingest.image_parser._get_client")
def test_image_endpoint_accepts_file(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_PNG, "rb") as f:
            response = client.post("/ingest/image", files={"file": ("sample.png", f, "image/png")})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@ST_PATCHER
@patch("backend.ingest.image_parser._get_client")
def test_image_extraction_yields_triples(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_PNG, "rb") as f:
            with client.stream("POST", "/ingest/image",
                               files={"file": ("sample.png", f, "image/png")}) as r:
                events = _collect_events(r)
    triple_events = [e for e in events if e.get("type") == "triples"]
    assert len(triple_events) >= 1
    assert len(triple_events[0]["triples"]) > 0


@ST_PATCHER
def test_image_invalid_mimetype_returns_error(mock_st):
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        fake_txt = b"this is not an image"
        response = client.post("/ingest/image",
                               files={"file": ("file.txt", fake_txt, "text/plain")})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Audio tests
# ---------------------------------------------------------------------------

@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
@patch("backend.ingest.audio_parser._get_whisper")
def test_audio_endpoint_accepts_file(mock_whisper, mock_client, mock_st):
    mock_whisper.return_value.transcribe.return_value = {
        "text": "Christopher Nolan directed Inception in 2010."
    }
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_WAV, "rb") as f:
            response = client.post("/ingest/audio", files={"file": ("sample.wav", f, "audio/wav")})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
@patch("backend.ingest.audio_parser._get_whisper")
def test_audio_transcription_step_emitted(mock_whisper, mock_client, mock_st):
    mock_whisper.return_value.transcribe.return_value = {
        "text": "Christopher Nolan directed Inception in 2010."
    }
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_WAV, "rb") as f:
            with client.stream("POST", "/ingest/audio",
                               files={"file": ("sample.wav", f, "audio/wav")}) as r:
                events = _collect_events(r)

    step_events = [e for e in events if e.get("type") == "step"]
    transcription_steps = [
        e for e in step_events
        if "transcri" in (e.get("step") or {}).get("message", "").lower()
    ]
    assert len(transcription_steps) >= 1


@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
@patch("backend.ingest.audio_parser._get_whisper")
def test_audio_yields_triples(mock_whisper, mock_client, mock_st):
    mock_whisper.return_value.transcribe.return_value = {
        "text": "Christopher Nolan directed Inception in 2010."
    }
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    store, embed_store = _make_store()
    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store), \
         patch("backend.agents.graph_agent.get_store", return_value=store):
        from backend.main import app
        client = TestClient(app)
        with open(SAMPLE_WAV, "rb") as f:
            with client.stream("POST", "/ingest/audio",
                               files={"file": ("sample.wav", f, "audio/wav")}) as r:
                events = _collect_events(r)

    triple_events = [e for e in events if e.get("type") == "triples"]
    assert len(triple_events) >= 1
    assert len(triple_events[0]["triples"]) > 0


# ---------------------------------------------------------------------------
# Unified graph test
# ---------------------------------------------------------------------------

@ST_PATCHER
@patch("backend.agents.extraction_agent._get_client")
@patch("backend.ingest.image_parser._get_client")
@patch("backend.ingest.audio_parser._get_whisper")
def test_all_modalities_write_to_same_graph(mock_whisper, mock_img_client, mock_txt_client, mock_st):
    mock_whisper.return_value.transcribe.return_value = {"text": "Alan Turing invented the Turing Machine."}
    mock_txt_client.return_value.messages.create.return_value = _make_llm_mock()
    mock_img_client.return_value.messages.create.return_value = _make_llm_mock(json.dumps([
        {"head": "Warner Bros", "relation": "produced", "tail": "Inception", "confidence": 0.9},
    ]))

    store, embed_store = _make_store()

    def get_s():
        return store

    def get_e():
        return embed_store

    with patch("backend.main.get_store", side_effect=get_s), \
         patch("backend.main.get_embed_store", side_effect=get_e), \
         patch("backend.agents.graph_agent.get_store", side_effect=get_s):
        from backend.main import app
        client = TestClient(app)

        # Ingest PDF
        with open(SAMPLE_PDF, "rb") as f:
            client.post("/ingest/pdf", files={"file": ("sample.pdf", f, "application/pdf")})

        # Ingest image
        with open(SAMPLE_PNG, "rb") as f:
            client.post("/ingest/image", files={"file": ("sample.png", f, "image/png")})

        # Ingest audio
        with open(SAMPLE_WAV, "rb") as f:
            client.post("/ingest/audio", files={"file": ("sample.wav", f, "audio/wav")})

        response = client.get("/graph")

    data = response.json()
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0