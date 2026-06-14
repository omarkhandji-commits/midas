import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Plug, RefreshCw, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type ChannelStatus = {
  name: string;
  label: string;
  connected: boolean;
  live_listener: boolean;
  required: string[];
  missing: string[];
  notes: string;
};

type ChannelsResponse = { channels: ChannelStatus[] };
type ChannelWriteResponse = { ok: boolean; channel: ChannelStatus };
type ChannelTestResponse = { ok: boolean; channel: string; message: string; missing: string[] };

export function ChannelsPage() {
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [botToken, setBotToken] = useState("");
  const [ownerChatId, setOwnerChatId] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await api.get<ChannelsResponse>("/api/channels");
    setChannels(response.channels);
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(readError(err)));
  }, []);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const response = await api.post<ChannelWriteResponse>("/api/channels/telegram", {
        bot_token: botToken,
        owner_chat_id: ownerChatId,
      });
      setBotToken("");
      setNotice(`${response.channel.label} connected.`);
      await load();
    });
  }

  async function testTelegram() {
    await run(async () => {
      const response = await api.post<ChannelTestResponse>("/api/channels/telegram/test");
      setNotice(response.message);
      await load();
    });
  }

  async function removeTelegram() {
    await run(async () => {
      const response = await api.delete<ChannelWriteResponse>("/api/channels/telegram");
      setNotice(`${response.channel.label} removed.`);
      await load();
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

  const telegram = channels.find((channel) => channel.name === "telegram");

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Channel Hub</CardKicker>
          <CardTitle>Telegram</CardTitle>
        </CardHeader>
        <CardBody>
          <p>Owner-gated callbacks use the same ApprovalQueue as the dashboard.</p>
        </CardBody>
        <form className="mt-5 space-y-4" onSubmit={connect}>
          <label className="grid gap-1.5 text-sm font-medium">
            Bot token
            <input
              className={inputClasses}
              type="password"
              autoComplete="off"
              value={botToken}
              onChange={(event) => setBotToken(event.target.value)}
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Owner chat ID
            <input
              className={inputClasses}
              value={ownerChatId}
              onChange={(event) => setOwnerChatId(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" disabled={busy}>
              <Plug className="size-4" aria-hidden />
              Connect
            </Button>
            <Button type="button" disabled={busy} onClick={testTelegram}>
              <Send className="size-4" aria-hidden />
              Test
            </Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => run(load)}>
              <RefreshCw className="size-4" aria-hidden />
              Refresh
            </Button>
            <Button type="button" variant="no" disabled={busy || !telegram?.connected} onClick={removeTelegram}>
              <Trash2 className="size-4" aria-hidden />
              Remove
            </Button>
          </div>
        </form>
        <StatusLine error={error} notice={notice} />
      </Card>

      <section className="grid content-start gap-4">
        {channels.map((channel) => (
          <Card key={channel.name} className="p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold">{channel.label}</h2>
                  <Badge connected={channel.connected} />
                </div>
                <p className="mt-1 text-sm text-mute">{channel.notes}</p>
              </div>
              {channel.live_listener && (
                <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-accent">
                  listener
                </span>
              )}
            </div>
            <div className="mt-4 grid gap-2 md:grid-cols-2">
              <Info label="Required" value={channel.required.join(", ")} />
              <Info label="Missing" value={channel.missing.length ? channel.missing.join(", ") : "none"} />
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}

const inputClasses = "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

function Badge({ connected }: { connected: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2 py-1 font-mono text-xs",
        connected ? "border-accent bg-ok-bg text-accent" : "border-rule bg-rule-soft text-mute",
      )}
    >
      <CheckCircle2 className="size-3.5" aria-hidden />
      {connected ? "connected" : "not connected"}
    </span>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-rule bg-rule-soft/25 p-3">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">{label}</div>
      <div className="mt-1 font-mono text-xs text-ink">{value}</div>
    </div>
  );
}

function StatusLine({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return (
    <div
      className={cn(
        "mt-4 border px-3 py-2 text-sm",
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
