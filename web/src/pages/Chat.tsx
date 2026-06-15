import { useState, type FormEvent } from "react";
import {
  CheckCircle2,
  Inbox,
  PlayCircle,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api, type SseFrame } from "@/lib/api";
import { cn } from "@/lib/utils";

type Mode = "chat" | "do";

type ChatMessage = { role: "user" | "assistant"; content: string };
type ApprovalCard = {
  id: number;
  run_id: string;
  agent: string;
  tool: string;
  action: string;
  summary: string;
  payload: Record<string, unknown>;
  status: string;
  created_ts: string;
};
type StepFrame = {
  tool: string;
  decision: string;
  ran: boolean;
  approval_id: number | null;
  output_summary: string;
  error: string | null;
};
type DoneChatFrame = { proof_level: string; sources: string[]; cost_usd: number };
type DoneDoFrame = {
  run_id: string;
  stopped_reason: string;
  step_count: number;
  queued_approvals: number[];
};
type ErrorFrame = { code: string; scope?: string; projected?: number; cap?: number };
type ExecutedResult = {
  path?: string;
  kind?: string;
  bytes_len?: number;
  sha256_new?: string;
  sha256_prev?: string | null;
};

export function ChatPage() {
  const [mode, setMode] = useState<Mode>("chat");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvals, setApprovals] = useState<ApprovalCard[]>([]);
  const [steps, setSteps] = useState<StepFrame[]>([]);
  const [executed, setExecuted] = useState<Record<number, ExecutedResult>>({});
  const [done, setDone] = useState<DoneChatFrame | null>(null);
  const [doDone, setDoDone] = useState<DoneDoFrame | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setDone(null);
    setDoDone(null);
    setError(null);
    setSteps([]);

    if (mode === "chat") {
      const nextMessages: ChatMessage[] = [
        ...messages,
        { role: "user", content: message },
        { role: "assistant", content: "" },
      ];
      setMessages(nextMessages);
    } else {
      setMessages([...messages, { role: "user", content: message }]);
    }

    try {
      await api.streamPost(
        "/api/chat",
        {
          message,
          mode,
          history:
            mode === "chat"
              ? messages.map((item) => ({ role: item.role, content: item.content }))
              : [],
        },
        handleFrame,
      );
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  function handleFrame(frame: SseFrame) {
    if (frame.event === "delta" && isRecord(frame.data)) {
      const text = String(frame.data.text ?? "");
      setMessages((current) => appendAssistantText(current, text));
    }
    if (frame.event === "step" && isStep(frame.data)) {
      const step = frame.data;
      setSteps((current) => [...current, step]);
    }
    if (frame.event === "approval") {
      const approval = frame.data;
      if (isApproval(approval)) {
        setApprovals((current) => [approval, ...current]);
      }
    }
    if (frame.event === "done") {
      if (isDone(frame.data)) setDone(frame.data);
      if (isDoneDo(frame.data)) setDoDone(frame.data);
    }
    if (frame.event === "error" && isRecord(frame.data)) {
      setError(errorCopy(frame.data as ErrorFrame));
    }
  }

  async function resolveApproval(id: number, approve: boolean) {
    setError(null);
    try {
      await api.post(`/api/approvals/${id}/${approve ? "approve" : "reject"}`);
      setApprovals((current) =>
        current.map((item) =>
          item.id === id ? { ...item, status: approve ? "approved" : "rejected" } : item,
        ),
      );
    } catch (err) {
      setError(readError(err));
    }
  }

  async function executeApproval(id: number) {
    setError(null);
    try {
      const response = await api.post<{ ok: boolean; result: ExecutedResult }>(
        `/api/execute/${id}`,
      );
      setExecuted((current) => ({ ...current, [id]: response.result }));
    } catch (err) {
      setError(readError(err));
    }
  }

  return (
    <div className="grid min-h-[calc(100vh-150px)] gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="flex min-h-[620px] flex-col border border-rule bg-paper">
        <div className="border-b border-rule px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                {mode === "chat" ? "Daily Revenue Move" : "Gated executor"}
              </p>
              <h1 className="font-display text-2xl font-medium">
                {mode === "chat" ? "Proof first chat" : "Do mode"}
              </h1>
            </div>
            <span className="inline-flex items-center gap-2 border border-accent bg-ok-bg px-2.5 py-1 font-mono text-xs text-accent">
              <ShieldCheck className="size-3.5" aria-hidden />
              Nothing sends without approval
            </span>
          </div>
          <ModeToggle mode={mode} onChange={setMode} />
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {mode === "chat" ? (
            <>
              {messages.length === 0 && (
                <div className="border border-rule bg-rule-soft/40 p-4 text-sm text-mute">
                  Ask for strategy, copy, SEO, outreach, or a decision. MIDAS can draft
                  outbound work here, but external actions become approval cards.
                </div>
              )}
              {messages.map((message, index) => (
                <ChatBubble key={`${message.role}-${index}`} message={message} />
              ))}
              {done && <ProofStrip done={done} />}
            </>
          ) : (
            <DoTimeline
              messages={messages}
              steps={steps}
              executed={executed}
              done={doDone}
              busy={busy}
            />
          )}
          {busy && (
            <div className="font-mono text-xs uppercase tracking-[0.08em] text-mute">
              Streaming...
            </div>
          )}
          {error && (
            <div className="border border-warn bg-warn-bg px-4 py-3 text-sm text-warn" role="alert">
              {error}
            </div>
          )}
        </div>

        <form className="border-t border-rule p-4" onSubmit={send}>
          <label className="grid gap-2 text-sm font-medium">
            {mode === "chat" ? "Message" : "Task"}
            <textarea
              className="min-h-28 resize-y border border-rule bg-paper p-3 text-sm text-ink placeholder:text-mute"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                mode === "chat"
                  ? "Find a revenue move, draft an email, or prepare a market decision..."
                  : "Draft an invoice for Acme, 10h consulting at $150..."
              }
            />
          </label>
          <div className="mt-3 flex justify-end">
            <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
              <Send className="size-4" aria-hidden />
              {mode === "chat" ? "Send" : "Run"}
            </Button>
          </div>
        </form>
      </section>

      <aside className="space-y-4">
        <Card className="p-5">
          <CardHeader>
            <CardKicker>Approvals</CardKicker>
            <CardTitle>{mode === "chat" ? "Action rail" : "Gated steps"}</CardTitle>
          </CardHeader>
          <CardBody>
            <p>
              {mode === "chat"
                ? "Risky actions proposed in chat appear here and in the main Approval Center."
                : "Mutating steps queue here with the proposed bytes' sha256. Approve, then Execute to materialize."}
            </p>
          </CardBody>
        </Card>
        {approvals.length === 0 ? (
          <div className="border border-rule px-4 py-3 text-sm text-mute">
            No pending approvals from this run.
          </div>
        ) : (
          approvals.map((approval) => (
            <ApprovalPanel
              key={approval.id}
              approval={approval}
              executed={executed[approval.id]}
              showExecute={mode === "do"}
              onResolve={resolveApproval}
              onExecute={executeApproval}
            />
          ))
        )}
      </aside>
    </div>
  );
}

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Chat mode"
      className="mt-3 inline-flex border border-rule bg-paper text-sm"
    >
      <button
        type="button"
        role="tab"
        aria-selected={mode === "chat"}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em]",
          mode === "chat" ? "bg-rule-soft text-ink" : "text-mute hover:text-ink",
        )}
        onClick={() => onChange("chat")}
      >
        <Sparkles className="size-3.5" aria-hidden />
        Chat
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={mode === "do"}
        className={cn(
          "flex items-center gap-2 border-l border-rule px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em]",
          mode === "do" ? "bg-rule-soft text-ink" : "text-mute hover:text-ink",
        )}
        onClick={() => onChange("do")}
      >
        <Terminal className="size-3.5" aria-hidden />
        Do
      </button>
    </div>
  );
}

