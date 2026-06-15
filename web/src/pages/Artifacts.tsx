import { useEffect, useState } from "react";
import { FileBox, ShieldCheck } from "lucide-react";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Artifact = {
  seq: number;
  run_id: string;
  kind: string;
  ts: string;
  hash: string;
};

type ArtifactsResponse = { artifacts: Artifact[] };

export function ArtifactsPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    setError(null);
    try {
      const data = await api.get<ArtifactsResponse>("/api/artifacts");
      setArtifacts(data.artifacts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Inbox</CardKicker>
          <CardTitle>Artifacts</CardTitle>
        </CardHeader>
        <CardBody>
          Files MIDAS materialized after an approval. Each row links to its receipt
          in the Proof Ledger. The chain is hash-linked: changing a byte breaks the
          chain at the corrupted seq.
        </CardBody>
      </Card>

      {error && (
        <div className="border border-warn bg-warn-bg px-4 py-3 text-sm text-warn" role="alert">
          {error}
        </div>
      )}

      {artifacts.length === 0 && !busy ? (
        <div className="border border-rule bg-rule-soft/30 p-6 text-sm text-mute">
          No artifacts yet. Switch the Chat to Do mode and ask MIDAS for a draft.
        </div>
      ) : (
        <ul className="grid gap-3">
          {artifacts.map((artifact) => (
            <li key={`${artifact.run_id}-${artifact.seq}`}>
              <Card className="p-4">
                <div className="flex items-start gap-3">
                  <FileBox className="mt-1 size-4 shrink-0 text-accent" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <h2 className="font-mono text-sm">{artifact.kind}</h2>
                      <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                        seq #{artifact.seq}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[11px] text-mute">
                      {artifact.ts} · run {artifact.run_id}
                    </p>
                    <p className="mt-2 font-mono text-[11px] text-accent">
                      <ShieldCheck className="mr-1 inline size-3.5" aria-hidden />
                      sha256 {artifact.hash.slice(0, 32)}…
                    </p>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
