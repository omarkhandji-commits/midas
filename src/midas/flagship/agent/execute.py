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


def _execute_code_complex(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    """Post-approval Claude Code delegation. Failure is recorded as DENY."""
    from .tools.code_complex import CodeComplexError, execute_code_complex

    payload = request.payload or {}
    try:
        result = execute_code_complex(payload)
    except CodeComplexError as e:
        runtime.append_receipt(
            run_id=request.run_id,
            agent="execute",
            tool="code.complex.failed",
            inputs={"approval_id": request.id},
            outputs={"error": str(e)},
            decision=Decision.DENY,
            taint_out=Taint.UNTRUSTED,
        )
        raise
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool="code.complex.executed",
        inputs={"approval_id": request.id},
        outputs={
            "duration_seconds": result.duration_seconds,
            "exit_code": result.exit_code,
            "truncated": result.truncated,
            "text_len": len(result.text),
        },
        decision=Decision.ALLOW,
        cost_usd=float(result.cost_usd),
        taint_out=Taint.UNTRUSTED,
    )
    return {
        "text": result.text,
        "cost_usd": float(result.cost_usd),
        "duration_seconds": result.duration_seconds,
        "exit_code": result.exit_code,
        "truncated": result.truncated,
    }


def _execute_stripe_payment_link(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    """Post-approval Stripe payment link. Failure is recorded as DENY."""
    from .tools.stripe_pay import StripeBackendError, execute_payment_link

    payload = request.payload or {}
    try:
        result = execute_payment_link(payload)
    except StripeBackendError as e:
        runtime.append_receipt(
            run_id=request.run_id,
            agent="execute",
            tool="stripe.payment_link.failed",
            inputs={"approval_id": request.id},
            outputs={"error": str(e)},
            decision=Decision.DENY,
            taint_out=Taint.UNTRUSTED,
        )
        raise
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool="stripe.payment_link.executed",
        inputs={"approval_id": request.id},
        outputs={
            "payment_link_id": result.payment_link_id,
            "url": result.url,
            "amount_minor": result.amount_minor,
            "currency": result.currency,
            "raw_status": result.raw_status,
        },
        decision=Decision.ALLOW,
        taint_out=Taint.UNTRUSTED,
    )
    return {
        "payment_link_id": result.payment_link_id,
        "url": result.url,
        "amount_minor": result.amount_minor,
        "currency": result.currency,
    }


def _execute_social_publish(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    """Post-approval social publish — calls the platform adapter and records
    a receipt tagged with ``platform`` + ``post_id`` so per-post ROI can join.

    A publish failure is recorded as a DENY receipt with the error class — the
    operator sees in the chain that the attempt happened, the bytes were never
    silently dropped.
    """
    from .tools.social import SocialAdapterError, execute_social_publish

    payload = request.payload or {}
    platform = str(payload.get("platform") or "")
    handle = str(payload.get("account_handle") or "")
    try:
        result = execute_social_publish(payload)
    except SocialAdapterError as e:
        runtime.append_receipt(
            run_id=request.run_id,
            agent="execute",
            tool="social.publish.failed",
            inputs={
                "approval_id": request.id,
                "platform": platform,
                "account_handle": handle,
            },
            outputs={"error": str(e)},
            decision=Decision.DENY,
            taint_out=Taint.UNTRUSTED,
        )
        raise
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool="social.publish.executed",
        inputs={
            "approval_id": request.id,
            "platform": platform,
            "account_handle": handle,
        },
        outputs={
            "platform": platform,
            "post_id": result.post_id,
            "account_handle": handle,
            "permalink": result.permalink,
            "raw_status": result.raw_status,
        },
        decision=Decision.ALLOW,
        cost_usd=float(result.cost_usd),
        taint_out=Taint.UNTRUSTED,
    )
    return {
        "platform": platform,
        "post_id": result.post_id,
        "permalink": result.permalink,
        "cost_usd": float(result.cost_usd),
    }


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


