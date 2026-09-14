/**
 * The public landing page ("/").
 *
 * Deliberately not a marketing hero: no video, no 3D opening, no scroll-
 * hijacked reveal. The page opens directly into the one part of the product
 * that is genuinely usable without an account — live crypto prices — because
 * "this is a real financial intelligence tool" is a stronger first
 * impression made by a real, working feature than by any amount of
 * cinematic motion. A signed-in visitor never sees this at all: RootGate
 * sends them straight to /dashboard.
 *
 * Everything under "Example data" is illustrative on purpose (this app never
 * presents an invented number as if it were the visitor's own) — the live
 * prices above it are the one exception, because they come from a real
 * WebSocket connection to a real provider (see useLiveMarket / app/market/live.py).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Sparkline } from "../components/Sparkline";
import { useInView } from "../hooks/useInView";
import { useLiveMarket, type ConnectionStatus, type FeedSource } from "../hooks/useLiveMarket";
import { useScrolledPast } from "../hooks/useScrolledPast";
import { useValueFlash } from "../hooks/useValueFlash";
import "../styles/landing.css";

const ASSETS = [
  { symbol: "BTC", name: "Bitcoin" },
  { symbol: "ETH", name: "Ethereum" },
  { symbol: "SOL", name: "Solana" },
] as const;

const SYMBOLS = ASSETS.map((asset) => asset.symbol);

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Disconnected",
  off: "Feed off",
};

/** Synthetic prices say so, in the status line, in the disclaimer, and in
 * place of the word "live". The server decides this; the page only reports
 * it. See app/market/live.py for why a fallback to mock is never silent. */
const SOURCE_LABEL: Partial<Record<FeedSource, string>> = { mock: "Demo data" };

const CAPABILITIES = [
  { title: "Financial health", body: "Savings rate, emergency fund, debt load, budget stability and goal progress, each scored out of twenty from the figures you enter." },
  { title: "Financial Twin", body: "Your income, eight spending categories, savings, debt and emergency fund, recomputed the moment any of them changes." },
  { title: "Goals & Simulate", body: "Track every goal against real progress. Run a scenario (a raise, a move, a new debt) and see the honest downstream effect." },
  { title: "Ask", body: "A financial assistant that explains your own numbers back to you, in plain terms." },
];

/** Every section reveals itself once, on the way into view — see the note
 * in landing.css's Motion block on why nothing here repeats or hijacks scroll. */
function Reveal({ className = "", children, ...rest }: JSX.IntrinsicElements["section"]) {
  const { ref, inView } = useInView<HTMLElement>();
  return (
    <section ref={ref} className={`landing-reveal${inView ? " is-in" : ""} ${className}`} {...rest}>
      {children}
    </section>
  );
}

/** The dot follows the *source* first and the connection second: a synthetic
 * feed is not a green light, however healthy the socket is. */
function StatusDot({ status, demo }: { status: ConnectionStatus; demo: boolean }) {
  return <span className={`status-dot status-dot--${demo ? "demo" : status}`} aria-hidden="true" />;
}

function timeAgo(unixSeconds: number | undefined): string {
  if (!unixSeconds) return "not yet";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - unixSeconds));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

/**
 * The price, and the beat of colour when it moves.
 *
 * The flash used to be a single accent colour for any change, which told the
 * reader that something happened but not what. It now carries the direction —
 * the device every trading surface uses — so a tick you weren't watching still
 * says which way it went. See useValueFlash.
 */
