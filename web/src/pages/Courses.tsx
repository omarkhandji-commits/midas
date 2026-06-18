import { useState, type FormEvent } from "react";
import { BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Module = { index: number; title: string; goal: string; key_concepts: string[]; exercise: string };
type Course = { topic: string; audience: string; modules: Module[]; markdown: string };

export function CoursesPage() {
  const [topic, setTopic] = useState("AI automation for local service businesses");
  const [audience, setAudience] = useState("beginners");
  const [modules, setModules] = useState(5);
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ course: Course }>("/api/tools/course-outline", {
        topic,
        audience,
        modules,
      });
      setCourse(res.course);
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Courses</CardKicker>
          <CardTitle>Outline builder</CardTitle>
        </CardHeader>
        <CardBody>Draft the sellable structure before recording lessons.</CardBody>
        <form className="mt-4 space-y-3" onSubmit={submit}>
          <label className="grid gap-1.5 text-sm font-medium">
            Topic
            <input className={inputClasses} value={topic} onChange={(e) => setTopic(e.target.value)} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Audience
            <input className={inputClasses} value={audience} onChange={(e) => setAudience(e.target.value)} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Modules
            <input
              className={inputClasses}
              type="number"
              min={2}
              max={20}
              value={modules}
              onChange={(e) => setModules(Number(e.target.value))}
            />
          </label>
          <Button type="submit" variant="primary" disabled={busy}>
            <BookOpen className="size-4" aria-hidden />
            Draft outline
          </Button>
        </form>
        {error && <p className="mt-3 border border-warn bg-warn-bg p-2 text-sm text-warn">{error}</p>}
      </Card>
      <section className="space-y-4">
        {course ? (
          <>
            <Card className="p-6">
              <CardHeader>
                <CardKicker>{course.audience}</CardKicker>
                <CardTitle>{course.topic}</CardTitle>
              </CardHeader>
              <ol className="space-y-3">
                {course.modules.map((m) => (
                  <li key={m.index} className="border border-rule p-3">
                    <p className="font-medium">{m.index}. {m.title}</p>
                    <p className="text-sm text-mute">{m.goal}</p>
                    <p className="mt-2 text-sm">{m.exercise}</p>
                  </li>
                ))}
              </ol>
            </Card>
            <textarea
              className="min-h-[260px] w-full border border-rule bg-paper p-4 font-mono text-sm"
              value={course.markdown}
              readOnly
            />
          </>
        ) : (
          <Card className="p-6">
            <p className="text-sm text-mute">No outline yet.</p>
          </Card>
        )}
      </section>
    </div>
  );
}

const inputClasses = "h-9 border border-rule bg-paper px-3 text-sm text-ink";

function readError(err: unknown): string {
  return err instanceof Error ? err.message : "Request failed.";
}