function DoTimeline({
  messages,
  steps,
  executed,
  done,
  busy,
}: {
  messages: ChatMessage[];
  steps: StepFrame[];
  executed: Record<number, ExecutedResult>;
  done: DoneDoFrame | null;
  busy: boolean;
}) {
  if (messages.length === 0 && steps.length === 0 && !busy) {
    return (
      <div className="border border-rule bg-rule-soft/40 p-4 text-sm text-mute">
        Describe a task in plain language. MIDAS plans tool steps, runs reads inline,
        and queues every mutation for approval — with the proposed bytes' sha256.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {messages
        .filter((m) => m.role === "user")
        .map((m, i) => (
          <ChatBubble key={`task-${i}`} message={m} />
        ))}
      {steps.map((step, i) => (
        <StepRow key={`step-${i}`} step={step} executed={step.approval_id ? executed[step.approval_id] : undefined} />
      ))}
      {done && (
        <div className="border border-rule bg-rule-soft/35 p-3 font-mono text-xs text-mute">
          {done.step_count} step{done.step_count === 1 ? "" : "s"} ·{" "}
          {done.queued_approvals.length} approval
          {done.queued_approvals.length === 1 ? "" : "s"} queued · stopped:{" "}
          <span className="text-ink">{done.stopped_reason}</span>
        </div>
      )}
    </div>
  );
}

