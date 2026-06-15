import { useEffect, useState, type FormEvent } from "react";
import { FileSearch, Plus, ShieldAlert, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Skill = {
  name: string;
  version: string;
  summary: string;
  permissions: string[];
  source: string;
  sha256: string;
};

type MediaInspection = {
  path: string;
  kind: string;
  size_bytes: number;
  sha256: string;
  text: string;
  warnings: string[];
};

const inputClasses =
  "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // create form
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [perms, setPerms] = useState("read");

  // remote download
  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteReason, setRemoteReason] = useState("");

  // multimodal inspect
  const [inspectPath, setInspectPath] = useState("");
  const [inspection, setInspection] = useState<MediaInspection | null>(null);

  async function load() {
    const res = await api.get<{ skills: Skill[] }>("/api/skills");
    setSkills(res.skills);
  }

  useEffect(() => {
    run(load).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createSkill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const res = await api.post<{ ok: boolean; skill: Skill }>("/api/skills", {
        name: name.trim(),
        summary: summary.trim(),
        permissions: perms
          .split(/[\s,]/)
          .map((p) => p.trim())
          .filter(Boolean),
      });
      setNotice(`Skill "${res.skill.name}" created.`);
      setName("");
      setSummary("");
      await load();
    });
  }

  async function removeSkill(target: string) {
    await run(async () => {
      await api.delete(`/api/skills/${encodeURIComponent(target)}`);
      setNotice(`Skill "${target}" removed.`);
      await load();
    });
  }

  async function planRemote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const res = await api.post<{ ok: boolean; approval_id: number }>(
        "/api/skills/plan-download",
        { url: remoteUrl.trim(), reason: remoteReason.trim() },
      );
      setNotice(`Remote download queued for approval (#${res.approval_id}).`);
      setRemoteUrl("");
      setRemoteReason("");
    });
  }

  async function inspectFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const res = await api.post<{ ok: boolean; media: MediaInspection }>(
        "/api/multimodal/inspect",
        { path: inspectPath.trim() },
      );
      setInspection(res.media);
      setNotice(`Inspected ${res.media.kind} (${formatBytes(res.media.size_bytes)}).`);
    });
  }

  async function run(op: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await op();
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Skills</CardKicker>
          <CardTitle>Approval-gated local skills</CardTitle>
        </CardHeader>
        <CardBody>
          Local skills are folders with a manifest and a <code>SKILL.md</code>. Executable
          payloads (<code>.exe</code>, <code>.dll</code>, <code>.bat</code>, …) are rejected at
          install. Remote sources require an explicit approval before download.
        </CardBody>
        <StatusLine error={error} notice={notice} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>New skill</CardKicker>
            <CardTitle>Create locally</CardTitle>
          </CardHeader>
          <form className="mt-4 space-y-3" onSubmit={createSkill}>
            <label className="grid gap-1.5 text-sm font-medium">
              Name
              <input
                className={inputClasses}
                type="text"
                placeholder="market-radar-pro"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Summary
              <input
                className={inputClasses}
                type="text"
                placeholder="Track competitors and summarize opportunities."
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Permissions (comma-separated)
              <input
                className={inputClasses}
                type="text"
                value={perms}
                onChange={(event) => setPerms(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <Plus className="size-4" aria-hidden />
              Create
            </Button>
          </form>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker>Remote skill</CardKicker>
            <CardTitle>Plan a download</CardTitle>
          </CardHeader>
          <CardBody>
            Remote installs never happen automatically. MIDAS queues an approval request
            so you can inspect the source before download.
          </CardBody>
          <form className="mt-4 space-y-3" onSubmit={planRemote}>
            <label className="grid gap-1.5 text-sm font-medium">
              URL
              <input
                className={inputClasses}
                type="url"
                placeholder="https://github.com/owner/skill.git"
                value={remoteUrl}
                onChange={(event) => setRemoteUrl(event.target.value)}
                required
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Reason
              <input
                className={inputClasses}
                type="text"
                value={remoteReason}
                onChange={(event) => setRemoteReason(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              <ShieldAlert className="size-4" aria-hidden />
              Plan download
            </Button>
          </form>
        </Card>
      </div>

      <Card className="p-5">
        <div className="mb-2 flex items-center gap-2">
          <Sparkles className="size-4 text-accent" aria-hidden />
          <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
            Installed · {skills.length}
          </span>
        </div>
        {skills.length === 0 && <p className="text-sm text-mute">No skill installed yet.</p>}
        <ul className="divide-y divide-rule">
          {skills.map((s) => (
            <li key={s.name} className="flex items-start justify-between gap-3 py-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-ink">{s.name}</span>
                  <span className="border border-rule px-1.5 font-mono text-[10px] text-mute">
                    v{s.version}
                  </span>
                  {s.permissions.map((p) => (
                    <span
                      key={p}
                      className="border border-rule px-1.5 font-mono text-[10px] text-mute"
                    >
                      {p}
                    </span>
                  ))}
                </div>
                <p className="mt-1 text-sm text-ink">{s.summary}</p>
                <p className="mt-1 font-mono text-[10px] text-mute">
                  sha {s.sha256.slice(0, 16)}…
                </p>
              </div>
              <Button
                type="button"
                variant="no"
                disabled={busy}
                onClick={() => removeSkill(s.name)}
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="p-6">
        <CardHeader>
          <CardKicker>Multimodal</CardKicker>
          <CardTitle>Inspect a local file</CardTitle>
        </CardHeader>
        <CardBody>
          Read PDF, image, audio, video metadata + safe text extraction. No external call —
          audio/video can use a <code>.txt</code> transcript sidecar next to the file.
        </CardBody>
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={inspectFile}>
          <label className="grid flex-1 gap-1.5 text-sm font-medium">
            File path (absolute)
            <input
              className={inputClasses}
              type="text"
              placeholder="C:\\Users\\…\\proposal.pdf"
              value={inspectPath}
              onChange={(event) => setInspectPath(event.target.value)}
              required
            />
          </label>
          <Button type="submit" variant="primary" disabled={busy}>
            <FileSearch className="size-4" aria-hidden />
            Inspect
          </Button>
        </form>
        {inspection && (
          <div className="mt-4 space-y-2 border border-rule p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="border border-rule px-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-mute">
                {inspection.kind}
              </span>
              <span className="font-mono text-[10px] text-mute">
                {formatBytes(inspection.size_bytes)}
              </span>
              <span className="font-mono text-[10px] text-mute">
                sha {inspection.sha256.slice(0, 16)}…
              </span>
            </div>
            {inspection.warnings.length > 0 && (
              <ul className="text-xs text-warn">
                {inspection.warnings.map((w, idx) => (
                  <li key={idx}>· {w}</li>
                ))}
              </ul>
            )}
            {inspection.text && (
              <pre className="max-h-64 overflow-y-auto border border-rule bg-paper p-2 text-[11px] text-ink">
                {inspection.text.slice(0, 4000)}
              </pre>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function StatusLine({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return (
    <div
      className={cn(
        "mt-3 border px-3 py-2 text-sm",
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
