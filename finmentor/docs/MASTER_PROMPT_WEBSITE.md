# MASTER PROMPT — FinMentor Website (Phase 7)

Paste this whole block into Claude Code at the start of a website session.

---

## 0. ROLE & OPERATING RULES (read first, Claude Code)

You are a senior full-stack engineer + product designer working on a
**production-grade web app that already exists**. Operate like a senior
collaborator, not a tutorial. Rules:

1. **Do not write any code yet.** First read everything below, then read
   `docs/SPEC.md`, `docs/ARCHITECTURE.md`, and `docs/ROADMAP.md` in the repo
   (these are ground truth — there is no `business.md`). Then ask me your
   clarifying questions (see §8), numbered, in one batch. Wait for my answers
   before touching anything.
2. **This is a brownfield repo.** Read the existing code before proposing
   changes. `web/src/pages/Landing.tsx`, `web/src/styles/layout.css`, and
   `web/src/router.tsx` define the conventions everything else follows.
3. **Challenge me** when you see a better architecture, library, or UX pattern
   than what I described. Propose, don't just comply. Especially challenge §2 —
   see the note there.
4. No fluff, no filler comments, no lorem. Real structure, real component names.
   Match the comment style already in the repo: file-level docstrings that
   explain *why*, not line-level narration of *what*.
5. Build incrementally, tell me what you're doing at each milestone. Confirm
   before installing any dependency — the current frontend has **four runtime
   deps on purpose**.
6. Everything ships optimized and accessible: see §7. Non-negotiable.

---

## 1. PROJECT OVERVIEW

**What we're building:** the website surface of FinMentor — a marketing landing
page plus an authenticated dashboard over the existing FastAPI backend. The
Telegram bot (Phase 6) keeps working against the same API; the website is a
second client, not a replacement.

**Who it's for:** young adults, 16–25, learning to understand their own money.
Assume low financial literacy and high design literacy — they have never read a
balance sheet but they can tell a cheap interface from a serious one instantly.

**Primary goal of the site:** sign up, then return. The landing page converts a
visitor into an account; the dashboard is the thing that earns the second visit.

**Business context:**

- English-only product (pivoted from Persian-first on 2026-09-07).
- Core is a **deterministic Financial Twin** plus engines: health score,
  what-if simulator, time machine, decision simulator, market analytics.
- **The hard architectural rule: AI only explains, it never computes numbers.**
  The flow is `User → intent → structured params → deterministic engine →
  verified result → LLM explanation`. Every number on screen comes from an
  engine endpoint. Never let a component synthesize, interpolate, or "smooth" a
  figure for visual effect.
- Live market data (Alpha Vantage / CoinGecko) is real but **untested by design**
  — it needs paid keys. Every market surface must degrade cleanly when the
  provider is cold, rate-limited, or absent. The landing page already does this;
  match its behavior.
- `DEMO_MODE` must run fully offline. This constrains fonts, assets, and any
  third-party runtime dependency.

**Reference / inspiration:** the **Fey design system** — "nocturnal Bloomberg
terminal, matte-black with luminous type."
Token spec: https://styles.refero.design/style/a0630421-7b66-48b4-aa14-6194a3b2c2b9
It is already adopted in `web/src/styles/layout.css` (token block + SKIN block)
and `landing.css`. Do not re-derive it; extend it.

---

## 2. TECH STACK — READ CAREFULLY, THIS IS NOT GREENFIELD

**What actually exists today:**

| Concern | Current |
|---|---|
| Build | Vite 6, TypeScript 5.7 |
| Framework | React 18 SPA, `react-router-dom` 6 (`createBrowserRouter`) |
| Data | TanStack Query 5 |
| Styling | Hand-written CSS + Fey design tokens. No Tailwind, no CSS-in-JS. |
| Components | Hand-rolled primitives (`Field`, `Money`, `Sparkline`, `AsyncBoundary`, `FormError`, `Layout`). No shadcn/ui. |
| Motion | Plain CSS in `styles/motion.css` + `useInView`. No Framer Motion, no GSAP. |
| Backend | FastAPI + SQLAlchemy 2.0 + Pydantic v2, same repo |
| Auth | `app/core/security.py`, `users.email` / `password_hash` |
| Tests | Vitest + Testing Library, Playwright e2e, `contrast.test.ts` |
| Package manager | npm |

**Total runtime dependencies: 4.** That is deliberate.

**The proposed stack in the original template was Next.js (App Router) +
Tailwind + shadcn/ui + Framer Motion + GSAP.** Before assuming that, answer this
in your question batch:

