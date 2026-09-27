"""
Transcription Service
=====================
Supports two transcription backends, controlled by env vars:

1. LOCAL  (USE_LOCAL_WHISPER=true)
   Uses faster-whisper running in-process.
   Model is downloaded once to ~/.cache/huggingface on first use.
   Model size controlled by WHISPER_MODEL_SIZE (default: base).
   Supported sizes: tiny, base, small, medium, large-v2, large-v3

2. COLAB  (USE_LOCAL_WHISPER=false, default)
   Sends audio to an external Colab Whisper API via HTTP.
   Requires COLAB_API_URL env var pointing to your ngrok/localtunnel URL.

For local dev with no GPU, use model_size=tiny or base (CPU is fine).
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
USE_LOCAL_WHISPER  = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

# ── Cache loaded model (singleton) ────────────────────────────────────────────
_whisper_model = None


def _get_local_model():
    """Load and cache the faster-whisper model (loads once, reused after)."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
        logger.info(f"[Transcribe] Loading local Whisper model '{WHISPER_MODEL_SIZE}' on CPU…")
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",   # int8 is fastest on CPU, good quality
        )
        logger.info("[Transcribe] Local Whisper model loaded.")
        return _whisper_model
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Run: pip install faster-whisper"
        )


def _transcribe_local(file_path: str) -> str:
    """Transcribe using local faster-whisper."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    model = _get_local_model()
    logger.info(f"[Transcribe] Local: transcribing '{file_path}'…")

    segments, info = model.transcribe(
        file_path,
        beam_size=5,
        language=None,    # auto-detect
        vad_filter=True,  # skip silent parts — much faster
    )
    logger.info(f"[Transcribe] Detected language: {info.language} ({info.language_probability:.2f})")

    text = " ".join(seg.text.strip() for seg in segments).strip()
    if not text:
        raise RuntimeError(
            "Local Whisper returned an empty transcription. "
            "Check the audio file contains speech."
        )
    logger.info(f"[Transcribe] Local done — {len(text)} chars")
    return text


def _transcribe_colab(file_path: str) -> str:
    """Transcribe via remote Colab Whisper API."""
    import requests

    colab_url = (
        os.getenv("COLAB_API_URL", "")
        or os.getenv("COLAB_WHISPER_URL", "")
    ).rstrip("/")

    if not colab_url:
        raise RuntimeError(
            "Audio transcription is not configured. "
            "Either set USE_LOCAL_WHISPER=true (for local Whisper), "
            "or set COLAB_API_URL to your running Colab Whisper server URL."
        )
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    endpoint = f"{colab_url}/transcribe"
    filename  = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    logger.info(f"[Transcribe] Colab: sending '{filename}' ({file_size} bytes) → {endpoint}")

    try:
        with open(file_path, "rb") as audio_file:
            response = requests.post(
                endpoint,
                files={"file": (filename, audio_file, "audio/mpeg")},
                headers={
                    "bypass-tunnel-reminder":      "true",
                    "ngrok-skip-browser-warning":  "69420",
                    "User-Agent":                  "python-requests/2.28.0",
                },
                timeout=300,
                verify=True,
            )

        if not response.ok:
            try:
                err = response.json().get("error", response.text[:200])
            except Exception:
                err = response.text[:200]
            raise RuntimeError(f"Colab API returned {response.status_code}: {err}")

        try:
            data = response.json()
        except Exception:
            raise RuntimeError("Colab API returned invalid JSON.")

        text = data.get("transcription") or data.get("text") or ""
        if not text:
            raise RuntimeError("Colab API returned an empty transcription.")

        logger.info(f"[Transcribe] Colab done — {len(text)} chars")
        return text

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "Colab Whisper API timed out (5 min). "
            "Try a shorter file, or switch to the 'tiny' model in Colab."
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Cannot connect to Colab Whisper server at {colab_url}. "
            "Make sure your Colab notebook is running."
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Network error: {exc}")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Unexpected transcription error: {exc}")


# ── Public API ─────────────────────────────────────────────────────────────────

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file.

    Routing:
      USE_LOCAL_WHISPER=true  → local faster-whisper (CPU, no external service)
      USE_LOCAL_WHISPER=false → remote Colab Whisper API (requires COLAB_API_URL)
    """
    if USE_LOCAL_WHISPER:
        logger.info("[Transcribe] Using local faster-whisper")
        return _transcribe_local(file_path)
    else:
        logger.info("[Transcribe] Using remote Colab Whisper API")
        return _transcribe_colab(file_path)
