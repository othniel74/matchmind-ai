export type Motion = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  heading: number;
};
type Player = { x: number; y: number; team_id: string; number: number };
const clamp = (n: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, n));

/** Field metres, bounded acceleration and turn rate; independent of viewport size. */
export function stepPlayer(
  motion: Motion,
  target: Player,
  ball: { x: number; y: number },
  dt: number,
  moving: boolean,
  reduced = false,
) {
  dt = clamp(dt, 0, 0.05);
  const keeper = target.number === 1;
  const home = target.team_id === "home";
  const maxSpeed = keeper ? 2.8 : 5.5;
  const acceleration = keeper ? 4 : 5.5;
  const dx = (target.x - motion.x) * 1.05;
  const dy = (target.y - motion.y) * 0.68;
  const distance = Math.hypot(dx, dy);
  const desiredSpeed = moving ? Math.min(maxSpeed, distance * 1.5) : 0;
  const desiredX = distance > 0.01 ? (dx / distance) * desiredSpeed : 0;
  const desiredY = distance > 0.01 ? (dy / distance) * desiredSpeed : 0;
  const changeX = desiredX - motion.vx,
    changeY = desiredY - motion.vy;
  const change = Math.hypot(changeX, changeY);
  const factor = change ? Math.min(1, (acceleration * dt) / change) : 0;
  motion.vx += changeX * factor;
  motion.vy += changeY * factor;
  if (reduced) {
    motion.x = target.x;
    motion.y = target.y;
    motion.vx = motion.vy = 0;
  } else {
    motion.x += (motion.vx * dt) / 1.05;
    motion.y += (motion.vy * dt) / 0.68;
  }
  if (keeper) {
    const x = clamp(motion.x, home ? 3 : 88, home ? 12 : 97);
    const y = clamp(motion.y, 32, 68);
    if (x !== motion.x) motion.vx = 0;
    if (y !== motion.y) motion.vy = 0;
    motion.x = x;
    motion.y = y;
  }
  const speed = Math.hypot(motion.vx, motion.vy);
  // Keepers face the field even while retreating or shuffling sideways.
  const lookX = keeper
    ? home
      ? Math.max(20, ball.x)
      : Math.min(80, ball.x)
    : ball.x;
  const lookY = ball.y;
  const heading =
    !keeper && speed > 0.22
      ? Math.atan2(motion.vx, motion.vy)
      : Math.atan2((lookX - motion.x) * 1.05, (lookY - motion.y) * 0.68);
  const turn = Math.atan2(
    Math.sin(heading - motion.heading),
    Math.cos(heading - motion.heading),
  );
  motion.heading += reduced ? turn : clamp(turn, -2.4 * dt, 2.4 * dt);
  // A keeper must never rotate through a backwards-facing stance.
  if (keeper && Math.sin(motion.heading) * (home ? 1 : -1) <= 0) {
    motion.heading = home ? Math.PI / 2 : -Math.PI / 2;
  }
  return reduced ? 0 : speed;
}
