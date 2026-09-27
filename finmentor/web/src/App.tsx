import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { AmbientField } from "./components/AmbientField";
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
        {/* Above the router on purpose: the atmosphere is the one thing that
            does not reload when the route does, which is what makes a
            navigation read as moving within the product rather than as
            fetching a new document. See AmbientField. */}
        <AmbientField />
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
