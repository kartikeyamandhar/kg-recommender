import json
import os
from typing import AsyncGenerator, List

import anthropic
from dotenv import load_dotenv

from backend.graph.kg_store import KGStore

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an intelligent assistant with access to a knowledge graph that was built from content the user uploaded (text, PDF, image, or audio).

Your job is to:
1. Answer questions about the content using the knowledge graph as structured context
2. Make specific, grounded recommendations based on what the graph reveals about the user's domain or interests
3. Ask smart clarifying questions when the user's intent is ambiguous
4. Proactively surface connections and insights the user might not have asked for

RULES:
- Always ground your answers in the knowledge graph when relevant
- Be specific — name actual books, tools, films, people, places, techniques
- If the graph doesn't have enough info, say so and ask a clarifying question
- Keep responses concise and scannable — use short paragraphs or bullet points
- When making recommendations, explain WHY based on what's in the graph
- You can ask ONE clarifying question at a time if needed — don't overwhelm the user

KNOWLEDGE GRAPH (extracted from user's uploaded content):
{graph_summary}

If the graph is empty, tell the user to upload some content first."""


def _graph_summary(kg_store: KGStore) -> str:
    if kg_store.node_count == 0:
        return "(empty — no content uploaded yet)"
    lines = []
    for u, v, data in kg_store.graph.edges(data=True):
        u_label = kg_store.graph.nodes[u].get("label", u)
        v_label = kg_store.graph.nodes[v].get("label", v)
        relation = data.get("relation", "related_to")
        conf = data.get("confidence", 1.0)
        lines.append(f"  {u_label} --[{relation}]--> {v_label} (confidence: {conf:.2f})")
    # Cap at 100 edges to stay within context
    if len(lines) > 100:
        lines = lines[:100]
        lines.append("  ... (truncated)")
    return "\n".join(lines)


async def run_chat_agent(
    kg_store: KGStore,
    message: str,
    history: List[dict],
) -> AsyncGenerator[str, None]:
    """
    Streams response text chunks.
    history format: [{"role": "user"|"assistant", "content": "..."}]
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    graph_summary = _graph_summary(kg_store)
    system = SYSTEM_PROMPT.format(graph_summary=graph_summary)

    # Build message list: history + new message
    messages = []
    for turn in history:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text