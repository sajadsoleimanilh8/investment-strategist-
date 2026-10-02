/**
 * Recorded spending, month by month.
 *
 * The data has always been there: every profile save files its expenses under
 * a `YYYY-MM` period and rewrites only that period, so a user six months in
 * has six months of records and could see one of them. This is the read.
 *
 * A table rather than a chart, with a proportional bar per row. Two reasons.
 * The numbers are the point and a table gives them exactly, to a screen
 * reader as well as to the eye. And the obvious chart component here is
 * `Sparkline`, which colours a series green or red by direction: that is a
 * market idea, and "spending went up" is not good or bad without knowing why.
 * A bar states the magnitude and claims nothing about it.
 *
 * Months with no records are not rows. The API leaves them out because zeros
 * would assert the user spent nothing, and the note under the table says so
 * rather than letting a gap read as a dip to zero.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getExpenseHistory } from "../api/expenses";
import { Money } from "./Money";
import { AsyncBoundary } from "./AsyncBoundary";

/** The windows worth offering. Each is a number the API will accept. */
const WINDOWS = [3, 6, 12, 24] as const;

/** `2026-01` -> `Jan 2026`, without pulling in a date library for one label. */
const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function monthLabel(period: string): string {
  const [year, month] = period.split("-");
  const name = MONTH_NAMES[Number(month) - 1];
  return name ? `${name} ${year}` : period;
}

/**
 * Whether any month inside the window is missing from the series.
 *
 * Counted from the span the data actually covers, not from the window asked
 * for: a user who started three months ago has not "missed" the nine before
 * that, and telling them they have would be wrong.
 */
export function hasGaps(periods: string[]): boolean {
  if (periods.length < 2) return false;
  const ordinal = (period: string) => {
    const [year, month] = period.split("-").map(Number);
    return year * 12 + month;
  };
  const span = ordinal(periods[periods.length - 1]) - ordinal(periods[0]) + 1;
  return span > periods.length;
}

export function ExpenseHistory() {
  const [months, setMonths] = useState<number>(12);
  const history = useQuery({
    queryKey: ["expense-history", months],
    queryFn: () => getExpenseHistory(months),
  });

  const periods = history.data?.periods ?? [];
  const peak = periods.reduce((most, row) => Math.max(most, row.total), 0);

  return (
    <section aria-labelledby="history-heading" className="stack">
      <h3 id="history-heading">Spending over time</h3>

      <p className="field">
        <label htmlFor="history-window">Show</label>
        <select
          id="history-window"
          value={months}
          onChange={(event) => setMonths(Number(event.target.value))}
        >
          {WINDOWS.map((window) => (
            <option key={window} value={window}>
              {window === 12 ? "the last 12 months" : `the last ${window} months`}
            </option>
          ))}
        </select>
      </p>

      <AsyncBoundary
        isLoading={history.isLoading}
        error={history.error}
        isEmpty={periods.length === 0}
        emptyMessage="Nothing recorded yet. Save your expenses and this fills in."
        onRetry={() => void history.refetch()}
      >
        <div className="table-scroll">
          <table className="history">
            <caption className="visually-hidden">
              Recorded spending per month, oldest first
            </caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Total</th>
                <th scope="col">Essentials</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((row) => (
                <tr key={row.period}>
                  <th scope="row">{monthLabel(row.period)}</th>
                  <td>
                    {/* The bar is decoration over a real number, so it is
                        hidden from the accessibility tree: a screen reader
                        reads the figure, not a width. */}
                    <span
                      aria-hidden="true"
                      className="history__bar"
                      style={{ width: peak > 0 ? `${(row.total / peak) * 100}%` : "0%" }}
                    />
                    <Money value={row.total} />
                  </td>
                  <td><Money value={row.essential_total} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {hasGaps(periods.map((row) => row.period)) && (
          <p className="muted">
            Months you have not recorded are not listed, so a missing month is
            a gap in the record rather than a month you spent nothing.
          </p>
        )}
      </AsyncBoundary>
    </section>
  );
}
