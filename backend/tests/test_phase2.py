"""Phase 2 tests — all 9 required by the build spec."""
import json
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from backend.graph.kg_store import KGStore, slugify
from backend.models.schemas import Triple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_TRIPLES_JSON = json.dumps([
    {"head": "Christopher Nolan", "relation": "directed", "tail": "Inception", "confidence": 0.95},
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


def _make_store(tmp_path: str) -> KGStore:
    return KGStore(db_path=tmp_path)


def _sample_triples():
    return [
        Triple(head="Christopher Nolan", relation="directed", tail="Inception", confidence=0.95),
        Triple(head="Inception", relation="released_in", tail="2010", confidence=0.9),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_triples_persisted_to_sqlite():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _make_store(db_path)
    for t in _sample_triples():
        store.add_triple(t)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT * FROM edges").fetchall()
    conn.close()
    assert len(rows) == 2


def test_graph_loads_from_sqlite_on_restart():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store1 = _make_store(db_path)
    for t in _sample_triples():
        store1.add_triple(t)

    # Simulate restart — new instance from same DB
    store2 = _make_store(db_path)
    assert store2.node_count >= 3  # Nolan, Inception, 2010
    assert store2.edge_count >= 2


def test_entity_deduplication():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _make_store(db_path)
    # Same entity, different case
    store.add_triple(Triple(head="Christopher Nolan", relation="directed", tail="Inception", confidence=0.9))
    store.add_triple(Triple(head="christopher nolan", relation="born_in", tail="London", confidence=0.8))

    nolan_id = slugify("Christopher Nolan")
    assert store.graph.has_node(nolan_id)
    # Only one node for Nolan regardless of case
    nolan_variants = [n for n in store.graph.nodes if "nolan" in n]
    assert len(nolan_variants) == 1


def test_get_graph_endpoint():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("backend.agents.graph_agent.get_store") as mock_get_store, \
         patch("backend.main.get_store") as mock_main_store:
        store = _make_store(db_path)
        for t in _sample_triples():
            store.add_triple(t)
        mock_get_store.return_value = store
        mock_main_store.return_value = store

        from backend.main import app
        client = TestClient(app)
        response = client.get("/graph")

    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_graph_endpoint_nodes_have_required_fields():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("backend.main.get_store") as mock_main_store:
        store = _make_store(db_path)
        for t in _sample_triples():
            store.add_triple(t)
        mock_main_store.return_value = store

        from backend.main import app
        client = TestClient(app)
        response = client.get("/graph")

    for node in response.json()["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "type" in node


def test_graph_endpoint_edges_have_required_fields():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("backend.main.get_store") as mock_main_store:
        store = _make_store(db_path)
        for t in _sample_triples():
            store.add_triple(t)
        mock_main_store.return_value = store

        from backend.main import app
        client = TestClient(app)
        response = client.get("/graph")

    for edge in response.json()["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "relation" in edge
        assert "confidence" in edge


def test_get_neighbors():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _make_store(db_path)
    for t in _sample_triples():
        store.add_triple(t)

    nolan_id = slugify("Christopher Nolan")
    result = store.get_neighbors(nolan_id, hops=1)
    neighbor_ids = {n["id"] for n in result["nodes"]}

    inception_id = slugify("Inception")
    assert inception_id in neighbor_ids
    # 2010 is 2 hops away — should NOT be in 1-hop result
    year_id = slugify("2010")
    assert year_id not in neighbor_ids


def test_centrality_returns_all_nodes():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _make_store(db_path)
    for t in _sample_triples():
        store.add_triple(t)

    centrality = store.get_centrality()
    for node_id in store.graph.nodes:
        assert node_id in centrality


@patch("backend.agents.extraction_agent._get_client")
def test_graph_agent_emits_steps(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _make_mock_response()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with patch("backend.agents.graph_agent.get_store") as mock_gs, \
         patch("backend.main.get_store") as mock_ms:
        store = _make_store(db_path)
        mock_gs.return_value = store
        mock_ms.return_value = store

        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/ingest/text", json={"text": "Christopher Nolan directed Inception."}) as r:
            events = _collect_events(r)

    graph_steps = [
        e for e in events
        if e.get("type") == "step" and e.get("step", {}).get("agent") == "graph"
    ]
    assert len(graph_steps) >= 1