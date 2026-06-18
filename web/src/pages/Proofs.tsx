import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw, ShieldCheck, ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Proof = {
  seq: number;
  run_id: string;
  agent: string;
  tool: string;
  decision: string;
  hash: string;
  prev_hash: string;
  ts: string;
};
type ProofResponse = {
  proofs: Proof[];
  chain: { ok: boolean; count: number; error: string | null };
  total_matches: number;
};

const inputClasses = "border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-mute";

export function ProofsPage() {
  const [proofs, setProofs] = useState<Proof[]>([]);
  const [chain, setChain] = useState<ProofResponse["chain"] | null>(null);
  const [totalMatches, setTotalMatches] = useState(0);
  const [runId, setRunId] = useState("");
  const [tool, setTool] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (runId.trim()) params.set("run_id", runId.trim());
      if (tool.trim()) params.set("tool", tool.trim());
      if (dateFrom.trim()) params.set("date_from", dateFrom.trim());
      if (dateTo.trim()) params.set("date_to", dateTo.trim());
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const response = await api.get<ProofResponse>(`/api/proofs${suffix}`);
      setProofs(response.proofs.reverse());
      setChain(response.chain);
      setTotalMatches(response.total_matches);
    } catch (err) {
      setError(readError(err));
    }
  }, [dateFrom, dateTo, runId, tool]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Proof Ledger</CardKicker>
            <CardTitle>Signed receipt chain</CardTitle>
          </CardHeader>
          <CardBody>
            <p>Every row is a hashed receipt. Raw payloads stay digested, not exposed.</p>
          </CardBody>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            <input className={inputClasses} value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="run_id" />
            <input className={inputClasses} value={tool} onChange={(e) => setTool(e.target.value)} placeholder="tool" />
            <input className={inputClasses} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} placeholder="from ISO" />
            <input className={inputClasses} value={dateTo} onChange={(e) => setDateTo(e.target.value)} placeholder="to ISO" />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" onClick={load}>
              <RefreshCw className="size-4" aria-hidden />
              Search
            </Button>
            <Button type="button" variant="default" onClick={() => exportProofs(proofs)}>
              <Download className="size-4" aria-hidden />
              Export JSON
            </Button>
          </div>
          {error && <div className="mt-4 border border-warn bg-warn-bg px-3 py-2 text-sm text-warn">{error}</div>}
        </Card>
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Chain verify</CardKicker>
            <CardTitle>{chain?.ok ? "OK" : "Check needed"}</CardTitle>
          </CardHeader>
          <div className="flex items-center gap-3 text-sm">
            {chain?.ok ? (
              <ShieldCheck className="size-5 text-accent" aria-hidden />
            ) : (
              <ShieldX className="size-5 text-warn" aria-hidden />
            )}
            <span className="text-mute">
              {chain ? `${chain.count} receipts` : "Loading"} · {totalMatches} match{totalMatches === 1 ? "" : "es"} {chain?.error ?? ""}
            </span>
          </div>
        </Card>
      </section>

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="border-b border-rule bg-rule-soft/50 text-left font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
              <tr>
                <th className="px-4 py-3 font-medium">Seq</th>
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Tool</th>
                <th className="px-4 py-3 font-medium">Decision</th>
                <th className="px-4 py-3 font-medium">Hash</th>
                <th className="px-4 py-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody>
              {proofs.map((proof) => (
                <tr key={`${proof.seq}-${proof.hash}`} className="border-b border-rule last:border-b-0">
                  <td className="px-4 py-3 font-mono text-xs">{proof.seq}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{proof.run_id || "(none)"}</div>
                    <div className="font-mono text-xs text-mute">{proof.agent}</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-mute">{proof.tool}</td>
                  <td className="px-4 py-3">
                    <DecisionBadge decision={proof.decision} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-mute">{proof.hash.slice(0, 18)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-mute">{new Date(proof.ts).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const isAllow = decision === "allow";
  const isQueue = decision === "queue_approval";
  return (
    <span
      className={`inline-flex border px-2 py-1 font-mono text-xs ${
        isAllow
          ? "border-accent bg-ok-bg text-accent"
          : isQueue
            ? "border-rule bg-rule-soft text-ink"
            : "border-warn bg-warn-bg text-warn"
      }`}
    >
      {decision}
    </span>
  );
}

function exportProofs(proofs: Proof[]) {
  const blob = new Blob([JSON.stringify({ proofs }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `midas-proofs-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
