import { useEffect, useState, type FormEvent } from "react";
import { LineChart, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type OutcomeEntry = {
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

type Summary = {
  move_key: string;
  count: number;
  latest: string | null;
  proof: string;
  sources: string[];
};

type HistoryResp = { summary?: Summary; entries: OutcomeEntry[] };
type RecordResp = { ok: boolean; id: number; proof_level: string };

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

export function OutcomesPage() {
  const [moveKey, setMoveKey] = useState("");
  const [outcome, setOutcome] = useState("");
  const [metrics, setMetrics] = useState("");
  const [sources, setSources] = useState("");
  const [note, setNote] = useState("");

  const [searchKey, setSearchKey] = useState("");
  const [entries, setEntries] = useState<OutcomeEntry[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadHistory(key: string) {
    const params = new URLSearchParams();
    if (key.trim()) params.set("move_key", key.trim());
    const res = await api.get<HistoryResp>(`/api/outcomes/history?${params.toString()}`);
    setEntries(res.entries);
    setSummary(res.summary || null);
  }

  useEffect(() => {
    run(() => loadHistory("")).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function recordOutcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const metricsObj: Record<string, number> = {};
      metrics
        .split(/[\n,]/)
        .map((m) => m.trim())
        .filter(Boolean)
        .forEach((pair) => {
          const [k, v] = pair.split(/[:=]/);
          const value = Number((v ?? "").trim());
          if (k && k.trim() && Number.isFinite(value)) {
            metricsObj[k.trim()] = value;
          }
        });
      const body = {
        move_key: moveKey.trim(),
        outcome: outcome.trim(),
        metrics: metricsObj,
        sources: sources
          .split(/[\n,]/)
          .map((s) => s.trim())
          .filter(Boolean),
        note: note.trim(),
      };
      const res = await api.post<RecordResp>("/api/outcomes", body);
      setNotice(`Recorded (proof: ${res.proof_level}).`);
      setOutcome("");
      setMetrics("");
      setSources("");
      setNote("");
      await loadHistory(searchKey || moveKey.trim());
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

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <section className="space-y-4">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Outcome Tracker</CardKicker>
            <CardTitle>Close the Track loop</CardTitle>
          </CardHeader>
          <CardBody>
            Replies, clicks, sales, errors. Outcomes are stored as RESULT memory and written as
            receipts. A metric without a source defaults to LOW proof.
          </CardBody>
          <form
            className="mt-4 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              run(() => loadHistory(searchKey)).catch(() => undefined);
            }}
          >
            <label className="grid flex-1 gap-1.5 text-sm font-medium">
              Move key
              <input
                className={inputClasses}
                type="text"
                placeholder="leave empty to list latest 50"
                value={searchKey}
                onChange={(event) => setSearchKey(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Search className="size-4" aria-hidden />
              Search
            </Button>
          </form>
          <StatusLine error={error} notice={notice} />
        </Card>

        {summary && (
          <Card className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <LineChart className="size-4 text-accent" aria-hidden />
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Summary · {summary.move_key}
              </span>
            </div>
            <p className="text-sm text-ink">
              {summary.count} entries · latest proof <strong>{summary.proof}</strong>
            </p>
            {summary.latest && (
              <p className="mt-1 text-sm text-mute">{summary.latest}</p>
            )}
          </Card>
        )}

        <Card className="p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
              Entries · {entries.length}
            </span>
          </div>
          {entries.length === 0 && (
            <p className="text-sm text-mute">No outcome recorded yet.</p>
          )}
          <ol className="space-y-3 text-sm">
            {entries.map((entry) => (
              <li
                key={entry.id}
                className={cn(
                  "border-l-2 pl-3",
                  entry.superseded ? "border-rule" : "border-accent",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-ink">{entry.key}</span>
                  <ProofBadge level={entry.proof_level} />
                  {entry.tags.map((t) => (
                    <span
                      key={t}
                      className="border border-rule px-1.5 font-mono text-[10px] text-mute"
                    >
                      {t}
                    </span>
                  ))}
                  <span className="font-mono text-[10px] text-mute">{entry.ts}</span>
                </div>
                <p className="mt-1 text-sm text-ink">{entry.content}</p>
                {entry.sources.length > 0 && (
                  <p className="mt-1 text-xs text-mute">{entry.sources.join(", ")}</p>
                )}
              </li>
            ))}
          </ol>
        </Card>
      </section>

      <aside>
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Record</CardKicker>
            <CardTitle>What happened</CardTitle>
          </CardHeader>
          <CardBody>
            Tie an outcome to a previously-approved move. Add a source URL (analytics, CRM) to
            grade the proof MEDIUM instead of LOW.
          </CardBody>
          <form className="mt-4 space-y-3" onSubmit={recordOutcome}>
            <label className="grid gap-1.5 text-sm font-medium">
              Move key
              <input
                className={inputClasses}
                type="text"
                placeholder="e.g. mission:abc123 or candidate name"
                value={moveKey}
                onChange={(event) => setMoveKey(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Outcome
              <textarea
                className={cn(inputClasses, "h-20 py-2")}
                placeholder="3 replies, 1 booked call…"
                value={outcome}
                onChange={(event) => setOutcome(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Metrics (key=value, comma or newline-separated)
              <textarea
                className={cn(inputClasses, "h-16 py-2")}
                placeholder="replies=3, calls=1, revenue_usd=0"
                value={metrics}
                onChange={(event) => setMetrics(event.target.value)}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Sources (URLs)
              <textarea
                className={cn(inputClasses, "h-16 py-2")}
                placeholder="https://… (required for MEDIUM proof)"
                value={sources}
                onChange={(event) => setSources(event.target.value)}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Note
              <input
                className={inputClasses}
                type="text"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus className="size-4" aria-hidden />
              Record
            </Button>
          </form>
        </Card>
      </aside>
    </div>
  );
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

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
