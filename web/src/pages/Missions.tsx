import { useState, type FormEvent } from "react";
import { Compass, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Mission = {
  run_id: string;
  niche: string;
  proof_level: string;
  spent_usd: number;
  approval_id: number | null;
  daily_move: null | {
    name: string;
    summary: string;
    score: number;
    band: string;
    proof_level: string;
    sources: string[];
    steps: string[];
    assets: Record<string, string>;
    estimate: { assumptions: string[]; est_cost_usd: number; est_time_hours: number; note: string };
    next_action: string;
  };
  shortlist: Array<{ name: string; score: number; band: string; proof_level: string }>;
};

type MissionResponse = { ok: boolean; mission: Mission };

export function MissionsPage() {
  const [niche, setNiche] = useState("local SEO agency");
  const [mode, setMode] = useState("deep");
  const [live, setLive] = useState(false);
  const [mission, setMission] = useState<Mission | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runMission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.post<MissionResponse>("/api/missions", { niche, mode, live });
      setMission(response.mission);
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
          <CardKicker>Missions</CardKicker>
          <CardTitle>Daily Revenue Move</CardTitle>
        </CardHeader>
        <form className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_160px_140px_auto]" onSubmit={runMission}>
          <label className="grid gap-1.5 text-sm font-medium">
            Niche
            <input
              className={inputClasses}
              value={niche}
              onChange={(event) => setNiche(event.target.value)}
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Mode
            <select className={inputClasses} value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="fast">Fast</option>
              <option value="deep">Deep</option>
              <option value="war-room">War-room</option>
            </select>
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm text-mute">
            <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
            Live
          </label>
          <div className="flex items-end">
            <Button type="submit" variant="primary" disabled={busy || !niche.trim()}>
              <Compass className="size-4" aria-hidden />
              Run
            </Button>
          </div>
        </form>
        {error && <Status error={error} />}
      </Card>

      {mission && (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Card className="p-6">
            <CardHeader>
              <CardKicker>{mission.run_id}</CardKicker>
              <CardTitle>{mission.daily_move?.name ?? "No move selected"}</CardTitle>
            </CardHeader>
            {mission.daily_move ? (
              <div className="space-y-5">
                <p className="text-sm leading-6 text-mute">{mission.daily_move.summary}</p>
                <div className="grid gap-3 md:grid-cols-4">
                  <Metric label="Score" value={`${mission.daily_move.score}/100`} />
                  <Metric label="Band" value={mission.daily_move.band} />
                  <Metric label="Proof" value={mission.daily_move.proof_level} />
                  <Metric label="Spent" value={`$${mission.spent_usd.toFixed(4)}`} />
                </div>
                <div>
                  <h2 className="mb-2 text-sm font-semibold">Prepared steps</h2>
                  <ul className="space-y-2 text-sm text-mute">
                    {mission.daily_move.steps.map((step) => (
                      <li key={step} className="border-l-2 border-accent pl-3">
                        {step}
                      </li>
                    ))}
                  </ul>
                </div>
                <AssetKeys keys={Object.keys(mission.daily_move.assets)} />
              </div>
            ) : (
              <CardBody>{mission.proof_level}</CardBody>
            )}
          </Card>

          <aside className="space-y-4">
            <Card className="p-5">
              <CardHeader>
                <CardKicker>Approval</CardKicker>
                <CardTitle>{mission.approval_id ? `#${mission.approval_id}` : "None"}</CardTitle>
              </CardHeader>
              <CardBody>
                <p>{mission.daily_move?.next_action ?? "No outbound action queued."}</p>
              </CardBody>
            </Card>
            <Card className="p-5">
              <CardHeader>
                <CardKicker>Shortlist</CardKicker>
                <CardTitle>{mission.shortlist.length} candidates</CardTitle>
              </CardHeader>
              <div className="space-y-2">
                {mission.shortlist.map((item) => (
                  <div key={item.name} className="border-b border-rule pb-2 text-sm last:border-b-0">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium">{item.name}</span>
                      <span className="font-mono text-xs">{item.score}</span>
                    </div>
                    <p className="font-mono text-xs text-mute">
                      {item.band} / {item.proof_level}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          </aside>
        </section>
      )}
    </div>
  );
}

const inputClasses = "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-rule bg-rule-soft/30 p-3">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">{label}</div>
      <div className="mt-1 font-mono text-sm text-ink">{value}</div>
    </div>
  );
}

function AssetKeys({ keys }: { keys: string[] }) {
  return (
    <div>
      <h2 className="mb-2 inline-flex items-center gap-2 text-sm font-semibold">
        <FileText className="size-4" aria-hidden />
        Assets ready
      </h2>
      <div className="flex flex-wrap gap-2">
        {keys.map((key) => (
          <span key={key} className="border border-rule px-2 py-1 font-mono text-xs text-mute">
            {key}
          </span>
        ))}
      </div>
    </div>
  );
}

function Status({ error }: { error: string }) {
  return (
    <div className={cn("mt-4 border border-warn bg-warn-bg px-4 py-3 text-sm text-warn")} role="alert">
      {error}
    </div>
  );
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
