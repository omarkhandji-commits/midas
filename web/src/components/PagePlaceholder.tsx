import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";
import type { ReactNode } from "react";

interface PagePlaceholderProps {
  kicker: string;
  title: string;
  description: string;
  children?: ReactNode;
}

// A polished "this screen exists, here's what it will do" panel. Used across every
// route during Sprint 0 so the IA is visible end-to-end before each screen ships.
export function PagePlaceholder({ kicker, title, description, children }: PagePlaceholderProps) {
  return (
    <Card className="p-8">
      <CardHeader>
        <CardKicker>{kicker}</CardKicker>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        <p>{description}</p>
        {children && <div className="mt-5">{children}</div>}
      </CardBody>
    </Card>
  );
}
