import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createGoal, listGoals } from "../api/goals";
import { AsyncBoundary, messageFor } from "../components/AsyncBoundary";
import { Field } from "../components/Field";
import { FormError } from "../components/FormError";
import { compact } from "../components/Money";
import { useAuth } from "../auth/AuthContext";

/** Priority is stored as 1-5 and weighs the goal-progress score (priority 1
 * counts five times a priority 5). A bare digit in a table says none of that,
 * so the two ends and the middle carry a word. */
const PRIORITY_LABEL: Record<number, string> = {
  1: "1 (highest)",
  2: "2",
  3: "3 (normal)",
  4: "4",
  5: "5 (lowest)",
};

export function Goals() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [current, setCurrent] = useState("");
  const [deadline, setDeadline] = useState("");
  const [priority, setPriority] = useState(3);
  const [error, setError] = useState<string | null>(null);

  const goals = useQuery({
    queryKey: ["goals", user?.id],
    queryFn: () => listGoals(user!.id),
    enabled: Boolean(user),
  });

  const add = useMutation({
    mutationFn: () =>
      createGoal(user!.id, {
        name: name.trim(),
        target_amount: Number(target),
        current_amount: Number(current || 0),
        deadline: deadline || null,
        priority,
      }),
    onSuccess: () => {
      setName("");
      setTarget("");
      setCurrent("");
      setDeadline("");
      // The dashboard shows goals too, and goal progress moves the health
      // score — so both caches are stale the moment one is added.
      queryClient.invalidateQueries({ queryKey: ["goals"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
    onError: (caught) => setError(messageFor(caught)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim() || Number(target) <= 0) {
      setError("A goal needs a name and a target above zero.");
      return;
    }
    add.mutate();
  }

  return (
    <>
      <section>
        <h2>Your goals</h2>
        <AsyncBoundary
          isLoading={goals.isLoading}
          error={goals.error}
          isEmpty={goals.data?.length === 0}
          emptyMessage="No goals yet. Add one below and I will track the date you reach it."
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Goal</th>
                  <th scope="col" className="numeric">Progress</th>
                  <th scope="col" className="numeric">Saved</th>
                  <th scope="col">On track for</th>
                  <th scope="col" className="numeric">Priority</th>
                </tr>
              </thead>
              <tbody>
                {goals.data?.map((goal) => (
                  <tr key={goal.id}>
                    <th scope="row">{goal.name}</th>
                    <td className="numeric">{goal.progress_pct.toFixed(1)}%</td>
                    <td className="numeric">
                      {compact(goal.current_amount)} / {compact(goal.target_amount)}
                    </td>
                    <td>{goal.estimated_completion ?? "no date yet"}</td>
                    <td className="numeric">
                      {PRIORITY_LABEL[goal.priority] ?? goal.priority}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncBoundary>
      </section>

      <section>
        <h2>Add a goal</h2>
        <form onSubmit={submit}>
          <Field
            label="Name"
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
          />
          <Field
            label="Target amount"
            inputMode="numeric"
            value={target}
            required
            onChange={(e) => setTarget(e.target.value)}
          />
          <Field
            label="Saved so far"
            inputMode="numeric"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <Field
            label="Want it by"
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
          <p className="field">
            <label htmlFor="goal-priority">Priority</label>
            <select
              id="goal-priority"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            >
              {Object.entries(PRIORITY_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </p>
          <FormError message={error} />
          <div className="actions">
            <button type="submit" disabled={add.isPending}>
              {add.isPending ? "Adding…" : "Add goal"}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
