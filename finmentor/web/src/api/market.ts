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

/** A short daily series for one of the live-ticker symbols. Public: no token,
 * cache-only on the server, and an empty `points` when the cache is cold. */
export interface PublicSeries {
  symbol: string;
  points: { date: string; close: number }[];
  disclaimer: string;
}

export const getPublicSeries = (symbol: string) =>
  api.get<PublicSeries>(`/api/market/public/${symbol}`);
