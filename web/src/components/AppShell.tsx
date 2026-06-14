import { NavLink, Outlet } from "react-router-dom";
import {
  MessageSquare,
  Compass,
  Wand2,
  Inbox,
  ScrollText,
  Brain,
  Radar,
  LineChart,
  Plug,
  KeyRound,
  CalendarClock,
  Sparkles,
  Settings as SettingsIcon,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = { to: string; label: string; icon: typeof MessageSquare };
type NavGroup = { label: string; items: NavItem[] };

const groups: NavGroup[] = [
  {
    label: "Work",
    items: [
      { to: "/", label: "Chat", icon: MessageSquare },
      { to: "/missions", label: "Missions", icon: Compass },
      { to: "/assets", label: "Asset Studio", icon: Wand2 },
      { to: "/approvals", label: "Approvals", icon: Inbox },
    ],
  },
  {
    label: "Verify",
    items: [
      { to: "/proofs", label: "Proof Ledger", icon: ScrollText },
      { to: "/memory", label: "Memory", icon: Brain },
      { to: "/outcomes", label: "Outcomes", icon: LineChart },
    ],
  },
  {
    label: "Connect",
    items: [
      { to: "/channels", label: "Channels", icon: Plug },
      { to: "/providers", label: "Providers", icon: KeyRound },
    ],
  },
  {
    label: "Automate",
    items: [
      { to: "/market", label: "Market Radar", icon: Radar },
      { to: "/schedule", label: "Schedule", icon: CalendarClock },
      { to: "/skills", label: "Skills", icon: Sparkles },
    ],
  },
];

const navLinkClasses = ({ isActive }: { isActive: boolean }) =>
  cn(
    "group flex items-center gap-2 px-3 py-1.5 text-sm transition-colors",
    "border-l-2",
    isActive
      ? "border-accent text-ink font-medium bg-rule-soft/60"
      : "border-transparent text-mute hover:text-ink hover:bg-rule-soft/40",
  );

export function AppShell() {
  return (
    <div className="grid h-full grid-cols-[260px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)]">
      <header className="col-span-2 sticky top-0 z-10 flex items-baseline justify-between gap-6 border-b border-rule bg-paper px-8 py-3">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-[22px] font-medium tracking-[0.02em]">MIDAS</span>
          <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-mute">
            operator
          </span>
        </div>
        <div className="flex items-baseline gap-6 font-mono text-xs text-mute">
          <MetaPill label="Spent" value="$0.0000" id="spent-usd" />
          <MetaPill label="Receipts" value="0" id="receipt-count" />
          <span className="inline-flex items-center gap-1.5 text-accent">
            <Shield className="size-3.5" aria-hidden />
            <span className="uppercase tracking-[0.08em]">Chain OK</span>
          </span>
        </div>
      </header>

      <aside className="row-start-2 border-r border-rule bg-paper py-4 overflow-y-auto">
        <nav className="space-y-6">
          {groups.map((g) => (
            <div key={g.label}>
              <div className="px-3 mb-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-mute">
                {g.label}
              </div>
              <ul>
                {g.items.map(({ to, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink to={to} end={to === "/"} className={navLinkClasses}>
                      <Icon className="size-4 shrink-0" aria-hidden />
                      <span>{label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="mt-8 px-3">
          <NavLink to="/settings" className={navLinkClasses}>
            <SettingsIcon className="size-4 shrink-0" aria-hidden />
            <span>Settings</span>
          </NavLink>
        </div>
      </aside>

      <main className="row-start-2 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function MetaPill({ label, value, id }: { label: string; value: string; id: string }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="uppercase tracking-[0.08em]">{label}</span>
      <span id={id} className="text-ink tabular">
        {value}
      </span>
    </span>
  );
}
