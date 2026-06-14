"""Safe local multimodal inspection.

No external model call happens here. Optional libraries can improve extraction, but the
fallback path still records type, size, hash, and safe warnings.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


@dataclass(frozen=True)
class MediaInspection:
    path: str
    kind: str
    size_bytes: int
    sha256: str
    text: str
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_media(path: str | Path, *, max_text_chars: int = 20_000) -> MediaInspection:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise ValueError("media path must be an existing file")
    suffix = p.suffix.lower()
    data = p.read_bytes()
    warnings: list[str] = []
    text = ""

    if suffix in TEXT_EXTENSIONS:
        text = p.read_text(encoding="utf-8", errors="replace")[:max_text_chars]
        kind = "text"
    elif suffix in PDF_EXTENSIONS:
        kind = "pdf"
        text, warnings = _extract_pdf_text(p, max_text_chars=max_text_chars)
    elif suffix in IMAGE_EXTENSIONS:
        kind = "image"
        text, warnings = _inspect_image(p)
    elif suffix in AUDIO_EXTENSIONS:
        kind = "audio"
        text, warnings = _read_transcript_sidecar(p, "audio")
    elif suffix in VIDEO_EXTENSIONS:
        kind = "video"
        text, warnings = _read_transcript_sidecar(p, "video")
    else:
        kind = "unknown"
        warnings.append("unknown media type; no content extraction attempted")

    return MediaInspection(
        path=str(p),
        kind=kind,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        text=text,
        warnings=warnings,
    )


def _extract_pdf_text(path: Path, *, max_text_chars: int) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", ["install optional PDF extractor dependency to extract PDF text"]

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
        if sum(len(c) for c in chunks) >= max_text_chars:
            break
    return "\n".join(chunks)[:max_text_chars], []


def _inspect_image(path: Path) -> tuple[str, list[str]]:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return "", ["install Pillow/OCR adapter to inspect image dimensions or extract text"]
    with Image.open(path) as img:
        return f"image {img.size[0]}x{img.size[1]} mode={img.mode}", [
            "OCR not enabled; image text was not extracted"
        ]


def _read_transcript_sidecar(path: Path, kind: str) -> tuple[str, list[str]]:
    for suffix in (".txt", ".vtt", ".srt"):
        sidecar = path.with_suffix(path.suffix + suffix)
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8", errors="replace")[:20_000], []
    return "", [f"{kind} transcription requires a sidecar transcript or an optional STT adapter"]
