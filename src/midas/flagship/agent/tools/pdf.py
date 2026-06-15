"""PDF extraction tool — reuses the existing `multimodal.inspect_media` machinery.

AUTO tier (`read_local_files`): reading a local PDF is not risky. The result is
treated as UNTRUSTED data (the trifecta guard prevents combining PDF content with
private + egress in one step).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from midas.flagship.multimodal import inspect_media

from .fsguard import FsGuard


@dataclass(frozen=True)
class PdfExtractResult:
    path: str
    size_bytes: int
    sha256: str
    text: str
    warnings: list[str]


def pdf_extract(guard: FsGuard, path: str, *, max_chars: int = 100_000) -> PdfExtractResult:
    target = guard.resolve(path, must_exist=True)
    inspection = inspect_media(target, max_text_chars=max_chars)
    return PdfExtractResult(
        path=str(Path(inspection.path)),
        size_bytes=inspection.size_bytes,
        sha256=inspection.sha256,
        text=inspection.text,
        warnings=list(inspection.warnings),
    )
