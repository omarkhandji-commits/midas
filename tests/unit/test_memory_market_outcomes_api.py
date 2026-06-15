"""Sprint 7 — Memory + Market Radar + Outcomes dashboard APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.memory import MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE
from midas.flagship.market import CompetitorStore


@dataclass
class _FakePage:
    text: str
    status: int = 200

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class _StubFetcher:
    """Deterministic fetcher used for snapshot tests — no network."""

    def __init__(self, pages: dict[str, _FakePage]) -> None:
        self._pages = pages

    def fetch(self, url: str) -> _FakePage:
        return self._pages.get(url, _FakePage(text="", status=0))


def _build(
    tmp_path: Path, *, fetcher: _StubFetcher | None = None
) -> tuple[TestClient, LoginToken, MemoryStore, CompetitorStore, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("64" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    memory = MemoryStore(tmp_path / "memory.db")
    competitors = CompetitorStore(tmp_path / "competitors.db")
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        memory=memory,
        competitors=competitors,
        fetcher=fetcher,
    )
    client = TestClient(create_app(deps), base_url="http://testserver")
    return client, token, memory, competitors, ledger


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return r.cookies[CSRF_COOKIE]


def _headers(csrf: str) -> dict[str, str]:
    return {"origin": "http://testserver", "x-midas-csrf": csrf}


def test_memory_add_supersedes_and_history(tmp_path: Path) -> None:
    client, token, _memory, _comp, _ledger = _build(tmp_path)
    csrf = _sign_in(client, token)

    r1 = client.post(
        "/api/memory/add",
        headers=_headers(csrf),
        json={"kind": "business", "key": "icp", "content": "dentists Montreal"},
    )
    assert r1.status_code == 200
    assert r1.json()["entry"]["proof_level"] == "low"

    r2 = client.post(
        "/api/memory/add",
        headers=_headers(csrf),
        json={
            "kind": "business",
            "key": "icp",
            "content": "dentists Laval",
            "proof_level": "medium",
            "sources": ["https://example.com/icp"],
            "tags": ["strategy"],
        },
    )
    assert r2.status_code == 200
    assert r2.json()["entry"]["proof_level"] == "medium"

    history = client.get("/api/memory/history?kind=business&key=icp").json()
    assert len(history["entries"]) == 2
    assert history["entries"][0]["superseded"] is True
    assert history["entries"][1]["superseded"] is False
    assert history["entries"][1]["content"] == "dentists Laval"


def test_memory_add_rejects_unsourced_medium(tmp_path: Path) -> None:
    client, token, _m, _c, _l = _build(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/memory/add",
        headers=_headers(csrf),
        json={
            "kind": "business",
            "key": "icp",
            "content": "no proof",
            "proof_level": "high",
        },
    )
    assert r.status_code == 400
    assert "source" in r.json()["error"].lower()


def test_memory_add_rejects_bad_kind(tmp_path: Path) -> None:
    client, token, _m, _c, _l = _build(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/memory/add",
        headers=_headers(csrf),
        json={"kind": "wrong", "key": "x", "content": "y"},
    )
    assert r.status_code == 400


def test_competitor_add_snapshot_delete_flow(tmp_path: Path) -> None:
    page = _FakePage(text="Initial homepage content for ACME.")
    fetcher = _StubFetcher({"https://acme.example/": page})
    client, token, memory, competitors, ledger = _build(tmp_path, fetcher=fetcher)
    csrf = _sign_in(client, token)

    add = client.post(
        "/api/competitors",
        headers=_headers(csrf),
        json={"name": "ACME", "url": "https://acme.example/"},
    )
    assert add.status_code == 200
    cid = add.json()["competitor"]["id"]

    snap = client.post(
        f"/api/competitors/{cid}/snapshot",
        headers=_headers(csrf),
    )
    assert snap.status_code == 200
    assert snap.json()["snapshot"]["change_kind"] == "initial"

    # second snapshot with identical page → unchanged
    again = client.post(
        f"/api/competitors/{cid}/snapshot",
        headers=_headers(csrf),
    )
    assert again.json()["snapshot"]["change_kind"] == "unchanged"

    snaps = client.get(f"/api/competitors/{cid}/snapshots").json()
    assert len(snaps["snapshots"]) == 2
    # Newest-first ordering
    assert snaps["snapshots"][0]["change_kind"] == "unchanged"
    assert snaps["snapshots"][1]["change_kind"] == "initial"

    deleted = client.delete(
        f"/api/competitors/{cid}",
        headers=_headers(csrf),
    )
    assert deleted.status_code == 200
    assert client.get("/api/competitors").json()["competitors"] == []
    # Underlying receipts: at least add + 2 snapshots + delete
    tools = {r.body.tool for r in ledger}
    assert "competitors.add" in tools
    assert "competitor.snapshot" in tools
    assert "competitors.delete" in tools


def test_competitor_add_rejects_non_http_url(tmp_path: Path) -> None:
    client, token, _m, _c, _l = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/competitors",
        headers=_headers(csrf),
        json={"name": "x", "url": "ftp://nope"},
    )
    assert r.status_code == 400


def test_outcomes_history_summary(tmp_path: Path) -> None:
    client, token, _m, _c, ledger = _build(tmp_path)
    csrf = _sign_in(client, token)

    rec = client.post(
        "/api/outcomes",
        headers=_headers(csrf),
        json={
            "move_key": "mission:abc",
            "outcome": "3 replies",
            "metrics": {"replies": 3},
            "sources": ["https://crm.example/leads"],
        },
    )
    assert rec.status_code == 200
    assert rec.json()["proof_level"] in {"medium", "high"}

    hist = client.get("/api/outcomes/history?move_key=mission:abc").json()
    assert hist["summary"]["count"] == 1
    assert hist["entries"][0]["content"].startswith("3 replies")

    # list mode (no move_key) returns latest 50 RESULT entries
    all_recent = client.get("/api/outcomes/history").json()
    assert len(all_recent["entries"]) == 1
    assert any(r.body.tool == "record_result" for r in ledger)
