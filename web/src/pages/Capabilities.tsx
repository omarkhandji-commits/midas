import { useEffect, useMemo, useState } from "react";
import { Loader2, ShieldCheck, ShieldAlert, Eye } from "lucide-react";

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

const GROUP_ORDER = [
  "Cash artifacts",
  "Social",
  "Files",
  "Code",
  "Research",
  "External tools (MCP)",
  "Other",
];

export function CapabilitiesPage() {
  const [tools, setTools] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CapabilitiesResponse>("/api/capabilities")
      .then((r) => setTools(r.tools))
      .catch((e) => setError(e?.message || "Could not load capabilities."))
      .finally(() => setLoading(false));
  }, []);

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