function LivePriceValue({ price }: { price: number }) {
  const flash = useValueFlash(price);

  return (
    <span className={`live-price mono ${flash}`}>
      ${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );
}

export function Landing() {
  const [activeSymbol, setActiveSymbol] = useState<(typeof ASSETS)[number]["symbol"]>("BTC");
  const { status, source, ticks, history } = useLiveMarket(SYMBOLS);
  // The nav is bare over the intro and grows a ground once the intro is past
  // it — see the note on .landing-nav in landing.css for why it does not hide.
  const { ref: introEnd, past: navGrounded } = useScrolledPast<HTMLDivElement>();
  const [, forceTick] = useState(0);

  // "3s ago" only stays honest if this component re-renders while sitting
  // idle between ticks, not just when a new one arrives.
  useEffect(() => {
    const id = window.setInterval(() => forceTick((n) => n + 1), 5000);
    return () => window.clearInterval(id);
  }, []);

  const feedOff = status === "off";
  const activeTick = ticks[activeSymbol];
  const activeHistory = (history[activeSymbol] ?? []).map((t) => t.price_usd);
  const positive = (activeTick?.change_24h_pct ?? 0) >= 0;

  return (
    <div className="landing">
      <header className={`landing-nav${navGrounded ? " is-grounded" : ""}`}>
        <span className="landing-nav__mark">FinMentor</span>
        <nav aria-label="Main">
          <Link to="/login">Sign in</Link>
          <Link to="/signup" className="landing-nav__cta">Sign up</Link>
        </nav>
      </header>

      <main>
        <Reveal className="landing-intro">
          <h1>
            Understand the <span className="landing-accent">structure</span> behind your
            financial life.
          </h1>
          <p>
            A deterministic model of where your money actually stands, explained in plain
            language. Not a forecast dressed up as a fact.
          </p>
          <div className="landing-intro__actions">
            <Link to="/signup" className="landing-btn landing-btn--primary">Create an account</Link>
            <Link to="/login" className="landing-btn landing-btn--ghost">Sign in</Link>
          </div>
        </Reveal>

        {/* The marker the nav's state is tied to: it changes when *this*
            crosses the top of the viewport, which anchors the change to the end
            of the intro rather than to a pixel count a longer headline breaks.
            It is 1px tall rather than zero on purpose — see landing.css. */}
        <div ref={introEnd} className="landing-sentinel" aria-hidden="true" />

        <Reveal className="landing-market" aria-labelledby="live-market-heading">
          <div className="landing-market__head">
            <div>
              <span className="landing-kicker">Live market intelligence</span>
              <h2 id="live-market-heading">
                {source === "mock" ? "Demo prices, clearly labelled." : "Real prices, not a mockup."}
              </h2>
            </div>
            <div className="landing-status" role="status">
              <StatusDot status={status} demo={source === "mock"} />
              <span>{SOURCE_LABEL[source] ?? STATUS_LABEL[status]}</span>
              {activeTick && <span className="landing-status__time">· updated {timeAgo(activeTick.as_of)}</span>}
            </div>
          </div>

          {feedOff ? (
            /* No feed configured (DEMO_MODE, or MARKET_LIVE_SOURCE=off). The
               section says so and stops, rather than showing tabs that switch
               between three empty charts or a spinner that never resolves.
               Nothing synthetic goes here: the headline above promises a real
               price, and the honest way to keep that promise with no feed is
               to show no price. */
            <p className="landing-market__off">
              This build runs with no market connection, so there are no live prices to
              show. Everything else on this page works the same way.
            </p>
          ) : (
          <>
          <div className="landing-market__tabs" role="tablist" aria-label="Asset">
            <span
              className="landing-tab-indicator"
              style={{ transform: `translateX(${ASSETS.findIndex((a) => a.symbol === activeSymbol) * 100}%)` }}
              aria-hidden="true"
            />
            {ASSETS.map((asset) => (
              <button
                key={asset.symbol}
                role="tab"
                aria-selected={activeSymbol === asset.symbol}
                className={`landing-tab${activeSymbol === asset.symbol ? " is-active" : ""}`}
                onClick={() => setActiveSymbol(asset.symbol)}
              >
                {asset.symbol}
              </button>
            ))}
          </div>

          <div className="landing-market__body">
            <div className="landing-market__content" key={activeSymbol}>
              <div className="landing-market__figures">
                {activeTick ? (
                  <>
                    <LivePriceValue price={activeTick.price_usd} />
                    {activeTick.change_24h_pct !== null && (
                      <span className={`landing-delta ${positive ? "delta-positive" : "delta-negative"}`}>
                        {positive ? "+" : ""}
                        {activeTick.change_24h_pct.toFixed(2)}% · 24h
                      </span>
                    )}
                  </>
                ) : (
                  <span className="landing-market__waiting">
                    {status === "reconnecting" ? "Reconnecting to the market feed…" : "Waiting for the first price…"}
                  </span>
                )}
              </div>
              <Sparkline points={activeHistory} positive={positive} />
            </div>
          </div>
          </>
          )}
          {/* Section 27 asks for a disclaimer on every market surface, and a
              disclaimer that describes a feed which is not running is not one.
              Each state gets the sentence that is true of it. */}
          <p className="disclaimer">
            {feedOff
              ? "No market data is shown here. FinMentor provides educational information and historical analysis, not investment advice."
              : source === "mock"
                ? "Synthetic prices, generated locally for this demo. Not real market data, and not investment advice."
                : "Prices from CoinGecko, polled every 20s and pushed the moment they change. Not investment advice."}
          </p>
        </Reveal>

        <Reveal className="landing-capabilities" aria-labelledby="capabilities-heading">
          <span className="landing-kicker">Inside your account</span>
          <h2 id="capabilities-heading">The rest of the system.</h2>
          <dl className="landing-capabilities__list">
            {CAPABILITIES.map((c) => (
              <div className="landing-capabilities__item" key={c.title}>
                <dt>{c.title}</dt>
                <dd>{c.body}</dd>
              </div>
            ))}
          </dl>
          <span className="landing-sample-tag">Example data, not yours until you sign up</span>
        </Reveal>

        <Reveal className="landing-cta">
          <h2>Your financial structure, understood.</h2>
          <Link to="/signup" className="landing-btn landing-btn--primary">Create an account</Link>
        </Reveal>
      </main>

      <footer className="landing-footer">
        <span>FinMentor</span>
        <span>Every figure here is calculated from your data. FinMentor explains; it never tells you what to buy or sell.</span>
      </footer>
    </div>
  );
}
