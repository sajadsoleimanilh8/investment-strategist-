/**
 * Recorded monthly income, and what its spread suggests.
 *
 * The suggestion is an observation and the panel is careful to keep it one.
 * It never changes "Is it steady?" for the user; it says what the records
 * look like and points at the field, which is on this page. Two reasons, and
 * the second is the one that matters: nothing reads `income_type` today, so
 * writing a derived value would have no effect at all; and the moment
 * something does read it, a silent derivation would move every existing
 * user's figures without them asking.
 *
 * Same shape as `ExpenseHistory` on purpose -- a table with a proportional
 * bar, the same window selector -- because they are the same kind of thing and
 * learning one should teach you the other.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getIncomeHistory } from "../api/income";
import { monthLabel } from "./ExpenseHistory";
import { Money } from "./Money";
import { AsyncBoundary } from "./AsyncBoundary";
import type { IncomeSignal } from "../api/types";

const WINDOWS = [3, 6, 12, 24] as const;

const STEADINESS: Record<string, string> = {
  fixed: "steady",
  variable: "variable",
  mixed: "a mix",
};

/** How the spread reads in a sentence, or null when there is nothing to say. */
export function signalNote(signal: IncomeSignal | null | undefined): string | null {
  if (!signal) return null;
  if (signal.insufficient) {
    const had = signal.periods === 1 ? "one month" : `${signal.periods} months`;
    return `Recorded for ${had} so far. Three is enough to say whether your income is steady.`;
  }
  if (!signal.disagrees) return null;

  const looks = STEADINESS[signal.suggested ?? ""] ?? signal.suggested;
  const said = STEADINESS[signal.declared] ?? signal.declared;
  return (
    `Your records over ${signal.periods} months look ${looks}, and "Is it steady?" ` +
    `above is set to ${said}. Change it if the records are right. Nothing here ` +
    `changes it for you.`
  );
}

export function IncomeHistory() {
  const [months, setMonths] = useState<number>(12);
  const history = useQuery({
    queryKey: ["income-history", months],
    queryFn: () => getIncomeHistory(months),
  });

  const periods = history.data?.periods ?? [];
  const peak = periods.reduce((most, row) => Math.max(most, row.amount), 0);
  const note = signalNote(history.data?.signal);

  return (
    <section aria-labelledby="income-history-heading" className="stack">
      <h3 id="income-history-heading">Income over time</h3>

      <p className="field">
        <label htmlFor="income-window">Show</label>
        <select
          id="income-window"
          value={months}
          onChange={(event) => setMonths(Number(event.target.value))}
        >
          {WINDOWS.map((window) => (
            <option key={window} value={window}>
              {`the last ${window} months`}
            </option>
          ))}
        </select>
      </p>

      <AsyncBoundary
        isLoading={history.isLoading}
        error={history.error}
        isEmpty={periods.length === 0}
        emptyMessage="Nothing recorded yet. Each time you save your profile, that month's income is filed here."
        onRetry={() => void history.refetch()}
      >
        <div className="table-scroll">
          <table className="history">
            <caption className="visually-hidden">
              Recorded monthly income, oldest first
            </caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Income</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((row) => (
                <tr key={row.period}>
                  <th scope="row">{monthLabel(row.period)}</th>
                  <td>
                    <span
                      aria-hidden="true"
                      className="history__bar"
                      style={{ width: peak > 0 ? `${(row.amount / peak) * 100}%` : "0%" }}
                    />
                    <Money value={row.amount} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {note && <p role="status" className="muted">{note}</p>}
      </AsyncBoundary>
    </section>
  );
}
