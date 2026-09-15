/**
 * Number formatting for display.
 *
 * The API returns plain numbers and the currency symbol is a server-side
 * setting, so the client formats magnitude and grouping only. It deliberately
 * does not compute anything — a number shown here is a number the engine sent.
 */
export function money(value: number): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value);
}

/**
 * A market price. Two decimals, always, because a price is quoted that way
 * and a figure that shows "4K" for bitcoin is not a price, it is a rounding.
 * `compact` stays for magnitudes where the shape matters more than the digits
 * (a goal of 60M), which is not the same job.
 */
export function price(value: number): string {
  return new Intl.NumberFormat("en", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
}

export function compact(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 })
    .format(value);
}

export function percent(fraction: number, decimals = 1): string {
  return `${(fraction * 100).toFixed(decimals)}%`;
}

export function Money({ value }: { value: number }) {
  return <span className="money">{money(value)}</span>;
}
