import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Cpu,
  KeyRound,
  PlugZap,
  RefreshCw,
  Trash2,
  Zap,
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
  tagline: string;
  base_url_default: string | null;
};

type ProvidersResponse = {
  providers: ProviderStatus[];
  active_models: { cheap: string; smart: string };
};
type ProviderWriteResponse = { ok: boolean; provider: ProviderStatus };
type ProviderTestResponse = {
  provider: string;
  ok: boolean;
  live: boolean;
  message: string;
  model: string | null;
  cost_usd: number;
};

// Curated list of providers shown as primary "1-click connect" cards.
// Order matters — most user-friendly first.
const CARD_ORDER: string[] = [
  "ollama",
  "openai",
  "anthropic",
  "opencode_zen",
  "openrouter",
  "groq",
  "deepseek",
  "google",
  "mistral",
];

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [activeCheap, setActiveCheap] = useState("");
  const [activeForKey, setActiveForKey] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advProvider, setAdvProvider] = useState("openai_compatible");
  const [advKey, setAdvKey] = useState("");
  const [advUrl, setAdvUrl] = useState("");
  const [advModel, setAdvModel] = useState("");
  const [testModel, setTestModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadProviders() {
    const data = await api.get<ProvidersResponse>("/api/providers");
    setProviders(data.providers);
    setActiveCheap(data.active_models?.cheap ?? "");
  }

  useEffect(() => {
    loadProviders().catch((err: unknown) => setError(readError(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cardProviders = useMemo(() => {
    const byName = new Map(providers.map((p) => [p.name, p]));
    return CARD_ORDER.map((n) => byName.get(n)).filter(Boolean) as ProviderStatus[];
  }, [providers]);
  const configuredCount = providers.filter((p) => p.configured).length;
  const activeProviderName = useMemo(() => {
    if (!activeCheap.includes("/")) return "";
    return activeCheap.split("/")[0];
  }, [activeCheap]);

  function openConnect(p: ProviderStatus) {
    setActiveForKey(p.name);
    setKeyInput("");
    setUrlInput(p.base_url_default ?? "");
    setError(null);
    setNotice(null);
  }

  async function submitConnect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeForKey) return;
    await run(async () => {
      const response = await api.post<ProviderWriteResponse>("/api/providers", {
        provider: activeForKey,
        api_key: keyInput || undefined,
        base_url: urlInput || undefined,
      });
      setKeyInput("");
      setActiveForKey(null);
      setNotice(
        `${response.provider.label} connected. Chat will use it on the next message.`,
      );
      await loadProviders();
    });
  }

  async function useLocalOllama() {
    await run(async () => {
      await api.post<ProviderWriteResponse>("/api/providers", {
        provider: "ollama",
      });
      setNotice("Ollama set as the active LLM. Make sure the server is running on :11434.");
      await loadProviders();
    });
  }

  async function submitAdvanced(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const response = await api.post<{
        ok: boolean;
        role: string;
        model: string;
        base_url: string;
      }>("/api/providers/quick-connect", {
        base_url: advUrl,
        api_key: advKey,
        model_name: advModel,
      });
      setAdvKey("");
      setNotice(
        `Wired ${response.model} via ${response.base_url}. Chat will use it on the next message.`,
      );
      await loadProviders();
    });
  }

  async function removeProvider(name: string) {
    await run(async () => {
      const response = await api.delete<ProviderWriteResponse>(`/api/providers/${name}`);
      setNotice(`${response.provider.label} removed from the keychain.`);
      await loadProviders();
    });
  }

  async function testActive() {
    await run(async () => {
      const provider = activeProviderName || "ollama";
      const response = await api.post<ProviderTestResponse>("/api/providers/test", {
        provider,
        live: true,
        model: testModel || activeCheap || undefined,
      });
      setNotice(`${response.provider}: ${response.message}`);
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
        <Card className="p-6 border-accent/30">
          <CardHeader>
            <CardKicker>Active LLM</CardKicker>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="size-5 text-accent" aria-hidden />
              {activeCheap || "Not configured"}
            </CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>
              This is the model MIDAS uses for chat, drafts, and scans. Pick another from the
              cards below — your key is saved in the OS keychain, never sent to your browser.
            </p>
          </CardBody>
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <label className="grid flex-1 gap-1.5 text-sm font-medium">
              Live-test model id (optional)
              <input
                className={inputClasses}
                value={testModel}
                onChange={(e) => setTestModel(e.target.value)}
                placeholder={activeCheap || "ollama/llama3.1:8b"}
              />
            </label>
            <Button type="button" disabled={busy} onClick={testActive}>
              <PlugZap className="size-4" aria-hidden />
              Test active
            </Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => run(loadProviders)}>
              <RefreshCw className="size-4" aria-hidden />
              Refresh
            </Button>
          </div>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker>Readiness</CardKicker>
            <CardTitle>{configuredCount} ready</CardTitle>
          </CardHeader>
          <CardBody>
            <p>
              Local models count as ready when their default endpoint is up. Cloud providers
              require a key in the keychain.
            </p>
          </CardBody>
        </Card>
      </section>

      <StatusLine error={error} notice={notice} />

      <section>
        <h2 className="mb-3 font-display text-lg font-medium">Choose your AI</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cardProviders.map((p) => (
            <ProviderCard
              key={p.name}
              provider={p}
              active={p.name === activeProviderName}
              busy={busy}
              onConnect={() => openConnect(p)}
              onUseLocal={p.name === "ollama" ? useLocalOllama : undefined}
              onRemove={() => removeProvider(p.name)}
            />
          ))}
        </div>
      </section>

      {activeForKey && (
        <Card className="p-6 border-accent">
          <CardHeader>
            <CardKicker>Connect</CardKicker>
            <CardTitle>{cardProviders.find((p) => p.name === activeForKey)?.label}</CardTitle>
          </CardHeader>
          <form className="mt-3 grid gap-3" onSubmit={submitConnect}>
            <label className="grid gap-1.5 text-sm font-medium">
              API key
              <input
                className={inputClasses}
                type="password"
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                placeholder="paste it here"
                autoComplete="off"
                required
                autoFocus
              />
            </label>
            {!cardProviders.find((p) => p.name === activeForKey)?.base_url_default && (
              <label className="grid gap-1.5 text-sm font-medium">
                Base URL (optional, only for custom hosts)
                <input
                  className={inputClasses}
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="leave empty for the default"
                />
              </label>
            )}
            <div className="flex gap-2">
              <Button type="submit" variant="primary" disabled={busy}>
                <KeyRound className="size-4" aria-hidden />
                Save to keychain
              </Button>
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => setActiveForKey(null)}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <section>
        <button
          type="button"
          className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.08em] text-mute hover:text-ink"
          onClick={() => setAdvancedOpen((o) => !o)}
        >
          <ChevronDown
            className={cn("size-3.5 transition-transform", advancedOpen && "rotate-180")}
            aria-hidden
          />
          Advanced — connect any other OpenAI-compatible LLM
        </button>

        {advancedOpen && (
          <Card className="mt-3 p-6">
            <CardHeader>
              <CardKicker>Power user</CardKicker>
              <CardTitle>One form, any endpoint</CardTitle>
            </CardHeader>
            <CardBody className="max-w-none">
              <p>
                For LM Studio, vLLM, Together, custom gateways, or any HTTP server that speaks
                the OpenAI chat-completions wire protocol.
              </p>
            </CardBody>
            <form className="mt-3 grid gap-3" onSubmit={submitAdvanced}>
              <label className="grid gap-1.5 text-sm font-medium">
                Endpoint URL
                <input
                  className={inputClasses}
                  value={advUrl}
                  onChange={(e) => setAdvUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  required
                />
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="grid gap-1.5 text-sm font-medium">
                  API key
                  <input
                    className={inputClasses}
                    type="password"
                    value={advKey}
                    onChange={(e) => setAdvKey(e.target.value)}
                    autoComplete="off"
                    required
                  />
                </label>
                <label className="grid gap-1.5 text-sm font-medium">
                  Model id
                  <input
                    className={inputClasses}
                    value={advModel}
                    onChange={(e) => setAdvModel(e.target.value)}
                    placeholder="gpt-4o-mini / llama3.1:8b / ..."
                    required
                  />
                </label>
              </div>
              <div>
                <Button type="submit" variant="primary" disabled={busy}>
                  <Zap className="size-4" aria-hidden />
                  Wire it
                </Button>
              </div>
            </form>

            <h3 className="mt-6 mb-2 font-display text-sm font-medium">
              Other providers ({providers.length - cardProviders.length} more)
            </h3>
            <select
              className={inputClasses}
              value={advProvider}
              onChange={(e) => setAdvProvider(e.target.value)}
            >
              {providers
                .filter((p) => !CARD_ORDER.includes(p.name))
                .map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.label} {p.configured ? "(connected)" : ""}
                  </option>
                ))}
            </select>
          </Card>
        )}
      </section>
    </div>
  );
}

