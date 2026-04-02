from pydantic import BaseModel
from typing import List, Optional


class Triple(BaseModel):
    head: str
    relation: str
    tail: str
    confidence: float


class Entity(BaseModel):
    id: str
    label: str
    type: str  # person | concept | place | work | organization | other
    properties: dict


class AgentStep(BaseModel):
    step: int
    agent: str  # "extraction" | "graph" | "recommendation"
    message: str
    data: Optional[dict] = None


class Recommendation(BaseModel):
    entity_id: str
    label: str
    score: float
    path: List[str]
    explanation: str
