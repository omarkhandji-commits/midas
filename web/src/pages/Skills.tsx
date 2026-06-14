import { PagePlaceholder } from "@/components/PagePlaceholder";

export function SkillsPage() {
  return (
    <PagePlaceholder
      kicker="Skills"
      title="Approval-gated local skills"
      description="Create, install and manage local MIDAS skills. Remote skills require an explicit approval before download. Skills with executable payloads are rejected by the registry."
    />
  );
}
