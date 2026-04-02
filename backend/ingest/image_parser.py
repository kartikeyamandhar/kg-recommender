import base64
import json
import os
from typing import List

import anthropic
from dotenv import load_dotenv

from backend.models.schemas import Triple

load_dotenv()

VISION_MODEL = "claude-sonnet-4-20250514"

VISION_PROMPT = """You are a knowledge graph extraction engine analyzing an image.
Identify all named entities visible or implied (people, places, organizations, works, concepts).
Extract relationships between them.
Return ONLY a JSON array. No preamble. No markdown.
Each object: {head: string, relation: string, tail: string, confidence: float 0-1}"""


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def _parse_triples(raw: str) -> List[Triple]:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(raw)
    triples = []
    for item in data:
        if not isinstance(item, dict):
            continue
        head = str(item.get("head", "")).strip()
        relation = str(item.get("relation", "")).strip()
        tail = str(item.get("tail", "")).strip()
        confidence = float(item.get("confidence", 0.5))
        if head and relation and tail:
            confidence = max(0.0, min(1.0, confidence))
            triples.append(Triple(head=head, relation=relation, tail=tail, confidence=confidence))
    return triples


def extract_image_triples(image_bytes: bytes, media_type: str) -> List[Triple]:
    """
    Call Claude vision model on the image and return extracted triples directly.
    media_type: e.g. "image/jpeg", "image/png", "image/webp"
    """
    client = _get_client()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    message = client.messages.create(
        model=VISION_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )

    raw = message.content[0].text
    return _parse_triples(raw)