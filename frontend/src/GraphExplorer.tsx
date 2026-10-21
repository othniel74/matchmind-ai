import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { Database, MessageCircleQuestion, Network } from "lucide-react";
import { directionOf } from "./languages";
import type { Profile } from "./Experience";
import "./graph-explorer.css";

// The match knowledge graph, made visible: who each team's play runs through, which lanes move the
// ball forward, what changed against the previous spell, how goals were built, and viewers' questions.

type RolePlayer = { player_id: string; name: string; involvement: number; pass_share: number; betweenness: number; pagerank: number };
type Lane = { from: string; to: string; passes: number; progressive: number; gain_m: number; minutes: [number, number]; event_ids: string[] };
type PlayerStat = { shirt: number | null; made: number; received: number; progressive: number };
type Measures = { players: number; lanes: number; density: number; two_way: number; top_three_share: number; progressive_share: number };
type TeamRoles = {
  team_id: string; window: [number, number]; completed_passes: number; players: RolePlayer[];
  hub: string | null; connector: string | null; edges: Lane[]; player_stats: Record<string, PlayerStat>; network: Measures;
  positions: Record<string, { x: number; y: number; actions: number }>; database_agrees?: boolean;
  previous?: { window: [number, number]; network: Measures; edges: { from: string; to: string; passes: number }[] };
};
type ChainRow = { player_id: string; name: string; xg_chain: number; xg_buildup: number };
type Buildup = { possession_id: string; ended_with: string; xg: number; end: number; passes: number;
                 steps: { event_id: string; name: string; event_type: string }[] };
type Knowledge = { networkx: { nodes: Record<string, number>; relationships: Record<string, number> };
                   database: { status: string; backend?: string; counts_match?: boolean; context?: { state_version: number } } };
type Selection = { kind: "player"; id: string } | { kind: "lane"; from: string; to: string } | null;

export type WhyDetail = {
  moment_id: string; kind: string; evidence_event_ids: string[]; source: string;
  buildup: Buildup | null; previous_moment: { kind: string; clock: number } | null;
  players: Record<string, { name: string; pass_share?: number; betweenness?: number; is_hub: boolean; is_connector: boolean }>;
};

const pct = (v: number) => `${Math.round(v * 100)}%`;
const minuteOf = (clock: number) => `${Math.floor(clock / 60) + 1}′`;
const Y = 0.68; // pitch drawn 100 x 68
const FORWARD_M = 10;
const laneKey = (a: string, b: string) => `${a}>${b}`;
const surname = (n: string) => n.split(" ").slice(-1)[0];

function chainNames(b: Buildup) {
  const names: string[] = [];
  for (const s of b.steps) if (names[names.length - 1] !== s.name) names.push(s.name);
  return names.join(" → ");
}

function trim(p: { x: number; y: number }, cx: number, cy: number, r: number) {
  const dx = cx - p.x, dy = cy - p.y, d = Math.hypot(dx, dy) || 1;
  return { x: p.x + (dx / d) * r, y: p.y + (dy / d) * r };
}

// A curved lane: A→B and B→A bow to opposite sides, so both directions stay readable.
function lanePath(a: { x: number; y: number }, b: { x: number; y: number }, ra: number, rb: number) {
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
  if (len < ra + rb + 1) return null;
  const bend = Math.min(3.2, Math.max(1, len * 0.12));
  const mx = (a.x + b.x) / 2 - (dy / len) * bend, my = (a.y + b.y) / 2 + (dx / len) * bend;
  const s = trim(a, mx, my, ra + 0.3), e = trim(b, mx, my, rb + 0.8);
  return `M${s.x.toFixed(2)},${s.y.toFixed(2)} Q${mx.toFixed(2)},${my.toFixed(2)} ${e.x.toFixed(2)},${e.y.toFixed(2)}`;
}

type LaneView = { from: string; to: string; passes: number; tone: string; dashed?: boolean; lane?: Lane };

