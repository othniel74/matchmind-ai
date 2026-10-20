import { useEffect, useState } from "react";
import { Database, MessageCircleQuestion, Network } from "lucide-react";
import { directionOf } from "./languages";
import type { Profile } from "./Experience";
import "./graph-explorer.css";

// The match knowledge graph, made visible: who each team's play runs through, which players'
// possessions create chances, how goals were built, and answers to viewers' questions.

type RolePlayer = { player_id: string; name: string; involvement: number; pass_share: number; betweenness: number; pagerank: number };
type TeamRoles = {
  team_id: string; window: [number, number]; completed_passes: number; players: RolePlayer[];
  hub: string | null; connector: string | null; edges: { from: string; to: string; passes: number }[];
  positions: Record<string, { x: number; y: number; actions: number }>; database_agrees?: boolean;
};
type ChainRow = { player_id: string; name: string; xg_chain: number; xg_buildup: number };
type Buildup = { possession_id: string; ended_with: string; xg: number; end: number; passes: number;
                 steps: { event_id: string; name: string; event_type: string }[] };
type Knowledge = { networkx: { nodes: Record<string, number>; relationships: Record<string, number> };
                   database: { status: string; backend?: string; counts_match?: boolean; context?: { state_version: number } } };

export type WhyDetail = {
  moment_id: string; kind: string; evidence_event_ids: string[]; source: string;
  buildup: Buildup | null; previous_moment: { kind: string; clock: number } | null;
  players: Record<string, { name: string; pass_share?: number; betweenness?: number; is_hub: boolean; is_connector: boolean }>;
};

const pct = (v: number) => `${Math.round(v * 100)}%`;
const minuteOf = (clock: number) => `${Math.floor(clock / 60) + 1}′`;

function chainNames(b: Buildup) {
  const names: string[] = [];
  for (const s of b.steps) if (names[names.length - 1] !== s.name) names.push(s.name);
  return names.join(" → ");
}

function PassNetwork({ roles }: { roles: TeamRoles }) {
  const share = Object.fromEntries(roles.players.map((p) => [p.player_id, p.pass_share]));
  const names = Object.fromEntries(roles.players.map((p) => [p.player_id, p.name]));
  const max = Math.max(1, ...roles.edges.map((e) => e.passes));
  const pos = (id: string) => roles.positions[id] ?? { x: 50, y: 50 };
  const surname = (n: string) => n.split(" ").slice(-1)[0];
  // Label the six most involved players (and the hub and key link); the rest show on hover.
  const labelled = new Set([...roles.players].sort((x, y) => y.pass_share - x.pass_share).slice(0, 6)
    .map((p) => p.player_id).concat([roles.hub ?? "", roles.connector ?? ""]));
  return (
    <svg className="pass-network" viewBox="-4 -4 108 76" role="img"
         aria-label={`Pass network: hub ${names[roles.hub ?? ""] ?? "none"}, key connector ${names[roles.connector ?? ""] ?? "none"}`}>
      <rect x="0" y="0" width="100" height="68" className="pitch" />
      <line x1="50" y1="0" x2="50" y2="68" className="pitch-line" />
      <circle cx="50" cy="34" r="9" className="pitch-line" />
      {roles.edges.filter((e) => e.passes >= 2).map((e) => {
        const a = pos(e.from), b = pos(e.to);
        return <line key={`${e.from}-${e.to}`} x1={a.x} y1={a.y * 0.68} x2={b.x} y2={b.y * 0.68}
                     className="lane" strokeWidth={0.2 + 1.6 * (e.passes / max)} strokeOpacity={0.25 + 0.6 * (e.passes / max)} />;
      })}
      {Object.keys(roles.positions).filter((id) => share[id] !== undefined).map((id) => {
        const p = pos(id);
        const role = id === roles.connector ? "connector" : id === roles.hub ? "hub" : "";
        return (
          <g key={id} className={`node ${role}`}>
            <circle cx={p.x} cy={p.y * 0.68} r={1.4 + 9 * (share[id] ?? 0)}>
              <title>{`${names[id]}: ${pct(share[id] ?? 0)} of passes`}</title>
            </circle>
            {labelled.has(id) && <text x={p.x} y={p.y * 0.68 - 2.6 - 9 * (share[id] ?? 0)}>{surname(names[id])}</text>}
          </g>
        );
      })}
    </svg>
  );
}

