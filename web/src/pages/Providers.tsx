import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  PlugZap,
  RefreshCw,
  Trash2,
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
  api_key_env: string | null;
  base_url_env: string | null;
  has_api_key: boolean;
  has_base_url: boolean;
  notes: string;
  source: string;
};

type ProvidersResponse = { providers: ProviderStatus[] };
type ProviderWriteResponse = { ok: boolean; provider: ProviderStatus };
type ProviderTestResponse = {
  provider: string;
  ok: boolean;
  live: boolean;
  message: string;
  model: string | null;
  cost_usd: number;
};

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selected, setSelected] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadProviders() {
    const data = await api.get<ProvidersResponse>("/api/providers");
    setProviders(data.providers);
    if (!data.providers.some((p) => p.name === selected) && data.providers[0]) {
      setSelected(data.providers[0].name);
    }
  }

  useEffect(() => {
    loadProviders().catch((err: unknown) => setError(readError(err)));
    // Initial load only; user selection is handled after the fetch resolves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = useMemo(
    () => providers.find((provider) => provider.name === selected),
    [providers, selected],
  );
  const configuredCount = providers.filter((provider) => provider.configured).length;

  async function saveProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const response = await api.post<ProviderWriteResponse>("/api/providers", {
        provider: selected,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
      });
      setApiKey("");
      setNotice(`${response.provider.label} saved. Secret values were not returned.`);
      await loadProviders();
    });
  }

  async function testProvider() {
    await run(async () => {
      const response = await api.post<ProviderTestResponse>("/api/providers/test", {
        provider: selected,
        live,
        model: model || undefined,
      });
      setNotice(`${response.provider}: ${response.message}`);
      await loadProviders();
    });
  }

  async function removeProvider(name: string) {
    await run(async () => {
      const response = await api.delete<ProviderWriteResponse>(`/api/providers/${name}`);
      setNotice(`${response.provider.label} removed from the local vault.`);
      await loadProviders();
    });
  }

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await operation();
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Providers & Keys</CardKicker>
            <CardTitle>Connect your AI</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>
              Paste a key or local endpoint once. MIDAS stores it in the OS keychain,
              forwards only status to the browser, and keeps raw secrets out of model context.
            </p>
            <div className="mt-4 border border-rule bg-rule-soft/35 p-3 text-sm text-mute">
              <p className="font-medium text-ink">Button guide</p>
              <p className="mt-1">
                Save to keychain stores the key locally. Test checks that MIDAS can call
                the provider. Refresh rereads local status. Remove deletes the saved
                connection.
              </p>
            </div>
          </CardBody>
          <form className="mt-6 grid gap-4" onSubmit={saveProvider}>
            <label className="grid gap-1.5 text-sm font-medium">
              Provider
              <select
                className={inputClasses}
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
              >
                {providers.map((provider) => (
                  <option key={provider.name} value={provider.name}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-medium">
                API key
                <input
                  className={inputClasses}
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  disabled={!current?.api_key_env}
                  autoComplete="off"
                  placeholder={current?.api_key_env ?? "No key required"}
                />
              </label>
              <label className="grid gap-1.5 text-sm font-medium">
                Base URL
                <input
                  className={inputClasses}
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  disabled={!current?.base_url_env}
                  placeholder={current?.base_url_env ?? "Managed by provider"}
                />
              </label>
            </div>

            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
              <label className="grid gap-1.5 text-sm font-medium">
                Live-test model
                <input
                  className={inputClasses}
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="ollama/llama3.1 or openai/gpt-4o-mini"
                />
              </label>
              <label className="flex h-9 items-center gap-2 text-sm text-mute">
                <input
                  type="checkbox"
                  checked={live}
                  onChange={(event) => setLive(event.target.checked)}
                />
                Live provider call
              </label>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="primary" disabled={busy}>
                <KeyRound className="size-4" aria-hidden />
                Save to keychain
              </Button>
              <Button type="button" disabled={busy} onClick={testProvider}>
                <PlugZap className="size-4" aria-hidden />
                Test
              </Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={() => run(loadProviders)}>
                <RefreshCw className="size-4" aria-hidden />
                Refresh
              </Button>
            </div>
          </form>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker>Readiness</CardKicker>
            <CardTitle>{configuredCount} ready</CardTitle>
          </CardHeader>
          <CardBody>
            <p>
              Local models count as ready when their default endpoint is usable. Cloud providers
              require a key in the keychain or environment.
            </p>
          </CardBody>
          {current && (
            <dl className="mt-5 space-y-3 text-sm">
              <InfoRow label="Selected" value={current.label} />
              <InfoRow label="Source" value={current.source} />
              <InfoRow label="API env" value={current.api_key_env ?? "none"} />
              <InfoRow label="Base URL env" value={current.base_url_env ?? "none"} />
            </dl>
          )}
        </Card>
      </section>

      <StatusLine error={error} notice={notice} />

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="border-b border-rule bg-rule-soft/50 text-left font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
              <tr>
                <th className="px-4 py-3 font-medium">Provider</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Missing</th>
                <th className="px-4 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => (
                <tr key={provider.name} className="border-b border-rule last:border-b-0">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="text-left font-medium text-ink hover:text-accent"
                      onClick={() => setSelected(provider.name)}
                    >
                      {provider.label}
                    </button>
                    <div className="mt-0.5 font-mono text-xs text-mute">{provider.name}</div>
                  </td>
                  <td className="px-4 py-3">
                    <ProviderBadge configured={provider.configured} local={provider.local} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-mute">{provider.source}</td>
                  <td className="px-4 py-3 font-mono text-xs text-mute">
                    {provider.missing.length ? provider.missing.join(", ") : "none"}
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busy || provider.source === "local-default"}
                      onClick={() => removeProvider(provider.name)}
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute " +
  "disabled:cursor-not-allowed disabled:opacity-55";

function ProviderBadge({ configured, local }: { configured: boolean; local: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2 py-1 font-mono text-xs",
        configured
          ? "border-accent text-accent bg-ok-bg"
          : "border-warn text-warn bg-warn-bg",
      )}
    >
      {configured ? (
        <CheckCircle2 className="size-3.5" aria-hidden />
      ) : (
        <AlertTriangle className="size-3.5" aria-hidden />
      )}
      {configured ? (local ? "local ready" : "ready") : "missing"}
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-rule pb-2">
      <dt className="text-mute">{label}</dt>
      <dd className="font-mono text-xs text-ink">{value}</dd>
    </div>
  );
}

function StatusLine({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return (
    <div
      className={cn(
        "border px-4 py-3 text-sm",
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
