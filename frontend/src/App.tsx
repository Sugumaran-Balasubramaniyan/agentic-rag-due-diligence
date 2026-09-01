import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "./index.css";

const queryClient = new QueryClient();

function Shell() {
  return (
    <main>
      <p>Deterministic demo mode</p>
      <h1>Due-Diligence Copilot</h1>
      <p>Evidence-first research workspace.</p>
    </main>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  );
}
