import { useEffect, useRef, useState } from "react";
import { BookOpen, Radio, Sparkles, Star, Target, UserRound } from "lucide-react";
import { LANGUAGES, directionOf, type LanguageCode } from "./languages";
import { WhyDetailView, type WhyDetail } from "./GraphExplorer";
import { AgentRunView, type AgentTraceView } from "./AgentRun";
import "./experience.css";

// Personalization for one viewer: the same verified intelligence, shaped by their choices.

export type Audience = "fan" | "analyst" | "broadcast";
export type Profile = {
  audience: Audience;
  language: LanguageCode;
  club: "" | "home" | "away";
  players: string[];
  focus: string;
  metric: string;
};
const DEFAULT_PROFILE: Profile = { audience: "fan", language: "en", club: "", players: [], focus: "", metric: "" };
const STORAGE_KEY = "matchmind.profile.v1";

export const METRIC_LABELS: Record<string, string> = {
  goals: "Goals", shots: "Shots", shots_on_target: "Shots on target", xg: "Expected goals (xG)",
  pass_completion: "Pass completion", possession: "Possession", corners: "Corners", fouls: "Fouls",
  yellow_cards: "Yellow cards", red_cards: "Red cards", substitutions: "Substitutions",
};

export function useProfile(): [Profile, (next: Profile) => void] {
  const [profile, setProfile] = useState<Profile>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      return saved ? { ...DEFAULT_PROFILE, ...saved } : DEFAULT_PROFILE;
    } catch {
      return DEFAULT_PROFILE;
    }
  });
  const update = (next: Profile) => {
    setProfile(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* Preferences still apply for this visit when storage is unavailable. */
    }
  };
  return [profile, update];
}

export function profileQuery(p: Profile, extra: Record<string, string | number> = {}) {
  const q = new URLSearchParams({ audience: p.audience, language: p.language });
  if (p.club) q.set("club", p.club);
  if (p.players.length) q.set("players", p.players.join(","));
  if (p.focus) q.set("focus_player", p.focus);
  if (p.metric) q.set("metric", p.metric);
  Object.entries(extra).forEach(([k, v]) => q.set(k, String(v)));
  return q.toString();
}

type Club = { team_id: string; name: string; short: string; code: string; primary: string };
type SquadPlayer = { player_id: string; team_id: string; name: string; shirt: number; position: string; role: string };
export type Squads = { clubs: Record<string, Club>; players: SquadPlayer[] };

export function useSquads() {
  const [squads, setSquads] = useState<Squads | null>(null);
  useEffect(() => {
    fetch("/api/squads").then((r) => (r.ok ? r.json() : null)).then(setSquads).catch(() => setSquads(null));
  }, []);
  return squads;
}

type Moment = {
  id: string; kind: string; minute: number; clock_seconds: number; team_id: string | null;
  headline: string; body: string; language: string; direction: "ltr" | "rtl";
  favourite_club: boolean; favourite_player: boolean; player_names: string[];
};
type PlayerStats = {
  player_id: string; team_id: string; name: string; shirt: number; position: string; minutes: number;
  touches: number; passes: number; completed_passes: number; pass_accuracy_pct: number;
  mean_pass_difficulty: number; key_passes: number; assists: number; shots: number; shots_on_target: number;
  goals: number; xg: number; tackles_won: number; recoveries: number; distance_km: number;
  top_speed_kmh: number; sprints: number; rating: number;
};
type Experience = {
  clubs: Record<string, Club & { favourite: boolean }>;
  moments: Moment[];
  dynamics: null | {
    control: { state: string; team_id: string | null };
    tempo: string;
    momentum: null | { team_id: string | null; share: number };
  };
  focus?: { player: PlayerStats; timeline: { clock_seconds: number; event_type: string; outcome: string; xg: number | null }[];
            physical: { minute: number; distance_km: number; top_speed_kmh: number }[];
            network_role?: Record<"match" | "last_15", { pass_share: number; is_hub: boolean; is_connector: boolean;
                                                       top_partners: { name: string; passes: number }[] }> };
  metric?: { metric: string; label: string; statement: string; series: { minute: number; home: number; away: number }[] };
};

