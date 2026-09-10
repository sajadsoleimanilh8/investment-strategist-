import { api } from "./client";
import type { Goal } from "./types";

export interface GoalDraft {
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  priority: number;
}

export const listGoals = (userId: number) => api.get<Goal[]>(`/api/goals/${userId}`);

export const createGoal = (userId: number, draft: GoalDraft) =>
  api.post<Goal>("/api/goals", { user_id: userId, ...draft });

export const updateGoal = (goalId: number, draft: GoalDraft & { is_active?: boolean }) =>
  api.put<Goal>(`/api/goals/${goalId}`, draft);
