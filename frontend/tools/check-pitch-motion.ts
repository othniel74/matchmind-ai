import assert from "node:assert/strict";
import { stepPlayer, type Motion } from "../src/pitchMotion.ts";

const state = (x = 25, y = 50, heading = Math.PI / 2): Motion => ({
  x,
  y,
  vx: 0,
  vy: 0,
  heading,
});
const target = { x: 80, y: 15, team_id: "home", number: 9 };
let player = state(),
  previous = { ...player };
for (let frame = 0; frame < 600; frame++) {
  const destination = frame < 150 ? target : { ...target, x: 20, y: 85 };
  const speed = stepPlayer(player, destination, { x: 50, y: 50 }, 1 / 30, true);
  assert(speed <= 5.5 + 1e-8, "Player speed is bounded");
  assert(
    Math.hypot(player.vx - previous.vx, player.vy - previous.vy) <=
      5.5 / 30 + 1e-8,
    "Acceleration is bounded when targets reverse",
  );
  assert(
    Math.hypot(
      (player.x - previous.x) * 1.05,
      (player.y - previous.y) * 0.68,
    ) <=
      5.5 / 30 + 1e-8,
    "No position teleport",
  );
  const turn = Math.atan2(
    Math.sin(player.heading - previous.heading),
    Math.cos(player.heading - previous.heading),
  );
  assert(Math.abs(turn) <= 2.4 / 30 + 1e-8, "Turning is bounded");
  previous = { ...player };
}
console.log(
  "PASS bounded speed, acceleration, displacement and turning through a target reversal",
);
for (const team of ["home", "away"]) {
  const home = team === "home";
  const keeper = state(home ? 8 : 92, 50, home ? Math.PI / 2 : -Math.PI / 2);
  for (let frame = 0; frame < 600; frame++) {
    stepPlayer(
      keeper,
      { x: home ? 2 : 98, y: frame < 300 ? 0 : 100, team_id: team, number: 1 },
      { x: frame % 100, y: frame % 100 },
      1 / 30,
      true,
    );
    assert(
      Math.sin(keeper.heading) * (home ? 1 : -1) > 0,
      "Keeper always faces into the field, even while retreating",
    );
    assert(
      keeper.y >= 32 && keeper.y <= 68,
      "Keeper stays within goal-area width",
    );
    assert(
      home ? keeper.x >= 3 && keeper.x <= 12 : keeper.x >= 88 && keeper.x <= 97,
      "Keeper stays near own goal",
    );
  }
}
console.log(
  "PASS both goalkeepers face the pitch and remain in their own penalty areas",
);
player = state();
for (let i = 0; i < 60; i++)
  stepPlayer(player, target, { x: 50, y: 50 }, 1 / 30, true);
const old = { ...player };
stepPlayer(player, { ...target, x: 0 }, { x: 50, y: 50 }, 1 / 30, true);
assert(
  player.vx > 0 && Math.abs(player.vx - old.vx) <= 5.5 / 30 + 1e-8,
  "Retargeting brakes instead of reversing instantly",
);
for (let i = 0; i < 120; i++)
  stepPlayer(player, target, { x: 50, y: 50 }, 1 / 30, false);
assert(Math.hypot(player.vx, player.vy) < 1e-8, "Full time brakes to a stop");
stepPlayer(player, target, { x: 50, y: 50 }, 1 / 30, true, true);
assert(
  player.x === target.x &&
    player.y === target.y &&
    player.vx === 0 &&
    player.vy === 0,
  "Reduced motion shows targets without animation",
);
console.log("PASS retarget braking, full-time stop and reduced motion");
