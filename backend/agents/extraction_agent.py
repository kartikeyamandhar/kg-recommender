import json
import os
from typing import AsyncGenerator, List

import anthropic
from dotenv import load_dotenv

from backend.models.schemas import AgentStep, Triple
from backend.ingest.text_parser import chunk_text

load_dotenv()

EXTRACTION_PROMPT = """You are a knowledge graph extraction engine.
Extract named entities and their relationships from the text below.
Only extract NAMED entities: real people, specific books, films, places, organizations, products, and technologies.
Do NOT extract: adjectives, descriptors, generic nouns, or abstract concepts like "nutty", "experiences", "food".
Return ONLY a JSON array of objects. No preamble, no explanation, no markdown.
Each object must have: head (string), relation (string), tail (string), confidence (float 0-1).
Use concise snake_case for relation strings (e.g. directed_by, located_in, authored_by, similar_to).

TEXT:
{text}"""

MODEL = "claude-haiku-4-5-20251001"


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


async def run_extraction_agent(text: str) -> AsyncGenerator[dict, None]:
    chunks = chunk_text(text)
    client = _get_client()
    step_counter = 0
    all_triples: List[Triple] = []

    for idx, chunk in enumerate(chunks):
        step_counter += 1
        yield {
            "type": "step",
            "step": AgentStep(
                step=step_counter,
                agent="extraction",
                message=f"Sending chunk {idx + 1}/{len(chunks)} to LLM ({len(chunk)} chars)",
            ).model_dump(),
        }

        message = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system="You are a knowledge graph extraction engine. Output only valid JSON. Only extract real named entities.",
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=chunk)}],
        )
        raw_response = message.content[0].text

        step_counter += 1
        try:
            triples = _parse_triples(raw_response)
        except Exception as e:
            yield {
                "type": "step",
                "step": AgentStep(
                    step=step_counter,
                    agent="extraction",
                    message=f"Parse error on chunk {idx + 1}: {e}",
                ).model_dump(),
            }
            continue

        all_triples.extend(triples)

        yield {
            "type": "step",
            "step": AgentStep(
                step=step_counter,
                agent="extraction",
                message=f"Extracted {len(triples)} triples from chunk {idx + 1}/{len(chunks)}",
                data={"triple_count": len(triples)},
            ).model_dump(),
        }

    yield {
        "type": "triples",
        "triples": [t.model_dump() for t in all_triples],
    }
