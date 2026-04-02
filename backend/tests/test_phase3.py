"""Phase 3 tests — all 10 required by the build spec."""
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from backend.graph.kg_store import KGStore, slugify
from backend.models.schemas import Triple, Entity

# ---------------------------------------------------------------------------
# Mock SentenceTransformer so tests don't need HuggingFace
# ---------------------------------------------------------------------------

def _make_st_mock():
    """Returns a SentenceTransformer mock that produces deterministic embeddings."""
    mock = MagicMock()
    def _encode(texts, normalize_embeddings=True):
        rng = np.random.default_rng(abs(hash(texts[0])) % (2**32))
        vec = rng.random((len(texts), 384)).astype(np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(vec, axis=1, keepdims=True)
            vec = vec / np.where(norms == 0, 1, norms)
        return vec
    mock.encode.side_effect = _encode
    return mock

ST_PATCHER = patch("backend.graph.embeddings.SentenceTransformer", return_value=_make_st_mock())

# ---------------------------------------------------------------------------
# Dataset: 20+ triples across 3 topics
# ---------------------------------------------------------------------------

TOPIC_TRIPLES = [
    Triple(head="Christopher Nolan", relation="directed", tail="Inception", confidence=0.95),
    Triple(head="Christopher Nolan", relation="directed", tail="The Dark Knight", confidence=0.95),
    Triple(head="Christopher Nolan", relation="directed", tail="Interstellar", confidence=0.95),
    Triple(head="Inception", relation="released_in", tail="2010", confidence=0.9),
    Triple(head="Inception", relation="stars", tail="Leonardo DiCaprio", confidence=0.9),
    Triple(head="The Dark Knight", relation="stars", tail="Christian Bale", confidence=0.9),
    Triple(head="Interstellar", relation="stars", tail="Matthew McConaughey", confidence=0.9),
    Triple(head="Christopher Nolan", relation="born_in", tail="London", confidence=0.85),
    Triple(head="Albert Einstein", relation="developed", tail="Theory of Relativity", confidence=0.99),
    Triple(head="Albert Einstein", relation="born_in", tail="Ulm", confidence=0.99),
    Triple(head="Theory of Relativity", relation="published_in", tail="1905", confidence=0.95),
    Triple(head="Albert Einstein", relation="awarded", tail="Nobel Prize", confidence=0.95),
    Triple(head="Nobel Prize", relation="established_by", tail="Alfred Nobel", confidence=0.9),
    Triple(head="Alfred Nobel", relation="invented", tail="Dynamite", confidence=0.9),
    Triple(head="Alan Turing", relation="created", tail="Turing Machine", confidence=0.95),
    Triple(head="Alan Turing", relation="worked_at", tail="Bletchley Park", confidence=0.9),
    Triple(head="Turing Machine", relation="influenced", tail="Modern Computing", confidence=0.85),
    Triple(head="Alan Turing", relation="born_in", tail="London", confidence=0.9),
    Triple(head="Modern Computing", relation="includes", tail="Artificial Intelligence", confidence=0.8),
    Triple(head="Artificial Intelligence", relation="subfield_of", tail="Computer Science", confidence=0.9),
    Triple(head="Alan Turing", relation="published", tail="Computing Machinery and Intelligence", confidence=0.95),
]

SAMPLE_LLM_RESPONSE = "They are related through shared cinematic history."


def _make_llm_mock(text=SAMPLE_LLM_RESPONSE):
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    return mock


def _build_store(db_path: str) -> KGStore:
    store = KGStore(db_path=db_path)
    for t in TOPIC_TRIPLES:
        store.add_triple(t)
    return store


def _build_embed_store(kg_store: KGStore):
    from backend.graph.embeddings import EmbeddingStore
    es = EmbeddingStore()
    es.rebuild_from_store(kg_store)
    return es


def _collect_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# Tests — all run with ST mocked
# ---------------------------------------------------------------------------

@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_recommendation_endpoint_returns_200(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        response = client.post("/recommend", json={"entity_id": seed_id, "k": 5})
    assert response.status_code == 200


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_recommendations_schema_valid(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 5}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    for rec in results:
        assert "entity_id" in rec
        assert "label" in rec
        assert isinstance(rec["score"], float)
        assert isinstance(rec["path"], list)
        assert "explanation" in rec


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_path_not_empty(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 5}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    for rec in results:
        assert len(rec["path"]) >= 2


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_explanation_not_empty(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock("They share a deep connection.")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 5}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    for rec in results:
        assert rec["explanation"] and len(rec["explanation"]) > 0


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_scores_ordered_descending(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 5}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


@ST_PATCHER
def test_unknown_entity_returns_error(mock_st):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        response = client.post("/recommend", json={"entity_id": "does_not_exist", "k": 5})
    assert response.status_code == 404


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_k_respected(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 3}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    assert len(results) <= 3


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_path_score_only_uses_high_confidence_triples(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    store.add_triple(Triple(
        head="Christopher Nolan", relation="rumored_link", tail="SecretEntity", confidence=0.2
    ))
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")
    secret_id = slugify("SecretEntity")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 20}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    for rec in results:
        assert secret_id not in rec["path"]


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_embedding_similarity_contributes_to_score(mock_client, mock_st):
    """Entities appearing only via embedding similarity (no graph path) show up in results."""
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)

    # Two isolated nodes — no edges connecting them to each other or to seed
    store.add_triple(Triple(head="ZIsolatedA", relation="exists", tail="ZNodeX", confidence=0.9))
    store.add_triple(Triple(head="ZIsolatedB", relation="exists", tail="ZNodeY", confidence=0.9))

    from backend.graph.embeddings import EmbeddingStore
    import faiss, numpy as np

    # Build a controlled embed store where ZIsolatedB is guaranteed nearest to ZIsolatedA
    embed_store = EmbeddingStore()
    seed_id = slugify("ZIsolatedA")
    target_id = slugify("ZIsolatedB")

    # Identical vectors => cosine similarity = 1.0
    vec = np.ones((1, 384), dtype=np.float32)
    vec /= np.linalg.norm(vec)

    embed_store._index.add(vec)
    embed_store._id_to_pos[seed_id] = 0
    embed_store._pos_to_id[0] = seed_id

    embed_store._index.add(vec)
    embed_store._id_to_pos[target_id] = 1
    embed_store._pos_to_id[1] = target_id

    # Add all graph nodes with random (but distinct) vecs so they score lower
    rng = np.random.default_rng(42)
    for i, node_id in enumerate(store.graph.nodes):
        if node_id in (seed_id, target_id):
            continue
        rv = rng.random((1, 384)).astype(np.float32)
        rv /= np.linalg.norm(rv)
        pos = embed_store._index.ntotal
        embed_store._index.add(rv)
        embed_store._id_to_pos[node_id] = pos
        embed_store._pos_to_id[pos] = node_id

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 10}) as r:
            events = _collect_events(r)

    results = [e for e in events if e.get("type") == "recommendations"][0]["results"]
    result_ids = [r["entity_id"] for r in results]
    # ZIsolatedB has cosine sim = 1.0 with seed and no graph path — must appear via embedding branch
    assert target_id in result_ids


@ST_PATCHER
@patch("backend.agents.recommendation_agent._get_client")
def test_agent_emits_recommendation_steps(mock_client, mock_st):
    mock_client.return_value.messages.create.return_value = _make_llm_mock()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = _build_store(db_path)
    embed_store = _build_embed_store(store)
    seed_id = slugify("Christopher Nolan")

    with patch("backend.main.get_store", return_value=store), \
         patch("backend.main.get_embed_store", return_value=embed_store):
        from backend.main import app
        client = TestClient(app)
        with client.stream("POST", "/recommend", json={"entity_id": seed_id, "k": 5}) as r:
            events = _collect_events(r)

    reco_steps = [
        e for e in events
        if e.get("type") == "step" and e.get("step", {}).get("agent") == "recommendation"
    ]
    assert len(reco_steps) >= 1