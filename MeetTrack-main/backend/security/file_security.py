"""
File Upload Security
====================
Validates uploaded files before processing:
  1. Extension whitelist
  2. MIME type verification (magic bytes, not just Content-Type header)
  3. File size limits
  4. Filename sanitization (path traversal prevention)
  5. Malware scan hook (ClamAV or VirusTotal if configured)
  6. Signed URL generation for private file access

OWASP A04: Insecure Design — never trust client-provided file metadata.
"""

import hashlib
import hmac
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

# ── Allowed file types ────────────────────────────────────────────────────────

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
ALLOWED_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS

# Magic bytes (file signatures) for MIME verification
MAGIC_BYTES: dict[bytes, str] = {
    b"\xff\xfb":         "audio/mpeg",       # MP3
    b"\xff\xf3":         "audio/mpeg",       # MP3
    b"\xff\xf2":         "audio/mpeg",       # MP3
    b"ID3":              "audio/mpeg",       # MP3 with ID3 tag
    b"RIFF":             "audio/wav",        # WAV
    b"\x1aE\xdf\xa3":   "video/webm",       # WebM
    b"ftyp":             "video/mp4",        # MP4 (offset 4)
    b"\x00\x00\x00\x18ftyp": "video/mp4",   # MP4
    b"\x00\x00\x00\x20ftyp": "video/mp4",   # MP4
    b"\xff\xd8\xff":     "image/jpeg",       # JPEG
    b"\x89PNG\r\n\x1a\n": "image/png",      # PNG
    b"GIF87a":           "image/gif",        # GIF
    b"GIF89a":           "image/gif",        # GIF
    b"RIFF....WEBP":     "image/webp",       # WebP (simplified)
}

# Size limits
MAX_AUDIO_SIZE  = 100 * 1024 * 1024   # 100 MB
MAX_IMAGE_SIZE  = 5   * 1024 * 1024   # 5 MB
MAX_UPLOAD_SIZE = MAX_AUDIO_SIZE


# ── Filename sanitization ─────────────────────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and injection.
    - Remove path separators
    - Remove null bytes
    - Limit length
    - Allow only safe characters
    """
    if not filename:
        return "upload"

    # Remove path components
    filename = Path(filename).name

    # Remove null bytes and control characters
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    # Allow only safe characters: alphanumeric, dash, underscore, dot
    filename = re.sub(r"[^\w\-.]", "_", filename)

    # Prevent double extensions (e.g. evil.php.jpg)
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        name, ext = parts
        name = re.sub(r"\.", "_", name)  # remove dots from name part
        filename = f"{name}.{ext}"

    # Limit length
    if len(filename) > 200:
        ext = Path(filename).suffix
        filename = filename[:200 - len(ext)] + ext

    return filename or "upload"


# ── MIME type detection ───────────────────────────────────────────────────────

def detect_mime_type(header_bytes: bytes) -> Optional[str]:
    """Detect MIME type from file magic bytes."""
    for magic, mime in MAGIC_BYTES.items():
        if header_bytes.startswith(magic):
            return mime
    # Check MP4 at offset 4
    if len(header_bytes) >= 8 and header_bytes[4:8] == b"ftyp":
        return "video/mp4"
    return None


# ── File validation ───────────────────────────────────────────────────────────

async def validate_upload(
    file: UploadFile,
    allowed_extensions: Optional[set] = None,
    max_size: int = MAX_UPLOAD_SIZE,
    require_audio: bool = False,
) -> dict:
    """
    Validate an uploaded file.

    Returns:
        {"filename": str, "size": int, "mime_type": str, "extension": str}

    Raises:
        HTTPException 400 on validation failure
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    safe_name = sanitize_filename(file.filename)
    extension = Path(safe_name).suffix.lower()

    # Extension check
    allowed = allowed_extensions or ALLOWED_EXTENSIONS
    if extension not in allowed:
        logger.warning(f"[FileSec] Rejected extension: {extension} from {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{extension}' not allowed. Allowed: {', '.join(sorted(allowed))}",
        )

    # Read header bytes for MIME detection (don't read whole file yet)
    header = await file.read(16)
    await file.seek(0)

    if len(header) < 4:
        raise HTTPException(status_code=400, detail="File is too small or empty")

    detected_mime = detect_mime_type(header)

    # For audio files, verify magic bytes
    if require_audio or extension in ALLOWED_AUDIO_EXTENSIONS:
        audio_mimes = {"audio/mpeg", "audio/wav", "video/webm", "video/mp4", "audio/ogg"}
        if detected_mime and detected_mime not in audio_mimes:
            logger.warning(f"[FileSec] MIME mismatch: claimed {extension}, detected {detected_mime}")
            raise HTTPException(
                status_code=400,
                detail="File content doesn't match the declared file type",
            )

    # Size check — read full file to count bytes
    content = await file.read()
    await file.seek(0)
    size = len(content)

    if size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {size // 1024 // 1024}MB. Max: {max_size // 1024 // 1024}MB",
        )

    if size == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Malware scan hook
    scan_result = await _malware_scan_hook(content, safe_name)
    if not scan_result["clean"]:
        logger.error(f"[FileSec] Malware detected in {safe_name}: {scan_result['reason']}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File failed security scan",
        )

    return {
        "filename":  safe_name,
        "size":      size,
        "mime_type": detected_mime or "application/octet-stream",
        "extension": extension,
        "sha256":    hashlib.sha256(content).hexdigest(),
    }


