import { PagePlaceholder } from "@/components/PagePlaceholder";

export function ProofsPage() {
  return (
    <PagePlaceholder
      kicker="Proof Ledger"
      title="Hash-chained, signed receipts for every decision"
      description="Every model call, tool invocation, approval and outcome is written as a signed receipt and chained to the previous one. Claims without surviving sources are downgraded."
    />
  );
}
