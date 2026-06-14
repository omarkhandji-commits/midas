import { useState, type FormEvent } from "react";
import { Copy, Download, FileText, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type PdfPayload = { filename: string; media_type: string; base64: string };
type AssetResponse = {
  ok: boolean;
  assets: Record<string, string>;
  pdfs: Record<string, PdfPayload>;
};

const priority = ["offer", "landing", "outreach_email", "proposal_pdf", "invoice_pdf"];

export function AssetsPage() {
  const [topic, setTopic] = useState("Proof-first audit");
  const [summary, setSummary] = useState("Validate a business opportunity before outreach.");
  const [live, setLive] = useState(false);
  const [assets, setAssets] = useState<Record<string, string>>({});
  const [pdfs, setPdfs] = useState<Record<string, PdfPayload>>({});
  const [selected, setSelected] = useState("offer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.post<AssetResponse>("/api/assets/generate", { topic, summary, live });
      setAssets(response.assets);
      setPdfs(response.pdfs);
      setSelected(priority.find((key) => response.assets[key]) ?? Object.keys(response.assets)[0] ?? "");
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  const keys = Object.keys(assets).sort((a, b) => {
    const ai = priority.indexOf(a);
    const bi = priority.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b);
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="p-5">
        <CardHeader>
          <CardKicker>Asset Studio</CardKicker>
          <CardTitle>Business drafts</CardTitle>
        </CardHeader>
        <form className="space-y-4" onSubmit={generate}>
          <label className="grid gap-1.5 text-sm font-medium">
            Topic
            <input className={inputClasses} value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Summary
            <textarea
              className="min-h-24 border border-rule bg-paper p-3 text-sm text-ink"
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-mute">
            <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
            Live LLM
          </label>
          <Button type="submit" variant="primary" disabled={busy || !topic.trim()}>
            <Wand2 className="size-4" aria-hidden />
            Generate
          </Button>
        </form>
        {error && <div className="mt-4 border border-warn bg-warn-bg px-3 py-2 text-sm text-warn">{error}</div>}
      </Card>

      <section className="min-h-[620px] border border-rule bg-paper">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">Drafts</p>
            <h1 className="font-display text-2xl font-medium">{selected || "No asset selected"}</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" disabled={!selected} onClick={() => copyAsset(assets[selected])}>
              <Copy className="size-4" aria-hidden />
              Copy
            </Button>
            {Object.entries(pdfs).map(([key, pdf]) => (
              <Button key={key} type="button" onClick={() => downloadPdf(pdf)}>
                <Download className="size-4" aria-hidden />
                {key}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid min-h-[560px] lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="border-r border-rule p-3">
            {keys.length === 0 ? (
              <p className="px-2 py-2 text-sm text-mute">No drafts yet.</p>
            ) : (
              keys.map((key) => (
                <button
                  key={key}
                  type="button"
                  className={`flex w-full items-center gap-2 px-2 py-2 text-left text-sm ${
                    selected === key ? "bg-rule-soft text-ink" : "text-mute hover:text-ink"
                  }`}
                  onClick={() => setSelected(key)}
                >
                  <FileText className="size-4" aria-hidden />
                  {key}
                </button>
              ))
            )}
          </nav>
          <textarea
            className="min-h-[560px] resize-none bg-paper p-5 font-mono text-sm leading-6 text-ink outline-none"
            value={assets[selected] ?? ""}
            onChange={(event) => setAssets({ ...assets, [selected]: event.target.value })}
            aria-label="Selected asset draft"
          />
        </div>
      </section>
    </div>
  );
}

const inputClasses = "h-9 border border-rule bg-paper px-3 text-sm text-ink placeholder:text-mute";

function copyAsset(value: string | undefined) {
  if (!value) return;
  void navigator.clipboard?.writeText(value);
}

function downloadPdf(pdf: PdfPayload) {
  const bytes = Uint8Array.from(atob(pdf.base64), (char) => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: pdf.media_type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = pdf.filename;
  link.click();
  URL.revokeObjectURL(url);
}

function readError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Request failed.";
}
