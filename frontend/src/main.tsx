import StudioEvidence, {type ReviewContext} from "./StudioEvidence";
import {signOut} from "./localAccess";
import EvidenceLab from "./EvidenceLab";
import HumanPlayers from "./HumanPlayers";
import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  CircleDot,
  GitBranch,
  LayoutDashboard,
  LogOut,
  MonitorPlay,
  Maximize2,
  GripVertical,
  Eye,
  EyeOff,
  Minimize2,
  ExternalLink,
  X,
  Radio,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";
import "./style.css";
import Landing from "./Landing";
import { LANGUAGES, directionOf, type LanguageCode } from "./languages";
import { ExperiencePanels, LiveStreamPanel, ProfilePanel, RecapPanel, useProfile, useSquads } from "./Experience";
import { AskPanel, GraphExplorer } from "./GraphExplorer";

// Real-data research views are local-only; the product itself uses synthetic data, and the
// research components load only when enabled.
const RESEARCH = import.meta.env.VITE_ENABLE_RESEARCH === "true";
const LazyStatsBomb = lazy(() => import("./StatsBombResearch"));
const LazyTracking = lazy(() => import("./TrackingReplay.tsx"));
const StatsBombResearch = (props: { standalone?: boolean }) =>
  RESEARCH ? <Suspense fallback={null}><LazyStatsBomb {...props} /></Suspense> : null;
const TrackingReplay = (props: { standalone?: boolean; source?: "skillcorner" | "metrica" }) =>
  RESEARCH ? <Suspense fallback={null}><LazyTracking {...props} /></Suspense> : null;

type Stats = {
  goals: number;
  events: number;
  passes: number;
  completed_passes: number;
  pass_completion_pct: number;
  shots: number;
  shots_on_target: number;
  xg: number;
  possession_pct: number;
  corners: number;
  fouls: number;
  yellow_cards: number;
  red_cards: number;
  recoveries: number;
  final_third_entries: number;
  advanced_events: number;
};
type Insight = {
  id: string;
  minute: number;
  team_id: string;
  headline: string;
  explanation: string;
  previous_count: number;
  current_count: number;
  evidence_event_ids: string[];
  validated: boolean;
  interpretation?: {
    label: string;
    z_score: number;
    z_threshold: number;
    meets_calibrated_threshold: boolean;
    status: string;
  };
};
type MatchEvent = {
  event_id: string;
  minute: number;
  second: number;
  team_id: string;
  event_type: string;
  player_id: string;
  x: number;
  outcome?: string;
  set_piece?: string | null;
  replacement_player_id?: string | null;
  player_name?: string;
  replacement_name?: string | null;
};
const shirt = (id: string | null | undefined) => `#${id?.split("-")[1] ?? "?"}`;
function eventLabel(e: MatchEvent) {
  if (e.event_type === "card") return `${(e.outcome ?? "").replace("_", " ")} card`;
  if (e.event_type === "substitution") return `substitution · ${e.replacement_name ?? shirt(e.replacement_player_id)} on`;
  if (e.event_type === "shot" && e.outcome === "goal") return "goal";
  return e.set_piece ? `${e.event_type} · ${e.set_piece.replace("_", " ")}` : e.event_type;
}
type Overlay = {
  overlay_id: string;
  insight_id: string;
  match_clock_seconds: number;
  duration_ms: number;
  headline: string;
  body: string;
  metric_label: string;
  previous_value: number | null;
  current_value: number | null;
  overlay_type?: string;
  favourite_club?: boolean;
  favourite_player?: boolean;
  evidence_event_ids: string[];
  validation_status: string;
  language: string;
  audience_mode: string;
};
type PitchPlayer = {
  player_id: string;
  team_id: string;
  number: number;
  x: number;
  y: number;
  active: boolean;
  occupant_id?: string | null;
  on_pitch?: boolean;
  position_source: string;
  source_event_id: string | null;
};
type PitchState = {
  players: PitchPlayer[];
  ball: { x: number; y: number; source_event_id: string | null };
  action: {
    event_id: string;
    team_id: string;
    player_id: string;
    type: string;
    outcome: string;
    from_x: number;
    from_y: number;
    to_x: number;
    to_y: number;
  } | null;
  mode: string;
};
const initialFormation = [
  [8, 50],
  [25, 14],
  [23, 38],
  [23, 62],
  [25, 86],
  [44, 25],
  [42, 50],
  [44, 75],
  [65, 16],
  [68, 50],
  [65, 84],
];
const initialPitch: PitchState = {
  players: ["home", "away"].flatMap((team) =>
    initialFormation.map(([x, y], i) => ({
      player_id: `${team}-${String(i + 1).padStart(2, "0")}`,
      team_id: team,
      number: i + 1,
      x: team === "home" ? x : 100 - x,
      y,
      active: false,
      position_source: "illustrative_formation",
      source_event_id: null,
    })),
  ),
  ball: { x: 50, y: 50, source_event_id: null },
  action: null,
  mode: "illustrative_event_simulation",
};
type Frame = {
  context?: {match_id:string;state_version:number;seed?:number};
  pitch?: PitchState;
  minute: number;
  statistics: { home: Stats; away: Stats };
  events: MatchEvent[];
  insights: Insight[];
};
type Edge = {
  source: string;
  target: string;
  weight: number;
  event_ids: string[];
};
type Network = {
  nodes: string[];
  edges: Edge[];
  metrics: { edges: number; passes: number; density: number };
};
type Graph = { previous: Network; current: Network };
type Sample = { minute: number; home: number; away: number };
const empty: Stats = {
  goals: 0,
  events: 0,
  passes: 0,
  completed_passes: 0,
  pass_completion_pct: 0,
  shots: 0,
  shots_on_target: 0,
  xg: 0,
  possession_pct: 0,
  corners: 0,
  fouls: 0,
  yellow_cards: 0,
  red_cards: 0,
  recoveries: 0,
  final_third_entries: 0,
  advanced_events: 0,
};
const initial: Frame = {
  minute: 0,
  statistics: { home: empty, away: empty },
  events: [],
  insights: [],
};