export function GraphExplorer({ minute, stateVersion, clubs }: { minute: number; stateVersion?: number;
                                                                 clubs: Record<string, { short: string }> }) {
  const [team, setTeam] = useState<"home" | "away">("away");
  const [span, setSpan] = useState<"match" | "last15">("match");
  const [roles, setRoles] = useState<Record<string, TeamRoles> | null>(null);
  const [chain, setChain] = useState<ChainRow[]>([]);
  const [buildups, setBuildups] = useState<Buildup[]>([]);
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const at = Math.max(1, minute);
  useEffect(() => {
    let cancelled = false;
    const start = span === "last15" ? Math.max(0, at - 15) : 0;
    const get = (url: string) => fetch(url).then((r) => (r.ok ? r.json() : null));
    Promise.all([
      get(`/api/graph/roles?minute=${at}&start=${start}`),
      get(`/api/graph/xg-chain?minute=${at}&team=${team}`),
      get(`/api/graph/buildup?minute=${at}&team=${team}&limit=5`),
      get(`/api/graph/knowledge?minute=${at}`),
    ]).then(([r, c, b, k]) => {
      if (cancelled) return;
      setRoles(r?.teams ?? null);
      setChain(c?.teams?.[team] ?? []);
      setBuildups((b?.teams?.[team] ?? []).filter((x: Buildup) => x.ended_with === "goal"));
      setKnowledge(k);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [at, team, span, stateVersion]);
  const current = roles?.[team];
  const name = (id: string | null) => current?.players.find((p) => p.player_id === id)?.name ?? "—";
  const db = knowledge?.database;
  return (
    <section className="panel graph-panel" aria-label="Match graph">
      <div className="panel-title">
        <h2><Network size={17} />Match graph</h2>
        <span className="panel-kicker graph-source" data-testid="graph-source">
          <Database size={12} />
          {db?.status === "ok" ? `${db.backend?.toUpperCase()} · ${db.counts_match ? "IN SYNC" : "CHECKING"}` : "NETWORKX"}
          {knowledge && ` · ${Object.values(knowledge.networkx.nodes).reduce((a, b) => a + b, 0).toLocaleString()} NODES`}
        </span>
      </div>
      <div className="graph-controls">
        {(["home", "away"] as const).map((t) => (
          <button key={t} className={`player-chip ${team === t ? "on" : ""}`} onClick={() => setTeam(t)}>{clubs[t]?.short ?? t}</button>
        ))}
        <span className="graph-divider" />
        <button className={`player-chip ${span === "match" ? "on" : ""}`} onClick={() => setSpan("match")}>Match so far</button>
        <button className={`player-chip ${span === "last15" ? "on" : ""}`} onClick={() => setSpan("last15")}>Last 15 min</button>
      </div>
      {current && current.completed_passes > 0 ? (
        <div className="graph-body">
          <div>
            <PassNetwork roles={current} />
            <div className="graph-roles">
              <div><span>Hub</span><b>{name(current.hub)}</b></div>
              <div><span>Key link</span><b>{name(current.connector)}</b></div>
              <div><span>Passes</span><b>{current.completed_passes}</b></div>
            </div>
          </div>
          <div className="graph-tables">
            <table className="graph-table" aria-label="Network roles">
              <thead><tr><th>Player</th><th>Share</th><th>Between.</th><th>PageRank</th></tr></thead>
              <tbody>
                {current.players.slice(0, 6).map((p) => (
                  <tr key={p.player_id} className={p.player_id === current.connector ? "is-connector" : ""}>
                    <td>{p.name}</td><td>{pct(p.pass_share)}</td><td>{p.betweenness.toFixed(2)}</td><td>{p.pagerank.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="graph-table" aria-label="xG chain">
              <thead><tr><th>xG chain</th><th>Chain</th><th>Build-up</th></tr></thead>
              <tbody>
                {chain.slice(0, 5).map((r) => (
                  <tr key={r.player_id}><td>{r.name}</td><td>{r.xg_chain.toFixed(2)}</td><td>{r.xg_buildup.toFixed(2)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : <p className="subtle-note">The pass network appears once the team completes passes.</p>}
      {buildups.length > 0 && (
        <ol className="buildup-list" aria-label="Goal build-ups">
          {buildups.map((b) => (
            <li key={b.possession_id}><span className="moment-clock">{minuteOf(b.end)}</span>{chainNames(b)} <em>xG {b.xg.toFixed(2)}</em></li>
          ))}
        </ol>
      )}
      <p className="subtle-note">Share: part in completed passes. Betweenness: how many passing routes run through a player. xG chain: total xG of possessions a player took part in; build-up excludes the shot and final pass.</p>
    </section>
  );
}

export function WhyDetailView({ detail }: { detail: WhyDetail }) {
  const roles = Object.values(detail.players);
  return (
    <div className="why-detail" data-testid="why-detail">
      {detail.buildup && <p><b>Build-up:</b> {chainNames(detail.buildup)} ({detail.buildup.passes} passes, xG {detail.buildup.xg.toFixed(2)})</p>}
      {roles.map((r) => (
        <p key={r.name}><b>{r.name}:</b>{" "}
          {r.pass_share !== undefined ? `${pct(r.pass_share)} of passes in the 15 minutes before` : "not in the pass network then"}
          {r.is_connector ? " · key link" : r.is_hub ? " · hub" : ""}</p>
      ))}
      {detail.previous_moment && <p><b>Just before:</b> {detail.previous_moment.kind.replace("_", " ")} at {minuteOf(detail.previous_moment.clock)}</p>}
      <p className="subtle-note">{detail.evidence_event_ids.length} evidence event{detail.evidence_event_ids.length === 1 ? "" : "s"} · from {detail.source}</p>
    </div>
  );
}

type Answer = { answer: string; intent: string; supported: boolean; router: string; evidence_event_ids: string[] };

export function AskPanel({ minute, profile }: { minute: number; profile: Profile }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = (q: string) => {
    if (q.trim().length < 2) return;
    setBusy(true);
    fetch(`/api/ask?q=${encodeURIComponent(q.trim())}&minute=${minute}&language=${profile.language}`)
      .then((r) => (r.ok ? r.json() : null)).then(setAnswer).catch(() => setAnswer(null)).finally(() => setBusy(false));
  };
  const suggestions = ["Who scored?", "Who is the key player?", "Why did the last goal happen?", "Who has momentum?"];
  return (
    <section className="panel ask-panel" aria-label="Ask the match">
      <div className="panel-title">
        <h2><MessageCircleQuestion size={17} />Ask the match</h2>
        <span className="panel-kicker">ANSWERS FROM VERIFIED FACTS</span>
      </div>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); ask(question); }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300}
               placeholder="Ask about the score, a player, a goal…" aria-label="Your question" dir="auto" />
        <button className="button primary" disabled={busy}>{busy ? "…" : "Ask"}</button>
      </form>
      <div className="ask-suggestions">
        {suggestions.map((s) => <button key={s} className="player-chip" onClick={() => { setQuestion(s); ask(s); }}>{s}</button>)}
      </div>
      {answer && (
        <div className={`ask-answer ${answer.supported ? "" : "unsupported"}`} data-testid="ask-answer">
          <p dir={directionOf(profile.language)} lang={profile.language}>{answer.answer}</p>
          <span className="subtle-note">
            {answer.supported ? `${answer.evidence_event_ids.length} evidence event${answer.evidence_event_ids.length === 1 ? "" : "s"}` : "Outside what the match data can answer"}
            {` · routed by ${answer.router === "model" ? "the model" : "keywords"}`}
          </span>
        </div>
      )}
    </section>
  );
}
