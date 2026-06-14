"""File export helpers for business assets.

No heavyweight dependency is required for V1. Markdown assets are written as `.md`;
`*_pdf` assets are rendered into a small valid PDF so proposals/devis are real files,
not just strings pretending to be documents.
"""

from __future__ import annotations

from pathlib import Path

from .drafts import AssetSet


def write_asset_files(assets: AssetSet, out_dir: str | Path) -> dict[str, Path]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for key, value in assets.as_dict().items():
        if key.endswith("_pdf"):
            path = root / f"{key}.pdf"
            path.write_bytes(simple_pdf_bytes(key.replace("_", " ").title(), value))
        else:
            path = root / f"{key}.md"
            path.write_text(value, encoding="utf-8")
        written[key] = path
    return written


def simple_pdf_bytes(title: str, body: str) -> bytes:
    lines = [title, ""] + body.splitlines()
    y = 780
    text_ops = ["BT", "/F1 11 Tf", "50 800 Td"]
    first = True
    for raw in lines[:48]:
        line = _escape_pdf(raw[:95])
        if first:
            text_ops.append(f"({line}) Tj")
            first = False
        else:
            y -= 14
            text_ops.append(f"50 {y} Td ({line}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream
        + b"\nendstream",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(sum(len(c) for c in chunks))
        chunks.append(f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref = sum(len(c) for c in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        chunks.append(f"{off:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return b"".join(chunks)


def _escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
