"""
Transcription Service — Local Whisper only.

On Render (or any server without Whisper/ffmpeg):
  - Audio upload will return a 503 with a clear message
  - Transcript paste (/process-transcript) works fine — no Whisper needed

To use audio upload locally:
  pip install openai-whisper
  Install ffmpeg and add to PATH
"""
import os
import shutil
import logging

logger = logging.getLogger(__name__)

# Lazy-load whisper — only imported when actually needed
_model = None


def _whisper_available() -> bool:
    """Check if whisper and ffmpeg are both available."""
    try:
        import whisper  # noqa: F401
        return shutil.which("ffmpeg") is not None
    except ImportError:
        return False


def _get_model():
    global _model
    if _model is None:
        import whisper
        logger.info("[Transcribe] Loading Whisper model (small)…")
        _model = whisper.load_model("small")
    return _model


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file using local Whisper.
    Raises RuntimeError with a user-friendly message if Whisper is not available.
    """
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if not _whisper_available():
        raise RuntimeError(
            "Audio transcription is not available on this server. "
            "Please paste your transcript directly using the text input instead."
        )

    logger.info(f"[Transcribe] Transcribing {file_path} with Whisper…")
    model = _get_model()
    result = model.transcribe(file_path)
    text = result["text"]
    logger.info(f"[Transcribe] Done — {len(text)} chars")
    return text
