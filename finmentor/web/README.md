# FinMentor — web client

A second delivery surface over the same FastAPI backend the Telegram bot uses.
No business logic lives here: every figure on screen was calculated by
`app/services` and arrived over HTTP. The client formats and routes; it does
not compute.

## This phase built structure, not design

**The app is deliberately unstyled.** Plain `<button>`, `<input>`, `<table>`,
browser fonts, browser colours. It will look like a 1996 form, and that is
correct — the visual design has not been chosen yet, and guessing at one now
would mean throwing it away later.

What *is* finished is everything underneath: routing, auth, the API client,
forms, validation, loading and error states, and cache invalidation. A reviewer
can complete the whole flow end to end.

### Where the design plugs in

`src/styles/layout.css` is structure only — flow, spacing, alignment. At the
top of it is a `:root` block of design tokens, declared and left **empty on
purpose**:

```css
:root {
  --color-bg: ;
  --color-text: ;
  --color-positive: ;   /* a delta in the user's favour */
  --font-body: ;
  --radius: ;
  ...
}
```

Fill those in and the structure below picks them up untouched. `reset.css` is
the other half: it removes browser defaults that fight any design, and
expresses none of its own.

Per SPEC §30 the intended direction is dark, with green/red/neutral for
financial deltas, reading as "trust · clarity · youth". That decision is
yours to make.

## Running it

```bash
npm install
cp .env.example .env          # VITE_API_BASE_URL, no trailing slash
npm run dev                   # http://localhost:5173
```

The API must be running and must allow this origin — `CORS_ORIGINS` in the
backend `.env` defaults to `["http://localhost:5173"]`.

```bash
npm run build                 # tsc -b && vite build
npm test                      # vitest
```

## Layout

```
src/
  api/          client.ts (fetch + auth header + refresh-on-401)
                one module per resource, typed against the API
  auth/         AuthContext (who is signed in), RequireAuth (route guard)
  pages/        Signup, Login, Onboarding, Dashboard, Goals, Simulate,
                Market, Learn, Ask, Profile, NotFound
  components/   Layout, Field, FormError, AsyncBoundary, Money — semantic
                HTML, no styling beyond structure
  styles/       reset.css + layout.css (with the theming seam)
```

## How auth works

- **Access token**: in memory only, 30 minutes. A token in `localStorage` is
  readable by anything injected into the page; a token in a variable dies with
  the tab, which is the right trade for a short-lived credential.
- **Refresh token**: in `localStorage`, 14 days, rotated on every use. This is
  what lets a reload recover a session.
- **Refresh-on-401**: handled once, centrally, in `api/client.ts`. Concurrent
  401s share a single refresh — six dashboard widgets expiring together must
  not fire six refreshes and rotate the token out from under each other. That
  case is tested, because when it breaks it looks like a random logout.
- Signup, login and refresh are sent anonymously and are never retried: a wrong
  password is not an expired session, and retrying would hide the real error.

## Rules this client follows

- **No business logic.** No page computes a score, a delta or a projection.
- **The disclaimer comes from the API.** Market payloads carry their own text
  and pages render it, so changing the wording server-side changes it here.
- **The decision page states consequences, never a verdict.** The API does not
  send one and the UI does not invent one.
- **`/ask` shows which tier answered.** `deterministic` means the model was
  unavailable and the reply is the verified figures rendered plainly. That is a
  different kind of answer and the user is entitled to know which one they got.
