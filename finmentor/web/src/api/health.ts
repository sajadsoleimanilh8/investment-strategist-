import { api } from "./client";
import type { FinancialDNA, HealthScore, Summary } from "./types";

export const getSummary = () => api.get<Summary>("/api/me/summary");
export const getHealth = (userId: number) => api.get<HealthScore>(`/api/health/${userId}`);
export const getDna = (userId: number) => api.get<FinancialDNA>(`/api/health/${userId}/dna`);
