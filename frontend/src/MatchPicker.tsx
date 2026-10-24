import { useEffect, useState } from "react";
import { MATCH, openMatch, type MatchSummary } from "./match";

// Pick another synthetic match: the whole workspace (moments, fact checker, Ask, AI recap, graph,
// tactics) follows it. The list is computed by the server from each match's events.

const label = (m: MatchSummary) =>
  `${m.featured ? "Featured · " : ""}Calderbrook ${m.score.home}–${m.score.away} Merridge` +
  (m.tags.length ? ` · ${m.tags.join(", ")}` : "");

export function MatchPicker() {
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  useEffect(() => {
    fetch("/api/matches").then((r) => (r.ok ? r.json() : null)).then((d) => d && setMatches(d.matches)).catch(() => undefined);
  }, []);
  if (!matches.length) return null;
  const known = matches.some((m) => m.seed === MATCH);
  return (
    <label className="match-picker">
      <span>Match</span>
      <select aria-label="Synthetic match" value={MATCH} onChange={(e) => openMatch(Number(e.target.value))}>
        {matches.map((m) => <option key={m.seed} value={m.seed}>{label(m)}</option>)}
        {!known && <option value={MATCH}>Synthetic match · seed {MATCH}</option>}
      </select>
    </label>
  );
}
