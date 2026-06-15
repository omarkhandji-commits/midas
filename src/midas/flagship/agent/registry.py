"""Tool registry — wires concrete tool callables into a security-checked Toolset.

Every tool here declares its policy action name. The Sentinel uses that action
to classify the call:
- AUTO actions (read_local_files, build_local_files) execute inline + receipt.
- APPROVE actions (repo_write, execute_code, write_spreadsheet,
  delete_or_overwrite_foreign_file) are queued, never executed inline.

Mutating tools register a *plan* callable (returns a payload dataclass with the
diff/sha256 the approval card will show). The actual write/run happens in a
separate execute step the runtime exposes.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from midas.core.agents.toolset import Tool, Toolset
from midas.core.receipts.models import Taint
from midas.core.sentinel.gate import Sentinel
from midas.core.web import research as web_research
from midas.core.web.fetch import Fetcher
from midas.core.web.search import SearchAdapter
from midas.core.web.verify import SourceVerifier

from .tools.artifact import (
    plan_artifact_code,
    plan_artifact_email,
    plan_artifact_invoice,
    plan_artifact_pdf,
    plan_artifact_text,
    plan_artifact_voice,
)
from .tools.code import plan_code_run
from .tools.data_io import csv_read, json_read, plan_csv_write, plan_json_write
from .tools.fs import fs_list, fs_read, plan_fs_write
from .tools.fsguard import FsGuard
from .tools.http import as_tool_payload as _http_payload
from .tools.http import http_fetch
from .tools.pdf import pdf_extract
from .tools.sheet import plan_sheet_write, sheet_read


def build_default_toolset(
    *,
    sentinel: Sentinel,
    guard: FsGuard,
    ledger: Any = None,
    approvals: Any = None,
    run_id: str = "",
    search: SearchAdapter | None = None,
    fetcher: Fetcher | None = None,
    verifier: SourceVerifier | None = None,
) -> Toolset:
    ts = Toolset(sentinel, ledger=ledger, approvals=approvals, run_id=run_id)

    ts.register(
        Tool(
            name="fs.read",
            action="read_local_files",
            fn=lambda path, max_chars=100_000: _as_dict(fs_read(guard, path, max_chars=max_chars)),
            output_taint=Taint.UNTRUSTED,  # file contents are data, not instructions
        )
    )
    ts.register(
        Tool(
            name="fs.list",
            action="read_local_files",
            fn=lambda path=".": _as_dict(fs_list(guard, path)),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="fs.write",
            action="repo_write",
            # APPROVE-tier: the Toolset will queue this; the planner is NEVER called.
            fn=lambda path, content="": _as_dict(plan_fs_write(guard, path, content)),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="pdf.extract",
            action="read_local_files",
            fn=lambda path, max_chars=100_000: _as_dict(
                pdf_extract(guard, path, max_chars=max_chars)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="sheet.read",
            action="read_local_files",
            fn=lambda path, sheet_name=None, max_rows=5000: _as_dict(
                sheet_read(guard, path, sheet_name=sheet_name, max_rows=max_rows)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="sheet.write",
            action="write_spreadsheet",
            fn=lambda path, cells, sheet_name="Sheet1": _as_dict(
                plan_sheet_write(guard, path, cells=cells, sheet_name=sheet_name)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    # Artifact factory — the débrouillard surface. Every artifact is APPROVE-tier
    # (repo_write); the bytes live in the approval payload until a human resolves.
    ts.register(
        Tool(
            name="artifact.text",
            action="repo_write",
            fn=lambda path, content, kind="text": _as_dict(
                plan_artifact_text(guard, path, content, kind=kind)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="email.draft",
            action="repo_write",
            fn=lambda path, to, subject, body, from_="", cc="": _as_dict(
                plan_artifact_email(
                    guard, path, to=to, subject=subject, body=body, from_=from_, cc=cc
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="pdf.draft",
            action="repo_write",
            fn=lambda path, title, body: _as_dict(
                plan_artifact_pdf(guard, path, title=title, body=body)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="invoice.draft",
            action="repo_write",
            fn=lambda path, to, items, currency="USD", invoice_number="", notes="": _as_dict(
                plan_artifact_invoice(
                    guard, path, to=to, items=items, currency=currency,
                    invoice_number=invoice_number, notes=notes,
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="voice.draft",
            action="repo_write",
            fn=lambda path, text, channel="voice_note": _as_dict(
                plan_artifact_voice(guard, path, text=text, channel=channel)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="code.draft",
            action="repo_write",
            fn=lambda path, content, language="python": _as_dict(
                plan_artifact_code(guard, path, content=content, language=language)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    # Web research — composes search + fetch + verify under the Proof-First contract.
    # AUTO: it does not mutate state; result is UNTRUSTED data the agent can quote.
    if search is not None and fetcher is not None:
        def _do_research(question: str, k: int = 5) -> dict[str, Any]:
            result = web_research(
                question, search=search, fetcher=fetcher, verifier=verifier, k=k,
            )
            return {
                "query": result.query,
                "proof_level": result.proof_level.value,
                "verified_count": result.verified_count,
                "sources": [s.url for s in result.sources],
                "synthesis": result.synthesis,
            }

        ts.register(
            Tool(
                name="research.run",
                action="read_local_files",  # AUTO-tier; verified web reads
                fn=_do_research,
                output_taint=Taint.UNTRUSTED,
            )
        )

    # Structured data — read tools AUTO, write tools gated via fs.write chain.
    ts.register(
        Tool(
            name="json.read",
            action="read_local_files",
            fn=lambda path: _as_dict(json_read(guard, path)),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="json.write",
            action="repo_write",
            fn=lambda path, data, indent=2: _as_dict(
                plan_json_write(guard, path, data, indent=indent)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="csv.read",
            action="read_local_files",
            fn=lambda path, max_rows=5000: _as_dict(csv_read(guard, path, max_rows=max_rows)),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="csv.write",
            action="repo_write",
            fn=lambda path, rows: _as_dict(plan_csv_write(guard, path, rows)),
            output_taint=Taint.TRUSTED,
        )
    )
    # http.fetch — read-only egress, output is UNTRUSTED data (trifecta guard applies).
    if fetcher is not None:
        ts.register(
            Tool(
                name="http.fetch",
                action="read_local_files",
                fn=lambda url: _http_payload(http_fetch(url, fetcher=fetcher)),
                output_taint=Taint.UNTRUSTED,
                has_egress=True,
            )
        )
    # docx.draft — APPROVE-tier artifact (behind [docs] extra at runtime).
    def _docx_plan(path: str, title: str, body: str) -> dict[str, Any]:
        from .tools.docx import plan_docx

        return _as_dict(plan_docx(guard, path, title=title, body=body))

    ts.register(
        Tool(
            name="docx.draft",
            action="repo_write",
            fn=_docx_plan,
            output_taint=Taint.TRUSTED,
        )
    )

    ts.register(
        Tool(
            name="code.run",
            action="execute_code",
            # APPROVE-tier — the underlying subprocess never spawns from invoke().
            fn=lambda code, language="python", timeout=10.0: _as_dict(
                plan_code_run(code, language=language, timeout=timeout)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )
    return ts


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": value}