- Does this app need SSR/SSG at all? It is an authenticated dashboard over a
  separate FastAPI backend; the only SSR-worthy route is the public landing page.
- What breaks: `DEMO_MODE` offline guarantees, the existing Playwright/Vitest
  setup, the contrast test, and the deploy story (currently FastAPI serves the
  built SPA).
- What it costs: a full rewrite of 13 pages and the entire Fey token layer.

**My position:** default to keeping Vite + React + the hand-rolled CSS system,
and add only what's load-bearing. If you believe Next.js is genuinely the right
call, argue it with specifics — bundle size, LCP numbers, SEO impact on the
landing page — and propose a migration path that keeps the backend contract and
the token layer intact. If you agree the current stack is right, say so and stop
proposing Next.js for the rest of the session.

**Hosting:** deploy is the final step, not now. Current assumption is FastAPI
serving the built SPA from one origin (no CORS, no split deploy). Challenge this
if you disagree.

---

## 3. DESIGN SYSTEM

The Fey token layer in `web/src/styles/layout.css` is the design authority.
Load-bearing rules from that spec:

- **99px pills** for every control. No square buttons.
- **16px radius** content cards.
- **One deep black halo** instead of stacked elevation. No layered shadows.
- **No chromatic CTA fill.** The primary button is not blue/green/purple.
- **Chroma only as meaning**: delta direction (up/down), status, and exactly one
  accent word per headline. Nothing is colored for decoration.
- **Tight negative tracking** at display sizes.

**Two local constraints override the Fey spec — these are non-negotiable:**

1. **No web fonts.** Calibre is substituted by the system font stack, because
   `DEMO_MODE` must run offline. Do not add `next/font`, Google Fonts, or any
   self-hosted font file.
2. **Every token must clear WCAG AA**, enforced by
   `web/src/styles/contrast.test.ts`. If you introduce a color, add it to that
   test. A failing contrast test blocks the change.

**Design language:** high-end, restrained, financial-terminal serious. Motion is
intentional and quiet — reveal-on-scroll, value flashes on live data, count-ups
on figures. Avoid generic AI/template aesthetics: no gradient mesh backgrounds,
no floating glassmorphic cards, no purple-to-pink CTAs, no emoji in the UI.

**Existing primitives to reuse, not reinvent:**
`Layout`, `Field`, `FormError`, `Money`, `Sparkline`, `AsyncBoundary`, and the
hooks `useCountUp`, `useInView`, `useLiveMarket`, `useValueFlash`.

---

## 4. PAGE STRUCTURE

**Landing (`/`)** — public, gated by `RootGate`, which sends a signed-in visitor
straight to `/dashboard`. Current section order in `pages/Landing.tsx`:

1. `landing-nav` — mark, links, **Sign up** CTA
2. `landing-intro` — h1 with a single accent word, dual CTA (Create an account /
   Sign in)
3. `landing-market` — **live market intelligence**, real prices with a tabbed
   asset switcher, a status line with freshness ("updated 12s ago"), and a
   `disclaimer`. Must degrade gracefully when the provider is cold.
4. `landing-capabilities` — "The rest of the system", a `<dl>` of what's inside
   an account, tagged "Example data, not yours until you sign up"
5. `landing-cta` — closing conversion block
6. `landing-footer`

Each section reveals once on the way into view via the `Reveal` wrapper. Keep
that mechanism; don't swap it for a library without arguing why.

**Authenticated routes**, all inside the pathless `Layout` route:

| Route | Purpose | Priority |
|---|---|---|
| `/dashboard` | Financial Twin overview + health score | **critical** |
| `/onboarding` | creates the profile — sits in `RequireAuth` with `needsProfile={false}` to avoid a redirect loop | **critical** |
| `/simulate` | what-if / time machine / decision simulator | high |
| `/goals` | goal tracking | high |
| `/market` | watchlist + market analytics | high |
| `/learn` | education engine | medium |
| `/ask` | AI explanation surface (explains engine output, never computes) | medium |
| `/profile` | account settings | medium |
| `/signup`, `/login` | outside `Layout` — a signed-out visitor has no nav to show | **critical** |
| `*` | `NotFound` | low |

---

## 5. HERO SECTION

The original template specified a scroll-scrubbed 6-second video hero.

**My read: this is wrong for FinMentor, and here's why I want your opinion.**
The current hero's differentiator is that it shows *real market prices, not a
mockup* — the proof is that the numbers are live. A video hero replaces
verifiable data with a rendered loop, which is exactly the "template SaaS" signal
the Fey system is built to avoid. It also costs an offline-incompatible asset
(`DEMO_MODE`), a large LCP payload, and a pinned-scroll interaction that fights
the reveal rhythm of the rest of the page.

