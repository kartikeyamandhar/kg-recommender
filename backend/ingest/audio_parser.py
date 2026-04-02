import io
import os
import tempfile
from typing import AsyncGenerator

from backend.models.schemas import AgentStep

# Whisper is imported lazily to avoid slow startup when not needed
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model("base")
    return _whisper_model


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.mp3") -> AsyncGenerator[dict, None]:
    """
    Async generator that:
    1. Emits a step event before transcription
    2. Transcribes the audio using local Whisper base model
    3. Emits a step event after transcription
    4. Yields {"type": "transcription", "text": <transcribed text>}
    """
    step_counter = 0

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="extraction",
            message=f"Starting audio transcription ({len(audio_bytes) // 1024} KB)",
        ).model_dump(),
    }

    # Write to temp file — Whisper needs a file path
    suffix = os.path.splitext(filename)[-1] or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_whisper()
        result = model.transcribe(tmp_path)
        text = result["text"].strip()
    finally:
        os.unlink(tmp_path)

    step_counter += 1
    yield {
        "type": "step",
        "step": AgentStep(
            step=step_counter,
            agent="extraction",
            message=f"Transcription complete ({len(text)} chars)",
            data={"char_count": len(text)},
        ).model_dump(),
    }

    yield {"type": "transcription", "text": text}