import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { OnboardingPage } from "@/pages/Onboarding";
import { CapabilitiesPage } from "@/pages/Capabilities";
import { ChatPage } from "@/pages/Chat";
import { MissionsPage } from "@/pages/Missions";
import { ArtifactsPage } from "@/pages/Artifacts";
import { AssetsPage } from "@/pages/Assets";
import { ApprovalsPage } from "@/pages/Approvals";
import { ProofsPage } from "@/pages/Proofs";
import { MemoryPage } from "@/pages/Memory";
import { OutcomesPage } from "@/pages/Outcomes";
import { ChannelsPage } from "@/pages/Channels";
import { ConnectionsPage } from "@/pages/Connections";
import { HowItWorksPage } from "@/pages/HowItWorks";
import { ProvidersPage } from "@/pages/Providers";
import { MarketPage } from "@/pages/Market";
import { SchedulePage } from "@/pages/Schedule";
import { SkillsPage } from "@/pages/Skills";
import { SettingsPage } from "@/pages/Settings";

// FastAPI serves the SPA from / after a successful login (the legacy Jinja /login
// page still owns the token form). React Router handles every in-app route.
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { path: "start", element: <OnboardingPage /> },
      { path: "capabilities", element: <CapabilitiesPage /> },
      { path: "how-it-works", element: <HowItWorksPage /> },
      { index: true, element: <ChatPage /> },
      { path: "missions", element: <MissionsPage /> },
      { path: "assets", element: <AssetsPage /> },
      { path: "artifacts", element: <ArtifactsPage /> },
      { path: "approvals", element: <ApprovalsPage /> },
      { path: "proofs", element: <ProofsPage /> },
      { path: "memory", element: <MemoryPage /> },
      { path: "outcomes", element: <OutcomesPage /> },
      { path: "connections", element: <ConnectionsPage /> },
      { path: "channels", element: <ChannelsPage /> },
      { path: "providers", element: <ProvidersPage /> },
      { path: "market", element: <MarketPage /> },
      { path: "schedule", element: <SchedulePage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
