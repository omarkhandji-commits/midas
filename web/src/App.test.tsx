import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ChatPage } from "@/pages/Chat";
import { OnboardingPage } from "@/pages/Onboarding";
import { ProvidersPage } from "@/pages/Providers";

// Smoke: the app shell mounts, every nav group is visible, and the default
// route renders the chat surface. This is the Sprint-0 contract.
describe("AppShell", () => {
  it("renders all nav groups and the chat surface at /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<ChatPage />} />
            <Route path="providers" element={<ProvidersPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("MIDAS")).toBeInTheDocument();
    expect(screen.getByText("Work")).toBeInTheDocument();
    expect(screen.getByText("Verify")).toBeInTheDocument();
    expect(screen.getByText("Connect")).toBeInTheDocument();
    expect(screen.getByText("Automate")).toBeInTheDocument();
    expect(screen.getByText(/Proof first/)).toBeInTheDocument();
  });

  it("renders the onboarding checklist at /start", () => {
    render(
      <MemoryRouter initialEntries={["/start"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route path="start" element={<OnboardingPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("First value in five minutes")).toBeInTheDocument();
    expect(screen.getByText("Connect your AI")).toBeInTheDocument();
    expect(screen.getByText("Approval-default")).toBeInTheDocument();
  });
});
