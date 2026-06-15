import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ClipboardList, History, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type MemoryEntry = {
  id: number;
  ts: string;
  kind: string;
  key: string;
  content: string;
  proof_level: "low" | "medium" | "high";
  sources: string[];
  tags: string[];
  superseded?: boolean;
};

type SearchResp = { memory: MemoryEntry[] };
type HistoryResp = { kind: string; key: string; entries: MemoryEntry[] };
type AddResp = { ok: boolean; entry: MemoryEntry };

const KINDS = ["user", "business", "decision", "result", "market", "error"] as const;
const PROOFS = ["low", "medium", "high"] as const;

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

export function MemoryPage() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<string>("");
  const [rows, setRows] = useState<MemoryEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryResp | null>(null);

  // add form
  const [addKind, setAddKind] = useState<string>("business");
  const [addKey, setAddKey] = useState("");
  const [addContent, setAddContent] = useState("");
  const [addProof, setAddProof] = useState<string>("low");
  const [addSources, setAddSources] = useState("");
  const [addTags, setAddTags] = useState("");

  async function search() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (kind) params.set("kind", kind);
      const res = await api.get<SearchResp>(`/api/memory/search?${params.toString()}`);
      setRows(res.memory);
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    search().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadHistory(entry: MemoryEntry) {
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({ kind: entry.kind, key: entry.key });
      const res = await api.get<HistoryResp>(`/api/memory/history?${params.toString()}`);
      setHistory(res);
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  async function addEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        kind: addKind,
        key: addKey.trim(),
        content: addContent.trim(),
        proof_level: addProof,
        sources: addSources
          .split(/[\n,]/)
          .map((s) => s.trim())
          .filter(Boolean),
        tags: addTags
          .split(/[\n,]/)
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const res = await api.post<AddResp>("/api/memory/add", body);
      setNotice(`Stored ${res.entry.kind}:${res.entry.key} (${res.entry.proof_level}).`);
      setAddKey("");
      setAddContent("");
      setAddSources("");
      setAddTags("");
      await search();
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  const grouped = useMemo(() => groupByKind(rows), [rows]);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="space-y-4">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Business Memory</CardKicker>
            <CardTitle>Six durable namespaces</CardTitle>
          </CardHeader>
          <CardBody>
            User, business, decisions, results, market, errors. Append-only with supersede so
            history is preserved. Sourced facts grade MEDIUM/HIGH; unsourced facts stay LOW.
          </CardBody>
          <form
            className="mt-4 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              search().catch(() => undefined);
            }}
          >
            <label className="grid gap-1.5 text-sm font-medium">
              Kind
              <select
                className={inputClasses}
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="">all</option>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid flex-1 gap-1.5 text-sm font-medium">
              Search
              <input
                className={inputClasses}
                type="text"
                placeholder="content or key substring…"
                value={q}
                onChange={(event) => setQ(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Search className="size-4" aria-hidden />
              Search
            </Button>
          </form>
          <StatusLine error={error} notice={notice} />
        </Card>

        {Object.entries(grouped).map(([k, entries]) => (
          <Card key={k} className="p-5">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                {k} · {entries.length}
              </span>
            </div>
            <ul className="divide-y divide-rule">
              {entries.map((row) => (
                <li key={row.id} className="flex items-start justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-ink">{row.key}</span>
                      <ProofBadge level={row.proof_level} />
                      {row.tags.map((t) => (
                        <span
                          key={t}
                          className="border border-rule px-1.5 font-mono text-[10px] text-mute"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <p className="mt-1 text-sm text-ink">{row.content}</p>
                    {row.sources.length > 0 && (
                      <p className="mt-1 text-xs text-mute">
                        sources: {row.sources.join(", ")}
                      </p>
                    )}
                    <p className="mt-1 font-mono text-[10px] text-mute">{row.ts}</p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => loadHistory(row)}
                    disabled={busy}
                  >
                    <History className="size-4" aria-hidden />
                    History
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        ))}

        {rows.length === 0 && !busy && (
          <Card className="p-5">
            <p className="text-sm text-mute">No memory yet. Use the form on the right to add one.</p>
          </Card>
        )}
      </section>

      <aside className="space-y-4">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Add</CardKicker>
            <CardTitle>Remember a fact</CardTitle>
          </CardHeader>
          <CardBody>
            Adding a new fact for an existing (kind, key) supersedes the prior version. Old versions
            stay accessible via History.
          </CardBody>
          <form className="mt-4 space-y-3" onSubmit={addEntry}>
            <label className="grid gap-1.5 text-sm font-medium">
              Kind
              <select
                className={inputClasses}
                value={addKind}
                onChange={(event) => setAddKind(event.target.value)}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Key
              <input
                className={inputClasses}
                type="text"
                placeholder="e.g. icp.primary"
                value={addKey}
                onChange={(event) => setAddKey(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Content
              <textarea
                className={cn(inputClasses, "h-24 py-2")}
                value={addContent}
                onChange={(event) => setAddContent(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Proof level
              <select
                className={inputClasses}
                value={addProof}
                onChange={(event) => setAddProof(event.target.value)}
              >
                {PROOFS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Sources (comma or newline-separated URLs)
              <textarea
                className={cn(inputClasses, "h-20 py-2")}
                placeholder="https://… (required for MEDIUM/HIGH)"
                value={addSources}
                onChange={(event) => setAddSources(event.target.value)}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Tags
              <input
                className={inputClasses}
                type="text"
                placeholder="strategy, q3, lessons"
                value={addTags}
                onChange={(event) => setAddTags(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus className="size-4" aria-hidden />
              Save
            </Button>
          </form>
        </Card>
      </aside>

      {history && (
        <HistoryModal data={history} onClose={() => setHistory(null)} />
      )}
    </div>
  );
}

function groupByKind(rows: MemoryEntry[]): Record<string, MemoryEntry[]> {
  return rows.reduce((acc, row) => {
    (acc[row.kind] ||= []).push(row);
    return acc;
  }, {} as Record<string, MemoryEntry[]>);
}

function ProofBadge({ level }: { level: string }) {
  const tone =
    level === "high"
      ? "border-accent text-accent bg-ok-bg"
      : level === "medium"
        ? "border-rule text-ink bg-rule-soft"
        : "border-rule text-mute bg-paper";
  return (
    <span
      className={cn(
        "border px-1.5 font-mono text-[10px] uppercase tracking-[0.08em]",
        tone,
      )}
    >
      {level}
    </span>
  );
}

function StatusLine({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return (
    <div
      className={cn(
        "mt-3 border px-3 py-2 text-sm",
        error ? "border-warn bg-warn-bg text-warn" : "border-accent bg-ok-bg text-accent",
      )}
      role={error ? "alert" : "status"}
      aria-live="polite"
    >
      {error ?? notice}
    </div>
  );
}

function HistoryModal({
  data,
  onClose,
}: {
  data: HistoryResp;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-ink/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto border border-rule bg-paper p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <ClipboardList className="size-4 text-accent" aria-hidden />
          <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
            History · {data.kind} · {data.key}
          </span>
        </div>
        <ol className="space-y-3 text-sm">
          {data.entries.map((entry, idx) => (
            <li
              key={entry.id}
              className={cn(
                "border-l-2 pl-3",
                entry.superseded ? "border-rule" : "border-accent",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-mute">v{idx + 1}</span>
                <ProofBadge level={entry.proof_level} />
                {entry.superseded && (
                  <span className="font-mono text-[10px] text-mute">superseded</span>
                )}
                <span className="font-mono text-[10px] text-mute">{entry.ts}</span>
              </div>
              <p className="mt-1 text-sm text-ink">{entry.content}</p>
              {entry.sources.length > 0 && (
                <p className="mt-1 text-xs text-mute">{entry.sources.join(", ")}</p>
              )}
            </li>
          ))}
        </ol>
        <div className="mt-4 flex justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