function ProviderCard({
  provider,
  active,
  busy,
  onConnect,
  onUseLocal,
  onRemove,
}: {
  provider: ProviderStatus;
  active: boolean;
  busy: boolean;
  onConnect: () => void;
  onUseLocal?: () => void;
  onRemove: () => void;
}) {
  return (
    <Card
      className={cn(
        "flex flex-col p-4",
        active && "border-accent bg-rule-soft/40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-display text-base font-medium">{provider.label}</div>
          <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
            {provider.name}
          </div>
        </div>
        <ProviderBadge configured={provider.configured} local={provider.local} active={active} />
      </div>
      {provider.tagline && (
        <p className="mt-2 text-sm text-mute">{provider.tagline}</p>
      )}
      <div className="mt-auto flex gap-2 pt-3">
        {onUseLocal && (
          <Button type="button" variant="primary" size="sm" disabled={busy} onClick={onUseLocal}>
            <Cpu className="size-3.5" aria-hidden />
            Use local
          </Button>
        )}
        {provider.api_key_env && (
          <Button
            type="button"
            variant={provider.configured ? "ghost" : "primary"}
            size="sm"
            disabled={busy}
            onClick={onConnect}
          >
            <KeyRound className="size-3.5" aria-hidden />
            {provider.configured ? "Update key" : "Connect"}
          </Button>
        )}
        {provider.configured && provider.source !== "local-default" && (
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={onRemove}>
            <Trash2 className="size-3.5" aria-hidden />
          </Button>
        )}
      </div>
    </Card>
  );
}

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute " +
  "disabled:cursor-not-allowed disabled:opacity-55";

function ProviderBadge({
  configured,
  local,
  active,
}: {
  configured: boolean;
  local: boolean;
  active: boolean;
}) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1 border border-accent bg-accent/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
        <Cpu className="size-3" aria-hidden />
        Active
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em]",
        configured
          ? "border-accent text-accent bg-ok-bg"
          : "border-rule text-mute",
      )}
    >
      {configured ? (
        <CheckCircle2 className="size-3" aria-hidden />
      ) : (
        <AlertTriangle className="size-3" aria-hidden />
      )}
      {configured ? (local ? "local ready" : "ready") : "no key"}
    </span>
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
