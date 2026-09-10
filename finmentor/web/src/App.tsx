import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 401 is handled by the client's refresh-and-retry; retrying it here
      // would just repeat a request that already failed for a good reason.
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