function PassNetwork({ roles, minPasses, showChange, selected, onSelect }: {
  roles: TeamRoles; minPasses: number; showChange: boolean; selected: Selection; onSelect: (s: Selection) => void;
}) {
  const share = Object.fromEntries(roles.players.map((p) => [p.player_id, p.pass_share]));
  const names = Object.fromEntries(roles.players.map((p) => [p.player_id, p.name]));
  const at = (id: string) => { const p = roles.positions[id] ?? { x: 50, y: 50 }; return { x: p.x, y: p.y * Y }; };
  const radius = (id: string) => 1.5 + 6.5 * Math.sqrt(share[id] ?? 0);
  const previous = new Map((roles.previous?.edges ?? []).map((e) => [laneKey(e.from, e.to), e.passes]));
  const change = showChange && !!roles.previous;
  const views: LaneView[] = roles.edges.filter((e) => e.passes >= minPasses).map((e) => {
    const delta = e.passes - (previous.get(laneKey(e.from, e.to)) ?? 0);
    const tone = change ? (delta >= 2 ? "grew" : delta <= -2 ? "faded" : "steady") : e.gain_m >= FORWARD_M ? "forward" : "lane";
    return { from: e.from, to: e.to, passes: e.passes, tone, lane: e };
  });
  if (change) {
    const now = new Set(roles.edges.map((e) => laneKey(e.from, e.to)));
    for (const e of roles.previous!.edges) {
      if (!now.has(laneKey(e.from, e.to)) && e.passes >= Math.max(2, minPasses) && share[e.from] !== undefined && share[e.to] !== undefined)
        views.push({ from: e.from, to: e.to, passes: e.passes, tone: "faded", dashed: true });
    }
  }
  const max = Math.max(1, ...views.map((v) => v.passes));
  const touches = (v: LaneView) => !selected ? true : selected.kind === "player"
    ? v.from === selected.id || v.to === selected.id : v.from === selected.from && v.to === selected.to;
  const isFocused = (id: string) => !selected || (selected.kind === "player" ? selected.id === id ||
    views.some((v) => touches(v) && (v.from === id || v.to === id)) : selected.from === id || selected.to === id);
  // Labels: the selection and its partners first, then hub, key link and the most involved. Each label
  // goes above its player, or below if that spot is taken, and never over another label or player.
  const labels: { id: string; x: number; y: number }[] = [];
  const boxes: [number, number, number, number][] = [];
  const shown = Object.keys(roles.positions).filter((id) => share[id] !== undefined);
  const hitsNode = (x0: number, y0: number, x1: number, y1: number, self: string) => shown.some((o) => {
    if (o === self) return false;
    const c = at(o), r = radius(o);
    return c.x + r > x0 && c.x - r < x1 && c.y + r > y0 && c.y - r < y1;
  });
  const focusIds = selected ? shown.filter((id) => isFocused(id)) : [];
  const priority = [...focusIds, roles.connector ?? "", roles.hub ?? "",
    ...[...roles.players].sort((x, y) => y.pass_share - x.pass_share).map((p) => p.player_id)];
  for (const id of priority) {
    if (!shown.includes(id) || labels.some((l) => l.id === id) || labels.length >= (selected ? 9 : 8)) continue;
    const p = at(id), r = radius(id), half = surname(names[id] ?? id).length * 0.62 + 0.4;
    for (const y of [p.y - r - 1.2, p.y + r + 3]) {
      const box: [number, number, number, number] = [p.x - half, y - 2.3, p.x + half, y + 0.5];
      const free = boxes.every(([a, b, c, d]) => box[2] < a || box[0] > c || box[3] < b || box[1] > d);
      if (free && !hitsNode(...box, id)) { labels.push({ id, x: p.x, y }); boxes.push(box); break; }
    }
  }
  const activate = (s: Selection) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s); }
  };
  return (
    <svg className="pass-network" viewBox="-3 -3 106 78" role="group" onClick={() => onSelect(null)}
         aria-label={`Pass network: hub ${names[roles.hub ?? ""] ?? "none"}, key link ${names[roles.connector ?? ""] ?? "none"}. Select a player or a lane for details.`}>
      <defs>
        {["lane", "forward", "grew", "faded", "steady"].map((t) => (
          <marker key={t} id={`arrow-${t}`} className={`arrow ${t}`} viewBox="0 0 6 6" refX="5" refY="3"
                  markerWidth="2.6" markerHeight="2.6" markerUnits="userSpaceOnUse" orient="auto">
            <path d="M0,0 L6,3 L0,6 z" />
          </marker>
        ))}
      </defs>
      <g className="pitch-markings">
        <rect x="0" y="0" width="100" height="68" className="pitch" />
        <line x1="50" y1="0" x2="50" y2="68" />
        <ellipse cx="50" cy="34" rx="8.7" ry="9.15" />
        <rect x="0" y="13.85" width="15.7" height="40.3" /><rect x="84.3" y="13.85" width="15.7" height="40.3" />
        <rect x="0" y="24.85" width="5.2" height="18.3" /><rect x="94.8" y="24.85" width="5.2" height="18.3" />
        <rect x="-1.6" y="30.35" width="1.6" height="7.3" /><rect x="100" y="30.35" width="1.6" height="7.3" />
      </g>
      <text x="50" y="73.5" className="attack-label">Attack →</text>
      {views.map((v) => {
        const path = lanePath(at(v.from), at(v.to), radius(v.from), radius(v.to));
        if (!path) return null;
        const focus = touches(v);
        const pick: Selection = { kind: "lane", from: v.from, to: v.to };
        return (
          <g key={`${laneKey(v.from, v.to)}${v.dashed ? "-gone" : ""}`} className={`lane-group ${v.tone}`} opacity={focus ? 1 : 0.12}>
            <path d={path} className={`lane ${v.tone} ${v.dashed ? "dashed" : ""}`} markerEnd={`url(#arrow-${v.tone})`}
                  strokeWidth={0.25 + 1.7 * (v.passes / max)} strokeOpacity={0.35 + 0.6 * (v.passes / max)} />
            {!v.dashed && (
              <path d={path} className="lane-hit" tabIndex={0} role="button"
                    aria-label={`${names[v.from]} to ${names[v.to]}: ${v.passes} passes`}
                    onClick={(e) => { e.stopPropagation(); onSelect(pick); }} onKeyDown={activate(pick)}>
                <title>{`${names[v.from]} → ${names[v.to]}: ${v.passes} passes`}</title>
              </path>
            )}
          </g>
        );
      })}
      {Object.keys(roles.positions).filter((id) => share[id] !== undefined).map((id) => {
        const p = at(id), r = radius(id);
        const role = id === roles.connector ? "connector" : id === roles.hub ? "hub" : "";
        const chosen = selected?.kind === "player" && selected.id === id;
        const pick: Selection = { kind: "player", id };
        const shirt = roles.player_stats[id]?.shirt;
        return (
          <g key={id} className={`node ${role} ${chosen ? "selected" : ""}`} opacity={isFocused(id) ? 1 : 0.3}
             tabIndex={0} role="button" aria-pressed={chosen}
             aria-label={`${names[id]}${shirt ? `, number ${shirt}` : ""}: ${pct(share[id] ?? 0)} of passes`}
             onClick={(e) => { e.stopPropagation(); onSelect(chosen ? null : pick); }} onKeyDown={activate(chosen ? null : pick)}>
            <circle cx={p.x} cy={p.y} r={r} />
            {(role || chosen) && <circle className="ring" cx={p.x} cy={p.y} r={r + 0.9} />}
            {shirt != null && r >= 2.2 && <text className="shirt" x={p.x} y={p.y + 0.95}>{shirt}</text>}
            <title>{`${names[id]}: ${pct(share[id] ?? 0)} of passes`}</title>
          </g>
        );
      })}
      {labels.map((l) => <text key={`label-${l.id}`} className="node-label" x={l.x} y={l.y}>{surname(names[l.id] ?? l.id)}</text>)}
    </svg>
  );
}