// Moments whose graph explanation adds something beyond the headline.
const WHY_KINDS = new Set(["goal", "big_chance", "connector", "brace", "hat_trick"]);

const clock = (seconds: number) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

export function ProfilePanel({ profile, onChange, squads }: { profile: Profile; onChange: (p: Profile) => void; squads: Squads | null }) {
  const set = (patch: Partial<Profile>) => onChange({ ...profile, ...patch });
  const togglePlayer = (id: string) =>
    set({ players: profile.players.includes(id) ? profile.players.filter((p) => p !== id) : [...profile.players, id] });
  return (
    <section className="panel profile-panel" aria-label="Personalize your match">
      <div className="panel-title">
        <h2><UserRound size={17} />Your view</h2>
        <span className="panel-kicker quiet">Saved on this device</span>
      </div>
      <div className="profile-controls">
        <div className="profile-mode" role="group" aria-label="Viewing mode">
          <span>Viewing mode</span>
          <div className="segmented">
            {(["fan", "analyst", "broadcast"] as const).map((mode) => (
              <button key={mode} type="button" aria-pressed={profile.audience === mode}
                      className={profile.audience === mode ? "on" : ""} onClick={() => set({ audience: mode })}>
                {mode === "fan" ? "Fan" : mode === "analyst" ? "Analyst" : "Broadcast"}
              </button>
            ))}
          </div>
        </div>
        <label>Language
          <select aria-label="Experience language" value={profile.language} onChange={(e) => set({ language: e.target.value as LanguageCode })}>
            {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
          </select>
        </label>
        <label>Favourite club
          <select aria-label="Favourite club" value={profile.club} onChange={(e) => set({ club: e.target.value as Profile["club"] })}>
            <option value="">No favourite</option>
            {squads && Object.values(squads.clubs).map((c) => <option key={c.team_id} value={c.team_id}>{c.name}</option>)}
          </select>
        </label>
        <label>Follow one player
          <select aria-label="Follow one player" value={profile.focus} onChange={(e) => set({ focus: e.target.value })}>
            <option value="">Whole match</option>
            {squads?.players.map((p) => (
              <option key={p.player_id} value={p.player_id}>{p.name} · {squads.clubs[p.team_id].short} #{p.shirt}</option>
            ))}
          </select>
        </label>
        <label>Track one metric
          <select aria-label="Track one metric" value={profile.metric} onChange={(e) => set({ metric: e.target.value })}>
            <option value="">None</option>
            {Object.entries(METRIC_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      {squads && (
        <details className="favourite-details" open={profile.players.length > 0 || undefined}>
        <summary>Favourite players{profile.players.length ? ` · ${profile.players.length} selected` : ""}</summary>
        <div className="favourite-players" role="group" aria-label="Favourite players">
          {(["home", "away"] as const).map((team) => (
            <div key={team}>
              <span className="favourite-club-label">{squads.clubs[team].short}</span>
              {squads.players.filter((p) => p.team_id === team).map((p) => (
                <button key={p.player_id} type="button" className={`player-chip ${profile.players.includes(p.player_id) ? "on" : ""}`}
                  aria-pressed={profile.players.includes(p.player_id)} onClick={() => togglePlayer(p.player_id)}>
                  #{p.shirt} {p.name}
                </button>
              ))}
            </div>
          ))}
        </div>
        </details>
      )}
    </section>
  );
}

function Sparkline({ series, keys, max }: { series: Record<string, number>[]; keys: string[]; max?: number }) {
  if (series.length < 2) return <p className="subtle-note">The chart appears after five minutes of play.</p>;
  const top = max ?? Math.max(1, ...series.flatMap((s) => keys.map((k) => s[k])));
  const x = (i: number) => (i / (series.length - 1)) * 300;
  const y = (v: number) => 70 - (v / top) * 64;
  return (
    <svg className="sparkline" viewBox="0 0 300 74" preserveAspectRatio="none" role="img" aria-label="Trend over the match">
      {keys.map((k) => (
        <polyline key={k} className={`line-${k}`} fill="none" points={series.map((s, i) => `${x(i)},${y(s[k])}`).join(" ")} />
      ))}
    </svg>
  );
}

function dynamicsLabel(d: Experience["dynamics"], clubs: Experience["clubs"]) {
  if (!d) return [];
  const chips = [
    d.control.state === "control" ? `${clubs[d.control.team_id!].short} in control`
      : d.control.state === "chaos" ? "Open, scrappy spell" : "Balanced",
    `Tempo ${d.tempo}`,
  ];
  if (d.momentum?.team_id) chips.push(`Momentum: ${clubs[d.momentum.team_id].short} (${Math.round(d.momentum.share * 100)}%)`);
  return chips;
}

export function ExperiencePanels({ minute, stateVersion, profile, onMoments }: {
  minute: number; stateVersion?: number; profile: Profile; onMoments?: (count: number) => void;
}) {
  const [data, setData] = useState<Experience | null>(null);
  const [why, setWhy] = useState<{ id: string; detail: WhyDetail | null } | null>(null);
  const explain = (id: string) => {
    if (why?.id === id) { setWhy(null); return; }
    setWhy({ id, detail: null });
    fetch(`/api/graph/why?moment_id=${encodeURIComponent(id)}&minute=${Math.max(1, minute)}`)
      .then((r) => (r.ok ? r.json() : null)).then((d) => setWhy({ id, detail: d })).catch(() => setWhy(null));
  };
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/experience?${profileQuery(profile, { minute })}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => { if (!cancelled) { setData(v); onMoments?.(v?.moments?.length ?? 0); } })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [minute, stateVersion, profile]);
  if (!data) return null;
  const dir = directionOf(profile.language);
  const focus = data.focus;
  return (
    <>
      <section className="panel moments-panel" aria-label="Your moments">
        <div className="panel-title">
          <h2><Sparkles size={17} />Your moments</h2>
          <span className="panel-kicker">{profile.audience.toUpperCase()} · VERIFIED</span>
        </div>
        <div className="dynamics-chips">
          {dynamicsLabel(data.dynamics, data.clubs).map((c) => <span key={c}>{c}</span>)}
        </div>
        {data.moments.length ? (
          <ol className="moment-list">
            {data.moments.slice(0, 10).map((m) => (
              <li key={m.id} className={`moment kind-${m.kind} ${m.favourite_player || m.favourite_club ? "favourite" : ""}`}>
                <span className="moment-clock">{Math.floor(m.clock_seconds / 60) + 1}′</span>
                <div dir={dir} lang={m.language}>
                  <strong>{(m.favourite_player || m.favourite_club) && <Star size={12} aria-label="Your pick" />} {m.headline}</strong>
                  {m.body && <span>{m.body}</span>}
                  {WHY_KINDS.has(m.kind) && (
                    <button className="why-button" aria-expanded={why?.id === m.id} onClick={() => explain(m.id)}>Why?</button>
                  )}
                  {why?.id === m.id && why.detail && <WhyDetailView detail={why.detail} />}
                </div>
              </li>
            ))}
          </ol>
        ) : <p className="subtle-note">Moments for your profile appear here as the match unfolds.</p>}
      </section>
      {focus && (
        <section className="panel focus-panel" aria-label="Player focus">
          <div className="panel-title">
            <h2><Target size={17} />Following {focus.player.name}</h2>
            <span className="panel-kicker">{data.clubs[focus.player.team_id].short.toUpperCase()} · #{focus.player.shirt} · {focus.player.position}</span>
          </div>
          <div className="focus-stats">
            {[
              ["Rating", focus.player.rating.toFixed(1)], ["Minutes", focus.player.minutes],
              ["Goals", focus.player.goals], ["Assists", focus.player.assists],
              ["Shots", `${focus.player.shots} (${focus.player.shots_on_target} on target)`], ["xG", focus.player.xg.toFixed(2)],
              ["Passes", `${focus.player.completed_passes}/${focus.player.passes} · ${focus.player.pass_accuracy_pct}%`],
              ["Pass difficulty", `${focus.player.mean_pass_difficulty}/10`], ["Key passes", focus.player.key_passes],
              ["Tackles won", focus.player.tackles_won], ["Distance", `${focus.player.distance_km} km`],
              ["Top speed", `${focus.player.top_speed_kmh} km/h`],
            ].map(([k, v]) => <div key={k as string}><span>{k}</span><b>{v}</b></div>)}
          </div>
          {focus.network_role && (
            <p className="subtle-note focus-network" data-testid="focus-network">
              Pass network: {Math.round(focus.network_role.match.pass_share * 100)}% of team passes
              {focus.network_role.match.is_connector ? " · key link" : focus.network_role.match.is_hub ? " · hub" : ""}
              {" · last 15 min "}{Math.round(focus.network_role.last_15.pass_share * 100)}%
              {focus.network_role.match.top_partners.length > 0 &&
                ` · links most with ${focus.network_role.match.top_partners.map((p) => p.name).join(", ")}`}
            </p>
          )}
          <Sparkline series={focus.physical as unknown as Record<string, number>[]} keys={["distance_km"]} />
          <p className="subtle-note">Distance and speed are synthetic physical data; actions come from match events.</p>
          <ol className="focus-timeline">
            {focus.timeline.slice(-6).reverse().map((t) => (
              <li key={`${t.clock_seconds}-${t.event_type}`}>{clock(t.clock_seconds)} · {t.event_type}{t.outcome && t.outcome !== "success" ? ` · ${t.outcome}` : ""}{t.xg ? ` · xG ${t.xg.toFixed(2)}` : ""}</li>
            ))}
          </ol>
        </section>
      )}
      {data.metric && (
        <section className="panel metric-panel" aria-label="Tracked metric">
          <div className="panel-title">
            <h2><Target size={17} />{METRIC_LABELS[data.metric.metric]}</h2>
            <span className="panel-kicker">YOUR METRIC</span>
          </div>
          <p className="metric-statement" dir={dir} lang={profile.language}>{data.metric.statement}</p>
          <Sparkline series={data.metric.series} keys={["home", "away"]} />
          <div className="sparkline-legend"><span className="home">{data.clubs.home.short}</span><span className="away">{data.clubs.away.short}</span></div>
        </section>
      )}
    </>
  );
}

type Recap = {
  title: string; direction: "ltr" | "rtl"; language: string;
  sections: { score: string; scorers: { minute: number; headline: string }[]; statistics: string[];
              key_moments: { clock_seconds: number; headline: string; body: string }[]; flow: string;
              player_of_match: { text: string }; followed_players: string[] };
};

export function RecapPanel({ minute, profile }: { minute: number; profile: Profile }) {
  const [recap, setRecap] = useState<Recap | null>(null);
  const [aiText, setAiText] = useState<{ body: string; trace: AgentTraceView } | null>(null);
  const [busy, setBusy] = useState("");
  const load = (at: number) => {
    setBusy("recap");
    setAiText(null);
    fetch(`/api/recap?${profileQuery(profile, { minute: at })}`)
      .then((r) => (r.ok ? r.json() : null)).then(setRecap).catch(() => setRecap(null)).finally(() => setBusy(""));
  };
  const loadAi = (at: number) => {
    setBusy("ai");
    fetch(`/api/recap/agent?minute=${at}&language=${profile.language}&audience=${profile.audience}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => v && setAiText({ body: v.narratives[0].body, trace: v.trace }))
      .catch(() => setAiText(null)).finally(() => setBusy(""));
  };
  const at = minute >= 90 ? 90 : minute;
  return (
    <section className="panel recap-panel" aria-label="Match recap">
      <div className="panel-title">
        <h2><BookOpen size={17} />Match recap</h2>
        <span className="panel-kicker">EVERY NUMBER VERIFIED</span>
      </div>
      <div className="recap-actions">
        <button className="button secondary" disabled={minute < 45 || !!busy} onClick={() => load(45)}>Half-time</button>
        <button className="button secondary" disabled={minute < 90 || !!busy} onClick={() => load(90)}>Full-time</button>
        <button className="button secondary" disabled={minute < 1 || !!busy} onClick={() => load(at)}>So far</button>
        <button className="button primary" disabled={minute < 1 || !!busy} onClick={() => loadAi(at)}>
          {busy === "ai" ? "Writing…" : "AI recap"}
        </button>
      </div>
      {aiText && (
        <div className="ai-recap" dir={directionOf(profile.language)} lang={profile.language}>
          <p>{aiText.body.split("\n")[0]}</p>
          {aiText.trace.steps.length > 2 ? <AgentRunView trace={aiText.trace} /> : (
            <span className="subtle-note">The AI model is unavailable right now, so the verified recap is shown.</span>
          )}
        </div>
      )}
      {recap ? (
        <div className="recap" dir={recap.direction} lang={recap.language}>
          <h3>{recap.title}</h3>
          <p className="recap-score">{recap.sections.score}</p>
          <ul>{recap.sections.scorers.map((s) => <li key={`${s.minute}-${s.headline}`}>{s.minute}′ {s.headline}</li>)}</ul>
          <ul className="recap-stats">{recap.sections.statistics.map((s) => <li key={s}>{s}</li>)}</ul>
          <p>{recap.sections.flow}</p>
          <p>{recap.sections.player_of_match.text}</p>
          {recap.sections.followed_players.map((f) => <p key={f}>{f}</p>)}
        </div>
      ) : <p className="subtle-note">Recaps are built from validated claims, in your language.</p>}
    </section>
  );
}

type LiveEvent = { event_id: string; clock_seconds: number; event_type: string; outcome: string; team_id: string;
                   player_name: string; recipient_name: string | null; speed_kmh: number | null };

export function LiveStreamPanel({ profile }: { profile: Profile }) {
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [count, setCount] = useState(0);
  const socket = useRef<WebSocket | null>(null);
  useEffect(() => () => socket.current?.close(), []);
  const start = () => {
    socket.current?.close();
    setEvents([]); setMoments([]); setCount(0); setRunning(true);
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws/live?${profileQuery(profile, { speed: 60 })}`);
    socket.current = ws;
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "event") {
        setCount((c) => c + 1);
        setEvents((prev) => [m.event, ...prev].slice(0, 8));
      } else if (m.type === "moment") setMoments((prev) => [m.moment, ...prev].slice(0, 6));
      else if (m.type === "end") setRunning(false);
    };
    ws.onclose = () => setRunning(false);
  };
  const stop = () => { socket.current?.close(); setRunning(false); };
  const dir = directionOf(profile.language);
  return (
    <section className="panel live-panel" aria-label="Live event stream">
      <div className="panel-title">
        <h2><Radio size={17} />Event-by-event stream</h2>
        <span className="panel-kicker">{count} EVENTS INGESTED</span>
      </div>
      <p className="subtle-note">Each synthetic event is validated, interpreted and personalized as it arrives. Plays the full match in about 90 seconds.</p>
      <button className={`button ${running ? "secondary" : "primary"}`} onClick={running ? stop : start}>
        {running ? "Stop stream" : "Start live stream"}
      </button>
      <div className="live-columns">
        <ol className="live-events" aria-label="Latest events">
          {events.map((e) => (
            <li key={e.event_id} className={`team-${e.team_id}`}>
              <span>{clock(e.clock_seconds)}</span> {e.player_name} · {e.event_type}
              {e.event_type === "pass" && e.recipient_name ? ` → ${e.recipient_name}` : ""}
              {e.outcome === "goal" ? " · GOAL" : ""}{e.speed_kmh ? ` · ${e.speed_kmh} km/h` : ""}
            </li>
          ))}
        </ol>
        <ol className="live-moments" aria-label="Moments as they happen">
          {moments.map((m) => (
            <li key={m.id} dir={dir} lang={m.language} className={m.favourite_player || m.favourite_club ? "favourite" : ""}>
              <b>{Math.floor(m.clock_seconds / 60) + 1}′ {m.headline}</b>{m.body && <span>{m.body}</span>}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
