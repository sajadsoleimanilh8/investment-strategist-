import { api } from "./client";
import type { AskResponse } from "./types";

export const ask = (userId: number, question: string) =>
  api.post<AskResponse>("/api/ai/ask", { user_id: userId, question });

export const transcript = (userId: number) =>
  api.get<{ question: string; answer: string; source: string }[]>(
    `/api/ai/transcript/${userId}`);
