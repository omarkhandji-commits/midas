import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  Compass,
  KeyRound,
  Loader2,
  MessageSquare,
  Plug,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";

type DetectResult = { models: string[]; chosen: string | null };
type StateResult = {
  has_provider: boolean;
  has_channel: boolean;
  has_first_run: boolean;
};
type ProviderTestResult = {
  ok: boolean;
  live: boolean;
  provider: string;
  message: string;
  cost_usd?: number;
};
type ProviderAddResult = {
  provider: {
    name: string;
    label: string;
    configured: boolean;
    has_api_key: boolean;
  };
};
type ChannelStatus = {
  name: string;
  label?: string;
  connected: boolean;
  missing?: string[];
};
type MissionResult = { ok: boolean; mission?: unknown };

type Step = 1 | 2 | 3 | 4;

const STEPS: { id: Step; title: string; subtitle: string; icon: typeof KeyRound }[] = [
  { id: 1, title: "Connect your model", subtitle: "Local Ollama or one API key", icon: KeyRound },
  { id: 2, title: "Choose a notification path", subtitle: "Optional", icon: Plug },
  { id: 3, title: "How Midas works", subtitle: "Read once, drives every action", icon: Sparkles },
  { id: 4, title: "Your first action", subtitle: "A real cash move", icon: Compass },
];

const inputClasses =
  "border border-rule bg-paper px-3 py-2 text-sm font-mono outline-none focus:border-accent transition-colors";

export function OnboardingPage() {
  const [step, setStep] = useState<Step>(1);
  const [resumeChecked, setResumeChecked] = useState(false);

  // Resume into the right step if the user already did some of this.
  useEffect(() => {
    if (resumeChecked) return;
    api
      .get<StateResult>("/api/onboard/state")
      .then((s) => {
        if (s.has_first_run) setStep(4);
        else if (s.has_channel) setStep(3);
        else if (s.has_provider) setStep(2);
        else setStep(1);
      })
      .catch(() => {
        // Stay at step 1 on any error — the user can still proceed manually.
      })
      .finally(() => setResumeChecked(true));
  }, [resumeChecked]);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Start</CardKicker>
            <CardTitle>Get ready in four short steps</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>
              Set a model, pick how you want to be notified, then run one real action.
              Every step that touches the outside world waits for your approval first.
            </p>
          </CardBody>
        </Card>

        <Card className="p-5">
          <CardHeader>
            <CardKicker>Invariant</CardKicker>
            <CardTitle>Approval-default</CardTitle>
          </CardHeader>
          <CardBody>
            <p>
              Public posts, money movement, outbound messages, and file writes always
              pause for your click. Midas drafts; you approve; Midas acts.
            </p>
          </CardBody>
        </Card>
      </section>

      <Stepper step={step} onJump={setStep} />

      {step === 1 && <StepBrain onDone={() => setStep(2)} />}
      {step === 2 && <StepChannel onSkip={() => setStep(3)} onDone={() => setStep(3)} />}
      {step === 3 && <StepExplain onDone={() => setStep(4)} />}
      {step === 4 && <StepFirstAction />}
    </div>
  );
}

