/**
 * Goals, and everything you can do to one after making it.
 *
 * The page used to be create-and-read only. That sounds like a missing
 * convenience and was not: `current_amount` could only be set at creation, so
 * progress never moved, `score_goal_progress` never moved, and a fifth of the
 * health score sat at whatever the first save happened to produce. Recording
 * what you have saved is the loop this product is built around.
 *
 * Four actions, and the split between the last two is deliberate. Saving more
 * is the common one and gets its own inline control rather than the full edit
 * form, because "I put aside another two million" should not require
 * re-reading five fields. Archiving is for a goal that is over; deleting is
 * for one that should not exist. Only deleting is irreversible, so only
 * deleting asks.
 */
import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createGoal, deleteGoal, listGoals, updateGoal } from "../api/goals";
import { AsyncBoundary, messageFor } from "../components/AsyncBoundary";
import { Field } from "../components/Field";
import { FormError } from "../components/FormError";
import { compact } from "../components/Money";
import { useAuth } from "../auth/AuthContext";
import type { Goal } from "../api/types";

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

/** Blank means zero, and so does anything unreadable. Matches Onboarding. */
function toNumber(value: string): number {
  const parsed = Number(value.replace(/[,\s]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

/** The fields a goal update has to carry. A PUT is a replace, so every one of
 * them travels even when only the amount changed. `is_active` is deliberately
 * absent: omitting it is what tells the server to leave the goal where it is. */
function draftOf(goal: Goal) {
  return {
    name: goal.name,
    target_amount: goal.target_amount,
    current_amount: goal.current_amount,
    deadline: goal.deadline,
    priority: goal.priority,
  };
}

export function Goals() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Goal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const goals = useQuery({
    queryKey: ["goals", user?.id, showArchived],
    queryFn: () => listGoals(user!.id, { activeOnly: !showArchived }),
    enabled: Boolean(user),
  });

  // Goal progress moves the health score, so the dashboard is stale the
  // moment any of this succeeds.
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["goals"] });
    queryClient.invalidateQueries({ queryKey: ["summary"] });
  };

  const save = useMutation({
    mutationFn: ({ id, draft }: { id: number; draft: Parameters<typeof updateGoal>[1] }) =>
      updateGoal(id, draft),
    onSuccess: () => {
      setEditing(null);
      refresh();
    },
    onError: (caught) => setError(messageFor(caught)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteGoal(id),
    onSuccess: refresh,
    onError: (caught) => setError(messageFor(caught)),
  });

  function addSaved(goal: Goal, amount: number) {
    setError(null);
    save.mutate({
      id: goal.id,
      // Clamped at the target: the engine caps progress at 100% anyway, and a
      // stored figure above the target would read as a mistake on reload.
      draft: {
        ...draftOf(goal),
        current_amount: Math.min(goal.target_amount, goal.current_amount + amount),
      },
    });
  }

  function setArchived(goal: Goal, isActive: boolean) {
    setError(null);
    save.mutate({ id: goal.id, draft: { ...draftOf(goal), is_active: isActive } });
  }

  function confirmDelete(goal: Goal) {
    setError(null);
    // The one irreversible action on this page. Archiving is what a finished
    // goal wants and it needs no confirmation, because it can be undone.
    if (window.confirm(
      `Delete "${goal.name}"? This cannot be undone. To keep the record of a `
      + `goal you have finished, archive it instead.`
    )) {
      remove.mutate(goal.id);
    }
  }

  const busy = save.isPending || remove.isPending;

  return (
    <>
      <section>
        <h2>Your goals</h2>
        <p className="field">
          <label className="inline">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />{" "}
            Include archived goals
          </label>
        </p>
        <AsyncBoundary
          isLoading={goals.isLoading}
          error={goals.error}
          isEmpty={goals.data?.length === 0}
          emptyMessage={showArchived
            ? "Nothing here yet. Add a goal below and I will track the date you reach it."
            : "No active goals. Add one below, or tick the box to see archived ones."}
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
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {goals.data?.map((goal) => (
                  <tr key={goal.id} data-archived={!goal.is_active || undefined}>
                    <th scope="row">
                      {goal.name}
                      {/* A word, not only the dimmed row: colour and opacity
                          alone do not say "archived" to everybody. */}
                      {!goal.is_active && <span className="tag"> Archived</span>}
                    </th>
                    <td className="numeric">{goal.progress_pct.toFixed(1)}%</td>
                    <td className="numeric">
                      {compact(goal.current_amount)} / {compact(goal.target_amount)}
                    </td>
                    <td>{goal.estimated_completion ?? "no date yet"}</td>
                    <td className="numeric">
                      {PRIORITY_LABEL[goal.priority] ?? goal.priority}
                    </td>
                    <td>
                      <span className="row-actions">
                        {goal.is_active && (
                          <AddSaved goal={goal} onAdd={addSaved} disabled={busy} />
                        )}
                        <button type="button" disabled={busy}
                                onClick={() => setEditing(goal)}>
                          Edit
                        </button>
                        <button type="button" disabled={busy}
                                onClick={() => setArchived(goal, !goal.is_active)}>
                          {goal.is_active ? "Archive" : "Restore"}
                        </button>
                        <button type="button" disabled={busy}
                                onClick={() => confirmDelete(goal)}>
                          Delete
                        </button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncBoundary>
        <FormError message={error} />
      </section>

      {editing ? (
        <GoalForm
          key={editing.id}
          title={`Edit ${editing.name}`}
          initial={editing}
          submitLabel="Save changes"
          busy={save.isPending}
          onCancel={() => setEditing(null)}
          onSubmit={(draft) => save.mutate({ id: editing.id, draft })}
        />
      ) : (
        <AddGoal userId={user?.id} onSaved={refresh} />
      )}
    </>
  );
}

/** Record money put aside, without reopening the whole goal.
 *
 * The common action by a wide margin, and the one the page existed without.
 * It adds rather than replaces because that is how the question arrives: you
 * know what you just saved, not what the running total became. */
function AddSaved({ goal, onAdd, disabled }: {
  goal: Goal;
  onAdd: (goal: Goal, amount: number) => void;
  disabled: boolean;
}) {
  const [amount, setAmount] = useState("");
  const parsed = toNumber(amount);

  return (
    <span className="row-actions__add">
      <label className="visually-hidden" htmlFor={`add-${goal.id}`}>
        Amount to add to {goal.name}
      </label>
      <input
        id={`add-${goal.id}`}
        inputMode="numeric"
        placeholder="Add saved"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <button
        type="button"
        disabled={disabled || parsed <= 0}
        onClick={() => {
          onAdd(goal, parsed);
          setAmount("");
        }}
      >
        Add
      </button>
    </span>
  );
}

function AddGoal({ userId, onSaved }: { userId?: number; onSaved: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: (draft: ReturnType<typeof draftOf>) => createGoal(userId!, draft),
    onSuccess: onSaved,
    onError: (caught) => setError(messageFor(caught)),
  });

  return (
    <GoalForm
      title="Add a goal"
      submitLabel="Add goal"
      busy={add.isPending}
      error={error}
      resetOnSubmit
      onSubmit={(draft) => {
        setError(null);
        add.mutate(draft);
      }}
    />
  );
}

/** One form, used to add and to edit. Two copies of five fields is two places
 * for the validation to drift. */
function GoalForm({
  title, initial, submitLabel, busy, error, resetOnSubmit, onSubmit, onCancel,
}: {
  title: string;
  initial?: Goal;
  submitLabel: string;
  busy: boolean;
  error?: string | null;
  resetOnSubmit?: boolean;
  onSubmit: (draft: ReturnType<typeof draftOf>) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [target, setTarget] = useState(initial ? String(initial.target_amount) : "");
  const [current, setCurrent] = useState(initial ? String(initial.current_amount) : "");
  const [deadline, setDeadline] = useState(initial?.deadline ?? "");
  const [priority, setPriority] = useState(initial?.priority ?? 3);
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!name.trim() || toNumber(target) <= 0) {
      setLocalError("A goal needs a name and a target above zero.");
      return;
    }
    if (toNumber(current) < 0) {
      setLocalError("Saved so far cannot be negative.");
      return;
    }
    onSubmit({
      name: name.trim(),
      target_amount: toNumber(target),
      current_amount: toNumber(current),
      deadline: deadline || null,
      priority,
    });
    if (resetOnSubmit) {
      setName("");
      setTarget("");
      setCurrent("");
      setDeadline("");
    }
  }

  return (
    <section>
      <h2>{title}</h2>
      <form onSubmit={submit}>
        <Field label="Name" value={name} required
               onChange={(e) => setName(e.target.value)} />
        <Field label="Target amount" inputMode="numeric" value={target} required
               onChange={(e) => setTarget(e.target.value)} />
        <Field label="Saved so far" inputMode="numeric" value={current}
               onChange={(e) => setCurrent(e.target.value)} />
        <Field label="Want it by" type="date" value={deadline}
               onChange={(e) => setDeadline(e.target.value)} />
        <p className="field">
          <label htmlFor="goal-priority">Priority</label>
          <select id="goal-priority" value={priority}
                  onChange={(e) => setPriority(Number(e.target.value))}>
            {Object.entries(PRIORITY_LABEL).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </p>
        <FormError message={localError ?? error} />
        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : submitLabel}
          </button>
          {onCancel && (
            <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
          )}
        </div>
      </form>
    </section>
  );
}