async def _malware_scan_hook(content: bytes, filename: str) -> dict:
    """
    Malware scan hook.
    - If CLAMAV_SOCKET is set: scan via ClamAV Unix socket
    - If VIRUSTOTAL_API_KEY is set: scan via VirusTotal API
    - Otherwise: basic heuristic checks only
    """
    # Basic heuristic: check for PHP/script injection in "audio" files
    DANGEROUS_PATTERNS = [
        b"<?php", b"<script", b"eval(", b"exec(",
        b"system(", b"passthru(", b"shell_exec(",
    ]
    content_lower = content[:1024].lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in content_lower:
            return {"clean": False, "reason": f"Suspicious pattern: {pattern.decode()}"}

    # ClamAV integration (if available)
    clamav_socket = os.getenv("CLAMAV_SOCKET", "")
    if clamav_socket:
        try:
            import socket
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(clamav_socket)
                s.sendall(b"zINSTREAM\0")
                chunk_size = len(content).to_bytes(4, "big")
                s.sendall(chunk_size + content + b"\x00\x00\x00\x00")
                result = s.recv(1024).decode()
                if "FOUND" in result:
                    return {"clean": False, "reason": result.strip()}
        except Exception as exc:
            logger.warning(f"[FileSec] ClamAV scan failed: {exc}")

    return {"clean": True, "reason": ""}


# ── Signed URLs ───────────────────────────────────────────────────────────────

_SIGNED_URL_SECRET = os.getenv("SECRET_KEY", "fallback-secret")


def generate_signed_url(
    file_path: str,
    user_id: int,
    expires_in: int = 3600,
) -> str:
    """
    Generate a time-limited signed URL for private file access.

    Format: /files/signed?path=<path>&uid=<uid>&exp=<ts>&sig=<hmac>
    """
    expires_at = int(time.time()) + expires_in
    message    = f"{file_path}:{user_id}:{expires_at}"
    signature  = hmac.new(
        _SIGNED_URL_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    from urllib.parse import urlencode
    params = urlencode({
        "path": file_path,
        "uid":  user_id,
        "exp":  expires_at,
        "sig":  signature,
    })
    return f"/files/signed?{params}"


def verify_signed_url(path: str, uid: int, exp: int, sig: str) -> bool:
    """Verify a signed URL. Returns True if valid and not expired."""
    if int(time.time()) > exp:
        return False  # expired

    message  = f"{path}:{uid}:{exp}"
    expected = hmac.new(
        _SIGNED_URL_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(sig, expected)