So: **tell me whether you agree.** If you think a scrubbed video earns its place,
make the case. If we do build it:

- Implementation: map scroll progress → `video.currentTime` on a `<video>` with
  `muted`, `playsInline`, `preload="auto"`, no controls. Smooth with a lerp.
  Prefer a small hand-rolled `requestAnimationFrame` + `IntersectionObserver`
  driver over adding GSAP (~70kb) for one effect — argue if you disagree.
- Placeholder at `public/hero-placeholder.mp4`, swappable via **one** path
  constant. I'll supply the real 6s clip after the build.
- `prefers-reduced-motion`: render a static poster frame, no scrub, no pin.
- It must not block first paint or regress LCP, and it must not break
  `DEMO_MODE` offline.
- Tell me the ideal export settings for smooth scrubbing — codec, resolution,
  keyframe interval / GOP, bitrate, fps.

---

## 6. HEADER / NAVIGATION

Currently `landing-nav` lives inside the landing page and `Layout` carries the
app nav for authenticated routes. The template asked for a scroll-aware header
that reveals only after the hero.

Decide and justify: is a hidden-then-revealing header right for a page whose
first CTA is "Sign up"? Hiding the only conversion affordance above the fold is a
real cost. If we do it, one implementation, consistent across all pages, using
the existing `useInView` hook rather than a new dependency.

---

## 7. OPTIMIZATION & QUALITY BAR (always on)

- **Core Web Vitals first.** Protect LCP/CLS/INP. No layout shift from live
  market values — reserve space for figures that arrive late. `useValueFlash`
  exists for this; use it.
- Lazy-load below the fold. Code-split any heavy route.
- **No new runtime dependency without justifying it against the 4-dep budget.**
  A dependency added for one visual effect is a no.
- **Accessible**: semantic HTML (the landing already uses `aria-labelledby`,
  `role="tablist"`, `role="status"` — match it), visible focus states, and a
  `prefers-reduced-motion` fallback for every animation.
- **WCAG AA on every color**, enforced by `contrast.test.ts`.
- Mobile-first, tested at real breakpoints.
- Typed props, no `any`, no dead code.
- **Tests are part of "done"**: Vitest for logic, Playwright for flows,
  `contrast.test.ts` for tokens. Screenshots land in `docs/screenshots/`.

---

## 8. WORKFLOW — ASK ME FIRST

Before writing any code:

1. Read this prompt, then `docs/SPEC.md`, `docs/ARCHITECTURE.md`,
   `docs/ROADMAP.md`, and the existing `web/src/` conventions.
2. Ask me all your clarifying questions in one numbered batch. I specifically
   want your position on: the Next.js question (§2), the video hero (§5), and the
   hiding header (§6). Plus anything ambiguous about auth flow, the onboarding
   profile gate, market-data degradation, or the AI-explains-only boundary.
3. Propose the file layout and build order. Wait for my OK.
4. Then: build section by section → wire auth → optimize → (final) deploy.

**Extra instructions for this project:**

- **Never let a UI component compute a financial number.** If a figure isn't in
  an API response, the answer is a new engine endpoint, not client-side math.
  This includes "just" summing, averaging, projecting, or annualizing.
- Persian strings still linger in `app/bot/messages.py`, `app/bot/keyboards.py`,
  `app/bot/formatting.py`, `app/ai/safety.py`, and
  `app/services/education_engine.py` (tracked as Part 0 of Phase 3). Don't let
  any of them reach the website.
- `python-telegram-bot` is in `requirements.txt` but not installed in this
  sandbox — `app.bot.handlers` / `app.bot.keyboards` won't import. Expected;
  don't try to fix it.
- Alpha Vantage / CoinGecko live paths and remote-LLM live paths are untested by
  design (paid keys). They're on the Phase 7 pre-deploy checklist. Don't write
  tests that require them; do write tests for the degraded path.

---

## 9. DELIVERABLES AFTER BUILD

1. If we build the video hero: exact export settings (codec, resolution, GOP /
   keyframe interval, bitrate, fps) for jank-free scrubbing.
2. Updated `docs/screenshots/` (`dashboard.png`, `deltas.png`, and any new page).
3. The Phase 7 pre-deploy checklist, filled in: env vars, the `users.email` /
   `password_hash` migration, the API-key story for Alpha Vantage + CoinGecko,
   and how the built SPA gets served.
4. A short note in `docs/ROADMAP.md` recording what Phase 7 actually shipped and
   what moved to Phase 8.
