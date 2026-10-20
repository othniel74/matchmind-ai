import { stepPlayer, type Motion } from "./pitchMotion.ts";

export type FormationPlayer = {
  player_id: string;
  team_id: string;
  number: number;
  x: number;
  y: number;
};
type Spot = { x: number; y: number; z: number };
export type FootballPlay = {
  formation: FormationPlayer[];
  players: Map<string, Motion>;
  ball: Spot;
  owner: string | null;
  receiver: string | null;
  phase: "dribble" | "windup" | "kick" | "pass" | "shot" | "loose" | "restart";
  timer: number;
  time: number;
  cycle: number;
  from: Spot;
  to: Spot;
  flight: number;
  travel: number;
  kickId: string | null;
  kickAge: number;
  shot: boolean;
  description: string;
  highlight: string | null;
  speeds: Map<string, number>;
  stats: {
    passes: number;
    receives: number;
    shots: number;
    saves: number;
    tackles: number;
  };
};
const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));
const distance = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.hypot((a.x - b.x) * 1.05, (a.y - b.y) * 0.68);
const foot = (m: Motion, time = 0): Spot => {
  const touch = 0.65 + 0.12 * Math.sin(time * 9);
  return {
    x: m.x + (Math.sin(m.heading) * touch) / 1.05,
    y: m.y + (Math.cos(m.heading) * touch) / 0.68,
    z: 0,
  };
};
const name = (id: string) =>
  `${id.startsWith("home") ? "CAL" : "MER"} #${Number(id.split("-")[1])}`;
export function createFootballPlay(input: FormationPlayer[]): FootballPlay {
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
  const formation = input.map((p) => {
    const [x, y] = anchors[p.number - 1] ?? [p.x, p.y];
    return {
      ...p,
      x: p.team_id === "home" ? x : 100 - x,
      y: p.team_id === "home" ? y : 100 - y,
    };
  });
  const players = new Map(
    formation.map((p) => [
      p.player_id,
      {
        x: p.x,
        y: p.y,
        vx: 0,
        vy: 0,
        heading: p.team_id === "home" ? Math.PI / 2 : -Math.PI / 2,
      },
    ]),
  );
  const owner =
    formation.find((p) => p.team_id === "home" && p.number === 7)?.player_id ??
    formation[0].player_id;
  const ball = foot(players.get(owner)!);
  return {
    formation,
    players,
    ball,
    owner,
    receiver: null,
    phase: "dribble",
    timer: 0,
    time: 0,
    cycle: 0,
    from: { ...ball },
    to: { ...ball },
    flight: 0,
    travel: 0,
    kickId: null,
    kickAge: 10,
    shot: false,
    description: `${name(owner)} in possession`,
    highlight: owner,
    speeds: new Map(),
    stats: { passes: 0, receives: 0, shots: 0, saves: 0, tackles: 0 },
  };
}

function choosePass(
  game: FootballPlay,
  formation: FormationPlayer[],
  owner: FormationPlayer,
) {
  const carrier = game.players.get(owner.player_id)!;
  const direction = owner.team_id === "home" ? 1 : -1;
  let best: FormationPlayer | undefined,
    bestScore = -Infinity;
  for (const p of formation) {
    if (
      p.team_id !== owner.team_id ||
      p.player_id === owner.player_id ||
      p.number === 1
    )
      continue;
    const m = game.players.get(p.player_id)!;
    const length = distance(carrier, m);
    if (length < 5 || length > 36) continue;
    let clearance = 12;
    for (const opponent of formation) {
      if (opponent.team_id === owner.team_id) continue;
      const d = game.players.get(opponent.player_id)!;
      const vx = (m.x - carrier.x) * 1.05,
        vy = (m.y - carrier.y) * 0.68;
      const t = clamp(
        ((d.x - carrier.x) * 1.05 * vx + (d.y - carrier.y) * 0.68 * vy) /
          (vx * vx + vy * vy),
        0,
        1,
      );
      clearance = Math.min(
        clearance,
        distance(d, {
          x: carrier.x + (m.x - carrier.x) * t,
          y: carrier.y + (m.y - carrier.y) * t,
        }),
      );
    }
    const score =
      (m.x - carrier.x) * direction * 0.3 +
      Math.min(clearance, 8) * 1.8 -
      length * 0.1 +
      (p.number % 3 === game.cycle % 3 ? 1.5 : 0);
    if (score > bestScore) {
      best = p;
      bestScore = score;
    }
  }
  return best;
}

