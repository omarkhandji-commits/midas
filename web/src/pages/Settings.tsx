import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Download,
  Gauge,
  Languages,
  Moon,
  Save,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

type DashboardSettings = {
  per_task_cap: number;
  daily_cap: number;
  monthly_cap: number;
  autonomy: "propose-only" | "semi-auto" | "full-auto-guarded";
  theme: "system" | "light" | "dark";
  language: "en" | "fr";
};

type SettingsResponse = { settings: DashboardSettings };
type SettingsWriteResponse = { ok: boolean; settings: DashboardSettings };

const defaults: DashboardSettings = {
  per_task_cap: 0.25,
  daily_cap: 2,
  monthly_cap: 30,
  autonomy: "semi-auto",
  theme: "system",
  language: "en",
};

export function SettingsPage() {
  const [settings, setSettings] = useState<DashboardSettings>(defaults);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<SettingsResponse>("/api/settings")
      .then((data) => setSettings(data.settings))
      .catch((err: unknown) => setError(readError(err)));
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await api.post<SettingsWriteResponse>("/api/settings", settings);
      setSettings(response.settings);
      setNotice("Settings saved locally.");
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
    <form className="space-y-6" onSubmit={save}>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Settings</CardKicker>
            <CardTitle>Budget and autonomy guardrails</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>
              These caps are product-level defaults for dashboard runs. External sends,
              public posts, payments, and legal-risk actions still require approval.
            </p>
          </CardBody>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <NumberField
              label="Per task cap"
              value={settings.per_task_cap}
              onChange={(value) => setSettings({ ...settings, per_task_cap: value })}
            />
            <NumberField
              label="Daily cap"
              value={settings.daily_cap}
              onChange={(value) => setSettings({ ...settings, daily_cap: value })}
            />
            <NumberField
              label="Monthly cap"
              value={settings.monthly_cap}
              onChange={(value) => setSettings({ ...settings, monthly_cap: value })}
            />
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <label className="grid gap-1.5 text-sm font-medium">
              Autonomy
              <select
                className={inputClasses}
                value={settings.autonomy}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    autonomy: event.target.value as DashboardSettings["autonomy"],
                  })
                }
              >
                <option value="propose-only">Propose only</option>
                <option value="semi-auto">Semi-auto</option>
                <option value="full-auto-guarded">Full-auto guarded</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Theme
              <select
                className={inputClasses}
                value={settings.theme}
                onChange={(event) =>
                  setSettings({ ...settings, theme: event.target.value as DashboardSettings["theme"] })
                }
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Language
              <select
                className={inputClasses}
                value={settings.language}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    language: event.target.value as DashboardSettings["language"],
                  })
                }
              >
                <option value="en">English</option>
                <option value="fr">Francais</option>
              </select>
            </label>
          </div>

          <div className="mt-6">
            <Button type="submit" variant="primary" disabled={busy}>
              <Save className="size-4" aria-hidden />
              Save settings
            </Button>
          </div>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker>Operating mode</CardKicker>
            <CardTitle>{modeLabel(settings.autonomy)}</CardTitle>
          </CardHeader>
          <CardBody>
            <p>{modeCopy(settings.autonomy)}</p>
          </CardBody>
          <div className="mt-5 grid gap-3 text-sm">
            <SettingSignal icon={Gauge} label="Per task" value={formatCurrency(settings.per_task_cap)} />
            <SettingSignal icon={ShieldCheck} label="Daily" value={formatCurrency(settings.daily_cap)} />
            <SettingSignal icon={Moon} label="Theme" value={settings.theme} />
            <SettingSignal icon={Languages} label="Language" value={settings.language.toUpperCase()} />
          </div>
        </Card>
      </div>

      <StatusLine error={error} notice={notice} />
    </form>
    <BackupSection />
    </div>
  );
}

function BackupSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function downloadExport() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await api.get<unknown>("/api/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      link.download = `midas-export-${stamp}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      setNotice("Backup downloaded.");
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  async function importFile(file: File) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const text = await file.text();
      const body = JSON.parse(text);
      const res = await api.post<{ ok: boolean; approval_id: number }>(
        "/api/import",
        body,
      );
      setNotice(
        `Restore queued for approval (#${res.approval_id}). Confirm from the Approvals page.`,
      );
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <Card className="p-6">
      <CardHeader>
        <CardKicker>Backup</CardKicker>
        <CardTitle>Export and restore</CardTitle>
      </CardHeader>
      <CardBody>
        Export bundles your memory, competitors, schedules, and skills metadata as a JSON
        file you keep yourself. Restore queues an approval — the data is never applied
        without your explicit confirmation.
      </CardBody>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button type="button" variant="primary" disabled={busy} onClick={downloadExport}>
          <Download className="size-4" aria-hidden />
          Download backup
        </Button>
        <Button
          type="button"
          variant="default"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          <Upload className="size-4" aria-hidden />
          Restore from file
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) importFile(file).catch(() => undefined);
          }}
        />
      </div>
      <StatusLine error={error} notice={notice} />
    </Card>
  );
}

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      {label}
      <input
        className={inputClasses}
        type="number"
        min="0.0001"
        step="0.0001"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function SettingSignal({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Gauge;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-rule pb-2">
      <span className="inline-flex items-center gap-2 text-mute">
        <Icon className="size-4" aria-hidden />
        {label}
      </span>
      <span className="font-mono text-xs text-ink">{value}</span>
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

function modeLabel(mode: DashboardSettings["autonomy"]): string {
  if (mode === "propose-only") return "Propose only";
  if (mode === "full-auto-guarded") return "Guarded full-auto";
  return "Semi-auto";
}

function modeCopy(mode: DashboardSettings["autonomy"]): string {
  if (mode === "propose-only") {
    return "MIDAS prepares drafts and decisions, then stops for the operator.";
  }
  if (mode === "full-auto-guarded") {
    return "Only low-risk local actions may run. Risky work still enters approvals.";
  }
  return "Default mode: research and draft freely, require approval for outbound or risky actions.";
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
