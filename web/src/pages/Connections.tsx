import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle2,
  KeyRound,
  Loader2,
  Plug,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type ProviderStatus = {
  name: string;
  label: string;
  configured: boolean;
  local: boolean;
  missing: string[];
  has_api_key: boolean;
  notes: string;
};

type ChannelStatus = {
  name: string;
  label: string;
  connected: boolean;
  required: string[];
  missing: string[];
  notes: string;
};

type ProvidersResponse = { providers: ProviderStatus[] };
type ChannelsResponse = { channels: ChannelStatus[] };

export function ConnectionsPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    setLoading(true);
    try {
      const [p, c] = await Promise.all([
        api.get<ProvidersResponse>("/api/providers"),
        api.get<ChannelsResponse>("/api/channels"),
      ]);
      setProviders(p.providers);
      setChannels(c.channels);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load connections.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const brainReady = useMemo(
    () => providers.some((p) => p.configured),
    [providers],
  );
  const channelReady = useMemo(
    () => channels.some((c) => c.connected),
    [channels],
  );

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Overview</CardKicker>
          <CardTitle>How Midas talks to the world</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <p>
            Two things wire Midas to your work: a <strong>brain</strong> (the LLM that
            drafts and plans) and at least one <strong>channel</strong> (where it pings
            you for approvals). Everything else is optional.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <ReadinessChip
              label="Brain"
              ready={brainReady}
              hint={brainReady ? "Configured" : "No model yet"}
            />
            <ReadinessChip
              label="Channel"
              ready={channelReady}
              hint={channelReady ? "Listening" : "None connected"}
            />
            <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
              <RefreshCw className={cn("size-4", loading && "animate-spin")} aria-hidden />
              <span className="ml-2">Refresh</span>
            </Button>
          </div>
        </CardBody>
      </Card>

      {error && (
        <p
          className="border-l-2 border-[hsl(var(--warn))] bg-[hsl(var(--warn))]/5 p-3 text-sm"
          role="alert"
        >
          {error}
        </p>
      )}

      {loading && providers.length === 0 && channels.length === 0 && (
        <p className="flex items-center gap-2 text-sm text-mute">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Loading…
        </p>
      )}

      <Section
        kicker="Brain"
        title="Model providers"
        icon={<Brain className="size-4" aria-hidden />}
        manageHref="/providers"
        manageLabel="Manage providers"
        empty="No providers detected — open the manage page to add one."
      >
        {providers.map((p) => (
          <ConnRow
            key={p.name}
            name={p.label || p.name}
            badge={p.local ? "local" : "cloud"}
            connected={p.configured}
            detail={
              p.configured
                ? p.notes || (p.has_api_key ? "Key stored in OS keychain" : "Ready")
                : p.missing.length
                  ? `Missing: ${p.missing.join(", ")}`
                  : "Not configured"
            }
          />
        ))}
      </Section>

      <Section
        kicker="Channels"
        title="Notification & ops channels"
        icon={<Plug className="size-4" aria-hidden />}
        manageHref="/channels"
        manageLabel="Manage channels"
        empty="No channels listed. Open manage to pick one."
      >
        {channels.map((c) => (
          <ConnRow
            key={c.name}
            name={c.label || c.name}
            connected={c.connected}
            detail={
              c.connected
                ? c.notes || "Connected"
                : c.missing.length
                  ? `Missing: ${c.missing.join(", ")}`
                  : "Not connected"
            }
          />
        ))}
      </Section>

      <Card className="p-6">
        <CardBody className="max-w-none text-sm text-mute">
          <p>
            <KeyRound className="mr-1 inline size-3.5 align-text-bottom" aria-hidden />
            Secrets live in the OS keychain (Windows Credential Manager / macOS Keychain /
            libsecret). They are never returned to this page or written to receipts.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

function Section({
  kicker,
  title,
  icon,
  manageHref,
  manageLabel,
  empty,
  children,
}: {
  kicker: string;
  title: string;
  icon: React.ReactNode;
  manageHref: string;
  manageLabel: string;
  empty: string;
  children: React.ReactNode;
}) {
  const items = Array.isArray(children) ? children : [children];
  const hasItems = items.some(Boolean);
  return (
    <Card className="p-6">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardKicker>
              <span className="inline-flex items-center gap-1.5">{icon} {kicker}</span>
            </CardKicker>
            <CardTitle>{title}</CardTitle>
          </div>
          <Link
            to={manageHref}
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            {manageLabel} <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      </CardHeader>
      <CardBody className="max-w-none">
        {hasItems ? (
          <ul className="divide-y divide-rule border-y border-rule">{children}</ul>
        ) : (
          <p className="text-sm text-mute">{empty}</p>
        )}
      </CardBody>
    </Card>
  );
}

function ConnRow({
  name,
  badge,
  connected,
  detail,
}: {
  name: string;
  badge?: string;
  connected: boolean;
  detail: string;
}) {
  return (
    <li className="flex items-start justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-sm font-medium">
          {name}
          {badge && (
            <span className="border border-rule px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
              {badge}
            </span>
          )}
        </p>
        <p className="mt-0.5 truncate text-xs text-mute">{detail}</p>
      </div>
      {connected ? (
        <span className="inline-flex shrink-0 items-center gap-1 border border-accent bg-accent/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
          <CheckCircle2 className="size-3" aria-hidden /> ready
        </span>
      ) : (
        <span className="inline-flex shrink-0 items-center gap-1 border border-rule px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
          <AlertTriangle className="size-3" aria-hidden /> pending
        </span>
      )}
    </li>
  );
}

function ReadinessChip({
  label,
  ready,
  hint,
}: {
  label: string;
  ready: boolean;
  hint: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.08em]",
        ready
          ? "border-accent bg-accent/5 text-accent"
          : "border-rule text-mute",
      )}
    >
      {ready ? (
        <CheckCircle2 className="size-3" aria-hidden />
      ) : (
        <AlertTriangle className="size-3" aria-hidden />
      )}
      <span>{label}</span>
      <span className="text-mute/80 normal-case tracking-normal">— {hint}</span>
    </span>
  );
}
