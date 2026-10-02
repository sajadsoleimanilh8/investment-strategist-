import { api } from "./client";
import type { LinkCode, TelegramStatus } from "./types";

export const getTelegramStatus = () => api.get<TelegramStatus>("/api/me/telegram");
export const createLinkCode = () => api.post<LinkCode>("/api/me/telegram/code");
export const unlinkTelegram = () => api.del<void>("/api/me/telegram");
