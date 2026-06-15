"""Auto-skills — propose reusable skills from multi-step receipt sequences.

When MIDAS completes a 3+ step task, this module turns the receipt sequence into a
draft skill proposal. Local-only sequences (all steps ALLOWed without external taint)
may be silently auto-created as drafts; anything touching the network or external
sources is queued for human approval via the existing ApprovalQueue.

Tool discovery (when a referenced tool is missing) is **multi-source**: PyPI, npm,
crates.io, GitHub, MCP registry, docs sites — never GitHub-only. Discovered candidates
become approval-gated `plan_install` requests; nothing is downloaded or executed
without explicit human consent. Approval-default holds.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from midas.core.approvals.queue import ApprovalQueue, ApprovalRequest
from midas.core.receipts.ledger import ReceiptLedger
from midas.core.receipts.models import Decision, Taint, utcnow_iso
from midas.core.web.search import SearchAdapter, SearchHit

from .skills import SkillManifest, SkillRegistry, is_remote_skill_source

PROPOSAL_VERSION = 1
MIN_SEQUENCE_STEPS = 3

DEFAULT_DISCOVERY_SOURCES: tuple[str, ...] = (
    "pypi.org",
    "registry.npmjs.org",
    "crates.io",
    "github.com",
    "mcp.so",
    "modelcontextprotocol.io",
)


@dataclass
class SkillProposal:
    """A draft skill, derived from a completed multi-step run."""

    proposal_id: str
    run_id: str
    name: str
    summary: str
    steps: list[dict[str, str]]
    local_only: bool
    status: str = "pending"  # pending | accepted | discarded
    created_ts: str = field(default_factory=utcnow_iso)
    skill_name: str | None = None  # set once accepted + registry.create() runs


@dataclass
class ToolCandidate:
    """A discovered remote tool candidate, awaiting approval before install."""

    source: str  # pypi.org / registry.npmjs.org / etc.
    title: str
    url: str
    snippet: str


class AutoSkillsStore:
    """JSON-backed store of proposals (file, not SQLite — proposals are small)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[SkillProposal]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [SkillProposal(**row) for row in raw]

    def upsert(self, proposal: SkillProposal) -> None:
        rows = [p for p in self.all() if p.proposal_id != proposal.proposal_id]
        rows.append(proposal)
        self.path.write_text(
            json.dumps([asdict(p) for p in rows], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, proposal_id: str) -> SkillProposal | None:
        for p in self.all():
            if p.proposal_id == proposal_id:
                return p
        return None

    def pending(self) -> list[SkillProposal]:
        return [p for p in self.all() if p.status == "pending"]


class AutoSkills:
    """Detect multi-step sequences and produce approval-gated skill proposals."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        ledger: ReceiptLedger,
        queue: ApprovalQueue,
        store: AutoSkillsStore,
        search: SearchAdapter | None = None,
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._queue = queue
        self._store = store
        self._search = search

    # ------------------------------------------------------------------ detect

    def detect(self, *, min_steps: int = MIN_SEQUENCE_STEPS) -> list[SkillProposal]:
        """Walk the ledger, group by run_id, propose drafts for new sequences."""
        runs: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for receipt in self._ledger:
            body = receipt.body
            runs.setdefault(body.run_id, []).append(
                {
                    "tool": body.tool,
                    "agent": body.agent,
                    "decision": body.decision.value,
                    "taint_in": body.taint_in.value,
                    "taint_out": body.taint_out.value,
                    "ts": body.ts,
                }
            )

        existing = {p.run_id for p in self._store.all()}
        proposals: list[SkillProposal] = []
        for run_id, steps in runs.items():
            if run_id in existing:
                continue
            if not _is_completed_sequence(steps, min_steps=min_steps):
                continue
            local_only = all(
                step["decision"] == Decision.ALLOW.value
                and step["taint_in"] in {Taint.TRUSTED.value, Taint.PRIVATE.value}
                and step["taint_out"] in {Taint.TRUSTED.value, Taint.PRIVATE.value}
                for step in steps
            )
            proposal = SkillProposal(
                proposal_id=f"asp-{run_id}",
                run_id=run_id,
                name=_propose_name(steps),
                summary=_propose_summary(steps),
                steps=[{"tool": s["tool"], "decision": s["decision"]} for s in steps],
                local_only=local_only,
            )
            self._store.upsert(proposal)
            proposals.append(proposal)
        return proposals

    # ------------------------------------------------------------------ accept

    def accept(self, proposal_id: str) -> SkillManifest:
        proposal = self._store.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        if proposal.status != "pending":
            raise ValueError(f"proposal already {proposal.status}")
        if not proposal.local_only:
            # Non-local proposals must clear an approval first.
            raise PermissionError(
                "non-local proposals must clear an approval queue before accept"
            )
        manifest = self._registry.create(name=proposal.name, summary=proposal.summary)
        proposal.status = "accepted"
        proposal.skill_name = manifest.name
        self._store.upsert(proposal)
        self._ledger.append(
            run_id=proposal.run_id,
            agent="autoskills",
            tool="autoskills.accept",
            decision=Decision.ALLOW,
            inputs={"proposal_id": proposal_id},
            outputs={"skill": manifest.name},
        )
        return manifest

    def discard(self, proposal_id: str, *, reason: str = "") -> SkillProposal:
        proposal = self._store.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        proposal.status = "discarded"
        self._store.upsert(proposal)
        self._ledger.append(
            run_id=proposal.run_id,
            agent="autoskills",
            tool="autoskills.discard",
            decision=Decision.ALLOW,
            inputs={"proposal_id": proposal_id, "reason": reason},
            outputs={"status": "discarded"},
        )
        return proposal

    # ------------------------------------------------------------------ remote

    def propose_remote(
        self,
        proposal_id: str,
        *,
        url: str,
        rationale: str,
    ) -> ApprovalRequest:
        """Queue an approval for a non-local proposal that needs a remote install."""
        proposal = self._store.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        if not is_remote_skill_source(url):
            raise ValueError(f"not a remote source: {url}")
        request = self._queue.enqueue(
            run_id=proposal.run_id,
            agent="autoskills",
            tool="autoskills.plan_remote",
            action="install_remote_skill",
            summary=f"Install remote skill for sequence {proposal.name}: {rationale}",
            payload={
                "proposal_id": proposal_id,
                "url": url,
                "rationale": rationale,
            },
        )
        self._ledger.append(
            run_id=proposal.run_id,
            agent="autoskills",
            tool="autoskills.plan_remote",
            decision=Decision.QUEUE_APPROVAL,
            inputs={"proposal_id": proposal_id, "url": url},
            outputs={"approval_id": request.id},
            approval_id=str(request.id),
        )
        return request

    # ----------------------------------------------------------------- discover

    def discover_tool(
        self,
        query: str,
        *,
        sources: Iterable[str] = DEFAULT_DISCOVERY_SOURCES,
        per_source_limit: int = 3,
    ) -> list[ToolCandidate]:
        """Multi-source search for a missing tool.

        Uses `site:` filters across PyPI, npm, crates.io, GitHub, MCP registry, and
        modelcontextprotocol.io. Returns a flat list; the caller picks one and asks
        for an approval-gated install via :meth:`propose_remote`.
        """
        if self._search is None:
            return []
        out: list[ToolCandidate] = []
        for site in sources:
            hits: list[SearchHit] = self._search.search(
                f"site:{site} {query}", limit=per_source_limit
            )
            for hit in hits:
                out.append(
                    ToolCandidate(source=site, title=hit.title, url=hit.url, snippet=hit.snippet)
                )
        return out


# ---------------------------------------------------------------------- helpers


def _is_completed_sequence(steps: list[dict[str, Any]], *, min_steps: int) -> bool:
    if len(steps) < min_steps:
        return False
    # Reject sequences that ended on a DENY — those are not reusable.
    return steps[-1]["decision"] != Decision.DENY.value


def _propose_name(steps: list[dict[str, Any]]) -> str:
    tools = [s["tool"].split(".")[0] for s in steps if s.get("tool")]
    unique = list(dict.fromkeys(tools))
    head = "-".join(unique[:3]) if unique else "auto"
    return f"auto-{head}"[:64]


def _propose_summary(steps: list[dict[str, Any]]) -> str:
    tool_seq = " → ".join(s["tool"] for s in steps[:6] if s.get("tool"))
    extra = "" if len(steps) <= 6 else " → …"
    return f"Auto-generated from {len(steps)}-step run: {tool_seq}{extra}"
