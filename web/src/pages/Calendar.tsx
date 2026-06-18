import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, X, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type ScheduledPost = {
  id: string;
  platform: string;
  account_handle: string;
  text: string;
  scheduled_at_iso: string;
  status: "pending" | "published" | "failed" | "cancelled";
  media_paths: string[];
  created_at_iso: string;
  note: string;
};

type ListResp = { posts: ScheduledPost[] };

function startOfWeek(d: Date): Date {
  const out = new Date(d);
  const day = out.getUTCDay(); // 0 = Sunday
  const diff = (day + 6) % 7; // Monday-anchored
  out.setUTCDate(out.getUTCDate() - diff);
  out.setUTCHours(0, 0, 0, 0);
  return out;
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setUTCDate(out.getUTCDate() + n);
  return out;
}

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

const STATUS_STYLES: Record<ScheduledPost["status"], string> = {
  pending: "border-accent bg-accent/10 text-ink",
  published: "border-emerald-500 bg-emerald-500/10 text-ink",
  failed: "border-red-500 bg-red-500/10 text-ink",
  cancelled: "border-mute bg-rule-soft/40 text-mute line-through",
};

export function CalendarPage() {
  const [weekAnchor, setWeekAnchor] = useState(() => startOfWeek(new Date()));
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const weekEnd = useMemo(() => addDays(weekAnchor, 7), [weekAnchor]);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        start: weekAnchor.toISOString(),
        end: weekEnd.toISOString(),
      });
      const res = await api.get<ListResp>(`/api/scheduled-posts?${params.toString()}`);
      setPosts(res.posts);
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekAnchor]);

  async function cancelPost(id: string) {
    if (!confirm("Cancel this scheduled post?")) return;
    try {
      await api.delete(`/api/scheduled-posts/${id}`);
      await load();
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }

  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => addDays(weekAnchor, i));
  }, [weekAnchor]);

  const postsByDay = useMemo(() => {
    const map: Record<string, ScheduledPost[]> = {};
    for (const p of posts) {
      const key = isoDay(new Date(p.scheduled_at_iso));
      (map[key] = map[key] || []).push(p);
    }
    return map;
  }, [posts]);

  const dayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardKicker>Plan</CardKicker>
          <CardTitle>Calendar</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => setWeekAnchor(addDays(weekAnchor, -7))}
              disabled={busy}
            >
              <ChevronLeft className="h-4 w-4" />
              Prev
            </Button>
            <Button
              variant="ghost"
              onClick={() => setWeekAnchor(startOfWeek(new Date()))}
              disabled={busy}
            >
              <CalendarDays className="h-4 w-4" />
              This week
            </Button>
            <Button
              variant="ghost"
              onClick={() => setWeekAnchor(addDays(weekAnchor, 7))}
              disabled={busy}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
            <div className="ml-auto text-sm text-mute">
              Week of {isoDay(weekAnchor)} · {posts.length} post
              {posts.length === 1 ? "" : "s"}
            </div>
          </div>
          {error ? (
            <div className="mt-3 border border-red-500 bg-red-500/10 px-3 py-2 text-sm text-ink">
              {error}
            </div>
          ) : null}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-7">
        {days.map((d, i) => {
          const key = isoDay(d);
          const dayPosts = postsByDay[key] || [];
          return (
            <div
              key={key}
              className="min-h-[160px] border border-rule bg-paper p-2"
            >
              <div className="mb-2 flex items-baseline justify-between">
                <div className="text-xs font-medium text-mute">
                  {dayLabels[i]}
                </div>
                <div className="text-xs text-mute">{key.slice(5)}</div>
              </div>
              <div className="space-y-1">
                {dayPosts.length === 0 ? (
                  <div className="text-xs text-mute/60">—</div>
                ) : (
                  dayPosts.map((p) => (
                    <div
                      key={p.id}
                      className={cn(
                        "border px-2 py-1 text-xs",
                        STATUS_STYLES[p.status],
                      )}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="flex-1">
                          <div className="font-medium">
                            {p.platform} · {p.account_handle}
                          </div>
                          <div className="text-[11px] text-mute">
                            {p.scheduled_at_iso.slice(11, 16)} UTC
                          </div>
                          <div className="mt-1 line-clamp-3 text-[11px]">
                            {p.text}
                          </div>
                        </div>
                        {p.status === "pending" ? (
                          <button
                            onClick={() => cancelPost(p.id)}
                            className="text-mute hover:text-red-500"
                            title="Cancel"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
