import { api } from "./client";
import type { MarketAsset, TrendReport } from "./types";

interface AssetList { items: MarketAsset[]; disclaimer: string }
interface Watchlist { items: TrendReport[]; disclaimer: string }

export const listAssets = () => api.get<AssetList>("/api/market/assets");
export const getWatchlist = (userId: number) =>
  api.get<Watchlist>(`/api/market/watchlist/${userId}`);
export const addToWatchlist = (userId: number, symbol: string) =>
  api.post<Watchlist>(`/api/market/watchlist/${userId}`, { symbol });
export const removeFromWatchlist = (userId: number, symbol: string) =>
  api.del<void>(`/api/market/watchlist/${userId}/${symbol}`);
