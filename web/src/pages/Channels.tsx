import { useEffect, useMemo, useState, type FormEvent } from "react";
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

type Field = {
  key: string;
  label: string;
  type?: "text" | "password" | "email" | "tel";
  placeholder?: string;
};

type ChannelsResponse = { channels: ChannelStatus[] };
type ChannelWriteResponse = { ok: boolean; channel: ChannelStatus };
type ChannelTestResponse = { ok: boolean; channel: string; message: string; missing: string[] };

const fieldSets: Record<string, Field[]> = {
  telegram: [
    { key: "bot_token", label: "Bot token", type: "password" },
    { key: "owner_chat_id", label: "Owner chat ID" },
  ],
  discord: [
    { key: "bot_token", label: "Bot token", type: "password" },
    { key: "owner_user_id", label: "Owner user ID" },
    { key: "guild_id", label: "Guild ID", placeholder: "optional" },
  ],
  slack: [
    { key: "bot_token", label: "Bot token", type: "password" },
    { key: "owner_user_id", label: "Owner user ID" },
    { key: "signing_secret", label: "Signing secret", type: "password", placeholder: "optional" },
  ],
  whatsapp: [
    { key: "access_token", label: "Access token", type: "password" },
    { key: "owner_phone", label: "Owner phone", type: "tel" },
    { key: "phone_number_id", label: "Phone number ID" },
  ],
  email: [
    { key: "owner_email", label: "Owner email", type: "email" },
    { key: "smtp_host", label: "SMTP host", placeholder: "optional, draft-only" },
    { key: "smtp_user", label: "SMTP user", placeholder: "optional" },
    { key: "smtp_pass", label: "SMTP password", type: "password", placeholder: "optional" },
  ],
  sms: [
    { key: "account_sid", label: "Account SID" },
    { key: "auth_token", label: "Auth token", type: "password" },
    { key: "from_number", label: "From number", type: "tel" },
    { key: "owner_phone", label: "Owner phone", type: "tel" },
  ],
};

export function ChannelsPage() {
  const [channels, setChannels] = useState<ChannelStatus[]>([]);
  const [selected, setSelected] = useState("telegram");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await api.get<ChannelsResponse>("/api/channels");
    setChannels(response.channels);
    if (!response.channels.some((channel) => channel.name === selected) && response.channels[0]) {
      setSelected(response.channels[0].name);
    }
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(readError(err)));
    // Initial load only; selected is reconciled after the fetch resolves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedChannel = useMemo(
    () => channels.find((channel) => channel.name === selected),
    [channels, selected],
  );
  const fields = fieldSets[selected] ?? [];

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const response = await api.post<ChannelWriteResponse>(
        `/api/channels/${selected}`,
        values,
      );
      setValues({});
      setNotice(`${response.channel.label} connected.`);
      await load();
    });
  }

  async function testSelected() {
    await run(async () => {
      const response = await api.post<ChannelTestResponse>(`/api/channels/${selected}/test`);
      setNotice(response.message);
      await load();
    });
  }

  async function removeSelected() {
    await run(async () => {
      const response = await api.delete<ChannelWriteResponse>(`/api/channels/${selected}`);
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

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Channel Hub</CardKicker>
          <CardTitle>{selectedChannel?.label ?? "Channel"}</CardTitle>
        </CardHeader>
        <CardBody>
          <p>
            Owner-gated callbacks use the same ApprovalQueue as the dashboard. Email
            remains draft-only; outbound messages require an approval card.
          </p>
          <div className="mt-4 border border-rule bg-rule-soft/35 p-3 text-sm text-mute">
            <p className="font-medium text-ink">Button guide</p>
            <p className="mt-1">
              Connect saves this channel locally. Test checks the connection. Refresh
              rereads status. Remove disconnects the channel. You can skip channels and
              still approve from the dashboard.
            </p>
          </div>
        </CardBody>
        <form className="mt-5 space-y-4" onSubmit={connect}>
          <label className="grid gap-1.5 text-sm font-medium">
            Channel
            <select
              className={inputClasses}
              value={selected}
              onChange={(event) => {
                setSelected(event.target.value);
                setValues({});
              }}
            >
              {channels.map((channel) => (
                <option key={channel.name} value={channel.name}>
                  {channel.label}
                </option>
              ))}
            </select>
          </label>

          {fields.map((field) => (
            <label key={field.key} className="grid gap-1.5 text-sm font-medium">
              {field.label}
              <input
                className={inputClasses}
                type={field.type ?? "text"}
                autoComplete="off"
                value={values[field.key] ?? ""}
                placeholder={field.placeholder}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.key]: event.target.value }))
                }
              />
            </label>
          ))}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" disabled={busy}>
              <Plug className="size-4" aria-hidden />
              Connect
            </Button>
            <Button type="button" disabled={busy} onClick={testSelected}>
              <Send className="size-4" aria-hidden />
              Test
            </Button>
            <Button type="button" variant="ghost" disabled={busy} onClick={() => run(load)}>
              <RefreshCw className="size-4" aria-hidden />
              Refresh
            </Button>
            <Button
              type="button"
              variant="no"
              disabled={busy || !selectedChannel?.connected}
              onClick={removeSelected}
            >
              <Trash2 className="size-4" aria-hidden />
              Remove
            </Button>
          </div>
        </form>
        <StatusLine error={error} notice={notice} />
      </Card>

      <section className="grid content-start gap-4">
        {channels.map((channel) => (
          <Card
            key={channel.name}
            className={`p-5 ${selected === channel.name ? "border-accent" : ""}`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="text-base font-semibold hover:text-accent"
                    onClick={() => {
                      setSelected(channel.name);
                      setValues({});
                    }}
                  >
                    {channel.label}
                  </button>
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
              <Info
                label="Missing"
                value={channel.missing.length ? channel.missing.join(", ") : "none"}
              />
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
