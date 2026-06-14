import { PagePlaceholder } from "@/components/PagePlaceholder";

export function SettingsPage() {
  return (
    <PagePlaceholder
      kicker="Settings"
      title="Budget caps, autonomy, theme, language"
      description="Set hard spend caps. Switch between semi-auto (default) and guarded full-auto (advanced). Pick a theme and a language. All settings are local — there is no MIDAS cloud."
    />
  );
}
