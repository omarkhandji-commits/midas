"""Sprint F2 — json/csv/http/docx tools + AgentLoop.resume."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from midas.core.agents.toolset import Toolset
from midas.core.config.models import (
    ActionsPolicy,
    ApprovalPolicy,
    AuditPolicy,
    FilesystemPolicy,
    ModelsPolicy,
    PolicyConfig,
    SourcesPolicy,
    SpendCaps,
)
from midas.core.sentinel import Sentinel
from midas.core.web.fetch import FetchedPage
from midas.flagship.agent import AgentLoop, build_default_toolset
from midas.flagship.agent.loop import AgentTranscript
from midas.flagship.agent.tools.data_io import (
    csv_read,
    json_read,
    plan_csv_write,
    plan_json_write,
)
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.http import http_fetch


def _g(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write", "execute_code"},
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


# ── json / csv read+write ────────────────────────────────────────────────────


def test_json_round_trip(tmp_path: Path) -> None:
    g = _g(tmp_path)
    plan = plan_json_write(g, "data.json", {"k": 1})
    assert not (tmp_path / "data.json").exists()
    # Materialize via the fs.write executor path.
    from midas.flagship.agent.tools.fs import execute_fs_write

    execute_fs_write(g, "data.json", '{\n  "k": 1\n}')
    res = json_read(g, "data.json")
    assert res.data == {"k": 1}
    assert plan.bytes_len > 0


def test_csv_round_trip(tmp_path: Path) -> None:
    g = _g(tmp_path)
    plan = plan_csv_write(g, "data.csv", [["a", "b"], [1, 2]])
    assert plan.bytes_len > 0
    assert not (tmp_path / "data.csv").exists()
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    res = csv_read(g, "data.csv")
    assert res.rows == [["a", "b"], ["1", "2"]]


# ── http.fetch ────────────────────────────────────────────────────────────────


class _StubFetcher:
    def __init__(self, text: str, status: int = 200) -> None:
        self._text = text
        self._status = status

    def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(url=url, status=self._status, text=self._text)


def test_http_fetch_text_and_sha256() -> None:
    res = http_fetch("https://example.com/x", fetcher=_StubFetcher("hello world"))
    assert res.ok is True
    assert res.status == 200
    assert res.text == "hello world"
    assert len(res.sha256) == 64


def test_http_fetch_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="absolute http"):
        http_fetch("file:///etc/passwd")


def test_http_fetch_truncates_large_text() -> None:
    big = "x" * 500_000
    res = http_fetch("https://example.com/big", fetcher=_StubFetcher(big))
    assert res.truncated is True
    assert len(res.text.encode("utf-8")) <= 200_000


# ── registry: new tools are exposed when their deps are present ──────────────


def test_registry_exposes_new_tools_when_fetcher_present(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    guard = _g(tmp_path)
    toolset = build_default_toolset(
        sentinel=sentinel,
        guard=guard,
        fetcher=_StubFetcher("ok"),  # type: ignore[arg-type]
        run_id="t",
    )
    names = set(toolset.names)
    assert {"json.read", "json.write", "csv.read", "csv.write", "http.fetch", "docx.draft"} <= names


def test_registry_omits_http_when_no_fetcher(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    toolset = build_default_toolset(sentinel=sentinel, guard=_g(tmp_path), run_id="t")
    assert "http.fetch" not in toolset.names


# ── AgentLoop.resume ──────────────────────────────────────────────────────────


def _stub_planner_factory(plans: list[dict[str, Any]]):
    queue = list(plans)

    def _planner(task: str, transcript: AgentTranscript) -> dict[str, Any]:  # noqa: ARG001
        if not queue:
            return {"done": True, "summary": "queue empty"}
        return queue.pop(0)

    return _planner


def test_resume_continues_after_approval(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    guard = _g(tmp_path)
    (tmp_path / "src.txt").write_text("input", encoding="utf-8")
    plans = [
        {"tool": "fs.read", "inputs": {"path": "src.txt"}},
        {"tool": "fs.write", "inputs": {"path": "out.txt", "content": "stage1"}},
    ]
    toolset = build_default_toolset(sentinel=sentinel, guard=guard, run_id="t")
    loop = AgentLoop(toolset=toolset, planner=_stub_planner_factory(plans), max_steps=6)
    t = loop.run("two stages")
    # Paused at the fs.write approval.
    assert "awaiting approval" in (t.stopped_reason or "")
    assert len(t.steps) == 2  # read + queued write
    # Resume with a fake executor outcome — should drive to done (planner queue empty).
    final = loop.resume(
        t, approval_outcome={"kind": "fs.write", "path": "out.txt", "sha256_new": "a" * 64}
    )
    assert final.stopped_reason == "queue empty"
    # Adds the synthetic executed step + completes.
    assert any(s.tool.endswith(".executed") for s in final.steps)


def test_resume_clears_stopped_reason(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    guard = _g(tmp_path)
    toolset = build_default_toolset(sentinel=sentinel, guard=guard, run_id="t")

    # Empty planner = immediate done.
    loop = AgentLoop(toolset=toolset, planner=lambda _t, _tr: {"done": True}, max_steps=4)
    t = AgentTranscript(task="x")
    t.stopped_reason = "awaiting approval #1"
    final = loop.resume(t, approval_outcome={"kind": "x", "sha256_new": "x" * 64})
    assert final.stopped_reason != "awaiting approval #1"


# ── helper: as_dict used by registry ─────────────────────────────────────────


def test_toolset_names_are_disjoint_and_complete(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    toolset: Toolset = build_default_toolset(sentinel=sentinel, guard=_g(tmp_path), run_id="t")
    names = toolset.names
    assert len(names) == len(set(names))
    # No duplicates and the previously-shipped tools are still there.
    for must_have in (
        "fs.read",
        "fs.write",
        "pdf.extract",
        "sheet.read",
        "sheet.write",
        "email.draft",
        "artifact.text",
        "code.run",
    ):
        assert must_have in names
