"""Deterministic data transforms.

Used by ``midas fill`` to turn extracted PDF text into a concrete cell map
*without* an LLM. The operator approves real cells with real values — no model
"interpretation" stage sits between the PDFs and the approval card.

Patterns recognized (intentionally narrow + obvious):
- ``<label>: <number>``                    → ("label", number)
- ``<YYYY-MM-DD>  <amount>``               → ("YYYY-MM-DD", amount)
- ``<DD/MM/YYYY>  <amount>``               → ("DD/MM/YYYY", amount)

Anything that doesn't match is dropped. Better to have the operator add cells
manually than to write garbage to a financial spreadsheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CellAddr = str

_NUMBER = r"-?\d+(?:[,. \s]\d{3})*(?:[.,]\d+)?"

_LABEL_VALUE = re.compile(
    rf"^\s*([A-Za-z][\w \-/']{{1,40}})\s*[:=]\s*(?:\$|€|£)?\s*(?P<num>{_NUMBER})\s*$",
    re.MULTILINE,
)
_DATE_ISO = re.compile(
    rf"^\s*(\d{{4}}-\d{{2}}-\d{{2}})\s+(?:\$|€|£)?\s*(?P<num>{_NUMBER})\s*$",
    re.MULTILINE,
)
_DATE_DMY = re.compile(
    rf"^\s*(\d{{1,2}}/\d{{1,2}}/\d{{4}})\s+(?:\$|€|£)?\s*(?P<num>{_NUMBER})\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ExtractedRow:
    label: str
    value: float | str


def extract_rows(text: str) -> list[ExtractedRow]:
    """Return ordered, deduped rows pulled from a PDF/text body."""
    rows: list[ExtractedRow] = []
    seen: set[tuple[str, str]] = set()
    for regex in (_LABEL_VALUE, _DATE_ISO, _DATE_DMY):
        for match in regex.finditer(text):
            label = match.group(1).strip()
            raw_value = match.group("num").strip()
            value: float | str = _parse_number(raw_value)
            key = (label, str(value))
            if key in seen:
                continue
            seen.add(key)
            rows.append(ExtractedRow(label=label, value=value))
    return rows


def rows_to_cells(
    rows: list[ExtractedRow], *, start_row: int = 1
) -> list[tuple[CellAddr, str | float]]:
    """Map (label, value) pairs into A/B columns starting at row ``start_row``."""
    out: list[tuple[CellAddr, str | float]] = []
    for offset, row in enumerate(rows):
        r = start_row + offset
        out.append((f"A{r}", row.label))
        out.append((f"B{r}", row.value))
    return out


def _parse_number(text: str) -> float | str:
    cleaned = text.replace(" ", "").replace(" ", "").replace(",", ".")
    # Multiple dots means the dots are thousands separators in some locales;
    # collapse all but the last.
    if cleaned.count(".") > 1:
        head, tail = cleaned.rsplit(".", 1)
        cleaned = head.replace(".", "") + "." + tail
    try:
        return float(cleaned)
    except ValueError:
        return text
