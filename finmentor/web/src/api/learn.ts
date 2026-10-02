import { api } from "./client";
import type { QuizResult, Topic, TopicListOut } from "./types";

export const listTopics = () => api.get<TopicListOut>("/api/learn");
export const getTopic = (key: string) => api.get<Topic>(`/api/learn/${key}`);
export const submitQuiz = (key: string, answers: number[]) =>
  api.post<QuizResult>(`/api/learn/${key}/quiz`, { answers });
