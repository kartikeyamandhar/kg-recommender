import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from backend.main import app

client = TestClient(app)

SAMPLE_TRIPLES_JSON = json.dumps([
    {"head": "Christopher Nolan", "relation": "directed_by", "tail": "Inception", "confidence": 0.95},
    {"head": "Inception", "relation": "released_in", "tail": "2010", "confidence": 0.9},
    {"head": "Christopher Nolan", "relation": "born_in", "tail": "London", "confidence": 0.85},
])


def _make_mock_response(content: str = SAMPLE_TRIPLES_JSON):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=content)]
    return mock_msg


def _collect_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


@patch("backend.agents.extraction_agent._get_client")
def test_endpoint_accepts_text(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    response = client.post(
        "/ingest/text",
        json={"text": "Christopher Nolan directed Inception in 2010."},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@patch("backend.agents.extraction_agent._get_client")
def test_stream_emits_step_events(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    with client.stream("POST", "/ingest/text", json={"text": "Christopher Nolan directed Inception."}) as r:
        events = _collect_events(r)
    assert len([e for e in events if e.get("type") == "step"]) >= 1


@patch("backend.agents.extraction_agent._get_client")
def test_stream_emits_triples(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    with client.stream("POST", "/ingest/text", json={"text": "Christopher Nolan directed Inception."}) as r:
        events = _collect_events(r)
    triple_events = [e for e in events if e.get("type") == "triples"]
    assert len(triple_events) == 1
    assert len(triple_events[0]["triples"]) > 0


@patch("backend.agents.extraction_agent._get_client")
def test_triples_schema_valid(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    with client.stream("POST", "/ingest/text", json={"text": "Christopher Nolan directed Inception."}) as r:
        events = _collect_events(r)
    triples = [e for e in events if e.get("type") == "triples"][0]["triples"]
    for t in triples:
        assert isinstance(t["head"], str) and t["head"]
        assert isinstance(t["relation"], str) and t["relation"]
        assert isinstance(t["tail"], str) and t["tail"]
        assert isinstance(t["confidence"], float)
        assert 0.0 <= t["confidence"] <= 1.0


@patch("backend.agents.extraction_agent._get_client")
def test_stream_ends_with_done(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    with client.stream("POST", "/ingest/text", json={"text": "Christopher Nolan directed Inception."}) as r:
        events = _collect_events(r)
    assert events[-1]["type"] == "done"


def test_empty_input_returns_error():
    response = client.post("/ingest/text", json={"text": ""})
    assert response.status_code == 422


@patch("backend.agents.extraction_agent._get_client")
def test_oversized_input_is_chunked(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()
    long_text = "Christopher Nolan directed Inception. " * 100
    with client.stream("POST", "/ingest/text", json={"text": long_text}) as r:
        events = _collect_events(r)
    assert mock_get_client.return_value.messages.create.call_count >= 2
    triple_events = [e for e in events if e.get("type") == "triples"]
    assert len(triple_events) == 1
    assert len(triple_events[0]["triples"]) > 0
