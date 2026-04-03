import asyncio
import os
import tempfile
from typing import AsyncGenerator

from backend.models.schemas import AgentStep

_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import torch
        torch.set_num_threads(1)
        import whisper
        _whisper_model = whisper.load_model("base")
    return _whisper_model


def _transcribe_sync(audio_bytes: bytes, suffix: str) -> str:
    import torch
    torch.set_num_threads(1)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        model = _get_whisper()
        result = model.transcribe(tmp_path, fp16=False)
        return result["text"].strip()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.mp3") -> AsyncGenerator[dict, None]:
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

    suffix = os.path.splitext(filename)[-1] or ".mp3"

    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _transcribe_sync, audio_bytes, suffix)
    except Exception as e:
        yield {
            "type": "step",
            "step": AgentStep(
                step=step_counter + 1,
                agent="extraction",
                message=f"Transcription failed: {e}",
            ).model_dump(),
        }
        yield {"type": "transcription", "text": ""}
        return

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
