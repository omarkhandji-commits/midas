import { useEffect, useState } from "react";
import { UsersRound } from "lucide-react";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type MemoryEntry = {
  id: number;
  ts: string;
  key: string;
  content: string;
  proof_level: string;
  sources: string[];
  tags: string[];
};

export function LeadsPage() {
  const [rows, setRows] = useState<MemoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ memory: MemoryEntry[] }>("/api/memory/search?kind=result&q=lead")
      .then((res) => setRows(res.memory))
      .catch((err) => setError(err instanceof Error ? err.message : "Request failed."));
  }, []);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Leads</CardKicker>
          <CardTitle>CRM view</CardTitle>
        </CardHeader>
        <CardBody>Lead records come from inbound tools and RESULT memory. No outreach is sent from this page.</CardBody>
      </Card>
      {error && <p className="border border-warn bg-warn-bg p-2 text-sm text-warn">{error}</p>}
      <div className="grid gap-3">
        {rows.map((lead) => (
          <Card key={lead.id} className="p-4">
            <div className="flex items-start gap-3">
              <UsersRound className="mt-1 size-4 text-accent" aria-hidden />
              <div>
                <p className="font-mono text-xs text-mute">{lead.key} · {lead.proof_level}</p>
                <p className="text-sm text-ink">{lead.content}</p>
                <p className="mt-1 font-mono text-[10px] text-mute">{lead.ts}</p>
              </div>
            </div>
          </Card>
        ))}
        {rows.length === 0 && <Card className="p-4 text-sm text-mute">No lead memory found.</Card>}
      </div>
    </div>
  );
}
