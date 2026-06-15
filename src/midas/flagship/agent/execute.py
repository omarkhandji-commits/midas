"""Execute an APPROVED gated step.

The Toolset never runs APPROVE-tier callables inline. Once the operator resolves
the approval (CLI / dashboard / channel), this module performs the actual
side-effect and writes a receipt naming the concrete outcome (sha256, cell range,
subprocess exit code). This is the only path through which fs.write, code.run, or
sheet.write actually mutate the world.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from midas.core.approvals.queue import ApprovalRequest, ApprovalStatus
from midas.core.receipts.models import Decision, Taint


def execute_approved_step(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    if request.status != ApprovalStatus.APPROVED:
        raise PermissionError(
            f"approval #{request.id} is {request.status.value}, not approved"
        )
    handler = _HANDLERS.get(request.tool)
    if handler is None:
        raise ValueError(f"no executor registered for tool {request.tool!r}")
    return handler(runtime, request)


# ── concrete handlers ────────────────────────────────────────────────────────


def _execute_fs_write(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    from .tools.fs import execute_fs_write

    payload = request.payload or {}
    path = str(payload.get("path") or "")
    content = payload.get("content") or ""
    plan = execute_fs_write(runtime.fs_guard, path, content)
    out = asdict(plan)
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool="fs.write.executed",
        inputs={"approval_id": request.id, "path": path},
        outputs={
            "path": plan.path,
            "bytes": plan.bytes_len,
            "sha256_new": plan.sha256_new,
            "sha256_prev": plan.sha256_prev,
        },
        decision=Decision.ALLOW,
    )
    return out


def _execute_code_run(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    from .tools.code import CodePlan, execute_code_approved

    payload = request.payload or {}
    plan = CodePlan(
        code=str(payload.get("code") or ""),
        language=str(payload.get("language") or "python"),
        timeout_seconds=float(payload.get("timeout_seconds") or payload.get("timeout") or 10.0),
        code_sha256=str(payload.get("code_sha256") or ""),
        preview=str(payload.get("preview") or ""),
    )
    result = execute_code_approved(runtime.fs_guard, plan)
    runtime.ledger.append(
        run_id=request.run_id,
        agent="execute",
        tool="code.run.executed",
        decision=Decision.ALLOW,
        inputs={"approval_id": request.id, "code_sha256": plan.code_sha256},
        outputs={
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "timed_out": result.timed_out,
            "truncated": result.truncated,
            "stdout_len": len(result.stdout),
            "stderr_len": len(result.stderr),
        },
        taint_out=Taint.UNTRUSTED,  # subprocess output is data, not instructions
    )
    return asdict(result)


def _execute_sheet_write(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    from .tools.sheet import SheetWritePlan, execute_sheet_write

    payload = request.payload or {}
    plan = SheetWritePlan(
        path=str(payload.get("path") or ""),
        sheet_name=str(payload.get("sheet_name") or "Sheet1"),
        cells=[(str(addr), v) for addr, v in (payload.get("cells") or [])],
        sha256_prev=payload.get("sha256_prev"),
    )
    result = execute_sheet_write(runtime.fs_guard, plan)
    runtime.ledger.append(
        run_id=request.run_id,
        agent="execute",
        tool="sheet.write.executed",
        decision=Decision.ALLOW,
        inputs={"approval_id": request.id, "path": plan.path, "sheet": plan.sheet_name},
        outputs={
            "path": result["path"],
            "sheet": result["sheet"],
            "cells_written": result["cells_written"],
            "cell_range": result["cell_range"],
            "sha256_prev": result.get("sha256_prev"),
            "sha256_new": result["sha256_new"],
        },
    )
    return result


_TOOL_TO_KIND = {
    "artifact.text": "text",
    "email.draft": "email",
    "pdf.draft": "pdf",
    "invoice.draft": "invoice",
    "voice.draft": "voice",
    "code.draft": "code",
}


def _execute_artifact(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    from .tools.artifact import execute_artifact

    payload = dict(request.payload or {})
    # Toolset stored the tool's kwargs (path, to, subject, body, ...). The kind is
    # implicit in the tool name — restore it so execute_artifact can rebuild bytes.
    payload.setdefault("kind", _TOOL_TO_KIND.get(request.tool, "text"))
    if request.tool == "invoice.draft":
        from .tools.artifact import _build_invoice_body  # private builder

        body = _build_invoice_body(
            to=str(payload.get("to") or ""),
            items=list(payload.get("items") or []),
            currency=str(payload.get("currency") or "USD"),
            invoice_number=str(payload.get("invoice_number") or ""),
            notes=str(payload.get("notes") or ""),
        )
        payload = {
            "kind": "pdf",
            "path": str(payload.get("path") or ""),
            "title": f"Invoice {payload.get('invoice_number') or ''}".strip() or "Invoice",
            "body": body,
        }
    plan = execute_artifact(runtime.fs_guard, payload)
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool=f"{request.tool}.executed",
        inputs={"approval_id": request.id, "path": plan.path, "kind": plan.kind},
        outputs={
            "path": plan.path,
            "bytes": plan.bytes_len,
            "sha256_new": plan.sha256_new,
            "sha256_prev": plan.sha256_prev,
        },
        decision=Decision.ALLOW,
    )
    return {
        "kind": plan.kind,
        "path": plan.path,
        "bytes_len": plan.bytes_len,
        "sha256_new": plan.sha256_new,
        "sha256_prev": plan.sha256_prev,
    }


_HANDLERS = {
    "fs.write": _execute_fs_write,
    "code.run": _execute_code_run,
    "sheet.write": _execute_sheet_write,
    "artifact.text": _execute_artifact,
    "email.draft": _execute_artifact,
    "pdf.draft": _execute_artifact,
    "invoice.draft": _execute_artifact,
    "voice.draft": _execute_artifact,
    "code.draft": _execute_artifact,
}
