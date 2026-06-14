import { PagePlaceholder } from "@/components/PagePlaceholder";

export function ProvidersPage() {
  return (
    <PagePlaceholder
      kicker="Providers & Keys"
      title="Bring your own LLM — local or cloud"
      description="Paste a key, run a test, store it in your OS keychain. MIDAS never logs keys, never echoes them back, and never puts them into model context. Local Ollama works without any key."
    />
  );
}