function SelectionCard({ roles, selected, onSelect, showChange }: {
  roles: TeamRoles; selected: Selection; onSelect: (s: Selection) => void; showChange: boolean;
}) {
  const names = Object.fromEntries(roles.players.map((p) => [p.player_id, p.name]));
  const prev = roles.previous;
  if (selected?.kind === "player") {
    const p = roles.players.find((x) => x.player_id === selected.id);
    const s = roles.player_stats[selected.id];
    if (!p || !s) return null;
    const out = roles.edges.filter((e) => e.from === p.player_id).sort((a, b) => b.passes - a.passes).slice(0, 3);
    const inn = roles.edges.filter((e) => e.to === p.player_id).sort((a, b) => b.passes - a.passes).slice(0, 3);
    const role = p.player_id === roles.hub ? "Hub" : p.player_id === roles.connector ? "Key link" : null;
    return (
      <div className="network-card" data-testid="network-card">
        <h3>{s.shirt != null && <span className="shirt-badge">{s.shirt}</span>}{p.name}{role && <em>{role}</em>}</h3>
        <dl className="card-stats">
          <div><dt>Share</dt><dd>{pct(p.pass_share)}</dd></div>
          <div><dt>Made</dt><dd>{s.made}</dd></div>
          <div><dt>Received</dt><dd>{s.received}</dd></div>
          <div><dt>Forward</dt><dd>{s.progressive}</dd></div>
          <div><dt>Between.</dt><dd>{p.betweenness.toFixed(2)}</dd></div>
          <div><dt>PageRank</dt><dd>{p.pagerank.toFixed(2)}</dd></div>
        </dl>
        <div className="partners">
          <div><span>Passes most to</span>{out.map((e) => (
            <button key={e.to} className="player-chip" onClick={() => onSelect({ kind: "lane", from: e.from, to: e.to })}>
              {surname(names[e.to] ?? e.to)} · {e.passes}</button>))}{!out.length && <i>—</i>}</div>
          <div><span>Receives most from</span>{inn.map((e) => (
            <button key={e.from} className="player-chip" onClick={() => onSelect({ kind: "lane", from: e.from, to: e.to })}>
              {surname(names[e.from] ?? e.from)} · {e.passes}</button>))}{!inn.length && <i>—</i>}</div>
        </div>
      </div>
    );
  }
  if (selected?.kind === "lane") {
    const lane = roles.edges.find((e) => e.from === selected.from && e.to === selected.to);
    if (!lane) return null;
    const back = roles.edges.find((e) => e.from === lane.to && e.to === lane.from)?.passes ?? 0;
    const before = prev?.edges.find((e) => e.from === lane.from && e.to === lane.to)?.passes ?? 0;
    return (
      <div className="network-card" data-testid="network-card">
        <h3>
          <button className="link" onClick={() => onSelect({ kind: "player", id: lane.from })}>{names[lane.from]}</button>
          <span className="lane-arrow">→</span>
          <button className="link" onClick={() => onSelect({ kind: "player", id: lane.to })}>{names[lane.to]}</button>
        </h3>
        <dl className="card-stats">
          <div><dt>Passes</dt><dd>{lane.passes}</dd></div>
          <div><dt>And back</dt><dd>{back}</dd></div>
          <div><dt>Forward</dt><dd>{lane.progressive}</dd></div>
          <div><dt>Avg gain</dt><dd>{lane.gain_m > 0 ? "+" : ""}{lane.gain_m.toFixed(1)} m</dd></div>
          <div><dt>Used</dt><dd>{lane.minutes[0] + 1}′–{lane.minutes[1] + 1}′</dd></div>
          {showChange && prev && <div><dt>Previous {prev.window[1] - prev.window[0]}′</dt><dd>{before}</dd></div>}
        </dl>
        <p className="subtle-note">{lane.event_ids.length} evidence event{lane.event_ids.length === 1 ? "" : "s"}. Forward: moved the ball at least {FORWARD_M} m towards goal.</p>
      </div>
    );
  }
  const n = roles.network;
  const was = showChange && prev ? prev.network : null;
  const diff = (now: number, then?: number, asPct = true) => was && then !== undefined
    ? <small className={now > then ? "up" : now < then ? "down" : ""}>{asPct ? `${now >= then ? "+" : ""}${Math.round((now - then) * 100)} pts` : `${now >= then ? "+" : ""}${now - then}`}</small> : null;
  return (
    <div className="network-card" data-testid="network-card">
      <h3>Network at a glance{was && <em>vs previous {prev!.window[1] - prev!.window[0]}′</em>}</h3>
      <dl className="card-stats">
        <div><dt>Lanes used</dt><dd>{n.lanes}{diff(n.lanes, was?.lanes, false)}</dd></div>
        <div><dt>Two-way lanes</dt><dd>{pct(n.two_way)}{diff(n.two_way, was?.two_way)}</dd></div>
        <div><dt>Top three share</dt><dd>{pct(n.top_three_share)}{diff(n.top_three_share, was?.top_three_share)}</dd></div>
        <div><dt>Forward passes</dt><dd>{pct(n.progressive_share)}{diff(n.progressive_share, was?.progressive_share)}</dd></div>
      </dl>
      <p className="subtle-note">Select a player or a lane on the pitch. Top three share: how much of the passing runs through three players.</p>
    </div>
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
  const [selected, setSelected] = useState<Selection>(null);
  const [minChoice, setMinChoice] = useState<number | null>(null);
  const [showChange, setShowChange] = useState(false);
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
  useEffect(() => setSelected(null), [team, span]);
  const current = roles?.[team];
  // Auto threshold: the fewest passes per lane that keeps the picture readable (about 30 lanes).
  const autoMin = useMemo(() => current
    ? [1, 2, 3, 4, 5].find((k) => current.edges.filter((e) => e.passes >= k).length <= 30) ?? 5 : 1, [current]);
  const minPasses = minChoice ?? autoMin;
  const canCompare = span === "last15" && !!current?.previous;
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
        {span === "last15" && (
          <button className={`player-chip ${showChange && canCompare ? "on" : ""}`} disabled={!canCompare}
                  aria-pressed={showChange && canCompare} onClick={() => setShowChange(!showChange)}
                  title={canCompare ? "Colour lanes by change against the previous 15 minutes" : "Needs 15 minutes of play before this window"}>
            Show change
          </button>
        )}
        <span className="graph-divider" />
        <span className="control-label" id="lane-filter">Lanes</span>
        <div className="lane-filter" role="group" aria-labelledby="lane-filter">
          {[null, 1, 2, 3, 5].map((k) => (
            <button key={String(k)} className={`player-chip ${minChoice === k ? "on" : ""}`} onClick={() => setMinChoice(k)}>
              {k === null ? `Auto (${autoMin}+)` : k === 1 ? "All" : `${k}+`}
            </button>
          ))}
        </div>
      </div>
      {current && current.completed_passes > 0 ? (
        <div className="graph-body">
          <div>
            <PassNetwork roles={current} minPasses={minPasses} showChange={showChange && canCompare}
                         selected={selected} onSelect={setSelected} />
            <ul className="network-legend" aria-label="Legend">
              <li><i className="key-node" />Size: share of passes</li>
              <li><i className="key-ring hub" />Hub</li>
              <li><i className="key-ring connector" />Key link</li>
              {showChange && canCompare ? (<>
                <li><i className="key-line grew" />More passes than before</li>
                <li><i className="key-line faded" />Fewer</li>
                <li><i className="key-line faded dashed" />No longer used</li>
              </>) : (<>
                <li><i className="key-line forward" />Moves the ball {FORWARD_M}+ m forward on average</li>
                <li><i className="key-line" />Other lanes; arrow shows direction</li>
              </>)}
            </ul>
            <div className="graph-roles">
              <div><span>Hub</span><b>{name(current.hub)}</b></div>
              <div><span>Key link</span><b>{name(current.connector)}</b></div>
              <div><span>Passes</span><b>{current.completed_passes}</b></div>
            </div>
          </div>
          <div className="graph-tables">
            <SelectionCard roles={current} selected={selected} onSelect={setSelected} showChange={showChange && canCompare} />
            <table className="graph-table" aria-label="Network roles">
              <thead><tr><th>Player</th><th>Share</th><th>Between.</th><th>PageRank</th></tr></thead>
              <tbody>
                {current.players.slice(0, 6).map((p) => {
                  const on = selected?.kind === "player" && selected.id === p.player_id;
                  return (
                    <tr key={p.player_id} className={`${p.player_id === current.connector ? "is-connector" : ""} ${on ? "is-selected" : ""}`}
                        onClick={() => setSelected(on ? null : { kind: "player", id: p.player_id })}>
                      <td><button className="link" aria-pressed={on}>{p.name}</button></td>
                      <td>{pct(p.pass_share)}</td><td>{p.betweenness.toFixed(2)}</td><td>{p.pagerank.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <table className="graph-table" aria-label="xG chain">
              <thead><tr><th>xG chain</th><th>Chain</th><th>Build-up</th></tr></thead>
              <tbody>
                {chain.slice(0, 5).map((r) => (
                  <tr key={r.player_id}><td>{r.name}</td><td>{r.xg_chain.toFixed(2)}</td><td>{r.xg_buildup.toFixed(2)}</td></tr>
                ))}
                {!chain.length && <tr><td colSpan={3} className="empty-row">No shots yet</td></tr>}
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
            {answer.router === "mcp_agent" ? " · Foundry agent via MCP" : " · keyword router"}
          </span>
        </div>
      )}
    </section>
  );
}
