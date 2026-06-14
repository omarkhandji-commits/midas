// MIDAS dashboard — vanilla JS, no framework. The CSP forbids inline scripts.
// Responsibilities are intentionally narrow:
//   1. Wire approve/reject buttons to POST /approvals/<id>/<action>;
//   2. Carry the CSRF cookie value in the X-MIDAS-CSRF header (double-submit);
//   3. Remove the resolved row on success, or surface the queue error on conflict.
"use strict";

(function () {
  const CSRF_COOKIE = "midas_csrf";
  const CSRF_HEADER = "X-MIDAS-CSRF";

  function readCookie(name) {
    return document.cookie
      .split(";")
      .map((c) => c.trim())
      .find((c) => c.startsWith(name + "="))
      ?.slice(name.length + 1) || "";
  }

  async function resolve(reqId, action, btn) {
    const csrf = readCookie(CSRF_COOKIE);
    if (!csrf) { window.location.href = "/login"; return; }

    const row = btn.closest("tr");
    row.querySelectorAll("button").forEach((b) => (b.disabled = true));

    let resp;
    try {
      resp = await fetch(`/approvals/${reqId}/${action}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { [CSRF_HEADER]: csrf, "Accept": "application/json" },
      });
    } catch (_e) {
      row.querySelectorAll("button").forEach((b) => (b.disabled = false));
      return;
    }

    if (resp.ok) { row.remove(); return; }
    if (resp.status === 401) { window.location.href = "/login"; return; }

    // 409 = idempotency conflict, 403 = CSRF/origin denied. Show inline, don't toast.
    const body = await resp.json().catch(() => ({ error: "request failed" }));
    const cell = row.querySelector(".m-table__sum");
    cell.textContent = `[${resp.status}] ${body.error || "denied"} — ${cell.textContent}`;
    row.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-action][data-id]");
    if (!btn) return;
    ev.preventDefault();
    resolve(btn.dataset.id, btn.dataset.action, btn);
  });

  // ── live header (SSE) ────────────────────────────────────────────────────
  // One-way push from the server. EventSource sends the session cookie
  // automatically (same-origin), so no extra auth glue is needed.
  function setLive(id, text) {
    const el = document.getElementById(id);
    if (!el || el.textContent === text) return;
    el.textContent = text;
    el.classList.remove("is-live");
    void el.offsetWidth; // restart CSS animation
    el.classList.add("is-live");
  }

  function startStream() {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/events");
    es.addEventListener("tick", (ev) => {
      let snap;
      try { snap = JSON.parse(ev.data); } catch { return; }
      setLive("spent-usd", "$" + Number(snap.spent_usd).toFixed(4));
      setLive("receipt-count", String(snap.receipts));
    });
    // Browser auto-reconnects on transient drops; we deliberately do nothing on error.
  }
  if (document.getElementById("spent-usd")) startStream();
})();
