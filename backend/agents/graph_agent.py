from typing import AsyncGenerator, List

from backend.models.schemas import AgentStep, Triple
from backend.graph.kg_store import KGStore

# Module-level singleton — shared across requests
_store: KGStore | None = None


def get_store() -> KGStore:
    global _store
    if _store is None:
        _store = KGStore()
    return _store


async def run_graph_agent(triples: List[Triple]) -> AsyncGenerator[dict, None]:
    """
    Async generator yielding SSE-ready dicts:
      {"type": "step", "step": <AgentStep dict>}
      {"type": "graph_updated", "node_count": N, "edge_count": M}
    """
    store = get_store()
    step_counter = 0

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="graph",
            message=f"Merging {len(triples)} triples into knowledge graph",
        ).model_dump(),
    }

    for idx, triple in enumerate(triples):
        store.add_triple(triple)
        # Emit progress every 10 triples
        if (idx + 1) % 10 == 0:
            step_counter += 1
            yield {
                "type": "step",
                "step": AgentStep(
                    step=step_counter,
                    agent="graph",
                    message=f"Processed {idx + 1}/{len(triples)} triples",
                    data={"processed": idx + 1, "total": len(triples)},
                ).model_dump(),
            }

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="graph",
            message=f"Graph updated: {store.node_count} nodes, {store.edge_count} edges",
            data={"node_count": store.node_count, "edge_count": store.edge_count},
        ).model_dump(),
    }

    yield {
        "type": "graph_updated",
        "node_count": store.node_count,
        "edge_count": store.edge_count,
    }