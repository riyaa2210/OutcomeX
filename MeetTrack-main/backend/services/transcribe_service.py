"""
Transcription Service
=====================
Sends audio to an external Colab Whisper API for transcription.
Local Whisper is NOT used — Render cannot run it (no GPU / low RAM).

Environment variable required:
    COLAB_API_URL  — your ngrok/localtunnel URL from Google Colab
                     e.g. https://xxxx.ngrok-free.app
                     or   https://xxxx.loca.lt

The Colab Flask API must expose:
    POST /transcribe  — accepts multipart file, returns {"transcription": "..."}
    GET  /health      — returns {"status": "ok"}
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

# ── Read Colab URL from environment ──────────────────────────
def _get_colab_url() -> str:
    url = (
        os.getenv("COLAB_API_URL", "")        # primary key
        or os.getenv("COLAB_WHISPER_URL", "")  # legacy fallback
    ).rstrip("/")
    return url


def transcribe_audio(file_path: str) -> str:
    """
    Send an audio file to the Colab Whisper API and return the transcription.

    Args:
        file_path: absolute path to the audio file on disk

    Returns:
        Transcribed text string

    Raises:
        RuntimeError: with a user-friendly message on any failure
    """
    colab_url = _get_colab_url()

    # ── Guard: env var must be set ────────────────────────────
    if not colab_url:
        logger.error("[Transcribe] COLAB_API_URL / COLAB_WHISPER_URL not set in environment")
        raise RuntimeError(
            "Audio transcription is not configured. "
            "Set COLAB_API_URL in your Render environment variables "
            "to your running Colab Whisper server URL."
        )

    # ── Guard: file must exist ────────────────────────────────
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    endpoint = f"{colab_url}/transcribe"
    filename  = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    logger.info(f"[Transcribe] Sending '{filename}' ({file_size} bytes) → {endpoint}")
    print(f"[Transcribe] DEBUG — calling: {endpoint}")  # visible in Render logs

    # ── Call Colab API ────────────────────────────────────────
    try:
        with open(file_path, "rb") as audio_file:
            response = requests.post(
                endpoint,
                files={"file": (filename, audio_file, "audio/mpeg")},
                headers={
                    "bypass-tunnel-reminder": "true",
                    "ngrok-skip-browser-warning": "true",
                    "User-Agent": "MeetTrack-Backend/1.0",
                },
                timeout=300,
                verify=True,
            )

        logger.info(f"[Transcribe] Response status: {response.status_code}")

        # ── Handle non-2xx ────────────────────────────────────
        if not response.ok:
            try:
                err_detail = response.json().get("error", response.text[:200])
            except Exception:
                err_detail = response.text[:200]

            logger.error(f"[Transcribe] Colab API error {response.status_code}: {err_detail}")
            raise RuntimeError(
                f"Colab Whisper API returned error {response.status_code}: {err_detail}"
            )

        # ── Parse response ────────────────────────────────────
        try:
            data = response.json()
        except Exception:
            logger.error(f"[Transcribe] Invalid JSON response: {response.text[:200]}")
            raise RuntimeError("Colab Whisper API returned invalid JSON response.")

        transcription = data.get("transcription") or data.get("text") or ""

        if not transcription:
            logger.warning(f"[Transcribe] Empty transcription in response: {data}")
            raise RuntimeError(
                "Colab Whisper API returned an empty transcription. "
                "Check that the audio file contains speech."
            )

        logger.info(f"[Transcribe] ✅ Success — {len(transcription)} chars transcribed")
        return transcription

    # ── Network error handling ────────────────────────────────
    except requests.exceptions.Timeout:
        logger.error(f"[Transcribe] Timeout after 300s calling {endpoint}")
        raise RuntimeError(
            "Colab Whisper API timed out (5 min limit). "
            "Try a shorter audio file, or switch to the 'tiny' Whisper model in Colab."
        )

    except requests.exceptions.ConnectionError as exc:
        logger.error(f"[Transcribe] Connection error: {exc}")
        raise RuntimeError(
            "Cannot connect to Colab Whisper server. "
            "Make sure your Colab notebook is running and the tunnel URL is correct. "
            f"Current URL: {colab_url}"
        )

    except requests.exceptions.RequestException as exc:
        logger.error(f"[Transcribe] Request error: {exc}")
        raise RuntimeError(f"Network error calling Colab Whisper API: {exc}")

    except RuntimeError:
        raise  # re-raise our own errors unchanged

    except Exception as exc:
        logger.error(f"[Transcribe] Unexpected error: {exc}")
        raise RuntimeError(f"Unexpected transcription error: {exc}")
