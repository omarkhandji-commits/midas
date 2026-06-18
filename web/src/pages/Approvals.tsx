import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  FileDiff,
  Hash,
  Loader2,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

type Approval = {
  id: number;
  run_id: string;
  agent: string;
  tool: string;
  action: string;
  summary: string;
  payload: Record<string, unknown>;
  risk: string;
  estimated_cost_usd: number;
  expires_ts: string | null;
  status: string;
  created_ts: string;
  resolved_ts: string | null;
  resolver: string | null;
  note: string | null;
};

type ExecuteResult = {
  kind?: string;
  path?: string;
  sha256_new?: string;
  bytes_len?: number;
};

const filters = ["all", "write", "send", "code", "money"] as const;
type Filter = (typeof filters)[number];

export function ApprovalsPage() {
  const [items, setItems] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [executed, setExecuted] = useState<Record<number, ExecuteResult>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<{ pending: Approval[] }>("/api/approvals");
      setItems(res.pending);
    } catch (err) {
      setError(readError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const visible = useMemo(() => items.filter((item) => matchesFilter(item, filter)), [items, filter]);

  async function resolve(id: number, approve: boolean) {
    setBusy(id);
    setError(null);
    try {
      await api.post(`/api/approvals/${id}/${approve ? "approve" : "reject"}`);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(null);
    }
  }

  async function execute(id: number) {
    setBusy(id);
    setError(null);
    try {
      const res = await api.post<{ ok: boolean; result: ExecuteResult }>(`/api/execute/${id}`);
      setExecuted((current) => ({ ...current, [id]: res.result }));
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <CardHeader>
            <CardKicker>Approval Center</CardKicker>
            <CardTitle>Review the exact action before it touches anything</CardTitle>
          </CardHeader>
          <Button type="button" variant="default" onClick={() => load()} disabled={loading}>
            <RefreshCw className={cn("size-4", loading && "animate-spin")} aria-hidden />
            Refresh
          </Button>
        </div>
        <CardBody className="mt-3">
          <p>
            Each card shows the planned payload, hash, preview, and action tier. Reject is the
            safe default; Execute appears only after an approval has been resolved.
          </p>
        </CardBody>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex border border-rule bg-paper">
          {filters.map((name) => (
            <button
              key={name}
              type="button"
              className={cn(
                "px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.08em]",
                filter === name ? "bg-rule-soft text-ink" : "text-mute hover:text-ink",
              )}
              onClick={() => setFilter(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <span className="font-mono text-xs text-mute">{visible.length} pending</span>
      </div>

      {error && (
        <div className="border border-warn bg-warn-bg px-4 py-3 text-sm text-warn" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-mute">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading approvals
        </div>
      ) : visible.length === 0 ? (
        <div className="border border-rule bg-paper p-5 text-sm text-mute">
          No pending approvals match this filter.
        </div>
      ) : (
        <div className="space-y-3">
          {visible.map((approval) => (
            <ApprovalRow
              key={approval.id}
              approval={approval}
              executed={executed[approval.id]}
              busy={busy === approval.id}
              onApprove={() => resolve(approval.id, true)}
              onReject={() => resolve(approval.id, false)}
              onExecute={() => execute(approval.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalRow({
  approval,
  executed,
  busy,
  onApprove,
  onReject,
  onExecute,
}: {
  approval: Approval;
  executed?: ExecuteResult;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onExecute: () => void;
}) {
  const sha = readText(approval.payload.sha256_new) || readText(approval.payload.sha256_intent);
  const preview = readText(approval.payload.preview);
  const path = readText(approval.payload.path);
  const risk = approval.risk || riskLabel(approval);

  return (
    <article className="border border-rule bg-paper p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="border border-rule px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
              #{approval.id}
            </span>
            <RiskBadge risk={risk} />
            <span className="font-mono text-[11px] text-mute">{approval.tool}</span>
          </div>
          <h2 className="mt-2 text-base font-semibold">{approval.summary}</h2>
          <p className="mt-1 font-mono text-[11px] text-mute">
            {approval.agent} / {approval.action} / run {approval.run_id}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="ok" size="sm" disabled={busy} onClick={onApprove}>
            <CheckCircle2 className="size-3.5" aria-hidden />
            Approve
          </Button>
          <Button type="button" variant="no" size="sm" disabled={busy} onClick={onReject}>
            <XCircle className="size-3.5" aria-hidden />
            Reject
          </Button>
          <Button type="button" variant="primary" size="sm" disabled={busy} onClick={onExecute}>
            <PlayCircle className="size-3.5" aria-hidden />
            Execute
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="space-y-2">
          {preview && (
            <div className="border border-rule bg-rule-soft/35 p-3 text-sm">
              <div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
                <FileDiff className="size-3.5" aria-hidden />
                Preview
              </div>
              <p className="whitespace-pre-wrap">{preview}</p>
            </div>
          )}
          <pre className="max-h-64 overflow-auto border border-rule bg-rule-soft/35 p-3 text-xs text-mute">
            {JSON.stringify(approval.payload, null, 2)}
          </pre>
        </div>

        <div className="space-y-2 text-sm">
          {sha && <Fact icon={Hash} label="Hash" value={`${sha.slice(0, 24)}...`} />}
          {path && <Fact icon={FileDiff} label="Path" value={path} />}
          <Fact icon={ShieldAlert} label="Cost est." value={formatCurrency(approval.estimated_cost_usd)} />
          {approval.expires_ts && <Fact icon={ShieldAlert} label="Expires" value={approval.expires_ts} />}
          <Fact icon={ShieldAlert} label="Status" value={approval.status} />
          {executed?.sha256_new && (
            <div className="border border-accent bg-ok-bg p-3 font-mono text-[11px] text-accent">
              executed {executed.sha256_new.slice(0, 24)}...
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function Fact({ icon: Icon, label, value }: { icon: typeof Hash; label: string; value: string }) {
  return (
    <div className="border border-rule p-3">
      <div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </div>
      <p className="break-words font-mono text-[11px] text-ink">{value}</p>
    </div>
  );
}

function RiskBadge({ risk }: { risk: string }) {
  const high = risk === "money" || risk === "code" || risk === "send";
  return (
    <span
      className={cn(
        "border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em]",
        high ? "border-warn bg-warn-bg text-warn" : "border-rule text-mute",
      )}
    >
      {risk}
    </span>
  );
}

function matchesFilter(item: Approval, filter: Filter): boolean {
  if (filter === "all") return true;
  return riskLabel(item) === filter;
}

function riskLabel(item: Approval): Exclude<Filter, "all"> | "write" {
  const joined = `${item.tool} ${item.action}`.toLowerCase();
  if (joined.includes("stripe") || joined.includes("pay") || joined.includes("price")) return "money";
  if (joined.includes("code") || joined.includes("execute")) return "code";
  if (joined.includes("email") || joined.includes("publish") || joined.includes("send")) return "send";
  return "write";
}

function readText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
