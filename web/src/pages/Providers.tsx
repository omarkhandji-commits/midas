import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ChevronDown,
  ClipboardCopy,
  Cpu,
  HelpCircle,
  PlugZap,
  RefreshCw,
  Search,
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
};

type ProvidersResponse = {
  providers: ProviderStatus[];
  active_models: { cheap: string; smart: string };
};
type DiscoverResponse = { models: string[] };

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [activeModel, setActiveModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Connect form
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [chosenModel, setChosenModel] = useState("");
  const [customModel, setCustomModel] = useState("");

  // Help panel
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpProviderName, setHelpProviderName] = useState("");

  // Switch model inline
  const [editModel, setEditModel] = useState(false);
  const [editValue, setEditValue] = useState("");

  async function loadProviders() {
    const data = await api.get<ProvidersResponse>("/api/providers");
    setProviders(data.providers);
    setActiveModel(data.active_models?.cheap ?? "");
  }

  useEffect(() => {
    loadProviders().catch((err: unknown) => setError(readError(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const configured = useMemo(
    () => providers.filter((p) => p.configured && !p.local),
    [providers],
  );
  const localProviders = useMemo(
    () => providers.filter((p) => p.local && p.configured),
    [providers],
  );

  async function discover() {
    await run(async () => {
      const response = await api.post<DiscoverResponse>(
        "/api/providers/discover-models",
        { base_url: url, api_key: key || undefined },
      );
      if (response.models.length === 0) {
        setNotice("Connected — but the server returned an empty model list. Type the model id manually below.");
      } else {
        setNotice(`Found ${response.models.length} model(s). Pick one or type your own.`);
      }
      setDiscoveredModels(response.models);
      if (response.models.length && !chosenModel) {
        setChosenModel(response.models[0]);
      }
    });
  }

  async function saveAndUse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const model = (customModel.trim() || chosenModel).trim();
    if (!url || !key || !model) {
      setError("Fill URL, API key, and model.");
      return;
    }
    await run(async () => {
      await api.post("/api/providers/quick-connect", {
        base_url: url,
        api_key: key,
        model_name: model,
      });
      setNotice(`Saved. Chat now uses openai/${model} via ${url}.`);
      setKey("");
      setCustomModel("");
      await loadProviders();
    });
  }

  async function useExistingProvider(p: ProviderStatus) {
    await run(async () => {
      await api.post("/api/providers", { provider: p.name });
      setNotice(`${p.label} set as active. Chat will use it on the next message.`);
      await loadProviders();
    });
  }

  async function useModelId(modelId: string) {
    await run(async () => {
      await api.post("/api/providers/use-model", { model_id: modelId });
      setNotice(`Active model is now ${modelId}.`);
      setEditModel(false);
      await loadProviders();
    });
  }

  async function removeProvider(name: string, label: string) {
    await run(async () => {
      await api.delete(`/api/providers/${name}`);
      setNotice(`${label} removed from the keychain.`);
      await loadProviders();
    });
  }

  async function testActive() {
    await run(async () => {
      const providerName = activeModel.includes("/")
        ? activeModel.split("/")[0]
        : "ollama";
      const response = await api.post<{
        ok: boolean;
        message: string;
        model: string | null;
      }>("/api/providers/test", {
        provider: providerName,
        live: true,
        model: activeModel || undefined,
      });
      setNotice(`${response.ok ? "✓" : "✗"} ${response.message}`);
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

  function copyHelpPrompt() {
    const name = helpProviderName.trim() || "<provider-name>";
    const prompt = HELP_PROMPT_TEMPLATE.replace(/<provider>/g, name);
    void navigator.clipboard.writeText(prompt).then(
      () => setNotice("Prompt copied. Paste it into ChatGPT, Claude, or any AI."),
      () => setError("Could not access clipboard."),
    );
  }

  function openSearch() {
    const q = helpProviderName.trim();
    if (!q) {
      setError("Type a provider name first.");
      return;
    }
    const query = encodeURIComponent(`${q} API endpoint key signup developer docs`);
    window.open(`https://duckduckgo.com/?q=${query}`, "_blank", "noopener");
  }

  return (
    <div className="space-y-6">
      <Card className="p-6 border-accent/40">
        <CardHeader>
          <CardKicker>Active LLM</CardKicker>
          <CardTitle className="flex items-baseline gap-3">
            <Cpu className="size-5 self-center text-accent" aria-hidden />
            {editModel ? (
              <input
                className={cn(inputClasses, "flex-1")}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                placeholder="openai/gpt-4o-mini"
                autoFocus
              />
            ) : (
              <span className="font-mono">{activeModel || "Not configured"}</span>
            )}
          </CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <p>
            This is what MIDAS calls for chat, drafts, and scans. Switch any time —
            keys are saved in the OS keychain, never sent to the browser.
          </p>
        </CardBody>
        <div className="mt-4 flex flex-wrap gap-2">
          {editModel ? (
            <>
              <Button
                type="button"
                variant="primary"
                disabled={busy || !editValue.trim()}
                onClick={() => useModelId(editValue.trim())}
              >
                Save
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditModel(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                onClick={() => {
                  setEditValue(activeModel);
                  setEditModel(true);
                }}
              >
                Change model id
              </Button>
              <Button type="button" disabled={busy} onClick={testActive}>
                <PlugZap className="size-4" aria-hidden />
                Test it
              </Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={() => run(loadProviders)}>
                <RefreshCw className="size-4" aria-hidden />
                Refresh
              </Button>
            </>
          )}
        </div>
      </Card>

      <StatusLine error={error} notice={notice} />

      <Card className="p-6">
        <CardHeader>
          <CardKicker>Connect any LLM</CardKicker>
          <CardTitle>One form for every provider</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <p>
            URL, key, model. No hardcoded list — works for OpenAI, Anthropic,
            OpenCode-Zen, Groq, LM Studio, vLLM, Ollama, or any service that
            speaks the OpenAI chat-completions protocol.
          </p>
        </CardBody>
        <form className="mt-3 grid gap-3" onSubmit={saveAndUse}>
          <label className="grid gap-1.5 text-sm font-medium">
            Endpoint URL (ends in /v1 for most)
            <input
              className={inputClasses}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              required
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            API key
            <input
              className={inputClasses}
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
              required
            />
          </label>

          <div>
            <Button
              type="button"
              variant="ghost"
              disabled={busy || !url || !key}
              onClick={discover}
            >
              <Search className="size-4" aria-hidden />
              Discover available models
            </Button>
            <p className="mt-1 text-xs text-mute">
              Calls <code className="text-ink">{url || "<url>"}/models</code> with your key.
            </p>
          </div>

          {discoveredModels.length > 0 && (
            <fieldset className="grid gap-1.5 border border-rule p-3 text-sm">
              <legend className="px-1 font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Pick a model ({discoveredModels.length})
              </legend>
              <div className="grid max-h-64 gap-1.5 overflow-y-auto">
                {discoveredModels.map((m) => (
                  <label key={m} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="model"
                      value={m}
                      checked={chosenModel === m}
                      onChange={() => {
                        setChosenModel(m);
                        setCustomModel("");
                      }}
                    />
                    <span className="font-mono text-xs">{m}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          <label className="grid gap-1.5 text-sm font-medium">
            …or type the model id directly
            <input
              className={inputClasses}
              value={customModel}
              onChange={(e) => {
                setCustomModel(e.target.value);
                if (e.target.value) setChosenModel("");
              }}
              placeholder="gpt-4o-mini / claude-3-5-haiku / llama3.1:8b / ..."
            />
          </label>

          <div className="flex gap-2">
            <Button type="submit" variant="primary" disabled={busy}>
              <Zap className="size-4" aria-hidden />
              Save & use
            </Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => setHelpOpen((o) => !o)}>
              <HelpCircle className="size-4" aria-hidden />
              How do I find these?
            </Button>
          </div>
        </form>

        {helpOpen && <HelpPanel
          name={helpProviderName}
          onName={setHelpProviderName}
          onCopy={copyHelpPrompt}
          onSearch={openSearch}
        />}
      </Card>

      {(configured.length > 0 || localProviders.length > 0) && (
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Connected ({configured.length + localProviders.length})</CardKicker>
            <CardTitle>My LLMs</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>Click <strong>Use this</strong> to switch which one MIDAS uses.</p>
          </CardBody>
          <ul className="mt-3 grid gap-2">
            {localProviders.map((p) => (
              <ConnectedRow
                key={p.name}
                p={p}
                isActive={activeModel.startsWith(`${p.name}/`)}
                busy={busy}
                onUse={() => useExistingProvider(p)}
                onRemove={() => removeProvider(p.name, p.label)}
              />
            ))}
            {configured.map((p) => (
              <ConnectedRow
                key={p.name}
                p={p}
                isActive={
                  activeModel.startsWith(`${p.name}/`) ||
                  (p.name === "openai_compatible" && activeModel.startsWith("openai/"))
                }
                busy={busy}
                onUse={() => useExistingProvider(p)}
                onRemove={() => removeProvider(p.name, p.label)}
              />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function ConnectedRow({
  p,
  isActive,
  busy,
  onUse,
  onRemove,
}: {
  p: ProviderStatus;
  isActive: boolean;
  busy: boolean;
  onUse: () => void;
  onRemove: () => void;
}) {
  return (
    <li
      className={cn(
        "flex items-center justify-between gap-3 border border-rule p-3",
        isActive && "border-accent bg-rule-soft/40",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-display text-sm font-medium">{p.label}</span>
          {isActive ? (
            <span className="border border-accent bg-accent/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-accent">
              Active
            </span>
          ) : (
            <span className="border border-rule px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
              Ready
            </span>
          )}
        </div>
        <div className="font-mono text-[11px] text-mute">{p.source}</div>
      </div>
      <div className="flex shrink-0 gap-1.5">
        {!isActive && (
          <Button type="button" size="sm" disabled={busy} onClick={onUse}>
            Use this
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={onRemove}>
          <Trash2 className="size-3.5" aria-hidden />
        </Button>
      </div>
    </li>
  );
}

function HelpPanel({
  name,
  onName,
  onCopy,
  onSearch,
}: {
  name: string;
  onName: (v: string) => void;
  onCopy: () => void;
  onSearch: () => void;
}) {
  return (
    <div className="mt-4 border border-rule bg-rule-soft/30 p-4">
      <h3 className="mb-2 font-display text-sm font-medium">3 ways to find URL / key / model</h3>
      <label className="grid gap-1.5 text-sm">
        Provider name (e.g. OpenAI, OpenCode-Zen, Together)
        <input
          className={inputClasses}
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="OpenCode-Zen"
        />
      </label>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="border border-rule bg-paper p-3">
          <div className="font-display text-sm font-medium">1. Ask any AI</div>
          <p className="mt-1 text-xs text-mute">
            Copy a structured prompt to your clipboard. Paste it into ChatGPT, Claude,
            Gemini, or any LLM you have access to. Bring back the 3 lines it returns.
          </p>
          <Button type="button" size="sm" className="mt-2" onClick={onCopy}>
            <ClipboardCopy className="size-3.5" aria-hidden />
            Copy the prompt
          </Button>
        </div>

        <div className="border border-rule bg-paper p-3">
          <div className="font-display text-sm font-medium">2. Search the web</div>
          <p className="mt-1 text-xs text-mute">
            Opens a DuckDuckGo search like “{name || "<provider>"} API endpoint key signup
            developer docs”. Skim the first 1-2 results.
          </p>
          <Button type="button" size="sm" className="mt-2" onClick={onSearch}>
            <Search className="size-3.5" aria-hidden />
            Open search
          </Button>
        </div>
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-mute">
          <ChevronDown className="inline size-3" aria-hidden /> Preview the AI prompt
        </summary>
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap border border-rule bg-paper p-3 font-mono text-[11px] text-ink">
          {HELP_PROMPT_TEMPLATE.replace(/<provider>/g, name || "<provider-name>")}
        </pre>
      </details>
    </div>
  );
}

const HELP_PROMPT_TEMPLATE = `I want to use <provider> as an OpenAI-compatible LLM API in a self-hosted agent.
Reply with EXACTLY 4 lines and no other text:

URL: <the base URL ending in /v1, ready to call /v1/chat/completions>
SIGNUP: <the exact URL where I sign up to get my API key>
KEY_PREFIX: <what every valid key starts with, e.g. sk- or sk-ant- or oc->
MODEL: <one cheap-and-fast model id from their current catalog>

If <provider> is not OpenAI-compatible, reply: NOT_OPENAI_COMPATIBLE
If you do not know <provider>, reply: UNKNOWN_PROVIDER
`;

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute " +
  "disabled:cursor-not-allowed disabled:opacity-55";

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