function StepRow({ step, executed }: { step: StepFrame; executed?: ExecutedResult }) {
  const badgeTone =
    step.decision === "allow"
      ? "border-accent text-accent"
      : step.decision === "queue_approval"
      ? "border-rule text-mute"
      : "border-warn text-warn";
  return (
    <article className="border border-rule p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <PlayCircle className="size-4 text-mute" aria-hidden />
          <span className="font-mono text-xs">{step.tool}</span>
        </div>
        <span
          className={cn(
            "border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em]",
            badgeTone,
          )}
        >
          {step.decision}
        </span>
      </div>
      {step.output_summary && (
        <p className="mt-1.5 font-mono text-xs text-mute">{step.output_summary}</p>
      )}
      {step.error && (
        <p className="mt-1.5 font-mono text-xs text-warn">{step.error}</p>
      )}
      {executed?.sha256_new && (
        <p className="mt-1.5 font-mono text-[11px] text-accent">
          executed · sha256 {executed.sha256_new.slice(0, 16)}…
        </p>
      )}
    </article>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article className={cn("max-w-[78ch] border p-4", isUser ? "ml-auto border-ink" : "border-rule")}>
      <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
        {isUser ? "You" : "MIDAS"}
      </p>
      <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p>
    </article>
  );
}

function ProofStrip({ done }: { done: DoneChatFrame }) {
  return (
    <div className="grid gap-2 border border-rule bg-rule-soft/35 p-3 text-sm md:grid-cols-3">
      <Metric label="Proof" value={done.proof_level} />
      <Metric label="Sources" value={done.sources.length ? String(done.sources.length) : "none"} />
      <Metric label="Cost" value={`$${done.cost_usd.toFixed(6)}`} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">{label}</span>
      <span className="font-mono text-xs text-ink">{value}</span>
    </div>
  );
}

function ApprovalPanel({
  approval,
  executed,
  showExecute,
  onResolve,
  onExecute,
}: {
  approval: ApprovalCard;
  executed?: ExecutedResult;
  showExecute: boolean;
  onResolve: (id: number, approve: boolean) => Promise<void>;
  onExecute: (id: number) => Promise<void>;
}) {
  const resolved = approval.status !== "pending";
  const approved = approval.status === "approved";
  const sha256 = typeof approval.payload?.sha256_new === "string"
    ? (approval.payload.sha256_new as string)
    : null;
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <Inbox className="mt-1 size-4 shrink-0 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">{approval.summary}</h2>
            <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
              #{approval.id}
            </span>
          </div>
          <p className="mt-1 font-mono text-xs text-mute">
            {approval.tool} / {approval.action}
          </p>
          {sha256 && (
            <p className="mt-1 font-mono text-[11px] text-accent">
              sha256 {sha256.slice(0, 24)}…
            </p>
          )}
          <pre className="mt-3 max-h-36 overflow-auto border border-rule bg-rule-soft/35 p-3 text-xs text-mute">
            {JSON.stringify(approval.payload, null, 2)}
          </pre>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="ok"
              size="sm"
              disabled={resolved}
              onClick={() => onResolve(approval.id, true)}
            >
              <CheckCircle2 className="size-3.5" aria-hidden />
              Approve
            </Button>
            <Button
              type="button"
              variant="no"
              size="sm"
              disabled={resolved}
              onClick={() => onResolve(approval.id, false)}
            >
              <XCircle className="size-3.5" aria-hidden />
              Reject
            </Button>
            {showExecute && approved && !executed && (
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => onExecute(approval.id)}
              >
                <PlayCircle className="size-3.5" aria-hidden />
                Execute
              </Button>
            )}
            {executed && (
              <span className="inline-flex items-center font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
                executed · {executed.sha256_new?.slice(0, 16)}…
              </span>
            )}
            {resolved && !executed && (
              <span className="inline-flex items-center font-mono text-xs uppercase tracking-[0.08em] text-mute">
                {approval.status}
              </span>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function appendAssistantText(messages: ChatMessage[], text: string): ChatMessage[] {
  const copy = [...messages];
  const last = copy[copy.length - 1];
  if (last?.role === "assistant") {
    copy[copy.length - 1] = { ...last, content: last.content + text };
    return copy;
  }
  return [...copy, { role: "assistant", content: text }];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isApproval(value: unknown): value is ApprovalCard {
  return isRecord(value) && typeof value.id === "number" && typeof value.summary === "string";
}

function isStep(value: unknown): value is StepFrame {
  return (
    isRecord(value) &&
    typeof value.tool === "string" &&
    typeof value.decision === "string" &&
    typeof value.ran === "boolean"
  );
}

function isDone(value: unknown): value is DoneChatFrame {
  return (
    isRecord(value) &&
    typeof value.proof_level === "string" &&
    Array.isArray(value.sources) &&
    typeof value.cost_usd === "number"
  );
}

function isDoneDo(value: unknown): value is DoneDoFrame {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.stopped_reason === "string" &&
    typeof value.step_count === "number" &&
    Array.isArray(value.queued_approvals)
  );
}

function errorCopy(error: ErrorFrame): string {
  if (error.code === "budget_exceeded") {
    return `Budget ${error.scope ?? ""} exceeded: $${error.projected ?? 0} > $${error.cap ?? 0}`;
  }
  if (error.code === "executor_unavailable") {
    return "Do mode requires the executor — configure providers and reload.";
  }
  if (error.code === "do_failed") {
    return "The executor stopped before completion.";
  }
  return "Request failed before completion.";
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
