import os
from collections import deque
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import anthropic
from dotenv import load_dotenv

from backend.models.schemas import AgentStep, Entity, Recommendation
from backend.graph.kg_store import KGStore
from backend.graph.embeddings import EmbeddingStore

load_dotenv()

PATH_WEIGHT = 0.6
EMBED_WEIGHT = 0.4
MIN_CONFIDENCE = 0.5
MODEL = "claude-haiku-3-5-20241022"


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def _bfs_scores(
    kg_store: KGStore, seed_id: str, max_hops: int = 3
) -> Dict[str, Tuple[float, List[str]]]:
    """
    BFS from seed up to max_hops, only traversing edges with confidence >= MIN_CONFIDENCE.
    Returns {entity_id: (path_score, path_labels)}.
    """
    graph = kg_store.graph
    visited: Dict[str, Tuple[float, List[str]]] = {}
    # queue: (node_id, hop_distance, path_of_labels)
    queue = deque([(seed_id, 0, [graph.nodes[seed_id].get("label", seed_id)])])

    while queue:
        node_id, hops, path = queue.popleft()
        if node_id in visited:
            continue
        if node_id != seed_id:
            visited[node_id] = (1.0 / hops, path)
        if hops >= max_hops:
            continue

        for neighbor in graph.successors(node_id):
            edge_data = graph.edges[node_id, neighbor]
            if edge_data.get("confidence", 1.0) >= MIN_CONFIDENCE:
                neighbor_label = graph.nodes[neighbor].get("label", neighbor)
                queue.append((neighbor, hops + 1, path + [neighbor_label]))

        for neighbor in graph.predecessors(node_id):
            edge_data = graph.edges[neighbor, node_id]
            if edge_data.get("confidence", 1.0) >= MIN_CONFIDENCE:
                neighbor_label = graph.nodes[neighbor].get("label", neighbor)
                queue.append((neighbor, hops + 1, path + [neighbor_label]))

    return visited


def _generate_explanation(client: anthropic.Anthropic, seed_label: str, target_label: str, path: List[str]) -> str:
    path_str = " → ".join(path)
    prompt = (
        f"In one sentence, explain why '{target_label}' is related to '{seed_label}' "
        f"via the path: {path_str}"
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return f"Connected to {seed_label} via {path_str}."


async def run_recommendation_agent(
    kg_store: KGStore,
    embed_store: EmbeddingStore,
    seed_entity_id: str,
    k: int = 5,
) -> AsyncGenerator[dict, None]:
    graph = kg_store.graph

    if seed_entity_id not in graph:
        raise ValueError(f"Entity '{seed_entity_id}' not found in graph")

    seed_label = graph.nodes[seed_entity_id].get("label", seed_entity_id)
    step_counter = 0
    client = _get_client()

    # --- BFS ---
    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="recommendation",
            message=f"Running BFS from '{seed_label}' (max 3 hops, min confidence {MIN_CONFIDENCE})",
        ).model_dump(),
    }

    bfs_results = _bfs_scores(kg_store, seed_entity_id)

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="recommendation",
            message=f"BFS found {len(bfs_results)} reachable entities",
            data={"reachable": len(bfs_results)},
        ).model_dump(),
    }

    # --- Embedding similarity ---
    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="recommendation",
            message="Computing embedding similarity",
        ).model_dump(),
    }

    embed_results = embed_store.find_similar(seed_entity_id, k=20)
    embed_map: Dict[str, float] = {eid: score for eid, score in embed_results}

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="recommendation",
            message=f"Found {len(embed_map)} embedding neighbours",
        ).model_dump(),
    }

    # --- Combine scores ---
    all_candidates = set(bfs_results.keys()) | set(embed_map.keys())
    # Remove seed itself
    all_candidates.discard(seed_entity_id)

    scored: List[Tuple[str, float, List[str]]] = []
    for eid in all_candidates:
        path_score, path = bfs_results.get(eid, (0.0, [seed_label, graph.nodes.get(eid, {}).get("label", eid)]))
        emb_score = embed_map.get(eid, 0.0)
        final = PATH_WEIGHT * path_score + EMBED_WEIGHT * emb_score
        scored.append((eid, final, path))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:k]

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="recommendation",
            message=f"Ranked {len(scored)} candidates, returning top {len(top)}",
        ).model_dump(),
    }

    # --- Build Recommendation objects with explanations ---
    recommendations: List[Recommendation] = []
    for eid, score, path in top:
        target_label = graph.nodes.get(eid, {}).get("label", eid)
        explanation = _generate_explanation(client, seed_label, target_label, path)
        recommendations.append(
            Recommendation(
                entity_id=eid,
                label=target_label,
                score=round(score, 6),
                path=path,
                explanation=explanation,
            )
        )

    yield {
        "type": "recommendations",
        "results": [r.model_dump() for r in recommendations],
    }