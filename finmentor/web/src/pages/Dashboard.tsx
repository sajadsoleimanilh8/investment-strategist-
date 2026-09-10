/** One request, one screen. Everything here came from `/api/me/summary`. */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { getSummary } from "../api/health";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { compact, money, percent } from "../components/Money";

const COMPONENT_LABELS: Record<string, string> = {
  savings_rate: "Savings rate",
  emergency_fund: "Emergency fund",
  debt_load: "Debt load",
  budget_stability: "Budget stability",
  goal_progress: "Goal progress",
};

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["summary"],
    queryFn: getSummary,
  });

  return (
    <AsyncBoundary isLoading={isLoading} error={error}>
      {data && !data.onboarded && (
        <section>
          <h2>Welcome</h2>
          <p>
            I do not have your numbers yet.{" "}
            <Link to="/onboarding">Set up your profile</Link> and I can show you
            where you stand.
          </p>
        </section>
      )}

      {data?.onboarded && data.health && data.twin && data.dna && (
        <>
          <section>
            <h2>Financial health: {data.health.total.toFixed(1)} / 100</h2>
            <div className="table-scroll">
              <table>
                <caption className="disclaimer">
                  Every component is out of 20. Higher is always better.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Component</th>
                    <th scope="col" className="numeric">Points</th>
                    <th scope="col">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {data.health.components.map((component) => (
                    <tr key={component.name}>
                      <th scope="row">
                        {COMPONENT_LABELS[component.name] ?? component.name}
                      </th>
                      <td className="numeric">
                        {component.points.toFixed(1)} / {component.max_points}
                      </td>
                      <td>{component.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2>Financial DNA</h2>
            <dl className="pairs">
              {Object.entries(data.dna).map(([trait, band]) => (
                <div key={trait}>
                  <dt>{trait.replace(/_/g, " ")}</dt>
                  <dd>{band}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section>
            <h2>This month</h2>
            <dl className="pairs">
              <dt>Income</dt>
              <dd>{money(data.twin.income)}</dd>
              <dt>Spending</dt>
              <dd>{money(data.twin.monthly_expenses)}</dd>
              <dt>Saving</dt>
              <dd>
                {money(data.twin.monthly_savings)} ({percent(data.twin.savings_rate)})
              </dd>
              <dt>Emergency cover</dt>
              <dd>{data.twin.emergency_months.toFixed(1)} months</dd>
              <dt>Debt</dt>
              <dd>{money(data.twin.debt)}</dd>
            </dl>
          </section>

          <section>
            <h2>Goals</h2>
            {data.goals.length === 0 ? (
              <p>
                No goals yet. <Link to="/goals">Add one</Link>.
              </p>
            ) : (
              <ul>
                {data.goals.map((goal) => (
                  <li key={goal.id}>
                    <strong>{goal.name}</strong> — {goal.progress_pct.toFixed(1)}%
                    ({compact(goal.current_amount)} of {compact(goal.target_amount)})
                    {goal.estimated_completion &&
                      ` · on track for ${goal.estimated_completion}`}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2>Watchlist</h2>
            {data.watchlist.length === 0 ? (
              <p>
                Nothing tracked. <Link to="/market">Add a symbol</Link>.
              </p>
            ) : (
              <ul>
                {data.watchlist.map((item) => (
                  <li key={item.symbol}>
                    <strong>{item.symbol}</strong> {compact(item.latest_price)} · 7d{" "}
                    <span
                      className={
                        item.change_7d_pct >= 0 ? "delta-positive" : "delta-negative"
                      }
                    >
                      {item.change_7d_pct.toFixed(2)}%
                    </span>{" "}
                    · {item.trend}
                  </li>
                ))}
              </ul>
            )}
            <p className="disclaimer">{data.market_disclaimer}</p>
          </section>
        </>
      )}
    </AsyncBoundary>
  );
}
