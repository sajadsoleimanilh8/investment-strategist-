import { api } from "./client";
import type { FinancialProfileIn, FinancialTwin } from "./types";

export const getProfile = (userId: number) =>
  api.get<FinancialTwin>(`/api/financial-profile/${userId}`);

export const saveProfile = (userId: number, payload: FinancialProfileIn) =>
  api.put<FinancialTwin>(`/api/financial-profile/${userId}`, payload);
