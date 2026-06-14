import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { ChatPage } from "@/pages/Chat";
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
});
