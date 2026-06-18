import { useMemo, useState } from "react";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";

type EventRow = { customer_id: string; cohort_week: string; active_week: string };

const sample = JSON.stringify(
  [
    { customer_id: "c1", cohort_week: "2026-W25", active_week: "2026-W25" },
    { customer_id: "c1", cohort_week: "2026-W25", active_week: "2026-W26" },
    { customer_id: "c2", cohort_week: "2026-W25", active_week: "2026-W25" },
  ],
  null,
  2,
);

export function CohortsPage() {
  const [raw, setRaw] = useState(sample);

  const parsed = useMemo(() => {
    try {
      return { cohorts: compute(JSON.parse(raw) as EventRow[]), error: null };
    } catch {
      return { cohorts: [], error: "Invalid JSON event list." };
    }
  }, [raw]);

  const { cohorts, error } = parsed;

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Cohorts</CardKicker>
          <CardTitle>Retention table</CardTitle>
        </CardHeader>
        <CardBody>
          Paste customer activity events. This local view computes retention only; it does not
          send data out.
        </CardBody>
        <textarea
          className="mt-4 min-h-[440px] w-full border border-rule bg-paper p-3 font-mono text-xs"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
        />
        {error && (
          <p className="mt-3 border border-warn bg-warn-bg p-2 text-sm text-warn">{error}</p>
        )}
      </Card>
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Retention</CardKicker>
          <CardTitle>{cohorts.length} cohorts</CardTitle>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-mute">
                <th className="py-2">Cohort</th>
                <th className="py-2">Size</th>
                <th className="py-2">Weeks</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((cohort) => (
                <tr key={cohort.cohort_week} className="border-b border-rule">
                  <td className="py-2 font-mono">{cohort.cohort_week}</td>
                  <td className="py-2">{cohort.size}</td>
                  <td className="py-2">
                    {cohort.retention
                      .map((r) => `${r.week}: ${(r.retention * 100).toFixed(0)}%`)
                      .join(" | ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function compute(events: EventRow[]) {
  const cohorts = new Map<string, Map<string, Set<string>>>();
  events.forEach((event) => {
    if (!event.customer_id || !event.cohort_week || !event.active_week) return;
    if (!cohorts.has(event.cohort_week)) cohorts.set(event.cohort_week, new Map());
    const weeks = cohorts.get(event.cohort_week)!;
    if (!weeks.has(event.active_week)) weeks.set(event.active_week, new Set());
    weeks.get(event.active_week)!.add(event.customer_id);
  });
  return [...cohorts.entries()].map(([cohort_week, weeks]) => {
    const all = new Set<string>();
    weeks.forEach((customers) => customers.forEach((id) => all.add(id)));
    const size = weeks.get(cohort_week)?.size || all.size;
    return {
      cohort_week,
      size,
      retention: [...weeks.entries()].map(([week, customers]) => ({
        week,
        active_customers: customers.size,
        retention: size ? customers.size / size : 0,
      })),
    };
  });
}