def _execute_json_write(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    """JSON writes route through the generic fs.write executor."""
    return _execute_fs_write(runtime, request)


def _execute_csv_write(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    return _execute_fs_write(runtime, request)


def _execute_docx(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    from .tools.docx import execute_docx

    payload = request.payload or {}
    plan = execute_docx(
        runtime.fs_guard,
        path=str(payload.get("path") or ""),
        title=str(payload.get("title") or "Document"),
        body=str(payload.get("body") or ""),
    )
    runtime.ledger.append(
        run_id=request.run_id,
        agent="execute",
        tool="docx.draft.executed",
        decision=Decision.ALLOW,
        inputs={"approval_id": request.id, "path": plan.path},
        outputs={
            "path": plan.path,
            "bytes": plan.bytes_len,
            "sha256_new": plan.sha256_new,
            "sha256_prev": plan.sha256_prev,
        },
    )
    return {
        "kind": "docx",
        "path": plan.path,
        "bytes_len": plan.bytes_len,
        "sha256_new": plan.sha256_new,
        "sha256_prev": plan.sha256_prev,
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


_CASH_BUILDERS: dict[str, Any] = {}


def _cash_handler(runtime: Any, request: ApprovalRequest) -> dict[str, Any]:
    """Generic post-approval executor for cash-shaped artifacts (WS2).

    Each tool name maps to a builder that re-derives the exact bytes from the
    approval payload. The bytes are then written through the same
    ``execute_fs_write`` chokepoint the rest of the artifact factory uses.
    """
    from .tools.fs import execute_fs_write

    builder = _CASH_BUILDERS.get(request.tool)
    if builder is None:
        raise ValueError(f"no cash builder registered for {request.tool!r}")
    payload = request.payload or {}
    content = builder(payload)
    path = str(payload.get("path") or "")
    plan = execute_fs_write(runtime.fs_guard, path, content)
    runtime.append_receipt(
        run_id=request.run_id,
        agent="execute",
        tool=f"{request.tool}.executed",
        inputs={"approval_id": request.id, "path": plan.path},
        outputs={
            "path": plan.path,
            "bytes": plan.bytes_len,
            "sha256_new": plan.sha256_new,
            "sha256_prev": plan.sha256_prev,
        },
        decision=Decision.ALLOW,
    )
    return {
        "kind": request.tool.split(".")[0],
        "path": plan.path,
        "bytes_len": plan.bytes_len,
        "sha256_new": plan.sha256_new,
        "sha256_prev": plan.sha256_prev,
    }


def _register_cash_builders() -> None:
    from .tools.cash import (
        execute_adcopy,
        execute_landing,
        execute_outreach,
        execute_product,
        execute_proposal,
        execute_quote,
    )
    from .tools.image import execute_image_bytes
    from .tools.voice_synth import execute_voice_bytes

    _CASH_BUILDERS.update(
        {
            "landing.draft": execute_landing,
            "product.draft": execute_product,
            "outreach.sequence": execute_outreach,
            "proposal.draft": execute_proposal,
            "quote.draft": execute_quote,
            "adcopy.draft": execute_adcopy,
            # Image + voice return bytes; execute_fs_write accepts bytes natively.
            "image.draft": execute_image_bytes,
            "voice.synthesize": execute_voice_bytes,
        }
    )


_register_cash_builders()


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
    "json.write": _execute_json_write,
    "csv.write": _execute_csv_write,
    "docx.draft": _execute_docx,
    # Cash-shaped artifacts (WS2) — all go through the same chokepoint.
    "landing.draft": _cash_handler,
    "product.draft": _cash_handler,
    "outreach.sequence": _cash_handler,
    "proposal.draft": _cash_handler,
    "quote.draft": _cash_handler,
    "adcopy.draft": _cash_handler,
    "image.draft": _cash_handler,
    "voice.synthesize": _cash_handler,
    "social.publish": _execute_social_publish,
    "stripe.payment_link": _execute_stripe_payment_link,
    "code.complex": _execute_code_complex,
}
