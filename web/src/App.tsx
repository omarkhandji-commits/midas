import { createBrowserRouter, RouterProvider, redirect } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { OnboardingPage } from "@/pages/Onboarding";
import { CapabilitiesPage } from "@/pages/Capabilities";
import { BlogsPage } from "@/pages/Blogs";
import { ChatPage } from "@/pages/Chat";
import { CohortsPage } from "@/pages/Cohorts";
import { CoursesPage } from "@/pages/Courses";
import { MissionsPage } from "@/pages/Missions";
import { ArtifactsPage } from "@/pages/Artifacts";
import { AssetsPage } from "@/pages/Assets";
import { ApprovalsPage } from "@/pages/Approvals";
import { ProofsPage } from "@/pages/Proofs";
import { LeadsPage } from "@/pages/Leads";
import { MemoryPage } from "@/pages/Memory";
import { NewslettersPage } from "@/pages/Newsletters";
import { OutcomesPage } from "@/pages/Outcomes";
import { ChannelsPage } from "@/pages/Channels";
import { ConnectionsPage } from "@/pages/Connections";
import { HowItWorksPage } from "@/pages/HowItWorks";
import { ProvidersPage } from "@/pages/Providers";
import { MarketPage } from "@/pages/Market";
import { SchedulePage } from "@/pages/Schedule";
import { CalendarPage } from "@/pages/Calendar";
import { SkillsPage } from "@/pages/Skills";
import { SettingsPage } from "@/pages/Settings";

// FastAPI serves the SPA from / after a successful login (the legacy Jinja /login
// page still owns the token form). React Router handles every in-app route.

// First-run gate. If the operator has no LLM provider configured, every route
// (except the onboarding wizard, settings, and how-it-works explainer) redirects
// to /start. The redirect happens on the loader, so the dashboard never flashes
// an empty Chat for new users — they land exactly where they need to be.
async function requireProvider() {
  try {
    const state = await api.get<{ has_provider: boolean }>("/api/onboard/state");
    if (!state.has_provider) {
      return redirect("/start");
    }
  } catch {
    // If the endpoint is unreachable (e.g. dashboard restarting) let the page render.
  }
  return null;
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { path: "start", element: <OnboardingPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "how-it-works", element: <HowItWorksPage /> },
      { path: "providers", element: <ProvidersPage /> },
      { path: "capabilities", element: <CapabilitiesPage /> },
      { index: true, element: <ChatPage />, loader: requireProvider },
      { path: "missions", element: <MissionsPage />, loader: requireProvider },
      { path: "assets", element: <AssetsPage />, loader: requireProvider },
      { path: "blogs", element: <BlogsPage />, loader: requireProvider },
      { path: "courses", element: <CoursesPage />, loader: requireProvider },
      { path: "newsletters", element: <NewslettersPage />, loader: requireProvider },
      { path: "artifacts", element: <ArtifactsPage />, loader: requireProvider },
      { path: "approvals", element: <ApprovalsPage />, loader: requireProvider },
      { path: "proofs", element: <ProofsPage />, loader: requireProvider },
      { path: "leads", element: <LeadsPage />, loader: requireProvider },
      { path: "memory", element: <MemoryPage />, loader: requireProvider },
      { path: "outcomes", element: <OutcomesPage />, loader: requireProvider },
      { path: "cohorts", element: <CohortsPage />, loader: requireProvider },
      { path: "connections", element: <ConnectionsPage /> },
      { path: "channels", element: <ChannelsPage /> },
      { path: "market", element: <MarketPage />, loader: requireProvider },
      { path: "schedule", element: <SchedulePage />, loader: requireProvider },
      { path: "calendar", element: <CalendarPage />, loader: requireProvider },
      { path: "skills", element: <SkillsPage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
