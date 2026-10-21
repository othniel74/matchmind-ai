import * as T from "three";
import { loadAthleteAsset } from "../athleteAsset";

// Renders ground-truth tracking (backend/app/tracking.py) as broadcast video, one frame at a time.
// The camera is a main broadcast camera: fixed position behind the near touchline at halfway,
// panning to follow play. Its exact parameters are returned with every frame so the vision
// pipeline's own pitch calibration can be scored.

type Frame = { t: number; ball: [number, number, number]; players: Record<string, [number, number]> };
type Tracking = { fps: number; frames: Frame[]; teams: Record<string, string> };

const L = 105, W = 68;
export const CAMERA = { x: 52.5, y: 18, z: -30, fov: 30, tiltTargetY: 30 };  // pitch metres; z<0 is behind y=0
const WIDTH = 1280, HEIGHT = 720;

// Pitch metres -> scene: X along the length, Z across (y=0 near touchline at Z=+34), Y up.
const toScene = (x: number, y: number, z = 0) => new T.Vector3(x - L / 2, z, W / 2 - y);

function pitchTexture() {
  const s = 40;  // pixels per metre
  const margin = 6;
  const c = document.createElement("canvas");
  c.width = (L + 2 * margin) * s;
  c.height = (W + 2 * margin) * s;
  const g = c.getContext("2d")!;
  for (let i = 0; i < 20; i++) {  // mowing stripes
    g.fillStyle = i % 2 ? "#2f7a3b" : "#2a7035";
    g.fillRect((margin + (i * L) / 20) * s, 0, (L / 20) * s + 1, c.height);
  }
  g.fillStyle = "#24612e";
  g.fillRect(0, 0, margin * s, c.height);
  g.fillRect((margin + L) * s, 0, margin * s, c.height);
  g.strokeStyle = "#f4f7f0";
  g.lineWidth = 0.12 * s;
  const P = (x: number, y: number): [number, number] => [(margin + x) * s, (margin + (W - y)) * s];
  const line = (pts: [number, number][]) => { g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(...P(x, y)) : g.moveTo(...P(x, y)))); g.stroke(); };
  line([[0, 0], [L, 0], [L, W], [0, W], [0, 0]]);
  line([[L / 2, 0], [L / 2, W]]);
  for (const side of [0, 1]) {
    const x0 = side ? L : 0, d = side ? -1 : 1;
    line([[x0, W / 2 - 20.16], [x0 + d * 16.5, W / 2 - 20.16], [x0 + d * 16.5, W / 2 + 20.16], [x0, W / 2 + 20.16]]);
    line([[x0, W / 2 - 9.16], [x0 + d * 5.5, W / 2 - 9.16], [x0 + d * 5.5, W / 2 + 9.16], [x0, W / 2 + 9.16]]);
    g.beginPath(); g.arc(...P(x0 + d * 11, W / 2), 0.2 * s, 0, 2 * Math.PI); g.fillStyle = "#f4f7f0"; g.fill();
    const [cx, cy] = P(x0 + d * 11, W / 2);
    const a = Math.acos(5.5 / 9.15);
    g.beginPath();
    side ? g.arc(cx, cy, 9.15 * s, Math.PI - a, Math.PI + a) : g.arc(cx, cy, 9.15 * s, -a, a);
    g.stroke();
  }
  const [mx, my] = P(L / 2, W / 2);
  g.beginPath(); g.arc(mx, my, 9.15 * s, 0, 2 * Math.PI); g.stroke();
  g.beginPath(); g.arc(mx, my, 0.25 * s, 0, 2 * Math.PI); g.fill();
  const tex = new T.CanvasTexture(c);
  tex.colorSpace = T.SRGBColorSpace;
  tex.anisotropy = 8;
  return { tex, size: [L + 2 * margin, W + 2 * margin] as const };
}

