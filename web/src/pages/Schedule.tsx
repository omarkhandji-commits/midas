import { PagePlaceholder } from "@/components/PagePlaceholder";

export function SchedulePage() {
  return (
    <PagePlaceholder
      kicker="Schedule"
      title="Recurring scans and watches, owned by you"
      description="MIDAS outputs a schedule recipe you can install in cron, Task Scheduler or GitHub Actions. Opt-in runtime scheduler with start/pause/cancel lands in a later sprint."
    />
  );
}
