export type Stats = {
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
export type Insight = {
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
export type MatchEvent = {
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
export const shirt = (id: string | null | undefined) => `#${id?.split("-")[1] ?? "?"}`;
export function eventLabel(e: MatchEvent) {
  if (e.event_type === "card") return `${(e.outcome ?? "").replace("_", " ")} card`;
  if (e.event_type === "substitution") return `substitution · ${e.replacement_name ?? shirt(e.replacement_player_id)} on`;
  if (e.event_type === "shot" && e.outcome === "goal") return "goal";
  return e.set_piece ? `${e.event_type} · ${e.set_piece.replace("_", " ")}` : e.event_type;
}
export type Overlay = {
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
export type PitchPlayer = {
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
export type PitchState = {
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
export const initialFormation = [
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
export const initialPitch: PitchState = {
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
export type Frame = {
  context?: {match_id:string;state_version:number;seed?:number};
  pitch?: PitchState;
  minute: number;
  statistics: { home: Stats; away: Stats };
  events: MatchEvent[];
  insights: Insight[];
};
export type Edge = {
  source: string;
  target: string;
  weight: number;
  event_ids: string[];
};
export type Network = {
  nodes: string[];
  edges: Edge[];
  metrics: { edges: number; passes: number; density: number };
};
export type Graph = { previous: Network; current: Network };
export type Sample = { minute: number; home: number; away: number };
export const empty: Stats = {
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
export const initial: Frame = {
  minute: 0,
  statistics: { home: empty, away: empty },
  events: [],
  insights: [],
};
