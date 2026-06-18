import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Loader2, ShieldCheck, ShieldAlert, Eye, SearchCheck, Wrench } from "lucide-react";

import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Capability = {
  name: string;
  action: string;
  tier: "auto" | "approve" | "forbidden";
  taint: "trusted" | "untrusted";
  has_egress: boolean;
  group: string;
};

type CapabilitiesResponse = { tools: Capability[] };
type LocalProbe = {
  name: string;
  status: "available" | "setup_required" | "approval_required" | "forbidden";
  category: string;
  detail: string;
};
type CapabilityPlan = {
  goal: string;
  status: LocalProbe["status"];
  primary_path: string;
  fallback_path: string;
  approval_required: boolean;
  privacy_note: string;
  cost_note: string;
  missing: string[];
};

const GROUP_ORDER = [
  "Cash artifacts",
  "Cash collection",
  "Inbound",
  "Social",
  "Files",
  "Code",
  "Skills",
  "Research",
  "External tools (MCP)",
  "Other",
];

export function CapabilitiesPage() {
  const [tools, setTools] = useState<Capability[]>([]);
  const [local, setLocal] = useState<LocalProbe[]>([]);
  const [goal, setGoal] = useState("");
  const [plan, setPlan] = useState<CapabilityPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CapabilitiesResponse>("/api/capabilities")
      .then((r) => setTools(r.tools))
      .catch((e) => setError(e?.message || "Could not load capabilities."))
      .finally(() => setLoading(false));
  }, []);

  async function scanLocal() {
    setScanning(true);
    setError(null);
    try {
      const res = await api.post<{ capabilities: LocalProbe[] }>("/api/capabilities/scan");
      setLocal(res.capabilities);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not scan local capabilities.");
    } finally {
      setScanning(false);
    }
  }

  async function planGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    setScanning(true);
    setError(null);
    try {
      const res = await api.post<{ plan: CapabilityPlan }>("/api/capabilities/plan", {
        goal: trimmed,
      });
      setPlan(res.plan);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not plan capability.");
    } finally {
      setScanning(false);
    }
  }

  const grouped = useMemo(() => {
    const map = new Map<string, Capability[]>();
    for (const t of tools) {
      const list = map.get(t.group) ?? [];
      list.push(t);
      map.set(t.group, list);
    }
    return GROUP_ORDER.filter((g) => map.has(g)).map((g) => ({
      group: g,
      items: (map.get(g) ?? []).sort((a, b) => a.name.localeCompare(b.name)),
    }));
  }, [tools]);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Reference</CardKicker>
          <CardTitle>Everything Midas can do, and what it waits for you on</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <p>
            This list is generated from the registered toolset — the same one the agent
            uses. If a tool isn't here, it cannot be called. If it's marked{" "}
            <Badge tier="approve" /> it queues an approval before any side effect.
          </p>
          <div className="mt-3 flex flex-wrap gap-3 text-xs">
            <Legend />
          </div>
        </CardBody>
      </Card>

      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <CardHeader>
            <CardKicker>Local readiness</CardKicker>
            <CardTitle>Ask if MIDAS can do a job on this machine</CardTitle>
          </CardHeader>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-2 border border-rule px-3 text-sm text-ink hover:bg-rule-soft"
            onClick={scanLocal}
            disabled={scanning}
          >
            <SearchCheck className="size-4" aria-hidden />
            Scan
          </button>
        </div>
        <form className="mt-4 flex flex-wrap gap-2" onSubmit={planGoal}>
          <input
            className="h-10 min-w-64 flex-1 border border-rule bg-paper px-3 text-sm"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Can MIDAS create a Remotion video with voice?"
          />
          <button
            type="submit"
            className="inline-flex h-10 items-center gap-2 border border-accent bg-accent px-3 text-sm text-paper"
            disabled={scanning || !goal.trim()}
          >
            <Wrench className="size-4" aria-hidden />
            Plan
          </button>
        </form>
        {plan && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <ReadinessFact label="Status" value={plan.status} />
            <ReadinessFact label="Approval" value={plan.approval_required ? "required" : "not required"} />
            <ReadinessFact label="Primary" value={plan.primary_path} />
            <ReadinessFact label="Fallback" value={plan.fallback_path} />
            <ReadinessFact label="Privacy" value={plan.privacy_note} />
            <ReadinessFact label="Cost" value={plan.cost_note} />
          </div>
        )}
        {local.length > 0 && (
          <ul className="mt-4 grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {local.map((probe) => (
              <li key={probe.name} className="border border-rule p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm">{probe.name}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
                    {probe.status === "available" ? "ready" : "setup"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-mute">{probe.detail}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {loading && (
        <p className="flex items-center gap-2 text-sm text-mute">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Loading…
        </p>
      )}

      {error && (
        <p
          className="border-l-2 border-[hsl(var(--warn))] bg-[hsl(var(--warn))]/5 p-3 text-sm"
          role="alert"
        >
          {error}
        </p>
      )}

      {grouped.map((g) => (
        <section key={g.group} className="space-y-2">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.12em] text-mute">
            {g.group}
          </h2>
          <ul className="grid gap-2 md:grid-cols-2">
            {g.items.map((t) => (
              <li
                key={t.name}
                className="border border-rule bg-paper p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-semibold">{t.name}</p>
                    <p className="mt-1 text-xs text-mute">
                      Policy action: <code>{t.action}</code>
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                    <Badge tier={t.tier} />
                    {t.has_egress && <EgressBadge />}
                    {t.taint === "untrusted" && <TaintBadge />}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Badge({ tier }: { tier: Capability["tier"] }) {
  if (tier === "approve") {
    return (
      <span className="inline-flex items-center gap-1 border border-[hsl(var(--warn))] bg-[hsl(var(--warn))]/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-[hsl(var(--warn))]">
        <ShieldAlert className="size-3" aria-hidden /> approve
      </span>
    );
  }
  if (tier === "forbidden") {
    return (
      <span className="inline-flex items-center gap-1 border border-rule bg-rule-soft/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
        forbidden
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 border border-accent bg-accent/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
      <ShieldCheck className="size-3" aria-hidden /> auto
    </span>
  );
}

function EgressBadge() {
  return (
    <span
      title="May reach the network"
      className="inline-flex items-center border border-rule px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute"
    >
      egress
    </span>
  );
}

function TaintBadge() {
  return (
    <span
      title="Output is untrusted (cannot become instructions)"
      className="inline-flex items-center gap-1 border border-rule px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute"
    >
      <Eye className="size-3" aria-hidden /> untrusted
    </span>
  );
}

function Legend() {
  return (
    <>
      <span className="inline-flex items-center gap-1.5">
        <Badge tier="auto" /> runs without asking (reads, drafts, research)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <Badge tier="approve" /> queues an approval (writes, sends, executes)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <EgressBadge /> may reach the network
      </span>
      <span className="inline-flex items-center gap-1.5">
        <TaintBadge /> third-party output is data, not instructions
      </span>
    </>
  );
}

function ReadinessFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-rule p-3">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
        {label}
      </div>
      <p className="text-sm">{value}</p>
    </div>
  );
}
