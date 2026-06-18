import { useState, type FormEvent } from "react";
import { SearchCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Issue = { code: string; message: string; severity: string };
type LintResult = {
  score: number;
  word_count: number;
  title: string;
  meta_description: string;
  issues: Issue[];
};

export function BlogsPage() {
  const [title, setTitle] = useState("How to validate a niche before outreach");
  const [meta, setMeta] = useState("A practical checklist for validating a niche before spending on outreach.");
  const [markdown, setMarkdown] = useState("# Draft\n\nWrite the post here.");
  const [result, setResult] = useState<LintResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ result: LintResult }>("/api/tools/blog-lint", {
        title,
        meta_description: meta,
        markdown,
      });
      setResult(res.result);
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Blogs</CardKicker>
          <CardTitle>Markdown with SEO lint</CardTitle>
        </CardHeader>
        <form className="space-y-3" onSubmit={submit}>
          <input className={inputClasses} value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className={inputClasses} value={meta} onChange={(e) => setMeta(e.target.value)} />
          <textarea
            className="min-h-[520px] w-full border border-rule bg-paper p-4 font-mono text-sm text-ink"
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
          />
          <Button type="submit" variant="primary" disabled={busy}>
            <SearchCheck className="size-4" aria-hidden />
            Lint draft
          </Button>
        </form>
        {error && <p className="mt-3 border border-warn bg-warn-bg p-2 text-sm text-warn">{error}</p>}
      </Card>
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Score</CardKicker>
          <CardTitle>{result ? `${result.score}/100` : "Not checked"}</CardTitle>
        </CardHeader>
        <CardBody>
          {result ? `${result.word_count} words. ${result.issues.length} issues.` : "Run the lint gate before publishing."}
        </CardBody>
        <ul className="mt-4 space-y-2 text-sm">
          {(result?.issues || []).map((issue) => (
            <li key={issue.code} className="border border-rule p-2">
              <span className="font-mono text-[10px] uppercase text-mute">{issue.severity}</span>
              <p>{issue.message}</p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

const inputClasses = "h-9 w-full border border-rule bg-paper px-3 text-sm text-ink";

function readError(err: unknown): string {
  return err instanceof Error ? err.message : "Request failed.";
}
