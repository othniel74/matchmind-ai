import assert from "node:assert/strict";
import {
  createFootballPlay,
  stepFootballPlay,
  advanceFootballTo,
  type FormationPlayer,
} from "../src/footballPlay.ts";
const anchors = [
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
const formation: FormationPlayer[] = ["home", "away"].flatMap((team) =>
  anchors.map(([x, y], i) => ({
    player_id: `${team}-${String(i + 1).padStart(2, "0")}`,
    team_id: team,
    number: i + 1,
    x: team === "home" ? x : 100 - x,
    y: team === "home" ? y : 100 - y,
  })),
);
const distance = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.hypot((a.x - b.x) * 1.05, (a.y - b.y) * 0.68);
const game = createFootballPlay(formation),
  phases = new Set<string>();
for (let i = 0; i < 90 * 60; i++) {
  const before = { ...game.ball };
  stepFootballPlay(game, formation, 1 / 60, true);
  phases.add(game.phase);
  assert(
    Number.isFinite(game.ball.x) && Number.isFinite(game.ball.y),
    "Ball position remains finite",
  );
  assert(
    game.ball.x >= 0 &&
      game.ball.x <= 100 &&
      game.ball.y >= 0 &&
      game.ball.y <= 100,
    "Ball remains on the field",
  );
  assert(
    distance(before, game.ball) < 1.5,
    "Ball never jumps to an unrelated event coordinate",
  );
  if (game.owner) {
    assert(
      distance(game.players.get(game.owner)!, game.ball) < 1,
      "Possession keeps the ball within playing distance of the carrier",
    );
  } else
    assert(
      ["pass", "shot", "loose"].includes(game.phase),
      "Unowned ball is visibly in flight or awaiting control",
    );
  for (const team of ["home", "away"]) {
    const keeper = game.players.get(`${team}-01`)!;
    assert(
      team === "home" ? keeper.x < 12 : keeper.x > 88,
      "Keeper remains near own goal",
    );
  }
}
console.log("Simulation metrics", game.stats, "phases", [...phases]);
assert(
  game.stats.passes >= 4 && game.stats.receives >= 4,
  "Players complete physical passes and receives",
);
assert(
  game.stats.shots >= 1 && game.stats.saves >= 1,
  "Attacks produce shots and goalkeeper collections",
);
assert(
  phases.has("windup") && phases.has("pass") && phases.has("dribble"),
  "Gameplay includes foot contact, dribbling and ball flight",
);
const ball = { ...game.ball };
stepFootballPlay(game, formation, 1 / 60, false);
assert(
  distance(ball, game.ball) < 0.5,
  "Full-time stop does not reset the ball to a remote position",
);
console.log(
  "PASS 90-second possession, pass, receive, shot, keeper and ball-continuity checks",
);

const challenged = createFootballPlay(formation);
challenged.timer = 1.2;
const carrier = challenged.players.get(challenged.owner!)!;
Object.assign(challenged.players.get("away-06")!, {
  x: carrier.x + 0.3,
  y: carrier.y,
  vx: 0,
  vy: 0,
});
stepFootballPlay(challenged, formation, 1 / 60, true);
assert(
  challenged.phase === "loose" &&
    challenged.receiver === "away-06" &&
    challenged.stats.tackles === 1,
  "A close defender can challenge for the ball",
);
assert(!challenged.owner, "A tackle must be followed by physical ball control");
const direct = createFootballPlay(formation),
  detached = createFootballPlay(formation);
advanceFootballTo(direct, 40, 10000);
for (let i = 1; i <= 1200; i++) advanceFootballTo(detached, i / 30, 10000);
assert.deepEqual(
  direct.ball,
  detached.ball,
  "Detached preview catches up to the same ball position",
);
assert.equal(direct.owner, detached.owner, "Views agree on possession");
assert.deepEqual(
  [...direct.players],
  [...detached.players],
  "Different render cadences produce identical play",
);
console.log(
  "PASS physical challenges and deterministic inline/detached clock synchronization",
);
