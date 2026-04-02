from typing import List

CHUNK_SIZE = 2000


def chunk_text(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end >= len(text):
            chunks.append(text[start:])
            break
        split_at = text.rfind(" ", start, end)
        if split_at == -1 or split_at <= start:
            split_at = end
        chunks.append(text[start:split_at].strip())
        start = split_at + 1
    return [c for c in chunks if c]
