// The synthetic match the workspace shows: ?match=<seed> in the URL, the featured match otherwise.
// Picking another match reloads the page, so every panel starts fresh on the same match.

export const FEATURED_MATCH = 20261020;
const requested = Number(new URLSearchParams(location.search).get("match"));
export const MATCH = Number.isInteger(requested) && requested > 0 && requested <= 2147483647 ? requested : FEATURED_MATCH;
export const IS_FEATURED = MATCH === FEATURED_MATCH;

/** An API path for the current match. */
export function withMatch(path: string): string {
  return `${path}${path.includes("?") ? "&" : "?"}seed=${MATCH}`;
}

export type MatchSummary = { seed: number; featured: boolean; score: { home: number; away: number }; tags: string[] };

export function openMatch(seed: number) {
  const url = new URL(location.href);
  if (seed === FEATURED_MATCH) url.searchParams.delete("match"); else url.searchParams.set("match", String(seed));
  location.assign(url.toString());
}
