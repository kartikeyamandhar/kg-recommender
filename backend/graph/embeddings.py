from typing import Dict, List, Tuple

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.models.schemas import Entity

MODEL_NAME = "all-MiniLM-L6-v2"
DIMS = 384


class EmbeddingStore:
    def __init__(self):
        self._model = SentenceTransformer(MODEL_NAME)
        self._index = faiss.IndexFlatIP(DIMS)  # inner product = cosine on normalized vecs
        self._id_to_pos: Dict[str, int] = {}   # entity_id -> faiss index position
        self._pos_to_id: Dict[int, str] = {}   # faiss position -> entity_id

    def _embed(self, text: str) -> np.ndarray:
        vec = self._model.encode([text], normalize_embeddings=True)
        return vec.astype(np.float32)

    def add_entity(self, entity: Entity) -> None:
        if entity.id in self._id_to_pos:
            return  # already indexed
        text = f"{entity.label} {entity.type}"
        vec = self._embed(text)
        pos = self._index.ntotal
        self._index.add(vec)
        self._id_to_pos[entity.id] = pos
        self._pos_to_id[pos] = entity.id

    def find_similar(self, entity_id: str, k: int = 10) -> List[Tuple[str, float]]:
        if entity_id not in self._id_to_pos:
            return []
        pos = self._id_to_pos[entity_id]
        # Reconstruct vector from index
        vec = np.zeros((1, DIMS), dtype=np.float32)
        self._index.reconstruct(pos, vec[0])

        actual_k = min(k + 1, self._index.ntotal)  # +1 to exclude self
        scores, positions = self._index.search(vec, actual_k)

        results = []
        for score, p in zip(scores[0], positions[0]):
            if p == -1:
                continue
            eid = self._pos_to_id.get(int(p))
            if eid is None or eid == entity_id:
                continue
            # Cosine similarity already in [-1,1]; clamp to [0,1]
            similarity = float(max(0.0, min(1.0, score)))
            results.append((eid, similarity))

        return sorted(results, key=lambda x: x[1], reverse=True)[:k]

    def rebuild_from_store(self, kg_store) -> None:
        """Re-index all entities already in the KGStore after a restart."""
        for node_id, data in kg_store.graph.nodes(data=True):
            entity = Entity(
                id=node_id,
                label=data.get("label", node_id),
                type=data.get("type", "other"),
                properties={},
            )
            self.add_entity(entity)

    @property
    def size(self) -> int:
        return self._index.ntotal