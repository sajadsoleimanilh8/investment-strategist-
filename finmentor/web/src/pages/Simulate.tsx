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

/**
 * Before, after, and the change between them.
 *
 * The change column is the engine's `deltas`, not a subtraction done here.
 * That distinction is the whole architectural rule in miniature: the two
 * outer columns are figures the engine sent, and the middle one would be a
 * figure this component invented if it were computed in the browser. The
 * engine already sends it, keyed by the same field names, so there is nothing
 * to invent.
 */
const ROWS = [
  { key: "monthly_savings", label: "Saving each month", format: money },
  { key: "projected_savings_end", label: "Projected savings", format: money },
  {
    key: "goal_completion_pct",
    label: "Goal progress",
    format: (value: number) => `${value.toFixed(1)}%`,
  },
  {
    key: "emergency_months",
    label: "Emergency cover",
    format: (value: number) => `${value.toFixed(1)} months`,
  },
  { key: "health_score", label: "Health score", format: (value: number) => value.toFixed(1) },
] as const;

function Sides({
  current, scenario, deltas,
}: {
  current: ScenarioComparison;
  scenario: ScenarioComparison;
  deltas: Record<string, number>;
}) {
  return (
    <div className="table-scroll result">
      <table>
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">Measure</span></th>
            <th scope="col" className="numeric">Now</th>
            <th scope="col" className="numeric">If you do this</th>
            <th scope="col" className="numeric">Change</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(({ key, label, format }) => {
            const before = current[key];
            const after = scenario[key];
            // A goal that does not exist has no percentage on either side, and
            // a zero there would read as "no change" rather than "no goal".
            if (before === null || after === null) return null;
            const delta = deltas[key];

            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td className="numeric">{format(before)}</td>
                <td className="numeric">{format(after)}</td>
                <td
                  className={`numeric ${
                    delta === undefined || delta === 0
                      ? ""
                      : delta > 0 ? "delta-positive" : "delta-negative"
                  }`}
                >
                  {delta === undefined
                    ? ""
                    : `${delta > 0 ? "+" : ""}${format(delta)}`}
                </td>
              </tr>
            );
          })}
          {(current.estimated_goal_date || scenario.estimated_goal_date) && (
            <tr>
              <th scope="row">Goal date</th>
              <td className="numeric">{current.estimated_goal_date ?? "no date yet"}</td>
              <td className="numeric">{scenario.estimated_goal_date ?? "no date yet"}</td>
              {/* A date has no delta: the engine sends none, and "three months
                  earlier" is arithmetic this file is not allowed to do. */}
              <td />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Simulate() {
  const { user } = useAuth();
  const [savingsDelta, setSavingsDelta] = useState("");
  const [price, setPrice] = useState("");
  // One message per form, not one for the page. Three simulators share this
  // screen, and a single error slot at the bottom put the reason for a failed
  // submission three sections away from the field that caused it.
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const fail = (form: string) => (caught: unknown) =>
    setErrors((prev) => ({ ...prev, [form]: messageFor(caught) }));
  const clear = (form: string) => setErrors((prev) => ({ ...prev, [form]: null }));

  const whatIf = useMutation<SimulationOut>({
    mutationFn: () => runWhatIf(user!.id, { monthly_savings_delta: Number(savingsDelta) }),
    onError: fail("whatIf"),
  });

  const decision = useMutation<DecisionOut>({
    mutationFn: () => runDecision(user!.id, Number(price)),
    onError: fail("decision"),
  });

  const timeMachine = useMutation<ScenarioComparison[]>({
    mutationFn: () => runTimeMachine(user!.id),
    onError: fail("timeMachine"),
  });

  function submitWhatIf(event: FormEvent) {
    event.preventDefault();
    clear("whatIf");
    if (!Number(savingsDelta)) {
      setErrors((prev) => ({
        ...prev,
        whatIf: "Enter how much more (or less) you would save each month.",
      }));
      return;
    }
    whatIf.mutate();
  }

  function submitDecision(event: FormEvent) {
    event.preventDefault();
    clear("decision");
    if (Number(price) <= 0) {
      setErrors((prev) => ({ ...prev, decision: "Enter what it costs." }));
      return;
    }
    decision.mutate();
  }

  return (
    <>
      {/* The widest table on the page, and the simulator people reach for
          first, so it takes the full width and the other two share the row
          below it. */}
      <section className="span">
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
        <FormError message={errors.whatIf} />

        {whatIf.data && (
          <>
            <Sides
              current={whatIf.data.current}
              scenario={whatIf.data.scenario}
              deltas={whatIf.data.deltas}
            />
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
        <FormError message={errors.decision} />

        {decision.data && (
          <>
            <div className="table-scroll result">
              <table>
                <thead>
                  <tr>
                    <th scope="col"><span className="visually-hidden">Measure</span></th>
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

        <FormError message={errors.timeMachine} />

        {timeMachine.data && (
          <div className="table-scroll result">
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

      <p className="disclaimer">
        These are straight-line projections from your own figures, not forecasts.
      </p>
    </>
  );
}
