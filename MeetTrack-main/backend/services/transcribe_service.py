import os
import shutil
import whisper

# Load Whisper model (tiny, base, small, medium, large)
# smaller = faster but less accurate
model = whisper.load_model("small")


def _ensure_ffmpeg_available() -> None:
    missing = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if shutil.which("ffprobe") is None:
        missing.append("ffprobe")

    if missing:
        raise EnvironmentError(
            "Missing dependency: {}. "
            "Install ffmpeg and ffprobe and add them to your PATH. "
            "On Windows, download ffmpeg from https://ffmpeg.org/download.html."
            .format(", ".join(missing))
        )


def transcribe_audio(file_path: str) -> str:
    """
    Transcribe audio locally using Whisper.
    """
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    _ensure_ffmpeg_available()

    print("🎙️ Transcribing locally using Whisper...")
    try:
        result = model.transcribe(file_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Whisper failed to load audio. Ensure ffmpeg/ffprobe are installed and available on PATH."
        ) from exc

    return result["text"]