/** A continuous, explicitly illustrative match-play loop, not event-coordinate tracking. */
export function stepFootballPlay(
  game: FootballPlay,
  _formation: FormationPlayer[],
  dt: number,
  moving: boolean,
  reduced = false,
) {
  const formation = game.formation;
  dt = clamp(dt, 0, 0.05);
  game.speeds.clear();
  if (!moving || reduced) {
    if (!moving && game.time > 0) game.description = "Full time � replay match";
    for (const p of formation) {
      const m = game.players.get(p.player_id)!;
      game.speeds.set(
        p.player_id,
        stepPlayer(m, { ...p, x: m.x, y: m.y }, game.ball, dt, false),
      );
    }
    if (game.owner) game.ball = foot(game.players.get(game.owner)!, game.time);
    else if (!reduced && (game.phase === "pass" || game.phase === "shot")) {
      game.flight += dt;
      const t = clamp(game.flight / game.travel, 0, 1);
      game.ball = {
        x: game.from.x + (game.to.x - game.from.x) * t,
        y: game.from.y + (game.to.y - game.from.y) * t,
        z: Math.sin(t * Math.PI) * (game.phase === "shot" ? 0.65 : 0.16),
      };
      if (t >= 1) game.phase = "loose";
    }
    return;
  }
  game.time += dt;
  game.timer += dt;
  game.kickAge += dt;
  const carrier = formation.find((p) => p.player_id === game.owner);
  const carrierMotion = carrier ? game.players.get(carrier.player_id)! : null;
  const attacking =
    carrier?.team_id ?? (game.kickId?.startsWith("home") ? "home" : "away");
  const direction = attacking === "home" ? 1 : -1;
  const targets = new Map(formation.map((p) => [p.player_id, { ...p }]));
  const progress = attacking === "home" ? game.ball.x : 100 - game.ball.x;
  for (const p of formation) {
    const target = targets.get(p.player_id)!;
    if (p.number === 1) {
      target.x = p.team_id === "home" ? 6.5 : 93.5;
      target.y = clamp(50 + (game.ball.y - 50) * 0.35, 43, 57);
      continue;
    }
    const same = p.team_id === attacking;
    target.x = clamp(
      p.x + direction * (progress - 45) * (same ? 0.3 : 0.18),
      8,
      92,
    );
    target.y = clamp(p.y + (game.ball.y - 50) * (same ? 0.12 : 0.2), 8, 92);
    if (same && p.number >= 9) {
      target.x = clamp(target.x + direction * 6, 10, 90);
    }
  }
  if (carrier && carrierMotion) {
    const t = targets.get(carrier.player_id)!;
    const dribbling = game.phase === "dribble" && carrier.number !== 1;
    t.x = dribbling
      ? clamp(carrierMotion.x + direction * 7, 7, 93)
      : carrierMotion.x;
    t.y = dribbling
      ? carrierMotion.y + (50 - carrierMotion.y) * 0.08
      : carrierMotion.y;
    // One defender presses the ball; the rest retain the defensive block.
    const defenders = formation
      .filter((p) => p.team_id !== carrier.team_id && p.number !== 1)
      .sort(
        (a, b) =>
          distance(game.players.get(a.player_id)!, carrierMotion) -
          distance(game.players.get(b.player_id)!, carrierMotion),
      );
    if (defenders[0]) {
      const press = targets.get(defenders[0].player_id)!;
      press.x = carrierMotion.x + direction * 0.65;
      press.y = carrierMotion.y;
    }
  }
  if (
    game.receiver &&
    (game.phase === "windup" ||
      game.phase === "kick" ||
      game.phase === "pass" ||
      game.phase === "loose")
  ) {
    const t = targets.get(game.receiver)!;
    if (t) {
      t.x = game.to.x;
      t.y = game.to.y;
    }
  }
  // Kickers face their pass/shot target while planting their supporting foot.
  for (const p of formation) {
    const m = game.players.get(p.player_id)!;
    const look =
      (game.phase === "windup" || game.phase === "kick") &&
      p.player_id === game.owner
        ? game.to
        : game.ball;
    game.speeds.set(
      p.player_id,
      stepPlayer(m, targets.get(p.player_id)!, look, dt, true),
    );
  }
  if ((game.phase === "windup" || game.phase === "kick") && game.owner)
    game.ball = foot(game.players.get(game.owner)!, game.time);
  if (game.phase === "dribble" && game.owner) {
    const m = game.players.get(game.owner)!;
    game.ball = foot(m, game.time);
    game.highlight = game.owner;
    const p = formation.find((p) => p.player_id === game.owner)!;
    game.description = `${name(game.owner)} · dribbling`;
    const pressure = formation
      .filter((d) => d.team_id !== p.team_id && d.number !== 1)
      .find((d) => distance(game.players.get(d.player_id)!, m) < 1.05);
    if (pressure && p.number !== 1 && game.timer > 1.1) {
      // A tackle is a genuine close-range contact, never a remote ownership switch.
      game.phase = "loose";
      game.receiver = pressure.player_id;
      game.owner = null;
      game.to = { ...game.ball };
      game.timer = 0;
      game.stats.tackles++;
      game.description = `${name(pressure.player_id)} · challenge`;
    } else if (game.timer > 1.4 + (game.cycle % 3) * 0.3) {
      const advanced = (p.team_id === "home" ? m.x : 100 - m.x) > 73;
      const pass = choosePass(game, formation, p);
      game.shot = advanced && p.number !== 1 && Math.abs(m.y - 50) < 30;
      if (game.shot) {
        const keeper = formation.find(
          (k) => k.team_id !== p.team_id && k.number === 1,
        )!;
        game.receiver = keeper.player_id;
        game.to = { ...game.players.get(keeper.player_id)!, z: 0.3 };
        game.description = `${name(game.owner)} · preparing shot`;
      } else if (pass) {
        game.receiver = pass.player_id;
        game.to = { ...game.players.get(pass.player_id)!, z: 0 };
        game.description = `${name(game.owner)} → ${name(pass.player_id)}`;
      } else return;
      game.phase = "windup";
      game.timer = 0;
    }
  } else if (game.phase === "windup" && game.owner && game.timer > 0.34) {
    const m = game.players.get(game.owner)!;
    const heading = Math.atan2(
      (game.to.x - m.x) * 1.05,
      (game.to.y - m.y) * 0.68,
    );
    const turn = Math.atan2(
      Math.sin(heading - m.heading),
      Math.cos(heading - m.heading),
    );
    if (
      (Math.hypot(m.vx, m.vy) < 0.75 && Math.abs(turn) < 0.45) ||
      game.timer > 2.2
    ) {
      game.phase = "kick";
      game.timer = 0;
      game.kickId = game.owner;
      game.kickAge = 0;
    }
  } else if (game.phase === "kick" && game.owner && game.timer > 0.14) {
    game.kickId = game.owner;
    game.from = foot(game.players.get(game.owner)!);
    game.ball = { ...game.from };
    // Aim at the receiver's current feet after their supporting run, not an old coordinate.
    const receiver = game.players.get(game.receiver!)!;
    game.to = foot(receiver);
    const length = distance(game.from, game.to);
    game.travel = clamp(length / (game.shot ? 23 : 16), 0.45, 2.5);
    game.flight = 0;
    game.phase = game.shot ? "shot" : "pass";
    game.owner = null;
    game.timer = 0;
    if (game.shot) {
      game.stats.shots++;
      game.to.z = 0.6;
      game.description = `${name(game.kickId)} · shot on target`;
    } else {
      game.stats.passes++;
      game.description = `${name(game.kickId)} · pass to ${name(game.receiver!)}`;
    }
  } else if (game.phase === "pass" || game.phase === "shot") {
    game.flight += dt;
    const t = clamp(game.flight / game.travel, 0, 1);
    game.ball = {
      x: game.from.x + (game.to.x - game.from.x) * t,
      y: game.from.y + (game.to.y - game.from.y) * t,
      z: Math.sin(t * Math.PI) * (game.phase === "shot" ? 0.65 : 0.16),
    };
    game.highlight = game.receiver;
    if (game.phase === "pass" && t > 0.12 && t < 0.9 && game.kickId) {
      const team = game.kickId.startsWith("home") ? "home" : "away";
      const interceptor = formation.find(
        (p) =>
          p.team_id !== team &&
          p.number !== 1 &&
          distance(foot(game.players.get(p.player_id)!, game.time), game.ball) <
            0.65,
      );
      if (interceptor) {
        game.receiver = interceptor.player_id;
        game.phase = "loose";
        game.to = { ...game.ball };
        game.timer = 0;
        game.stats.tackles++;
        game.description = `${name(interceptor.player_id)} � interception`;
        return;
      }
    }
    if (t >= 1) {
      game.phase = "loose";
      game.timer = 0;
      game.description = game.shot
        ? "Goalkeeper moving to gather"
        : "Receiver moving to control";
    }
  } else if (game.phase === "loose" && game.receiver) {
    const m = game.players.get(game.receiver)!;
    const receiver = formation.find((p) => p.player_id === game.receiver)!;
    if (distance(foot(m, game.time), game.ball) < 0.6) {
      game.owner = game.receiver;
      game.highlight = game.owner;
      game.receiver = null;
      game.phase = "dribble";
      game.timer = 0;
      game.cycle++;
      game.ball = foot(m, game.time);
      game.stats.receives++;
      if (game.shot && receiver.number === 1) {
        game.stats.saves++;
        game.description = `${name(game.owner)} · save and gather`;
      } else game.description = `${name(game.owner)} · controls the ball`;
      game.shot = false;
    }
  }
}

export function kickAmount(game: FootballPlay, id: string) {
  return game.kickId === id && game.kickAge < 0.55
    ? Math.sin((Math.PI * game.kickAge) / 0.55)
    : 0;
}

/** Fixed-step clock synchronization keeps inline and detached views on the same play. */
export function advanceFootballTo(
  game: FootballPlay,
  seconds: number,
  budget = 240,
) {
  const target = clamp(seconds, 0, 90);
  let count = 0;
  while (game.time + 1 / 60 <= target + 1e-9 && count < budget) {
    stepFootballPlay(game, game.formation, 1 / 60, true);
    count++;
  }
  return count;
}