function Crest({
  away = false,
  small = false,
}: {
  away?: boolean;
  small?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={`crest ${away ? "away" : ""} ${small ? "small" : ""}`}
    >
      <ShieldCheck size={small ? 17 : 29} strokeWidth={1.6} />
      <span>{away ? "MER" : "CAL"}</span>
    </div>
  );
}
function PanelTitle({
  icon,
  title,
  kicker,
}: {
  icon: React.ReactNode;
  title: string;
  kicker?: string;
}) {
  return (
    <div className="panel-title">
      <h2>
        {icon}
        {title}
      </h2>
      {kicker && <span className="panel-kicker">{kicker}</span>}
    </div>
  );
}
function Comparison({
  label,
  home,
  away,
  suffix = "",
}: {
  label: string;
  home: number;
  away: number;
  suffix?: string;
}) {
  const total = home + away;
  return (
    <div className="comparison-row">
      <div>
        <strong>
          {home}
          {suffix}
        </strong>
        <span>{label}</span>
        <strong>
          {away}
          {suffix}
        </strong>
      </div>
      <div className="comparison-track">
        <i style={{ flex: total ? home : 1 }} />
        <i style={{ flex: total ? away : 1 }} />
      </div>
    </div>
  );
}
function PassingNetwork({ network }: { network: Network }) {
  const points = new Map(
    network.nodes.map((id, i) => [
      id,
      {
        x:
          150 +
          104 *
            Math.cos((i * 2 * Math.PI) / network.nodes.length - Math.PI / 2),
        y:
          112 +
          78 * Math.sin((i * 2 * Math.PI) / network.nodes.length - Math.PI / 2),
      },
    ]),
  );
  return (
    <svg
      className="network"
      viewBox="0 0 300 224"
      role="img"
      aria-label={`Synthetic passing network with ${network.nodes.length} players and ${network.metrics.edges} connections`}
    >
      <rect
        x="16"
        y="12"
        width="268"
        height="200"
        rx="4"
        className="field-line"
      />
      <path
        d="M150 12V212M16 72H49V152H16M284 72H251V152H284"
        className="field-line"
      />
      <circle cx="150" cy="112" r="32" className="field-line" />
      {network.edges.map((edge) => {
        const a = points.get(edge.source),
          b = points.get(edge.target);
        return a && b ? (
          <line
            key={`${edge.source}-${edge.target}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            className="network-edge"
            strokeWidth={Math.min(1 + edge.weight * 0.6, 4)}
          >
            <title>
              {edge.source} to {edge.target}: {edge.weight} completed passes
            </title>
          </line>
        ) : null;
      })}
      {network.nodes.map((id) => {
        const p = points.get(id)!;
        return (
          <g key={id}>
            <circle cx={p.x} cy={p.y} r="11" className="network-node" />
            <text x={p.x} y={p.y + 3.5}>
              {id.split("-")[1]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
function PitchPlayers({
  pitch,
  moving,
}: {
  pitch: PitchState;
  moving: boolean;
}) {
  const action = pitch.action;
  const [humanReady, setHumanReady] = useState(false);
  const [playStatus, setPlayStatus] = useState("");
  return (
    <>
      <div
        className={`simulation-layer ${humanReady ? "human-ready" : ""} ${moving ? "players-moving" : "players-still"}`}
        role="group"
        aria-label="22 synthetic football players in an illustrative 4-3-3 formation. Not real tracking."
      >
        <HumanPlayers
          pitch={pitch}
          moving={moving}
          onReady={setHumanReady}
          onPlayStatus={setPlayStatus}
        />
        {action && action.type === "pass" && (
          <svg
            className="pitch-action"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <line
              x1={action.from_x}
              y1={action.from_y}
              x2={action.to_x}
              y2={action.to_y}
            />
            <circle cx={action.to_x} cy={action.to_y} r=".5" />
          </svg>
        )}
        {pitch.players.filter((player) => player.on_pitch !== false).map((player) => (
          <div
            key={player.player_id}
            className={`pitch-player team-${player.team_id} ${player.number === 1 ? "keeper" : ""} ${player.active ? "active" : ""}`}
            style={{ left: `${player.x}%`, top: `${player.y}%` }}
            title={`${player.team_id === "home" ? "Calderbrook" : "Merridge"} #${player.number} · ${player.position_source === "illustrative_formation" ? "Illustrative position" : "Synthetic event position"}`}
          >
            <svg
              viewBox="0 0 40 64"
              aria-hidden="true"
              style={
                {
                  "--skin": ["#bd8967", "#704833", "#d5a480", "#956348"][
                    player.number % 4
                  ],
                  "--stride": `${(player.number % 4) * -0.17}s`,
                } as React.CSSProperties
              }
            >
              <defs>
                <linearGradient
                  id={`kit-${player.player_id}`}
                  x1="0"
                  y1="0"
                  x2="1"
                  y2=".3"
                >
                  <stop offset="0" stopColor="var(--kit-shadow)" />
                  <stop offset=".36" stopColor="var(--kit)" />
                  <stop offset=".65" stopColor="var(--kit-light)" />
                  <stop offset="1" stopColor="var(--kit-shadow)" />
                </linearGradient>
                <radialGradient
                  id={`skin-${player.player_id}`}
                  cx="35%"
                  cy="25%"
                  r="80%"
                >
                  <stop offset="0" stopColor="var(--skin)" />
                  <stop offset="1" stopColor="var(--skin)" stopOpacity=".64" />
                </radialGradient>
              </defs>
              <ellipse
                className="player-shadow"
                cx="23"
                cy="60"
                rx="11"
                ry="2.4"
              />
              <g className="athlete-body">
                <g className="athlete-leg leg-left">
                  <path
                    d="M16 37L14.5 46L15.5 54"
                    fill="none"
                    stroke="var(--skin)"
                    strokeWidth="4.4"
                    strokeLinecap="round"
                  />
                  <path className="athlete-sock" d="M14.7 49L15.5 56" />
                  <path
                    className="athlete-boot"
                    d="M13.5 55.5Q17 54 18 58L12.5 59Q11 57 13.5 55.5"
                  />
                </g>
                <g className="athlete-leg leg-right">
                  <path
                    d="M24 37L25.5 46L24.5 54"
                    fill="none"
                    stroke="var(--skin)"
                    strokeWidth="4.4"
                    strokeLinecap="round"
                  />
                  <path className="athlete-sock" d="M25.3 49L24.5 56" />
                  <path
                    className="athlete-boot"
                    d="M22.5 55.5Q26 54 27 58L21.5 59Q20 57 22.5 55.5"
                  />
                </g>
                <g className="athlete-arm arm-left">
                  <path
                    d="M13 19L9 27L7 32"
                    fill="none"
                    stroke="var(--skin)"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                  <ellipse
                    cx="6.7"
                    cy="33"
                    rx="1.6"
                    ry="2.2"
                    fill="var(--skin)"
                  />
                </g>
                <g className="athlete-arm arm-right">
                  <path
                    d="M27 19L31 27L33 32"
                    fill="none"
                    stroke="var(--skin)"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                  />
                  <ellipse
                    cx="33.3"
                    cy="33"
                    rx="1.6"
                    ry="2.2"
                    fill="var(--skin)"
                  />
                </g>
                <path
                  className="player-shorts"
                  d="M13 32Q20 34 27 32L28 40L21.5 41L20 36L18.5 41L12 40Z"
                />
                <path d="M17 11H23L24 16L20 19L16 16Z" fill="var(--skin)" />
                <path
                  className="athlete-kit"
                  fill={`url(#kit-${player.player_id})`}
                  d="M16 15L12 16L8 22L12 25L14 22L13.5 33Q20 35 26.5 33L26 22L28 25L32 22L28 16L24 15Q20 18 16 15Z"
                />
                <path
                  className="kit-seam"
                  d="M14 22L15 31M26 22L25 31M16 16Q20 20 24 16M9 22L12 24M28 24L31 22"
                />
                <path
                  d="M17 28L19 29M23 30L25 29"
                  stroke="#000"
                  strokeOpacity=".14"
                  strokeWidth=".6"
                />
                <text x="20" y="28">
                  {player.number}
                </text>
                <ellipse
                  cx="20"
                  cy="8.5"
                  rx="4.1"
                  ry="5.1"
                  fill={`url(#skin-${player.player_id})`}
                />
                <path
                  d={
                    player.number % 3 === 0
                      ? "M16 8Q15 2 20 2Q25 2 24 8L22.5 5L18 5Z"
                      : "M16 8Q14.5 2.5 20 2Q25 2 24 8L23 6Q20 4 17 6Z"
                  }
                  fill={player.number % 5 === 0 ? "#57402a" : "#211e1a"}
                />
                <path
                  d="M17.5 11.5Q20 13 22.5 11.5"
                  fill="none"
                  stroke="#4b3023"
                  strokeOpacity=".35"
                  strokeWidth=".6"
                />
              </g>
            </svg>
          </div>
        ))}
        <div
          className="pitch-ball"
          style={{ left: `${pitch.ball.x}%`, top: `${pitch.ball.y}%` }}
          title={
            pitch.ball.source_event_id
              ? `Ball cue from ${pitch.ball.source_event_id}`
              : "Ball at centre"
          }
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <circle
              cx="10"
              cy="10"
              r="9"
              fill="#fafbf1"
              stroke="#263329"
              strokeWidth="1"
            />
            <path
              d="M10 5L14 8L12.5 13H7.5L6 8ZM2 8L6 8M14 8L18 8M7.5 13L5 17M12.5 13L15 17M10 5V1"
              fill="#263329"
              stroke="#263329"
              strokeWidth="1"
            />
          </svg>
        </div>
      </div>
      <div className="pitch-legend">
        <span>
          <i className="legend-home" />
          Calderbrook
        </span>
        <span>
          <i className="legend-away" />
          Merridge
        </span>
        <small>
          {humanReady && playStatus
            ? playStatus
            : action
              ? `${action.team_id === "home" ? "CAL" : "MER"} #${action.player_id.split("-")[1]} · ${action.type}${action.outcome === "goal" ? " · GOAL" : ""}`
              : "Formation preview"}
        </small>
      </div>
    </>
  );
}
type PreviewPayload = { frame: Frame; overlay?: Overlay };
function BroadcastCanvas({ frame, overlay }: PreviewPayload) {
  const { home, away } = frame.statistics;
  const canvasRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 1 });
  const [size, setSize] = useState({ x: 0, y: 0, padding: 12 });
  const [background, setBackground] = useState(35);
  const [visible, setVisible] = useState(true);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{
    id: number;
    x: number;
    y: number;
    startX: number;
    startY: number;
    rangeX: number;
    rangeY: number;
  } | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current,
      card = overlayRef.current;
    if (!canvas || !card || !visible) return;
    const measure = () => {
      const padding = Math.min(24, canvas.clientWidth * 0.03);
      setSize({
        x: Math.max(0, canvas.clientWidth - card.offsetWidth - padding * 2),
        y: Math.max(0, canvas.clientHeight - card.offsetHeight - padding * 2),
        padding,
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    observer.observe(card);
    measure();
    return () => observer.disconnect();
  }, [visible]);
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const startDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startX: position.x,
      startY: position.y,
      rangeX: size.x,
      rangeY: size.y,
    };
    setDragging(true);
  };
  const moveDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start || start.id !== event.pointerId) return;
    setPosition({
      x: clamp(
        start.startX + (event.clientX - start.x) / Math.max(1, start.rangeX),
      ),
      y: clamp(
        start.startY + (event.clientY - start.y) / Math.max(1, start.rangeY),
      ),
    });
  };
  const endDrag = () => {
    drag.current = null;
    setDragging(false);
  };
  const moveWithKeys = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (
      !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home"].includes(
        event.key,
      )
    )
      return;
    event.preventDefault();
    if (event.key === "Home") {
      setPosition({ x: 0, y: 1 });
      return;
    }
    setPosition((p) => ({
      x: clamp(
        p.x +
          (event.key === "ArrowLeft"
            ? -0.03
            : event.key === "ArrowRight"
              ? 0.03
              : 0),
      ),
      y: clamp(
        p.y +
          (event.key === "ArrowUp"
            ? -0.03
            : event.key === "ArrowDown"
              ? 0.03
              : 0),
      ),
    }));
  };
  const onAir =
    overlay &&
    frame.minute * 60 >= overlay.match_clock_seconds &&
    frame.minute * 60 <
      overlay.match_clock_seconds + overlay.duration_ms / 1000;
  return (
    <div ref={canvasRef} className="broadcast-screen">
      <details className="overlay-settings">
        <summary>Overlay controls</summary>
        <div className="overlay-settings-panel">
          <label>
            Background opacity <span>{background}%</span>
            <input
              aria-label="Overlay background opacity"
              type="range"
              min="15"
              max="80"
              value={background}
              onChange={(e) => setBackground(Number(e.target.value))}
            />
          </label>
          <div>
            <button onClick={() => setVisible((v) => !v)}>
              {visible ? <EyeOff size={13} /> : <Eye size={13} />}{" "}
              {visible ? "Hide overlay" : "Show overlay"}
            </button>
            <button onClick={() => setPosition({ x: 0, y: 1 })}>
              <RotateCcw size={13} />
              Reset position
            </button>
          </div>
          <p>
            Drag the overlay to move it. Use arrow keys when focused; Home
            resets its position.
          </p>
        </div>
      </details>
      <div className="broadcast-bug">
        <AudioLines size={17} /> MATCHMIND <span>DEMO</span>
      </div>
      <div className="broadcast-score">
        NL{" "}
        <b>
          {home.goals} : {away.goals}
        </b>{" "}
        MB <span>{frame.minute}′</span>
      </div>
      <div className="broadcast-pitch">
        <div />
        <i />
        <span className="penalty left" />
        <span className="penalty right" />
      </div>
      <PitchPlayers
        moving={frame.minute > 0 && frame.minute < 90}
        pitch={frame.pitch ?? initialPitch}
      />
      {visible && (
        <div
          ref={overlayRef}
          role="group"
          tabIndex={0}
          aria-label="Movable insight overlay. Drag or use arrow keys to move; Home resets position."
          className={`broadcast-lower movable-overlay ${dragging ? "dragging" : ""} ${onAir ? "on-air" : ""}`}
          style={{
            left: size.padding + position.x * size.x,
            top: size.padding + position.y * size.y,
            backgroundColor: `rgba(8,17,24,${background / 100})`,
          }}
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onLostPointerCapture={endDrag}
          onKeyDown={moveWithKeys}
        >
          <GripVertical className="overlay-grip" size={16} aria-hidden="true" />
          <span className="lower-icon">
            <Sparkles size={22} />
          </span>
          <div>
            <small>
              {onAir
                ? "ON AIR · VERIFIED INSIGHT"
                : "HISTORICAL OVERLAY PREVIEW"}
            </small>
            <div
              dir={overlay ? directionOf(overlay.language) : "ltr"}
              lang={overlay?.language}
            >
              <h3>{overlay?.headline || "The next moment is taking shape."}</h3>
              <p>
                {overlay
                  ? overlay.previous_value != null && overlay.current_value != null
                    ? `${overlay.metric_label}: ${overlay.previous_value} ${directionOf(overlay.language) === "rtl" ? "←" : "→"} ${overlay.current_value}`
                    : overlay.body
                  : "Validated match observations will appear here."}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
function PreviewWindow() {
  const [payload, setPayload] = useState<PreviewPayload>({ frame: initial });
  const [full, setFull] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("channel");
    if (!id) {
      setNotice("Open this preview from Broadcast Studio.");
      return;
    }
    const channel = new BroadcastChannel(id);
    channel.onmessage = (event) => {
      if (event.data?.type === "studio_closed") {
        setPayload({ frame: initial });
        setNotice("The studio session has ended. You can close this preview.");
        return;
      }
      if (event.data?.type === "preview" && event.data.payload?.frame)
        setPayload(event.data.payload);
    };
    channel.postMessage({ type: "ready" });
    const changed = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", changed);
    return () => {
      channel.close();
      document.removeEventListener("fullscreenchange", changed);
    };
  }, []);
  const toggleFull = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      setNotice(
        "Full screen is unavailable in this browser. You can maximise this window.",
      );
    }
  };
  return (
    <div className="preview-window">
      <div className="preview-window-toolbar">
        <span>
          <MonitorPlay size={17} /> Broadcast preview{" "}
          <small>LIVE FROM STUDIO</small>
        </span>
        <div>
          <button className="button secondary" onClick={toggleFull}>
            {full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}{" "}
            {full ? "Exit full screen" : "Full screen"}
          </button>
          <button className="button primary" onClick={() => window.close()}>
            <X size={15} />
            Return to studio
          </button>
        </div>
      </div>
      {notice && (
        <p role="status" className="preview-notice">
          {notice}
        </p>
      )}
      <BroadcastCanvas {...payload} />
      <p className="preview-window-note">
        Synthetic player simulation · Off-ball movement is illustrative · Close
        this window to return
      </p>
    </div>
  );
}
function App() {
  const [reviewWindow,setReviewWindow]=useState<ReviewContext|null>(null);
  const openReview=()=>setReviewWindow({minute:frame.minute,seed:frame.context?.seed??20261020});
  const [frame, setFrame] = useState<Frame>(initial);
  const [run, setRun] = useState(0);
  const [connected, setConnected] = useState(false);
  const [mode, setMode] = useState<"analyst" | "fan">("analyst");
  const [history, setHistory] = useState<Insight[]>([]);
  const [studio, setStudio] = useState(
    new URLSearchParams(location.search).get("view") === "studio",
  );
  const [profile, setProfile] = useProfile();
  const squads = useSquads();
  const [language, setLanguage] = useState<LanguageCode>("en");
  const [audience, setAudience] = useState<"fan" | "analyst" | "broadcast">(
    "broadcast",
  );
  const [queue, setQueue] = useState<Overlay[]>([]);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [selected, setSelected] = useState("");
  const [selectedInsight, setSelectedInsight] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [overlayError, setOverlayError] = useState(false);
  const [previewSource, setPreviewSource] = useState('synthetic');
  const trackingMode = previewSource !== 'synthetic';
  const [expanded, setExpanded] = useState(false);
  const [previewNotice, setPreviewNotice] = useState("");
  const [popupHref, setPopupHref] = useState("");
  const previewRef = useRef<HTMLElement>(null);
  const expandButtonRef = useRef<HTMLButtonElement>(null);
  const previewChannel = useRef<BroadcastChannel | null>(null);
  const popupRef = useRef<Window | null>(null);
  const popupTimer = useRef<ReturnType<typeof setInterval> | undefined>();
  const latestPreview = useRef<PreviewPayload>({ frame: initial });
  const closeExpanded = async () => {
    if (document.fullscreenElement)
      await document.exitFullscreen().catch(() => {});
    setExpanded(false);
    expandButtonRef.current?.focus();
  };
  const expandPreview = async () => {
    setExpanded(true);
    setPreviewNotice("");
    try {
      await previewRef.current?.requestFullscreen();
    } catch {
      /* The expanded layout remains available when fullscreen is blocked. */
    }
  };
  const popOutPreview = () => {
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus();
      return;
    }
    previewChannel.current?.close();
    const id = `matchmind-preview-${crypto.randomUUID()}`;
    const channel = new BroadcastChannel(id);
    previewChannel.current = channel;
    channel.onmessage = (event) => {
      if (event.data?.type === "ready")
        channel.postMessage({
          type: "preview",
          payload: latestPreview.current,
        });
    };
    const href = `${location.origin}/?preview=1&channel=${encodeURIComponent(id)}`;
    setPopupHref(href);
    const popup = window.open(
      href,
      "matchmind-broadcast-preview",
      "popup=yes,width=1280,height=820",
    );
    if (!popup) {
      setPreviewNotice(
        "The preview window was blocked. Allow pop-ups, or open the preview in a tab.",
      );
      return;
    }
    popupRef.current = popup;
    setPreviewNotice(
      "Preview opened in a separate window. It stays synced with this studio.",
    );
    clearInterval(popupTimer.current);
    popupTimer.current = setInterval(() => {
      if (popup.closed) {
        clearInterval(popupTimer.current);
        popupRef.current = null;
        setPopupHref("");
        channel.close();
        if (previewChannel.current === channel) previewChannel.current = null;
        setPreviewNotice("Preview window closed. The studio is ready.");
      }
    }, 500);
  };
  useEffect(
    () => () => {
      clearInterval(popupTimer.current);
      previewChannel.current?.close();
      popupRef.current?.close();
    },
    [],
  );
  useEffect(() => {
    const changed = () => {
      if (!document.fullscreenElement) setExpanded(false);
    };
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panel = previewRef.current;
    panel?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        void closeExpanded();
      }
      if (event.key === "Tab" && panel) {
        const controls = [
          ...panel.querySelectorAll<HTMLElement>(
            'button,a[href],select,[tabindex="0"]',
          ),
        ];
        const first = controls[0],
          last = controls[controls.length - 1];
        if (
          event.shiftKey &&
          (document.activeElement === first || document.activeElement === panel)
        ) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", key);
      expandButtonRef.current?.focus();
    };
  }, [expanded]);
  useEffect(() => {
    if (!studio) setExpanded(false);
  }, [studio]);
  useEffect(() => {
    setHistory([]);
    setQueue([]);
    setSelected("");
    setSelectedInsight("");
    setSamples([]);
    setFrame(initial);
    setConnected(false);
    let disposed = false,
      lastMinute = 0,
      lastVersion = 0,
      socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(
        `${scheme}://${location.host}/ws/match?speed=1&start_minute=${lastMinute + 1}`,
      );
      socket.onopen = () => {
        if (!disposed) setConnected(true);
      };
      socket.onmessage = (e) => {
        if (disposed) return;
        const next: Frame = JSON.parse(e.data);
        if (next.minute <= lastMinute) return;
        if(lastVersion && next.context?.state_version !== lastVersion){setHistory([]);setQueue([]);setGraph(null);setSamples([]);setSelected("");setSelectedInsight("");}
        lastVersion=next.context?.state_version??0;
        lastMinute = next.minute;
        setFrame(next);
        setSamples((prev) => [
          ...prev,
          {
            minute: next.minute,
            home: next.statistics.home.advanced_events,
            away: next.statistics.away.advanced_events,
          },
        ]);
        setHistory((prev) => {
          const items = new Map(prev.map((x) => [x.id, x]));
          next.insights.forEach((x) => items.set(x.id, x));
          return [...items.values()].slice(-30);
        });
      };
      socket.onclose = () => {
        if (disposed) return;
        setConnected(false);
        if (lastMinute < 90) retry = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [run]);
  useEffect(() => {
    if (!studio) return;
    let cancelled = false;
    setOverlayError(false);
    fetch(
      `/api/overlays?minute=${frame.minute}&language=${language}&audience=${audience}` +
        (profile.club ? `&club=${profile.club}` : "") +
        (profile.players.length ? `&players=${profile.players.join(",")}` : "") +
        (profile.focus ? `&focus_player=${profile.focus}` : ""),
    )
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setQueue(data.context?.state_version===frame.context?.state_version ? data.overlays : []);
      })
      .catch(() => {
        if (!cancelled) {
          setQueue([]);
          setOverlayError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [studio, frame.minute, frame.context?.state_version, language, audience, profile]);
  useEffect(() => {
    if (frame.minute < 20) {
      setGraph(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/graph/compare?minute=${frame.minute}&team=away`)
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((v) => {
        if (!cancelled) setGraph(v.context?.state_version===frame.context?.state_version ? v : null);
      })
      .catch(() => {
        if (!cancelled) setGraph(null);
      });
    return () => {
      cancelled = true;
    };
  }, [frame.minute, frame.context?.state_version]);
  useEffect(() => {
    if(connected || frame.minute===0) return;
    const controller=new AbortController();
    const timer=setInterval(()=>{
      fetch(`/api/state?minute=${frame.minute}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(next=>{
        if(controller.signal.aborted || next.context?.state_version===frame.context?.state_version)return;
        setFrame(prev=>prev.minute===next.minute?{...prev,...next}:prev);
        setHistory(next.insights);setQueue([]);setGraph(null);setSamples([]);setSelected("");setSelectedInsight("");
      }).catch(()=>{});
    },2000);
    return()=>{controller.abort();clearInterval(timer)};
  },[connected,frame.minute,frame.context?.state_version]);
  const currentOverlay =
    queue.find((o) => o.overlay_id === selected) || queue[queue.length - 1];
  latestPreview.current = { frame, overlay: currentOverlay };
  useEffect(() => {
    previewChannel.current?.postMessage({
      type: "preview",
      payload: { frame, overlay: currentOverlay },
    });
  }, [frame, currentOverlay]);
  const isActive = (o: Overlay) =>
    frame.minute * 60 >= o.match_clock_seconds &&
    frame.minute * 60 < o.match_clock_seconds + o.duration_ms / 1000;
  const insight =
    history.find((i) => i.id === selectedInsight) ||
    history[history.length - 1];
  const home = frame.statistics.home,
    away = frame.statistics.away;
  const totalPasses = home.passes + away.passes;
  const completion = totalPasses
    ? (
        ((home.completed_passes + away.completed_passes) / totalPasses) *
        100
      ).toFixed(1)
    : "0.0";
  const status =
    frame.minute === 90
      ? "Full time"
      : connected
        ? "Simulation live"
        : frame.minute
          ? "Reconnecting"
          : "Connecting";
  const exportSnapshot = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          { source: "synthetic", frame, insights: history, graph },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = `matchmind-minute-${frame.minute}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const [accessError,setAccessError]=useState("");
  const exitWorkspace = async () => {
    try{await signOut()}catch{setAccessError("Could not sign out. Please retry.");return;}
    clearInterval(popupTimer.current);
    previewChannel.current?.postMessage({ type: "studio_closed" });
    previewChannel.current?.close();
    popupRef.current?.close();
    window.location.assign("/");
  };
  return (
    <div className="workspace">
      {reviewWindow&&<StudioEvidence context={reviewWindow} onDismiss={()=>setReviewWindow(null)}/>} 
      <a className="skip-link" href="#main">
        Skip to match intelligence
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="MatchMind home">
          <div className="brand-mark">
            <AudioLines size={23} />
          </div>
          <span>
            matchmind<span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="workspace-label">INTELLIGENCE WORKSPACE</div>
        <nav className="side-nav" aria-label="Workspace">
          <button
            aria-label="Match overview"
            className={!studio ? "active" : ""}
            aria-current={!studio ? "page" : undefined}
            onClick={() => setStudio(false)}
          >
            <LayoutDashboard size={18} />
            <span>Match overview</span>
            {!studio && <i />}
          </button>
          <button
            aria-label="Broadcast Studio"
            className={studio ? "active" : ""}
            aria-current={studio ? "page" : undefined}
            onClick={() => setStudio(true)}
          >
            <MonitorPlay size={18} />
            <span>Broadcast Studio</span>
            {studio && <i />}
          </button>
        </nav>
        <div className="sidebar-session">
          <div className="section-label">
            CURRENT SESSION <span className="tiny-dot" />
          </div>
          <div className="session-match">
            <Crest small />
            <span>
              Calderbrook<small>vs Merridge</small>
            </span>
          </div>
          <div className="session-meta">
            <span>Synthetic match</span>
            <span>
              {frame.minute === 90 ? "Completed" : `${frame.minute}′ / 90′`}
            </span>
          </div>
          <div className="session-progress">
            <i style={{ width: `${(frame.minute / 90) * 100}%` }} />
          </div>
        </div>
        <div className="sidebar-bottom">
          <div className="trust-icon">
            <ShieldCheck size={19} />
          </div>
          <strong>Every insight. Evidenced.</strong>
          <p>Inspect the source behind every match observation.</p>
          <div className="environment">
            <span className="tiny-dot" /> DEMO WORKSPACE <span>v0.1</span>
          </div>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <div className="breadcrumbs">
            <span className="breadcrumb-root">Workspace</span>{" "}
            <ChevronRight size={13} />
            <span>{studio ? "Broadcast Studio" : "Match overview"}</span>
          </div>
          <div className="topbar-right">
            <span className="synthetic-label">SYNTHETIC DATA</span>
            <button
              className="workspace-exit"
              onClick={exitWorkspace}
              title="Sign out of the local session and return to the landing page"
            >
              <LogOut size={14} />
              <span>Sign out & exit</span>
            </button>
            {accessError&&<span role="alert">{accessError}</span>}
            <button className="button secondary" onClick={()=>setReviewWindow({minute:frame.minute,seed:frame.context?.seed??20261020,accountOnly:true})}>Account & access</button>
            <div className="avatar" aria-label="MatchMind workspace">
              MM
            </div>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span /> THE GAME, EXPLAINED
              </div>
              <h1>
                {studio ? "Broadcast Studio" : "Match intelligence"}
                <span className="live-pill">
                  <i className={connected ? "pulsing" : ""} />
                  {status}
                </span>
              </h1>
              <p>
                {studio
                  ? "Turn verified observations into broadcast-ready moments."
                  : "A clearer view of the match. Every observation backed by evidence."}
              </p>
            </div>
            <div className="page-actions">
              <button
                className="button secondary"
                onClick={exportSnapshot}
                title="Download current match state as JSON"
              >
                <ArrowDownToLine size={15} />
                <span>Export snapshot</span>
              </button>
              <button
                className="button primary"
                onClick={() => setRun((x) => x + 1)}
              >
                <RotateCcw size={15} />
                Replay match
              </button>
              <button className="button secondary" onClick={openReview} disabled={frame.minute<20||trackingMode} title={trackingMode?"Research playback uses a different source; this review is for the synthetic match.":frame.minute<20?"Two complete ten-minute windows are needed before review.":"Inspect and review the current passing observation"}><ShieldCheck size={15}/> Inspect evidence</button>
            </div>
          </div>
          <section className="match-card" aria-label="Match scoreboard">
            <div className="match-card-top">
              <span>
                <span className="tiny-dot" /> SYNTHETIC MATCHDAY
              </span>
              <span>
                {frame.minute === 90 ? "MATCH COMPLETE" : "90-MINUTE REPLAY"}{" "}
                <span className="separator">/</span> DEMO 001
              </span>
            </div>
            <div className="scoreboard">
              <div className="score-team home-team">
                <Crest />
                <div>
                  <h2>Calderbrook</h2>
                  <span>
                    <i /> HOME
                  </span>
                </div>
              </div>
              <div className="score-center">
                <div className="score-numbers">
                  <span>{home.goals}</span>
                  <span className="score-colon">:</span>
                  <span>{away.goals}</span>
                </div>
                <div className="match-clock">
                  <span className="tiny-dot" />
                  {frame.minute === 90
                    ? "FULL TIME"
                    : `${String(frame.minute).padStart(2, "0")}:00`}
                </div>
              </div>
              <div className="score-team away-team">
                <div>
                  <h2>Merridge</h2>
                  <span>
                    AWAY <i />
                  </span>
                </div>
                <Crest away />
              </div>
            </div>
            <div
              className="match-progress"
              aria-label={`${frame.minute} of 90 minutes played`}
            >
              <i style={{ width: `${(frame.minute / 90) * 100}%` }} />
              <span className="half-marker" />
            </div>
            <div className="match-card-bottom">
              <span>
                <ShieldCheck size={13} /> Deterministic simulation
              </span>
              <span>Fictional teams. Real calculations.</span>
              <span>
                00′ <span className="timeline-end">90′</span>
              </span>
            </div>
          </section>
          <section className="metric-grid" aria-label="Match summary">
            <div className="metric">
              <span className="metric-label">
                Events processed
                <Activity size={16} />
              </span>
              <div>
                {home.events + away.events}
                <small>so far</small>
              </div>
              <span className="metric-note">Match events recorded</span>
            </div>
            <div className="metric">
              <span className="metric-label">
                Pass completion
                <GitBranch size={16} />
              </span>
              <div>
                {completion}
                <small>%</small>
              </div>
              <span className="metric-note">
                {home.completed_passes + away.completed_passes} completed passes
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">
                Total shots
                <Target size={16} />
              </span>
              <div>
                {home.shots + away.shots}
                <small>attempts</small>
              </div>
              <span className="metric-note">
                {home.goals + away.goals} goals · xG {(home.xg + away.xg).toFixed(2)}
              </span>
            </div>
            <div className="metric accent-metric">
              <span className="metric-label">
                Verified insights
                <Sparkles size={16} />
              </span>
              <div>
                {history.filter((x) => x.validated).length}
                <span className="verified-chip">
                  <Check size={12} /> Evidence linked
                </span>
              </div>
              <span className="metric-note">Traceable to source events</span>
            </div>
          </section>
          <div className="content-tabs">
            <div
              role="tablist"
              aria-label="Match views"
              onKeyDown={(e) => {
                if (
                  ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
                ) {
                  e.preventDefault();
                  const next =
                    e.key === "Home" ? false : e.key === "End" ? true : !studio;
                  setStudio(next);
                  document
                    .getElementById(next ? "tab-studio" : "tab-live")
                    ?.focus();
                }
              }}
            >
              <button
                id="tab-live"
                role="tab"
                tabIndex={studio ? -1 : 0}
                aria-controls="match-view"
                aria-selected={!studio}
                className={!studio ? "selected" : ""}
                onClick={() => setStudio(false)}
              >
                <Activity size={15} />
                Live match
              </button>
              <button
                id="tab-studio"
                role="tab"
                tabIndex={studio ? 0 : -1}
                aria-controls="match-view"
                aria-selected={studio}
                className={studio ? "selected" : ""}
                onClick={() => setStudio(true)}
              >
                <MonitorPlay size={15} />
                Broadcast Studio
              </button>
            </div>
            <span>
              <ShieldCheck size={13} /> Evidence-first intelligence
            </span>
          </div>
          <div
            id="match-view"
            role="tabpanel"
            aria-labelledby={studio ? "tab-studio" : "tab-live"}
          >
            {studio ? (
              <div className="studio-grid">
                <section
                  ref={previewRef}
                  tabIndex={expanded ? -1 : undefined}
                  role={expanded ? "dialog" : undefined}
                  aria-modal={expanded ? true : undefined}
                  aria-label="Broadcast preview"
                  className={`panel preview-panel ${expanded ? "preview-expanded" : ""}`}
                >
                  <div className="preview-controls">
                    <button
                      ref={expandButtonRef}
                      className="button secondary"
                      onClick={() =>
                        expanded ? void closeExpanded() : void expandPreview()
                      }
                      aria-label={
                        expanded
                          ? "Reset preview size"
                          : "Expand preview to full screen"
                      }
                    >
                      {expanded ? (
                        <Minimize2 size={15} />
                      ) : (
                        <Maximize2 size={15} />
                      )}{" "}
                      {expanded ? "Reset view" : "Full screen"}
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => trackingMode ? window.open(`/app?view=${previewSource}`, "_blank", "noopener") : popOutPreview()}
                    >
                      <ExternalLink size={15} /> Pop out
                    </button>
                    {expanded && (
                      <button
                        className="button secondary"
                        onClick={() => void closeExpanded()}
                        aria-label="Close expanded preview"
                      >
                        <X size={16} />
                      </button>
                    )}
                  </div>
                  {previewNotice && (
                    <p className="preview-notice" role="status">
                      {previewNotice}
                      {popupHref && (
                        <>
                          {" "}
                          <a href={popupHref} target="_blank" rel="noopener">
                            Open preview in a tab <ExternalLink size={12} />
                          </a>
                        </>
                      )}
                    </p>
                  )}
                  <PanelTitle
                    icon={<MonitorPlay size={17} />}
                    title="Broadcast preview"
                    kicker={previewSource==='statsbomb'?"SOURCE EVENT ANALYSIS":trackingMode ? "RECORDED TRACKING" : "MATCH-CLOCK SYNC"}
                  />
                  <label className="tracking-source">Preview source
                    <select aria-label="Preview source" value={previewSource} onChange={e=>setPreviewSource(e.target.value)}>
                      <option value="synthetic">Synthetic demo</option>{RESEARCH && <><option value="tracking">Real tracking - SkillCorner</option><option value="metrica">Metrica - tracking + events</option><option value="statsbomb">StatsBomb - real event analysis</option></>}
                    </select>
                  </label>
                  {previewSource==='statsbomb' ? <StatsBombResearch/> : trackingMode ? <TrackingReplay key={previewSource} source={previewSource==='metrica'?'metrica':'skillcorner'}/> : <BroadcastCanvas frame={frame} overlay={currentOverlay} />}
                  <div className="preview-caption">
                    <span>
                      <CircleDot size={13} /> {trackingMode ? "Real data research view" : "Illustrative match play"}
                    </span>
                    <span>Preview canvas</span>
                  </div>
                  <p className="subtle-note">
                    {trackingMode ? "Real data uses a separate source clock. The surrounding score, insights and overlay queue belong to the synthetic demo, not the selected research match." : "Players and ball share an illustrative gameplay simulation; source statistics use the match clock. Historical selections are previews. Only overlays within their eight-second match-clock window are marked on air."}
                  </p>
                </section>
                <section className="panel control-panel">
                  <PanelTitle
                    icon={<Radio size={17} />}
                    title="Overlay control room"
                    kicker={`${queue.length} MESSAGES`}
                  />
                  <div className="studio-filters">
                    <label>
                      Audience
                      <select
                        aria-label="Audience"
                        value={audience}
                        onChange={(e) =>
                          setAudience(e.target.value as typeof audience)
                        }
                      >
                        <option value="broadcast">Broadcast</option>
                        <option value="analyst">Analyst</option>
                        <option value="fan">Fan</option>
                      </select>
                    </label>
                    <label>
                      Language
                      <select
                        aria-label="Language"
                        value={language}
                        onChange={(e) =>
                          setLanguage(e.target.value as typeof language)
                        }
                      >
                        {LANGUAGES.map((l) => (
                          <option key={l.code} value={l.code}>
                            {l.native}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="queue-label">
                    VERIFIED OVERLAY QUEUE
                    <span>{queue.length.toString().padStart(2, "0")}</span>
                  </div>
                  <div className="overlay-queue">
                    {queue.length ? (
                      queue
                        .slice()
                        .reverse()
                        .map((o) => (
                          <button
                            className={`overlay-item ${currentOverlay?.overlay_id === o.overlay_id ? "selected" : ""}`}
                            key={o.overlay_id}
                            onClick={() => setSelected(o.overlay_id)}
                            aria-pressed={
                              currentOverlay?.overlay_id === o.overlay_id
                            }
                          >
                            <span className="overlay-minute">
                              {Math.floor(o.match_clock_seconds / 60)}′
                            </span>
                            <span>
                              <strong dir={directionOf(o.language)} lang={o.language}>
                                {(o.favourite_player || o.favourite_club) && "★ "}
                                {o.headline}
                              </strong>
                              <small>
                                {o.evidence_event_ids.length} source events ·{" "}
                                {isActive(o) ? "On air" : "Historical"}
                              </small>
                            </span>
                            <ChevronRight size={15} />
                          </button>
                        ))
                    ) : (
                      <div className="empty-state">
                        <Radio size={25} />
                        <h3>
                          {overlayError
                            ? "Overlays unavailable"
                            : "Waiting for a moment"}
                        </h3>
                        <p>
                          {overlayError
                            ? "The overlay request failed. Switch views or replay to retry."
                            : "The queue fills as evidence-backed insights are detected."}
                        </p>
                      </div>
                    )}
                  </div>
                  {currentOverlay && (
                    <div className="payload">
                      <div className="evidence-label">
                        <ShieldCheck size={15} /> VERIFIED CONTENT
                      </div>
                      <p>{currentOverlay.body}</p>
                      <details>
                        <summary>
                          Inspect synchronized JSON payload
                          <ChevronRight size={14} />
                        </summary>
                        <pre>{JSON.stringify(currentOverlay, null, 2)}</pre>
                      </details>
                    </div>
                  )}
                </section>
              </div>
            ) : (
              <>
                <div className="experience-grid">
                  <ProfilePanel profile={profile} onChange={setProfile} squads={squads} />
                  <ExperiencePanels minute={frame.minute} stateVersion={frame.context?.state_version} profile={profile} />
                  <AskPanel minute={frame.minute} profile={profile} />
                  <RecapPanel minute={frame.minute} profile={profile} />
                  <LiveStreamPanel profile={profile} />
                  {squads && <GraphExplorer minute={frame.minute} stateVersion={frame.context?.state_version} clubs={squads.clubs} />}
                </div>
                <div className="dashboard-grid">
                  <div className="main-column">
                    <section className="panel team-panel">
                      <PanelTitle
                        icon={<Activity size={17} />}
                        title="The match in numbers"
                        kicker="TEAM COMPARISON"
                      />
                      <div className="comparison-teams">
                        <span>
                          <i className="home-dot" />
                          Calderbrook
                        </span>
                        <span>
                          Merridge
                          <i className="away-dot" />
                        </span>
                      </div>
                      <Comparison
                        label="Possession (time)"
                        home={home.possession_pct}
                        away={away.possession_pct}
                        suffix="%"
                      />
                      <Comparison
                        label="Pass completion"
                        home={home.pass_completion_pct}
                        away={away.pass_completion_pct}
                        suffix="%"
                      />
                      <Comparison
                        label="Shots"
                        home={home.shots}
                        away={away.shots}
                      />
                      <Comparison
                        label="Shots on target"
                        home={home.shots_on_target}
                        away={away.shots_on_target}
                      />
                      <Comparison
                        label="Expected goals (xG)"
                        home={home.xg}
                        away={away.xg}
                      />
                      <Comparison
                        label="Corners"
                        home={home.corners}
                        away={away.corners}
                      />
                      <Comparison
                        label="Fouls"
                        home={home.fouls}
                        away={away.fouls}
                      />
                      <Comparison
                        label="Yellow / red cards"
                        home={home.yellow_cards + home.red_cards}
                        away={away.yellow_cards + away.red_cards}
                      />
                      <Comparison
                        label="Recoveries"
                        home={home.recoveries}
                        away={away.recoveries}
                      />
                      <Comparison
                        label="Final-third entries"
                        home={home.final_third_entries}
                        away={away.final_third_entries}
                      />
                    </section>
                    <section className="panel activity-panel">
                      <PanelTitle
                        icon={<TrendingUp size={17} />}
                        title="Advanced-area activity"
                        kicker="CUMULATIVE EVENTS"
                      />
                      <div className="activity-legend">
                        <span>
                          <i className="home-dot" />
                          Calderbrook <b>{home.advanced_events}</b>
                        </span>
                        <span>
                          <i className="away-dot" />
                          Merridge <b>{away.advanced_events}</b>
                        </span>
                      </div>
                      <svg
                        className="activity-chart"
                        viewBox="0 0 500 120"
                        role="img"
                        aria-label="Cumulative advanced-area events through the current match minute"
                      >
                        <path
                          d="M0 24H500M0 60H500M0 96H500"
                          className="chart-grid"
                        />
                        {(["home", "away"] as const).map((team) => (
                          <polyline
                            key={team}
                            className={`chart-line ${team}`}
                            points={samples
                              .map(
                                (s) =>
                                  `${(s.minute / 90) * 500},${110 - (s[team] / Math.max(10, home.advanced_events, away.advanced_events)) * 96}`,
                              )
                              .join(" ")}
                          />
                        ))}
                      </svg>
                      <div className="chart-axis">
                        <span>00′</span>
                        <span>30′</span>
                        <span>60′</span>
                        <span>90′</span>
                      </div>
                      <p className="subtle-note">
                        Event activity in advanced areas, rather than possession
                        or causal tactical pressure.
                      </p>
                    </section>
                  </div>
                  <section className="panel insight-panel" id="insight">
                    <PanelTitle
                      icon={<Sparkles size={17} />}
                      title="Match intelligence"
                      kicker="RULE-BASED"
                    />
                    <div
                      className="mode-switch"
                      role="group"
                      aria-label="Insight audience"
                    >
                      <button
                        aria-pressed={mode === "analyst"}
                        className={mode === "analyst" ? "selected" : ""}
                        onClick={() => setMode("analyst")}
                      >
                        Analyst mode
                      </button>
                      <button
                        aria-pressed={mode === "fan"}
                        className={mode === "fan" ? "selected" : ""}
                        onClick={() => setMode("fan")}
                      >
                        Fan mode
                      </button>
                    </div>
                    {insight ? (
                      <>
                        <div className="insight-label">
                          <span>
                            <Zap size={13} /> MORE ADVANCED ACTIVITY
                          </span>
                          <span>{insight.minute}′</span>
                        </div>
                        <h2 className="insight-headline">
                          {insight.team_id === "away"
                            ? "The away side is playing more often in advanced areas."
                            : "The home side is playing more often in advanced areas."}
                        </h2>
                        <p className="insight-copy">
                          {mode === "analyst"
                            ? insight.explanation
                            : `${insight.team_id === "away" ? "Merridge" : "Calderbrook"} is recording more actions in advanced areas than in the previous ten minutes.`}
                        </p>
                        {insight.interpretation && (
                          <p className="insight-copy subtle-note">
                            Shift interpretation: needs human review · z{" "}
                            {insight.interpretation.z_score.toFixed(2)} (calibrated
                            threshold {insight.interpretation.z_threshold}
                            {insight.interpretation.meets_calibrated_threshold
                              ? ", met"
                              : ", not met"}
                            )
                          </p>
                        )}
                        <div className="evidence-card">
                          <div className="evidence-label">
                            <ShieldCheck size={15} /> EVIDENCE VERIFIED
                          </div>
                          <div className="evidence-values">
                            <div>
                              <span>Previous 10 min</span>
                              <strong>{insight.previous_count}</strong>
                            </div>
                            <ArrowRight size={23} />
                            <div>
                              <span>Latest 10 min</span>
                              <strong>{insight.current_count}</strong>
                            </div>
                            <span className="difference">
                              +{insight.current_count - insight.previous_count}
                            </span>
                          </div>
                          <div className="evidence-foot">
                            <span>
                              {insight.evidence_event_ids.length} source events
                            </span>
                            <span>
                              <Check size={12} /> References verified
                            </span>
                          </div>
                        </div>
                        <details className="source-details">
                          <summary>
                            Explore the evidence
                            <ChevronRight size={15} />
                          </summary>
                          <div className="source-ids">
                            {insight.evidence_event_ids.map((id) => (
                              <span key={id}>{id}</span>
                            ))}
                          </div>
                        </details>
                      </>
                    ) : (
                      <div className="empty-state insight-empty">
                        <div className="waiting-orbit">
                          <Sparkles size={29} />
                        </div>
                        <span className="eyebrow">WATCHING THE MATCH</span>
                        <h3>Good insights take context.</h3>
                        <p>
                          We compare consecutive ten-minute windows to find
                          meaningful changes. Verified observations will appear
                          here as the match develops.
                        </p>
                        <span className="watching-label">
                          <i />
                          Evaluating match events
                        </span>
                      </div>
                    )}
                    <div className="insight-disclaimer">
                      <ShieldCheck size={14} />
                      <span>
                        Deterministic observations. Traceable evidence. No
                        unsupported causal claims.
                      </span>
                    </div>
                  </section>
                </div>
                <div className="bottom-grid">
                  <section className="panel network-panel">
                    <PanelTitle
                      icon={<GitBranch size={17} />}
                      title="Passing connections"
                      kicker="AWAY · LAST 10 MIN"
                    />
                    {graph ? (
                      <>
                        <div className="network-content">
                          <PassingNetwork network={graph.current} />
                          <div className="network-stats">
                            <div>
                              <span>Connections</span>
                              <strong>
                                {graph.current.metrics.edges}
                                <small>
                                  prev. {graph.previous.metrics.edges}
                                </small>
                              </strong>
                            </div>
                            <div>
                              <span>Completed passes</span>
                              <strong>
                                {graph.current.metrics.passes}
                                <small>
                                  prev. {graph.previous.metrics.passes}
                                </small>
                              </strong>
                            </div>
                          </div>
                        </div>
                        <details className="source-details">
                          <summary>
                            Inspect graph evidence
                            <ChevronRight size={14} />
                          </summary>
                          <pre>
                            {JSON.stringify(graph.current.edges, null, 2)}
                          </pre>
                        </details>
                      </>
                    ) : (
                      <div className="empty-state">
                        <GitBranch size={27} />
                        <p>
                          Passing connections appear after two complete
                          ten-minute windows.
                        </p>
                      </div>
                    )}
                    <p className="subtle-note">
                      Synthetic recipients. Layout shows connections, not player
                      positions.
                    </p>
                  </section>
                  <section className="panel events-panel">
                    <PanelTitle
                      icon={<AudioLines size={17} />}
                      title="The latest actions"
                      kicker="EVENT FEED"
                    />
                    {frame.events.length ? (
                      <div className="event-feed">
                        {frame.events
                          .slice()
                          .reverse()
                          .map((e) => (
                            <div className="event-row" key={e.event_id}>
                              <span className="event-time">
                                {String(e.minute).padStart(2, "0")}:
                                {String(e.second).padStart(2, "0")}
                              </span>
                              <span className={`event-symbol ${e.team_id}`}>
                                <CircleDot size={16} />
                              </span>
                              <div>
                                <strong>{eventLabel(e)}</strong>
                                <span>
                                  {e.team_id === "home"
                                    ? "Calderbrook"
                                    : "Merridge"}{" "}
                                  <span>·</span> {e.player_name ?? `#${e.player_id.split("-")[1]}`}
                                </span>
                              </div>
                              <ChevronRight size={14} />
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div className="empty-state">
                        <Activity size={25} />
                        <p>Waiting for the first match events.</p>
                      </div>
                    )}
                  </section>
                </div>
                <section className="panel timeline-panel">
                  <PanelTitle
                    icon={<Zap size={17} />}
                    title="Key observations"
                    kicker={`${history.length} DETECTED`}
                  />
                  {history.length ? (
                    <div className="insight-timeline">
                      {history
                        .slice(-5)
                        .reverse()
                        .map((x) => (
                          <button
                            key={x.id}
                            className={insight?.id === x.id ? "selected" : ""}
                            aria-pressed={insight?.id === x.id}
                            onClick={() => {
                              setSelectedInsight(x.id);
                              document
                                .getElementById("insight")
                                ?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                });
                            }}
                          >
                            <span className="timeline-minute">{x.minute}′</span>
                            <div>
                              <strong>{x.headline}</strong>
                              <span>
                                {x.previous_count} → {x.current_count}{" "}
                                advanced-area events
                              </span>
                            </div>
                            <ShieldCheck size={15} />
                            <ChevronRight size={15} />
                          </button>
                        ))}
                    </div>
                  ) : (
                    <p className="timeline-empty">
                      Meaningful moments will be collected here as the match
                      unfolds.
                    </p>
                  )}
                </section>
              </>
            )}
          </div>
          <footer>
            <span>
              <AudioLines size={14} /> MATCHMIND AI{" "}
              <span className="footer-divider">/</span> Explain the game.
            </span>
            <span>
              {trackingMode ? "Preview: real research data. Surrounding analytics: synthetic demo." : "All teams and events are synthetic. Not affiliated with the Premier League."}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(location.search).get("view") === "evidence" ? <EvidenceLab/> : RESEARCH && new URLSearchParams(location.search).get("view") === "statsbomb" ? <StatsBombResearch standalone/> : RESEARCH && new URLSearchParams(location.search).get("view") === "metrica" ? <TrackingReplay standalone source="metrica"/> : RESEARCH && ["tracking","skillcorner"].includes(new URLSearchParams(location.search).get("view")??'') ? <TrackingReplay standalone/> : new URLSearchParams(location.search).get("preview") === "1" ? (
      <PreviewWindow />
    ) : location.pathname.startsWith("/app") ? (
      <App />
    ) : (
      <Landing />
    )}
  </React.StrictMode>,
);

