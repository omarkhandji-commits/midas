import { useEffect, useState, type FormEvent } from "react";
import { Activity, Plus, Radar, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Competitor = {
  id: number;
  created_ts: string;
  name: string;
  url: string;
  notes: string;
};

type Snapshot = {
  competitor_id: number;
  name: string;
  url: string;
  status: number;
  content_hash: string;
  changed: boolean;
  change_kind: "initial" | "changed" | "unchanged" | "unreachable" | string;
  excerpt: string;
  ts: string;
};

type ListResp = { competitors: Competitor[] };
type SnapsResp = { competitor: Competitor; snapshots: Snapshot[] };
type SnapResp = { ok: boolean; snapshot: Snapshot };

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

export function MarketPage() {
  const [list, setList] = useState<Competitor[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");

  async function loadList() {
    const res = await api.get<ListResp>("/api/competitors");
    setList(res.competitors);
    if (selected === null && res.competitors[0]) {
      setSelected(res.competitors[0].id);
    }
  }

  async function loadSnaps(id: number) {
    const res = await api.get<SnapsResp>(`/api/competitors/${id}/snapshots`);
    setSnaps(res.snapshots);
  }

  useEffect(() => {
    run(loadList).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selected !== null) {
      run(() => loadSnaps(selected)).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  async function addCompetitor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const res = await api.post<{ ok: boolean; competitor: Competitor }>(
        "/api/competitors",
        { name: name.trim(), url: url.trim(), notes: notes.trim() },
      );
      setNotice(`Added ${res.competitor.name}.`);
      setName("");
      setUrl("");
      setNotes("");
      await loadList();
      setSelected(res.competitor.id);
    });
  }

  async function snapshotSelected() {
    if (selected === null) return;
    await run(async () => {
      const res = await api.post<SnapResp>(`/api/competitors/${selected}/snapshot`);
      setNotice(
        `Snapshot ${res.snapshot.change_kind} (status ${res.snapshot.status}) saved.`,
      );
      await loadSnaps(selected);
    });
  }

  async function deleteSelected() {
    if (selected === null) return;
    await run(async () => {
      await api.delete(`/api/competitors/${selected}`);
      setNotice("Competitor removed.");
      setSelected(null);
      setSnaps([]);
      await loadList();
    });
  }

  async function run(op: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await op();
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  const current = list.find((c) => c.id === selected);

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <section className="space-y-4">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Market Radar</CardKicker>
            <CardTitle>Add a competitor</CardTitle>
          </CardHeader>
          <CardBody>
            Track competitor pages over time. Each snapshot hashes the content; receipts mark
            <em> initial</em>, <em>changed</em>, <em>unchanged</em>, or <em>unreachable</em>.
          </CardBody>
          <form className="mt-4 space-y-3" onSubmit={addCompetitor}>
            <label className="grid gap-1.5 text-sm font-medium">
              Name
              <input
                className={inputClasses}
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              URL
              <input
                className={inputClasses}
                type="url"
                placeholder="https://…"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Notes
              <input
                className={inputClasses}
                type="text"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus className="size-4" aria-hidden />
              Watch
            </Button>
          </form>
        </Card>

        <Card className="p-5">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
              Watched · {list.length}
            </span>
          </div>
          <ul className="divide-y divide-rule">
            {list.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={cn(
                    "w-full px-2 py-2 text-left text-sm hover:bg-rule-soft/40",
                    selected === c.id ? "bg-rule-soft/60 text-ink" : "text-mute",
                  )}
                  onClick={() => setSelected(c.id)}
                >
                  <div className="flex items-center gap-2">
                    <Radar className="size-3.5" aria-hidden />
                    <span className="font-mono text-xs">{c.name}</span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-mute">{c.url}</div>
                </button>
              </li>
            ))}
          </ul>
          {list.length === 0 && (
            <p className="text-sm text-mute">No competitor yet.</p>
          )}
        </Card>
      </section>

      <section className="space-y-4">
        {current ? (
          <Card className="p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardKicker>{current.url}</CardKicker>
                <CardTitle>{current.name}</CardTitle>
                {current.notes && <p className="mt-1 text-sm text-mute">{current.notes}</p>}
              </div>
              <div className="flex gap-2">
                <Button type="button" disabled={busy} onClick={snapshotSelected}>
                  <RefreshCw className="size-4" aria-hidden />
                  Snapshot now
                </Button>
                <Button type="button" variant="no" disabled={busy} onClick={deleteSelected}>
                  <Trash2 className="size-4" aria-hidden />
                  Remove
                </Button>
              </div>
            </div>
            <StatusLine error={error} notice={notice} />
          </Card>
        ) : (
          <Card className="p-6">
            <CardBody>Select a competitor on the left or add one to see snapshots here.</CardBody>
            <StatusLine error={error} notice={notice} />
          </Card>
        )}

        {current && (
          <Card className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <Activity className="size-4 text-accent" aria-hidden />
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Dated snapshots
              </span>
            </div>
            {snaps.length === 0 && (
              <p className="text-sm text-mute">
                No snapshot yet. Click <em>Snapshot now</em> to capture a baseline.
              </p>
            )}
            <ol className="space-y-3 text-sm">
              {snaps.map((s, idx) => (
                <li key={`${s.ts}-${idx}`} className="border-l-2 border-rule pl-3">
                  <div className="flex items-center gap-2">
                    <ChangeBadge kind={s.change_kind} />
                    <span className="font-mono text-[10px] text-mute">HTTP {s.status}</span>
                    <span className="font-mono text-[10px] text-mute">{s.ts}</span>
                  </div>
                  {s.excerpt && <p className="mt-1 text-xs text-mute">{s.excerpt}</p>}
                  {s.content_hash && (
                    <p className="mt-1 font-mono text-[10px] text-mute">
                      hash {s.content_hash.slice(0, 16)}…
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </Card>
        )}
      </section>
    </div>
  );
}

function ChangeBadge({ kind }: { kind: string }) {
  const tone =
    kind === "changed"
      ? "border-accent bg-ok-bg text-accent"
      : kind === "initial"
        ? "border-rule bg-rule-soft text-ink"
        : kind === "unreachable"
          ? "border-warn bg-warn-bg text-warn"
          : "border-rule bg-paper text-mute";
  return (
    <span
      className={cn(
        "border px-1.5 font-mono text-[10px] uppercase tracking-[0.08em]",
        tone,
      )}
    >
      {kind}
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

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
