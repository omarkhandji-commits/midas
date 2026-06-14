import { useState, type FormEvent } from "react";
import { CheckCircle2, Inbox, Send, ShieldCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api, type SseFrame } from "@/lib/api";
import { cn } from "@/lib/utils";

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
type DoneFrame = { proof_level: string; sources: string[]; cost_usd: number };
type ErrorFrame = { code: string; scope?: string; projected?: number; cap?: number };

export function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvals, setApprovals] = useState<ApprovalCard[]>([]);
  const [done, setDone] = useState<DoneFrame | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setDone(null);
    setError(null);

    const nextMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: message },
      { role: "assistant", content: "" },
    ];
    setMessages(nextMessages);

    try {
      await api.streamPost(
        "/api/chat",
        {
          message,
          history: messages.map((item) => ({ role: item.role, content: item.content })),
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
    if (frame.event === "approval") {
      const approval = frame.data;
      if (isApproval(approval)) {
        setApprovals((current) => [approval, ...current]);
      }
    }
    if (frame.event === "done" && isDone(frame.data)) {
      setDone(frame.data);
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

  return (
    <div className="grid min-h-[calc(100vh-150px)] gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="flex min-h-[620px] flex-col border border-rule bg-paper">
        <div className="border-b border-rule px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                Daily Revenue Move
              </p>
              <h1 className="font-display text-2xl font-medium">Proof first chat</h1>
            </div>
            <span className="inline-flex items-center gap-2 border border-accent bg-ok-bg px-2.5 py-1 font-mono text-xs text-accent">
              <ShieldCheck className="size-3.5" aria-hidden />
              Nothing sends without approval
            </span>
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="border border-rule bg-rule-soft/40 p-4 text-sm text-mute">
              Ask for strategy, copy, SEO, outreach, or a decision. MIDAS can draft
              outbound work here, but external actions become approval cards.
            </div>
          )}
          {messages.map((message, index) => (
            <ChatBubble key={`${message.role}-${index}`} message={message} />
          ))}
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
          {done && <ProofStrip done={done} />}
        </div>

        <form className="border-t border-rule p-4" onSubmit={send}>
          <label className="grid gap-2 text-sm font-medium">
            Message
            <textarea
              className="min-h-28 resize-y border border-rule bg-paper p-3 text-sm text-ink placeholder:text-mute"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Find a revenue move, draft an email, or prepare a market decision..."
            />
          </label>
          <div className="mt-3 flex justify-end">
            <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
              <Send className="size-4" aria-hidden />
              Send
            </Button>
          </div>
        </form>
      </section>

      <aside className="space-y-4">
        <Card className="p-5">
          <CardHeader>
            <CardKicker>Approvals</CardKicker>
            <CardTitle>Action rail</CardTitle>
          </CardHeader>
          <CardBody>
            <p>Risky actions proposed in chat appear here and in the main Approval Center.</p>
          </CardBody>
        </Card>
        {approvals.length === 0 ? (
          <div className="border border-rule px-4 py-3 text-sm text-mute">
            No pending chat approvals.
          </div>
        ) : (
          approvals.map((approval) => (
            <ApprovalPanel key={approval.id} approval={approval} onResolve={resolveApproval} />
          ))
        )}
      </aside>
    </div>
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

function ProofStrip({ done }: { done: DoneFrame }) {
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
  onResolve,
}: {
  approval: ApprovalCard;
  onResolve: (id: number, approve: boolean) => Promise<void>;
}) {
  const resolved = approval.status !== "pending";
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
            {resolved && (
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

function isDone(value: unknown): value is DoneFrame {
  return (
    isRecord(value) &&
    typeof value.proof_level === "string" &&
    Array.isArray(value.sources) &&
    typeof value.cost_usd === "number"
  );
}

function errorCopy(error: ErrorFrame): string {
  if (error.code === "budget_exceeded") {
    return `Budget ${error.scope ?? ""} exceeded: $${error.projected ?? 0} > $${error.cap ?? 0}`;
  }
  return "Chat failed before completion.";
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
