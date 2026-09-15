/**
 * The "continue with" buttons, above the email form.
 *
 * Which ones appear is the server's answer, not a constant here: a provider
 * without credentials is absent rather than disabled, because a button that
 * leads to Google's own error page reads as this product being broken.
 *
 * They are links, not buttons with click handlers. The provider has to see a
 * top-level navigation — an XHR cannot show a consent screen — and an anchor
 * is what a browser already knows how to do with the middle mouse button, a
 * long press, or a keyboard.
 *
 * On the marks: these are text labels rather than each provider's logo.
 * Google and Apple both publish branding rules for their sign-in buttons that
 * a text label does not satisfy, and meeting them means shipping their
 * official SVGs as static assets. That is a launch task, noted in
 * docs/PRE_DEPLOY.md, not something to approximate by drawing the logos here.
 */
import { useQuery } from "@tanstack/react-query";

import { oauthProviders, oauthStartUrl } from "../api/auth";

const LABEL: Record<string, string> = {
  google: "Google",
  github: "GitHub",
  apple: "Apple",
};

export function ProviderSignIn({ next = "/dashboard" }: { next?: string }) {
  const { data } = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: oauthProviders,
    // The answer changes on deploy, not while somebody is looking at it.
    staleTime: Infinity,
    retry: false,
  });

  const providers = data?.providers ?? [];
  if (providers.length === 0) return null;

  return (
    <div className="providers">
      <ul className="providers__list">
        {providers.map((provider) => (
          <li key={provider}>
            <a className="provider-button" href={oauthStartUrl(provider, next)}>
              Continue with {LABEL[provider] ?? provider}
            </a>
          </li>
        ))}
      </ul>
      {/* A separator that says what the two halves are, rather than a bare
          rule the eye has to interpret. */}
      <p className="providers__or"><span>or use your email</span></p>
    </div>
  );
}
