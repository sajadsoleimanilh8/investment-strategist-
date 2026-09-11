/**
 * The three simulators, on one page.
 *
 * All of them POST `/api/simulations` with a different `kind`, and all of them
 * render before/after side by side. The engine decides every figure — this file
 * formats what came back and never computes a delta of its own.
 */
import { type FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { runDecision, runTimeMachine, runWhatIf } from "../api/simulations";
import { Field } from "../components/Field";
import { messageFor } from "../components/AsyncBoundary";
import { FormError } from "../components/FormError";
import { money } from "../components/Money";
import { useAuth } from "../auth/AuthContext";
import type { DecisionOut, ScenarioComparison, SimulationOut } from "../api/types";

function Sides({ current, scenario }: { current: ScenarioComparison; scenario: ScenarioComparison }) {
  const rows: [string, string, string][] = [
    ["Saving each month", money(current.monthly_savings), money(scenario.monthly_savings)],
    ["Projected savings", money(current.projected_savings_end), money(scenario.projected_savings_end)],
    ["Emergency cover", `${current.emergency_months.toFixed(1)} months`,
      `${scenario.emergency_months.toFixed(1)} months`],
    ["Health score", current.health_score.toFixed(1), scenario.health_score.toFixed(1)],
  ];
  if (current.estimated_goal_date || scenario.estimated_goal_date) {
    rows.push(["Goal date", current.estimated_goal_date ?? "no date yet",
      scenario.estimated_goal_date ?? "no date yet"]);
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">&nbsp;</th>
            <th scope="col" className="numeric">Now</th>
            <th scope="col" className="numeric">If you do this</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, before, after]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td className="numeric">{before}</td>
              <td className="numeric">{after}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Simulate() {
  const { user } = useAuth();
  const [savingsDelta, setSavingsDelta] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const whatIf = useMutation<SimulationOut>({
    mutationFn: () => runWhatIf(user!.id, { monthly_savings_delta: Number(savingsDelta) }),
    onError: (caught) => setError(messageFor(caught)),
  });

  const decision = useMutation<DecisionOut>({
    mutationFn: () => runDecision(user!.id, Number(price)),
    onError: (caught) => setError(messageFor(caught)),
  });

  const timeMachine = useMutation<ScenarioComparison[]>({
    mutationFn: () => runTimeMachine(user!.id),
    onError: (caught) => setError(messageFor(caught)),
  });

  function submitWhatIf(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!Number(savingsDelta)) {
      setError("Enter how much more (or less) you would save each month.");
      return;
    }
    whatIf.mutate();
  }

  function submitDecision(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (Number(price) <= 0) {
      setError("Enter what it costs.");
      return;
    }
    decision.mutate();
  }

  return (
    <>
      <section>
        <h2>What if I saved more?</h2>
        <form onSubmit={submitWhatIf}>
          <Field
            label="Extra saved each month"
            inputMode="numeric"
            value={savingsDelta}
            hint="A negative number works too."
            onChange={(e) => setSavingsDelta(e.target.value)}
          />
          <div className="actions">
            <button type="submit" disabled={whatIf.isPending}>
              {whatIf.isPending ? "Calculating…" : "Run it"}
            </button>
          </div>
        </form>

        {whatIf.data && (
          <>
            <Sides current={whatIf.data.current} scenario={whatIf.data.scenario} />
            <p className="disclaimer">{whatIf.data.disclaimer}</p>
          </>
        )}
      </section>

      <section>
        <h2>What would buying this do?</h2>
        <form onSubmit={submitDecision}>
          <Field
            label="What it costs"
            inputMode="numeric"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <div className="actions">
            <button type="submit" disabled={decision.isPending}>
              {decision.isPending ? "Calculating…" : "Show me"}
            </button>
          </div>
        </form>

        {decision.data && (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">&nbsp;</th>
                    <th scope="col" className="numeric">Before</th>
                    <th scope="col" className="numeric">After</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Savings</th>
                    <td className="numeric">{money(decision.data.savings_before)}</td>
                    <td className="numeric">{money(decision.data.savings_after)}</td>
                  </tr>
                  <tr>
                    <th scope="row">Emergency cover</th>
                    <td className="numeric">
                      {decision.data.emergency_months_before.toFixed(1)} months
                    </td>
                    <td className="numeric">
                      {decision.data.emergency_months_after.toFixed(1)} months
                    </td>
                  </tr>
                  <tr>
                    <th scope="row">Health score</th>
                    <td className="numeric">
                      {decision.data.health_score_before.toFixed(1)}
                    </td>
                    <td className="numeric">
                      {decision.data.health_score_after.toFixed(1)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            {/* Consequences, never a verdict. The API does not send one and
                this page does not invent one. */}
            <p className="disclaimer">{decision.data.disclaimer}</p>
          </>
        )}
      </section>

      <section>
        <h2>Time machine</h2>
        <p>The same you, four different habits, projected forward.</p>
        <div className="actions">
          <button
            type="button"
            onClick={() => timeMachine.mutate()}
            disabled={timeMachine.isPending}
          >
            {timeMachine.isPending ? "Calculating…" : "Show the paths"}
          </button>
        </div>

        {timeMachine.data && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Path</th>
                  <th scope="col" className="numeric">Saving each month</th>
                  <th scope="col" className="numeric">Projected savings</th>
                  <th scope="col" className="numeric">Health score</th>
                </tr>
              </thead>
              <tbody>
                {timeMachine.data.map((path) => (
                  <tr key={path.label}>
                    <th scope="row">{path.label}</th>
                    <td className="numeric">{money(path.monthly_savings)}</td>
                    <td className="numeric">{money(path.projected_savings_end)}</td>
                    <td className="numeric">{path.health_score.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <FormError message={error} />
      <p className="disclaimer">
        These are straight-line projections from your own figures, not forecasts.
      </p>
    </>
  );
}
