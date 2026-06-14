import { Link } from "react-router-dom";
import {
  Bot,
  CheckCircle2,
  Compass,
  Inbox,
  KeyRound,
  MessageSquare,
  Plug,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";

const steps = [
  {
    title: "Connect your AI",
    detail: "Add a cloud key or point MIDAS to Ollama. Secrets stay local.",
    to: "/providers",
    icon: KeyRound,
  },
  {
    title: "Pick an approval channel",
    detail: "Telegram, Discord, Slack, WhatsApp, SMS, or draft-only email.",
    to: "/channels",
    icon: Plug,
  },
  {
    title: "Run one mission",
    detail: "Start with a niche and get a sourced Daily Revenue Move.",
    to: "/missions",
    icon: Compass,
  },
  {
    title: "Prepare assets",
    detail: "Turn the move into offer, email, SEO brief, proposal, or invoice PDF.",
    to: "/assets",
    icon: Wand2,
  },
  {
    title: "Approve deliberately",
    detail: "Anything outbound lands in the Approval Center before it can move.",
    to: "/approvals",
    icon: Inbox,
  },
];

export function OnboardingPage() {
  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-6">
          <CardHeader>
            <CardKicker>Start</CardKicker>
            <CardTitle>First value in five minutes</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <p>
              Set one model, connect one private approval path, then run a focused
              mission. MIDAS drafts work, cites proof, and stops before external action.
            </p>
          </CardBody>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild variant="primary">
              <Link to="/providers">
                <Bot className="size-4" aria-hidden />
                Connect AI
              </Link>
            </Button>
            <Button asChild>
              <Link to="/">
                <MessageSquare className="size-4" aria-hidden />
                Open chat
              </Link>
            </Button>
          </div>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker>Invariant</CardKicker>
            <CardTitle>Approval-default</CardTitle>
          </CardHeader>
          <CardBody>
            <p>
              Public posts, email sends, SMS, WhatsApp, phone-like work, money, legal,
              and account changes remain approval-gated.
            </p>
          </CardBody>
        </Card>
      </section>

      <section className="grid gap-3">
        {steps.map((step, index) => (
          <Card key={step.title} className="p-4">
            <div className="grid gap-4 md:grid-cols-[44px_minmax(0,1fr)_auto] md:items-center">
              <div className="flex size-11 items-center justify-center border border-rule bg-rule-soft/45">
                <step.icon className="size-5 text-accent" aria-hidden />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-mute">
                    Step {index + 1}
                  </span>
                  {index === 0 && <CheckCircle2 className="size-3.5 text-accent" aria-hidden />}
                </div>
                <h2 className="mt-1 text-base font-semibold">{step.title}</h2>
                <p className="mt-1 text-sm text-mute">{step.detail}</p>
              </div>
              <Button asChild variant="ghost" size="sm">
                <Link to={step.to}>Open</Link>
              </Button>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
