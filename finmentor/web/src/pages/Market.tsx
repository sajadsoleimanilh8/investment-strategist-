/**
 * The watchlist, and the assets that can join it.
 *
 * Every payload from the market API carries its own disclaimer and this page
 * renders it rather than restating it — if the wording changes server-side, it
 * changes here without an edit.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { addToWatchlist, getWatchlist, listAssets, removeFromWatchlist } from "../api/market";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { compact } from "../components/Money";
import { useAuth } from "../auth/AuthContext";

export function Market() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const watchlist = useQuery({
    queryKey: ["watchlist", user?.id],
    queryFn: () => getWatchlist(user!.id),
    enabled: Boolean(user),
  });

  const assets = useQuery({ queryKey: ["assets"], queryFn: listAssets });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    queryClient.invalidateQueries({ queryKey: ["summary"] });
  };

  const add = useMutation({
    mutationFn: (symbol: string) => addToWatchlist(user!.id, symbol),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (symbol: string) => removeFromWatchlist(user!.id, symbol),
    onSuccess: invalidate,
  });

  const watched = new Set(watchlist.data?.items.map((item) => item.symbol) ?? []);

  return (
    <>
      <section>
        <h2>Your watchlist</h2>
        <AsyncBoundary
          isLoading={watchlist.isLoading}
          error={watchlist.error}
          isEmpty={watchlist.data?.items.length === 0}
          emptyMessage="Nothing tracked yet. Add something from the list below."
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Symbol</th>
                  <th scope="col" className="numeric">Price</th>
                  <th scope="col" className="numeric">7 days</th>
                  <th scope="col" className="numeric">30 days</th>
                  <th scope="col">Trend</th>
                  <th scope="col">Volatility</th>
                  <th scope="col">&nbsp;</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.data?.items.map((item) => (
                  <tr key={item.symbol}>
                    <th scope="row">{item.symbol}</th>
                    <td className="numeric">{compact(item.latest_price)}</td>
                    <td
                      className={`numeric ${
                        item.change_7d_pct >= 0 ? "delta-positive" : "delta-negative"
                      }`}
                    >
                      {item.change_7d_pct.toFixed(2)}%
                    </td>
                    <td
                      className={`numeric ${
                        item.change_30d_pct >= 0 ? "delta-positive" : "delta-negative"
                      }`}
                    >
                      {item.change_30d_pct.toFixed(2)}%
                    </td>
                    <td>{item.trend}</td>
                    <td>{item.volatility_label}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => remove.mutate(item.symbol)}
                        disabled={remove.isPending}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="disclaimer">{watchlist.data?.disclaimer}</p>
        </AsyncBoundary>
      </section>

      <section>
        <h2>Everything I track</h2>
        <AsyncBoundary isLoading={assets.isLoading} error={assets.error}>
          <ul>
            {assets.data?.items.map((asset) => (
              <li key={asset.symbol}>
                <strong>{asset.symbol}</strong> — {asset.display_name} ({asset.asset_class})
                {!watched.has(asset.symbol) && (
                  <>
                    {" "}
                    <button
                      type="button"
                      onClick={() => add.mutate(asset.symbol)}
                      disabled={add.isPending}
                    >
                      Add
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="disclaimer">{assets.data?.disclaimer}</p>
        </AsyncBoundary>
      </section>
    </>
  );
}
