import { api } from "./client";
import type { IncomeHistory } from "./types";

export const getIncomeHistory = (months: number) =>
  api.get<IncomeHistory>(`/api/me/income/history?months=${months}`);
