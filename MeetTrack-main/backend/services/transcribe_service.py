"""
Transcription Service
=====================
Local dev  → uses openai-whisper (requires ffmpeg)
Production → uses AWS Transcribe (set USE_AWS_TRANSCRIBE=true in env)

On Render, whisper is NOT installed. Set USE_AWS_TRANSCRIBE=true and
configure AWS credentials to use the cloud transcription path.
"""
import os
import shutil
import logging
import time
import boto3

logger = logging.getLogger(__name__)

# ── lazy-load whisper only when needed ───────────────────────
_whisper_model = None

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            _whisper_model = whisper.load_model("small")
        except ImportError:
            raise RuntimeError(
                "openai-whisper is not installed. "
                "Set USE_AWS_TRANSCRIBE=true to use AWS Transcribe instead, "
                "or install whisper locally: pip install openai-whisper"
            )
    return _whisper_model


def _ensure_ffmpeg_available() -> None:
    missing = [b for b in ("ffmpeg", "ffprobe") if shutil.which(b) is None]
    if missing:
        raise EnvironmentError(
            f"Missing: {', '.join(missing)}. Install ffmpeg and add it to PATH."
        )


# ── AWS Transcribe path ───────────────────────────────────────

def _transcribe_with_aws(file_path: str) -> str:
    """Upload file to S3 and transcribe via AWS Transcribe."""
    import uuid

    bucket   = os.getenv("TRANSCRIBE_BUCKET")
    region   = os.getenv("AWS_REGION", "ap-south-1")
    key_id   = os.getenv("AWS_ACCESS_KEY_ID")
    secret   = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not bucket:
        raise EnvironmentError("TRANSCRIBE_BUCKET env var not set")

    job_name = f"meettrack-{uuid.uuid4().hex[:12]}"
    s3_key   = f"uploads/{os.path.basename(file_path)}"
    s3_uri   = f"s3://{bucket}/{s3_key}"

    s3 = boto3.client("s3", region_name=region,
                      aws_access_key_id=key_id,
                      aws_secret_access_key=secret)
    transcribe = boto3.client("transcribe", region_name=region,
                              aws_access_key_id=key_id,
                              aws_secret_access_key=secret)

    logger.info(f"[Transcribe] Uploading {file_path} → s3://{bucket}/{s3_key}")
    s3.upload_file(file_path, bucket, s3_key)

    logger.info(f"[Transcribe] Starting AWS Transcribe job: {job_name}")
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat=file_path.rsplit(".", 1)[-1].lower() or "mp3",
        LanguageCode="en-US",
    )

    # Poll until complete (max 10 min)
    for _ in range(120):
        status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        state  = status["TranscriptionJob"]["TranscriptionJobStatus"]
        if state == "COMPLETED":
            transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            import urllib.request, json as _json
            with urllib.request.urlopen(transcript_uri) as r:
                data = _json.loads(r.read())
            text = data["results"]["transcripts"][0]["transcript"]
            logger.info(f"[Transcribe] AWS job complete: {len(text)} chars")
            return text
        if state == "FAILED":
            raise RuntimeError(f"AWS Transcribe job failed: {job_name}")
        time.sleep(5)

    raise TimeoutError(f"AWS Transcribe job timed out: {job_name}")


# ── public entry point ────────────────────────────────────────

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file.
    Automatically chooses AWS Transcribe (production) or local Whisper (dev)
    based on the USE_AWS_TRANSCRIBE environment variable.
    """
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    use_aws = os.getenv("USE_AWS_TRANSCRIBE", "false").lower() in ("true", "1", "yes")

    if use_aws:
        logger.info("[Transcribe] Using AWS Transcribe")
        return _transcribe_with_aws(file_path)

    # Local Whisper
    logger.info("[Transcribe] Using local Whisper")
    _ensure_ffmpeg_available()
    model = _get_whisper_model()
    result = model.transcribe(file_path)
    return result["text"]
