import { api } from "./client";
import type { ExpenseHistory } from "./types";

export const getExpenseHistory = (months: number) =>
  api.get<ExpenseHistory>(`/api/me/expenses/history?months=${months}`);
