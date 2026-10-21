import React, { useState } from "react";
import HumanPlayers from "./HumanPlayers";
import { type PitchState } from "./matchTypes";

export function PitchPlayers({
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