function Stepper({ step, onJump }: { step: Step; onJump: (s: Step) => void }) {
  return (
    <ol className="grid gap-3 md:grid-cols-4">
      {STEPS.map((s) => {
        const done = s.id < step;
        const active = s.id === step;
        return (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onJump(s.id)}
              className={`group w-full border p-3 text-left transition-colors ${
                active
                  ? "border-accent bg-accent/5"
                  : done
                  ? "border-rule bg-rule-soft/30"
                  : "border-rule bg-paper hover:bg-rule-soft/20"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                  Step {s.id}
                </span>
                {done && <CheckCircle2 className="size-3.5 text-accent" aria-hidden />}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <s.icon className="size-4 text-accent" aria-hidden />
                <span className="text-sm font-semibold">{s.title}</span>
              </div>
              <p className="mt-1 text-xs text-mute">{s.subtitle}</p>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ── Step 1: brain (Ollama auto-detect OR paste cloud key) ──────────────────────
function StepBrain({ onDone }: { onDone: () => void }) {
  const [detect, setDetect] = useState<DetectResult | null>(null);
  const [detecting, setDetecting] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [chosenProvider, setChosenProvider] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<DetectResult>("/api/onboard/detect-ollama")
      .then(setDetect)
      .catch(() => setDetect({ models: [], chosen: null }))
      .finally(() => setDetecting(false));
  }, []);

  const providerFromKey = useMemo(() => providerFromPrefix(apiKey.trim()), [apiKey]);

  const useLocal = () => {
    if (!detect?.chosen) return;
    setNotice(`Using local model: ollama/${detect.chosen}. No API key needed.`);
    // Local Ollama is already wired by `midas init` — there's nothing to POST.
    onDone();
  };

  const useKey = async () => {
    setError(null);
    setNotice(null);
    const guess = providerFromKey;
    if (!guess) {
      setError("This key prefix is not recognized. Paste an OpenAI, Anthropic, OpenRouter, Groq, or Google key.");
      return;
    }
    setChosenProvider(guess);
    setBusy(true);
    try {
      const added = await api.post<ProviderAddResult>("/api/providers", {
        provider: guess,
        api_key: apiKey.trim(),
      });
      if (!added.provider.configured) {
        setError("Saved, but the provider still reports missing fields. Check the key.");
        return;
      }
      const test = await api.post<ProviderTestResult>("/api/providers/test", {
        provider: guess,
        live: true,
      });
      if (test.ok) {
        setNotice(`Connected ${guess}. ${test.message || ""}`);
        setApiKey("");
        setTimeout(onDone, 600);
      } else {
        setError(`Live test failed: ${test.message || "no response"}`);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the key.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-6">
      <CardHeader>
        <CardKicker>Step 1</CardKicker>
        <CardTitle>Connect your model</CardTitle>
      </CardHeader>
      <CardBody>
        {detecting ? (
          <p className="flex items-center gap-2 text-sm text-mute">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Looking for a local Ollama…
          </p>
        ) : detect?.chosen ? (
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
            <div>
              <p className="text-sm">
                Local model detected: <code className="font-mono text-accent">ollama/{detect.chosen}</code>
              </p>
              <p className="mt-1 text-xs text-mute">
                Runs on your machine. No key, no token cost. Recommended for first use.
              </p>
            </div>
            <Button variant="primary" onClick={useLocal}>
              Use this
              <ChevronRight className="size-4" aria-hidden />
            </Button>
          </div>
        ) : (
          <p className="text-sm text-mute">
            No local model running. Paste a cloud API key below — provider is detected
            from the prefix.
          </p>
        )}

        <div className="my-5 h-px bg-rule" />

        <div className="grid gap-3">
          <label className="grid gap-1.5 text-sm font-medium">
            Cloud API key
            <input
              className={inputClasses}
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-… (OpenAI) · sk-ant-… (Anthropic) · sk-or-… (OpenRouter) · gsk_… (Groq) · AIza… (Google)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={busy}
            />
            {providerFromKey && (
              <span className="font-mono text-xs text-accent">
                detected → {providerFromKey}
              </span>
            )}
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              onClick={useKey}
              disabled={busy || !apiKey.trim()}
            >
              {busy ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden /> Saving and testing…
                </>
              ) : (
                <>
                  <Bot className="size-4" aria-hidden /> Connect{chosenProvider ? ` ${chosenProvider}` : ""}
                </>
              )}
            </Button>
            <Button variant="ghost" asChild>
              <Link to="/providers">More options</Link>
            </Button>
          </div>
        </div>

        {notice && (
          <p className="mt-4 border-l-2 border-accent bg-accent/5 p-3 text-sm" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p
            className="mt-4 border-l-2 border-[hsl(var(--warn))] bg-[hsl(var(--warn))]/5 p-3 text-sm"
            role="alert"
          >
            {error}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

// ── Step 2: optional notification channel ──────────────────────────────────────
function StepChannel({ onDone, onSkip }: { onDone: () => void; onSkip: () => void }) {
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<{ channels: ChannelStatus[] }>("/api/channels")
      .then((r) => setChannels(r.channels))
      .catch(() => setChannels([]))
      .finally(() => setLoading(false));
  }, []);

  const hasOne = channels.some((c) => c.connected);

  return (
    <Card className="p-6">
      <CardHeader>
        <CardKicker>Step 2</CardKicker>
        <CardTitle>Pick how you want to be notified</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="text-sm text-mute">
          When Midas needs your approval (publishing, sending, paying), it can ping you
          on Telegram, Discord, Slack, WhatsApp, SMS, or email. This step is optional —
          you can always approve from this dashboard.
        </p>
        {loading ? (
          <p className="mt-4 flex items-center gap-2 text-sm text-mute">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Reading channel status…
          </p>
        ) : (
          <ul className="mt-4 grid gap-2 md:grid-cols-2">
            {channels.slice(0, 6).map((c) => (
              <li
                key={c.name}
                className="flex items-center justify-between border border-rule bg-paper p-3"
              >
                <span className="text-sm font-medium">{c.label || c.name}</span>
                <span
                  className={`text-xs font-mono ${
                    c.connected ? "text-accent" : "text-mute"
                  }`}
                >
                  {c.connected ? "connected" : "not set"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          <Button asChild variant="primary">
            <Link to="/channels">Open the Channels page</Link>
          </Button>
          <Button onClick={hasOne ? onDone : onSkip} variant={hasOne ? "primary" : "ghost"}>
            {hasOne ? "Continue" : "Skip for now"}
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

// ── Step 3: explain the loop in 30 seconds ─────────────────────────────────────
function StepExplain({ onDone }: { onDone: () => void }) {
  return (
    <Card className="p-6">
      <CardHeader>
        <CardKicker>Step 3</CardKicker>
        <CardTitle>How Midas works in 30 seconds</CardTitle>
      </CardHeader>
      <CardBody>
        <ol className="grid gap-3 md:grid-cols-5">
          {[
            ["Scan", "Read your niche, score moves."],
            ["Draft", "Prepare assets locally."],
            ["Approve", "You click before any send."],
            ["Execute", "Midas materializes the action."],
            ["Measure", "Cost from receipts, revenue from outcomes."],
          ].map(([title, body]) => (
            <li key={title} className="border border-rule bg-paper p-3">
              <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                {title}
              </p>
              <p className="mt-1 text-sm">{body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-sm">
          Every step writes a signed receipt. The chain is verifiable offline. If a fetched
          page or a third-party tool tries to inject instructions, the sentinel refuses.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="primary" onClick={onDone}>
            I'm ready to try
            <ChevronRight className="size-4" aria-hidden />
          </Button>
          <Button variant="ghost" asChild>
            <Link to="/capabilities">See every capability</Link>
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

// ── Step 4: first real action ──────────────────────────────────────────────────
function StepFirstAction() {
  const [niche, setNiche] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null);
    setNotice(null);
    if (!niche.trim()) {
      setError("Type a niche, e.g. \"local plumbers Montreal\".");
      return;
    }
    setBusy(true);
    try {
      await api.post<MissionResult>("/api/missions", {
        niche: niche.trim(),
        live: true,
        mode: "fast",
      });
      setNotice(
        "Mission queued. Open the Chat or the Approval Center to see what Midas prepared.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the mission.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-6">
      <CardHeader>
        <CardKicker>Step 4</CardKicker>
        <CardTitle>Try a real cash move</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="text-sm text-mute">
          Type a niche. Midas scans, scores, drafts a daily revenue move, and queues an
          approval card. Nothing leaves your machine without your click.
        </p>
        <div className="mt-4 grid gap-3">
          <label className="grid gap-1.5 text-sm font-medium">
            Your niche
            <input
              className={inputClasses}
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              placeholder='e.g. "freelance copywriters", "Montreal dentists"…'
              disabled={busy}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={run} disabled={busy}>
              {busy ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden /> Running…
                </>
              ) : (
                <>
                  <Compass className="size-4" aria-hidden /> Run the mission
                </>
              )}
            </Button>
            <Button asChild variant="ghost">
              <Link to="/">
                <MessageSquare className="size-4" aria-hidden /> Open the chat
              </Link>
            </Button>
          </div>
        </div>
        {notice && (
          <p className="mt-4 border-l-2 border-accent bg-accent/5 p-3 text-sm" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p
            className="mt-4 border-l-2 border-[hsl(var(--warn))] bg-[hsl(var(--warn))]/5 p-3 text-sm"
            role="alert"
          >
            {error}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

// Mirrors src/midas/flagship/provider_defaults.py — kept here for instant UI
// feedback. The backend remains the source of truth (always re-validates).
function providerFromPrefix(key: string): string | null {
  if (!key) return null;
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-or-")) return "openrouter";
  if (key.startsWith("gsk_")) return "groq";
  if (key.startsWith("sk-proj-") || key.startsWith("sk-")) return "openai";
  if (key.startsWith("AIza")) return "google";
  return null;
}
