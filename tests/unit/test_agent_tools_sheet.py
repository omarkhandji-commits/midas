"""sheet.read + sheet.write + data extraction (E2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.data import extract_rows, rows_to_cells
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.sheet import (
    _parse_addr,
    execute_sheet_write,
    plan_sheet_write,
    sheet_read,
)


def _g(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def test_parse_addr_basic_and_double_letter() -> None:
    assert _parse_addr("A1") == (1, 1)
    assert _parse_addr("B7") == (2, 7)
    assert _parse_addr("AA10") == (27, 10)


def test_parse_addr_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _parse_addr("1A")
    with pytest.raises(ValueError):
        _parse_addr("")


def test_plan_sheet_write_csv_does_not_touch_disk(tmp_path: Path) -> None:
    plan = plan_sheet_write(
        _g(tmp_path), "out.csv", sheet_name="Sheet1",
        cells=[("A1", "label"), ("B1", 42)],
    )
    assert plan.cell_count == 2
    assert plan.cell_range == "A1:B1"
    assert plan.sha256_prev is None
    assert not (tmp_path / "out.csv").exists()


def test_execute_sheet_write_csv_writes_cells(tmp_path: Path) -> None:
    plan = plan_sheet_write(
        _g(tmp_path), "out.csv", sheet_name="Sheet1",
        cells=[("A1", "label"), ("B1", 42), ("A2", "second"), ("B2", 7.5)],
    )
    result = execute_sheet_write(_g(tmp_path), plan)
    content = (tmp_path / "out.csv").read_text(encoding="utf-8")
    assert "label,42" in content
    assert "second,7.5" in content
    assert result["cells_written"] == 4
    assert result["cell_range"] == "A1:B2"
    assert result["sha256_new"]


def test_sheet_read_csv_returns_matrix(tmp_path: Path) -> None:
    (tmp_path / "in.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    res = sheet_read(_g(tmp_path), "in.csv")
    assert res.rows == [["a", "b"], ["1", "2"]]
    assert res.n_rows == 2
    assert res.n_cols == 2


def test_xlsx_roundtrip_when_openpyxl_present(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    plan = plan_sheet_write(
        _g(tmp_path), "out.xlsx", sheet_name="Data",
        cells=[("A1", "label"), ("B1", 42)],
    )
    execute_sheet_write(_g(tmp_path), plan)
    res = sheet_read(_g(tmp_path), "out.xlsx", sheet_name="Data")
    assert res.rows[0] == ["label", 42]


def test_extract_rows_label_value_pairs() -> None:
    text = """\
Revenue: 1234.56
Cost: -200
Note: not a value
Total : 1034.56
"""
    rows = extract_rows(text)
    labels = {r.label for r in rows}
    assert "Revenue" in labels
    assert "Cost" in labels
    assert "Total" in labels
    # "Note" line is "not a value" → not matched as number, dropped.
    assert "Note" not in labels


def test_extract_rows_dated_amounts() -> None:
    text = "2026-01-15  120.50\n14/02/2026  -45\n"
    rows = extract_rows(text)
    assert any(r.label == "2026-01-15" and r.value == 120.5 for r in rows)
    assert any(r.label == "14/02/2026" and r.value == -45.0 for r in rows)


def test_rows_to_cells_lays_out_columns() -> None:
    cells = rows_to_cells(
        [
            extract_rows("Revenue: 100")[0],
            extract_rows("Cost: 50")[0],
        ],
        start_row=2,
    )
    assert cells[0] == ("A2", "Revenue")
    assert cells[1] == ("B2", 100.0)
    assert cells[2] == ("A3", "Cost")
    assert cells[3] == ("B3", 50.0)
