import os
import re
import sqlite3
from typing import Dict

import networkx as nx
from dotenv import load_dotenv

from backend.models.schemas import Triple

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "./kg_store.db")


def slugify(label: str) -> str:
    """Lowercase, strip punctuation, replace spaces with underscores."""
    label = label.lower().strip()
    label = re.sub(r"[^\w\s]", "", label)
    label = re.sub(r"\s+", "_", label)
    return label


class KGStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.graph = nx.DiGraph()
        self._init_db()
        self._load_from_db()

    # ------------------------------------------------------------------
    # DB bootstrap
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'other'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    PRIMARY KEY (source, target, relation)
                )
            """)
            conn.commit()

    def _load_from_db(self) -> None:
        with self._get_conn() as conn:
            for row in conn.execute("SELECT id, label, type FROM nodes"):
                self.graph.add_node(row["id"], label=row["label"], type=row["type"])
            for row in conn.execute("SELECT source, target, relation, confidence FROM edges"):
                self.graph.add_edge(
                    row["source"],
                    row["target"],
                    relation=row["relation"],
                    confidence=row["confidence"],
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_triple(self, triple: Triple) -> None:
        head_id = slugify(triple.head)
        tail_id = slugify(triple.tail)

        # Infer type naively — can be enriched later
        head_type = "other"
        tail_type = "other"

        self._upsert_node(head_id, triple.head, head_type)
        self._upsert_node(tail_id, triple.tail, tail_type)
        self._upsert_edge(head_id, tail_id, triple.relation, triple.confidence)

    def _upsert_node(self, node_id: str, label: str, node_type: str) -> None:
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id, label=label, type=node_type)
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO nodes (id, label, type) VALUES (?, ?, ?)",
                    (node_id, label, node_type),
                )
                conn.commit()

    def _upsert_edge(self, source: str, target: str, relation: str, confidence: float) -> None:
        self.graph.add_edge(source, target, relation=relation, confidence=confidence)
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO edges (source, target, relation, confidence)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(source, target, relation)
                   DO UPDATE SET confidence=excluded.confidence""",
                (source, target, relation, confidence),
            )
            conn.commit()

    def get_graph(self) -> dict:
        nodes = [
            {"id": n, "label": d.get("label", n), "type": d.get("type", "other")}
            for n, d in self.graph.nodes(data=True)
        ]
        edges = [
            {
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", 1.0),
            }
            for u, v, d in self.graph.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def get_neighbors(self, entity_id: str, hops: int = 2) -> dict:
        if entity_id not in self.graph:
            return {"nodes": [], "edges": []}
        reachable = {entity_id}
        frontier = {entity_id}
        for _ in range(hops):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(self.graph.successors(node))
                next_frontier.update(self.graph.predecessors(node))
            frontier = next_frontier - reachable
            reachable.update(frontier)
        subgraph = self.graph.subgraph(reachable)
        nodes = [
            {"id": n, "label": d.get("label", n), "type": d.get("type", "other")}
            for n, d in subgraph.nodes(data=True)
        ]
        edges = [
            {
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", 1.0),
            }
            for u, v, d in subgraph.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def get_centrality(self) -> Dict[str, float]:
        if len(self.graph) == 0:
            return {}
        return nx.degree_centrality(self.graph)

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()