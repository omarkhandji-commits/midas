import { useState, type FormEvent } from "react";
import { MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Newsletter = {
  subject: string;
  html: string;
  plaintext: string;
  sha256_intent: string;
};

export function NewslettersPage() {
  const [subject, setSubject] = useState("This week's operator moves");
  const [body, setBody] = useState("## What changed\n\nAdd the useful update here.");
  const [unsubscribeUrl, setUnsubscribeUrl] = useState("https://example.com/unsubscribe");
  const [address, setAddress] = useState("123 Main St, Montreal, QC");
  const [draft, setDraft] = useState<Newsletter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ newsletter: Newsletter }>("/api/tools/newsletter-draft", {
        subject,
        body,
        unsubscribe_url: unsubscribeUrl,
        physical_address: address,
      });
      setDraft(res.newsletter);
    } catch (err) {
      setError(readError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Newsletters</CardKicker>
          <CardTitle>Compliant draft</CardTitle>
        </CardHeader>
        <CardBody>Requires unsubscribe URL and physical address. Sending remains approval-gated.</CardBody>
        <form className="mt-4 space-y-3" onSubmit={submit}>
          <input className={inputClasses} value={subject} onChange={(e) => setSubject(e.target.value)} />
          <input className={inputClasses} value={unsubscribeUrl} onChange={(e) => setUnsubscribeUrl(e.target.value)} />
          <input className={inputClasses} value={address} onChange={(e) => setAddress(e.target.value)} />
          <textarea
            className="min-h-48 w-full border border-rule bg-paper p-3 text-sm"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <Button type="submit" variant="primary" disabled={busy}>
            <MailCheck className="size-4" aria-hidden />
            Draft newsletter
          </Button>
        </form>
        {error && <p className="mt-3 border border-warn bg-warn-bg p-2 text-sm text-warn">{error}</p>}
      </Card>
      <section className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5">
          <CardHeader>
            <CardKicker>Plaintext</CardKicker>
            <CardTitle>{draft?.subject || "No draft"}</CardTitle>
          </CardHeader>
          <textarea
            className="min-h-[520px] w-full border border-rule bg-paper p-3 font-mono text-sm"
            value={draft?.plaintext || ""}
            readOnly
          />
        </Card>
        <Card className="p-5">
          <CardHeader>
            <CardKicker>HTML</CardKicker>
            <CardTitle>{draft ? draft.sha256_intent.slice(0, 12) : "No hash"}</CardTitle>
          </CardHeader>
          <textarea
            className="min-h-[520px] w-full border border-rule bg-paper p-3 font-mono text-xs"
            value={draft?.html || ""}
            readOnly
          />
        </Card>
      </section>
    </div>
  );
}

const inputClasses = "h-9 w-full border border-rule bg-paper px-3 text-sm text-ink";

function readError(err: unknown): string {
  return err instanceof Error ? err.message : "Request failed.";
}
