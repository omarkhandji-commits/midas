import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  CalendarClock,
  CheckCircle2,
  ClipboardCopy,
  CircleAlert,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

type Recipe = {
  name: string;
  command: string;
  cadence: string;
  at: string;
  windows_task: string;
  cron_line: string;
  github_actions: string;
};

type RunRow = {
  run_id: string;
  receipts: number;
  cost_usd: number;
  latest_ts: string;
  started_ts: string;
  agents: string[];
  tools: string[];
  pending_approval: boolean;
  denied: boolean;
  status: "ok" | "awaiting_approval" | "denied" | string;
};

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

export function SchedulePage() {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [at, setAt] = useState("09:00");
  const [mode, setMode] = useState("deep");

  async function loadAll() {
    const [recipesRes, runsRes] = await Promise.all([
      api.get<{ schedules: Recipe[] }>("/api/schedules"),
      api.get<{ runs: RunRow[] }>("/api/runs"),
    ]);
    setRecipes(recipesRes.schedules);
    setRuns(runsRes.runs);
  }

  useEffect(() => {
    run(loadAll).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function addRecipe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      await api.post("/api/schedules", {
        name: name.trim(),
        niche: niche.trim(),
        at: at.trim(),
        mode,
      });
      setNotice(`Recipe "${name.trim()}" saved.`);
      setName("");
      setNiche("");
      await loadAll();
    });
  }

  async function removeRecipe(target: string) {
    await run(async () => {
      await api.delete(`/api/schedules/${encodeURIComponent(target)}`);
      setNotice(`Recipe "${target}" removed.`);
      if (expanded === target) setExpanded(null);
      await loadAll();
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
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Schedule</CardKicker>
          <CardTitle>Recurring scans, owned by you</CardTitle>
        </CardHeader>
        <CardBody>
          MIDAS writes a recipe you install yourself in cron, Windows Task Scheduler, or
          GitHub Actions. No silent OS jobs are created — the operator always installs
          deliberately.
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>New recipe</CardKicker>
            <CardTitle>Daily scan</CardTitle>
          </CardHeader>
          <form className="mt-4 space-y-3" onSubmit={addRecipe}>
            <label className="grid gap-1.5 text-sm font-medium">
              Name
              <input
                className={inputClasses}
                type="text"
                placeholder="daily-seo-veille"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Niche
              <input
                className={inputClasses}
                type="text"
                placeholder="local SEO agency"
                value={niche}
                onChange={(event) => setNiche(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Time (HH:MM)
              <input
                className={inputClasses}
                type="text"
                pattern="\d{2}:\d{2}"
                value={at}
                onChange={(event) => setAt(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Mode
              <select
                className={inputClasses}
                value={mode}
                onChange={(event) => setMode(event.target.value)}
              >
                <option value="fast">fast</option>
                <option value="deep">deep</option>
                <option value="war-room">war-room</option>
              </select>
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus className="size-4" aria-hidden />
              Save recipe
            </Button>
          </form>
          <StatusLine error={error} notice={notice} />
        </Card>

        <section className="space-y-4">
          <Card className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <CalendarClock className="size-4 text-accent" aria-hidden />
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Recipes · {recipes.length}
              </span>
            </div>
            {recipes.length === 0 && (
              <p className="text-sm text-mute">No recipe saved yet.</p>
            )}
            <ul className="divide-y divide-rule">
              {recipes.map((r) => (
                <li key={r.name} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm text-ink">{r.name}</span>
                        <span className="border border-rule px-1.5 font-mono text-[10px] text-mute">
                          {r.cadence} · {r.at}
                        </span>
                      </div>
                      <p className="mt-1 font-mono text-xs text-mute">{r.command}</p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setExpanded(expanded === r.name ? null : r.name)}
                      >
                        {expanded === r.name ? "Hide" : "Show install"}
                      </Button>
                      <Button
                        type="button"
                        variant="no"
                        disabled={busy}
                        onClick={() => removeRecipe(r.name)}
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </Button>
                    </div>
                  </div>
                  {expanded === r.name && (
                    <div className="mt-3 space-y-3">
                      <CopyBlock label="Windows Task Scheduler" body={r.windows_task} />
                      <CopyBlock label="Cron (Linux/macOS)" body={r.cron_line} />
                      <CopyBlock label="GitHub Actions workflow" body={r.github_actions} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <Activity className="size-4 text-accent" aria-hidden />
              <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Recent runs · {runs.length}
              </span>
            </div>
            {runs.length === 0 && (
              <p className="text-sm text-mute">No run recorded yet.</p>
            )}
            <ul className="divide-y divide-rule">
              {runs.map((row) => (
                <li key={row.run_id} className="py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <RunStatusBadge status={row.status} />
                    <span className="font-mono text-xs text-ink">{row.run_id}</span>
                    <span className="font-mono text-[10px] text-mute">
                      {row.receipts} receipts · {formatCurrency(row.cost_usd)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-mute">
                    agents: {row.agents.join(", ") || "—"} · tools: {row.tools.join(", ") || "—"}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-mute">{row.latest_ts}</p>
                </li>
              ))}
            </ul>
          </Card>
        </section>
      </div>
    </div>
  );
}

function CopyBlock({ label, body }: { label: string; body: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard might be unavailable; the textarea still lets the user copy by hand.
    }
  }
  return (
    <div className="border border-rule">
      <div className="flex items-center justify-between border-b border-rule bg-rule-soft/40 px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
          {label}
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={copy}>
          <ClipboardCopy className="size-3.5" aria-hidden />
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto bg-paper p-3 font-mono text-[11px] text-ink">{body}</pre>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  if (status === "denied") {
    return (
      <span className="inline-flex items-center gap-1 border border-warn bg-warn-bg px-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-warn">
        <CircleAlert className="size-3" aria-hidden />
        denied
      </span>
    );
  }
  if (status === "awaiting_approval") {
    return (
      <span className="inline-flex items-center gap-1 border border-rule bg-rule-soft px-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-ink">
        awaiting
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 border border-accent bg-ok-bg px-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
      <CheckCircle2 className="size-3" aria-hidden />
      ok
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
