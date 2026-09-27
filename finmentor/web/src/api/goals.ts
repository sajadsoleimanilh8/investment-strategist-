import { api } from "./client";
import type { Goal } from "./types";

export interface GoalDraft {
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  priority: number;
}

/** A user's goals. Active only by default, which is what the dashboard and
 * the health score both mean by "goals"; pass `activeOnly: false` to include
 * the archived ones. */
export const listGoals = (userId: number, options: { activeOnly?: boolean } = {}) =>
  api.get<Goal[]>(
    `/api/goals/${userId}?active_only=${options.activeOnly === false ? "false" : "true"}`,
  );

export const createGoal = (userId: number, draft: GoalDraft) =>
  api.post<Goal>("/api/goals", { user_id: userId, ...draft });

/** Replace a goal.
 *
 * `is_active` is optional and the server reads absence and `false`
 * differently: omitting it leaves the goal where it is, so an ordinary edit
 * cannot accidentally un-archive something. It was declared here long before
 * the API honoured it, which made this signature a promise nothing kept. */
export const updateGoal = (goalId: number, draft: GoalDraft & { is_active?: boolean }) =>
  api.put<Goal>(`/api/goals/${goalId}`, draft);

/** Remove a goal for good. Archiving (`is_active: false`) is the reversible
 * one; this is not, which is why the caller confirms first. */
export const deleteGoal = (goalId: number) =>
  api.del<void>(`/api/goals/${goalId}`);