async function setup() {
  const renderer = new T.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(WIDTH, HEIGHT);
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = T.SRGBColorSpace;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  document.body.appendChild(renderer.domElement);
  const scene = new T.Scene();
  scene.background = new T.Color("#1a2a1f");
  scene.add(new T.HemisphereLight(0xeef4ff, 0x2f4a35, 2.2));
  const sun = new T.DirectionalLight(0xfff3dd, 2.6);
  sun.position.set(-40, 80, 40);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -70, right: 70, top: 50, bottom: -50, far: 220 });
  scene.add(sun);
  const { tex, size } = pitchTexture();
  const grass = new T.Mesh(new T.PlaneGeometry(size[0], size[1]), new T.MeshStandardMaterial({ map: tex, roughness: 0.95 }));
  grass.rotation.x = -Math.PI / 2;
  grass.receiveShadow = true;
  scene.add(grass);
  const surround = new T.Mesh(new T.PlaneGeometry(400, 300), new T.MeshStandardMaterial({ color: "#1d3b25" }));
  surround.rotation.x = -Math.PI / 2;
  surround.position.y = -0.02;
  scene.add(surround);
  const white = new T.MeshStandardMaterial({ color: "#f5f5f5" });
  for (const x of [0, L]) {  // goals: 7.32 m x 2.44 m
    for (const y of [W / 2 - 3.66, W / 2 + 3.66]) {
      const post = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 2.44), white);
      post.position.copy(toScene(x, y, 1.22));
      scene.add(post);
    }
    const bar = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 7.32), white);
    bar.rotation.x = Math.PI / 2;
    bar.position.copy(toScene(x, W / 2, 2.44));
    scene.add(bar);
    const net = new T.Mesh(new T.BoxGeometry(2, 2.44, 7.32), new T.MeshStandardMaterial({ color: "#dddddd", transparent: true, opacity: 0.25 }));
    net.position.copy(toScene(x + (x ? 1 : -1), W / 2, 1.22));
    scene.add(net);
  }
  const ball = new T.Mesh(new T.SphereGeometry(0.16, 20, 14), new T.MeshStandardMaterial({ color: "#ffffff", roughness: 0.4 }));
  ball.castShadow = true;
  scene.add(ball);
  const camera = new T.PerspectiveCamera(CAMERA.fov, WIDTH / HEIGHT, 0.5, 400);
  camera.position.copy(toScene(CAMERA.x, CAMERA.z, CAMERA.y));
  const asset = await loadAthleteAsset(new AbortController().signal);
  return { renderer, scene, camera, ball, asset };
}

const ready = setup();

declare global {
  interface Window {
    matchmindRender: {
      load: (tracking: Tracking) => Promise<number>;
      frame: (i: number) => Promise<{ dataUrl: string; camera: { position: number[]; target: number[]; fov: number; width: number; height: number } }>;
    };
  }
}

let tracking: Tracking | null = null;
const athletes = new Map<string, { object: T.Object3D; update: (dt: number, speed: number, reduced: boolean) => void; last?: [number, number] }>();
let panX = L / 2;

window.matchmindRender = {
  async load(data) {
    const { scene, asset } = await ready;
    tracking = data;
    athletes.forEach((a) => scene.remove(a.object));
    athletes.clear();
    const ids = new Set(data.frames.flatMap((f) => Object.keys(f.players)));
    for (const id of ids) {
      const team = data.teams[id] ?? (id.startsWith("home") ? "home" : "away");
      const number = Number(id.split("-")[1]) || 1;
      const made = asset!.instantiate(team, number === 1, number);
      const box = new T.Box3().setFromObject(made.object);
      made.object.scale.multiplyScalar(1.82 / Math.max(box.max.y - box.min.y, 0.01));
      made.object.traverse((o) => { if ((o as T.Mesh).isMesh) o.castShadow = true; });
      scene.add(made.object);
      athletes.set(id, { object: made.object, update: made.update });
    }
    panX = data.frames[0]?.ball[0] ?? L / 2;
    return data.frames.length;
  },
  async frame(i) {
    const { renderer, scene, camera, ball } = await ready;
    const f = tracking!.frames[i];
    const dt = 1 / tracking!.fps;
    for (const [id, a] of athletes) {
      const p = f.players[id];
      a.object.visible = !!p;
      if (!p) continue;
      const pos = toScene(p[0], p[1]);
      const speed = a.last ? Math.hypot(p[0] - a.last[0], p[1] - a.last[1]) / dt : 0;
      if (a.last && speed > 0.3) a.object.rotation.y = Math.atan2(p[0] - a.last[0], -(p[1] - a.last[1]));
      a.object.position.copy(pos);
      a.update(dt, speed, false);
      a.last = [p[0], p[1]];
    }
    ball.position.copy(toScene(f.ball[0], f.ball[1], 0.16 + f.ball[2]));
    // Pan smoothly to follow the ball, as a camera operator would; tilt fixed on the pitch.
    panX += (Math.min(Math.max(f.ball[0], 22), L - 22) - panX) * 0.06;
    const target = toScene(panX, CAMERA.tiltTargetY, 0);
    camera.lookAt(target);
    camera.updateMatrixWorld();
    renderer.render(scene, camera);
    return {
      dataUrl: renderer.domElement.toDataURL("image/jpeg", 0.92),
      camera: { position: [CAMERA.x, CAMERA.z, CAMERA.y], target: [panX, CAMERA.tiltTargetY, 0], fov: CAMERA.fov,
                width: WIDTH, height: HEIGHT },
    };
  },
};
