import { useEffect, useRef, useState } from "react";
import type * as Three from "three";
import type { ImportedAthlete } from "./athleteAsset";
import type { Motion } from "./pitchMotion";
import {ballDisplay} from "./ballDisplay";
import {
  createFootballPlay,
  stepFootballPlay,
  kickAmount,
  advanceFootballTo,
} from "./footballPlay";

type Player = {
  player_id: string;
  team_id: string;
  number: number;
  x: number;
  y: number;
  active: boolean;
  goalkeeper?: boolean;
  on_pitch?: boolean;
  vx?: number; vy?: number; heading?: number;
};
// Sent-off players leave the illustrative play; their slot stays in the payload.
const onPitch = (players: Player[]) => players.filter((p) => p.on_pitch !== false);
type Pitch = {
  players: Player[];
  ball: { x: number; y: number };
  minute?: number;
  tracking?: boolean;
  ballVisible?: boolean;
  ballHeight?: number;
};
type Athlete = {
  root: Three.Group;
  body: Three.Group;
  legs: Three.Group[];
  knees: Three.Group[];
  arms: Three.Group[];
  ring: Three.Mesh;
  target: Three.Vector3;
  phase: number;
  motion: Motion;
};

/** Locally hosted footballers with a procedural fallback and illustrative gameplay. */
export default function HumanPlayers({
  pitch,
  moving,
  onReady,
  onPlayStatus,
}: {
  pitch: Pitch;
  moving: boolean;
  onReady: (ready: boolean) => void;
  onPlayStatus?: (status: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const current = useRef({ pitch, moving });
  current.current = { pitch, moving };
  const [detail, setDetail] = useState(false);
  const [portrait, setPortrait] = useState(false);
  const portraitRef = useRef(portrait);
  portraitRef.current = portrait;
  const [textured, setTextured] = useState(false);
  const detailRef = useRef(detail);
  detailRef.current = detail;
  const readyCallback = useRef(onReady);
  readyCallback.current = onReady;
  const statusCallback = useRef(onPlayStatus);
  statusCallback.current = onPlayStatus;

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    import("three")
      .then((T) => {
        if (disposed || !host.current) return;
        const container = host.current;
        let renderer: Three.WebGLRenderer;
        try {
          renderer = new T.WebGLRenderer({
            alpha: true,
            antialias: true,
            powerPreference: "low-power",
          });
        } catch {
          return;
        }
        renderer.setClearColor(0x000000, 0);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = T.PCFShadowMap;
        renderer.outputColorSpace = T.SRGBColorSpace;
        renderer.toneMapping = T.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1;
        renderer.domElement.setAttribute("aria-hidden", "true");
        container.prepend(renderer.domElement);
        const ballMarker =
          container.querySelector<HTMLElement>(".ball-tracker");
        const scene = new T.Scene();
        const camera = new T.OrthographicCamera(-50, 50, 30, -30, 0.1, 400);
        camera.position.set(0, 100, 140);
        camera.lookAt(0, 0, 0);
        const projection = 100 / Math.hypot(100, 140);
        scene.add(new T.HemisphereLight(0xe8f1ff, 0x385642, 2.4));
        const key = new T.DirectionalLight(0xfff4df, 3.2);
        key.position.set(-35, 65, 35);
        key.castShadow = true;
        key.shadow.mapSize.set(1024, 1024);
        Object.assign(key.shadow.camera, {
          left: -65,
          right: 65,
          top: 80,
          bottom: -80,
          far: 180,
        });
        key.shadow.normalBias = 0.04;
        key.shadow.bias = -0.00015;
        scene.add(key);
        const rim = new T.DirectionalLight(0xb3d7ff, 1.6);
        rim.position.set(30, 25, -30);
        scene.add(rim);
        const ground = new T.Mesh(
          new T.PlaneGeometry(220, 240),
          new T.ShadowMaterial({ opacity: 0.28 }),
        );
        ground.rotation.x = -Math.PI / 2;
        ground.receiveShadow = true;
        scene.add(ground);
        const sphere = new T.SphereGeometry(1, 16, 12);
        const resources: Three.Texture[] = [];
        const material = (color: string, roughness = 0.8) =>
          new T.MeshStandardMaterial({ color, roughness });
        const boot = material("#182225", 0.5);
        const white = material("#e7edf0");
        const eye = material("#251e1a");
        const athletes = new Map<string, Athlete>();
        const imported = new Map<string, ImportedAthlete>();
        let disposeAsset = () => {};
        const put = (
          parent: Three.Object3D,
          geometry: Three.BufferGeometry,
          mat: Three.Material,
          x: number,
          y: number,
          z: number,
          sx = 1,
          sy = 1,
          sz = 1,
        ) => {
          const mesh = new T.Mesh(geometry, mat);
          mesh.position.set(x, y, z);
          mesh.scale.set(sx, sy, sz);
          mesh.castShadow = true;
          parent.add(mesh);
          return mesh;
        };
        const ellipsoid = (
          parent: Three.Object3D,
          mat: Three.Material,
          x: number,
          y: number,
          z: number,
          sx: number,
          sy: number,
          sz: number,
        ) => put(parent, sphere, mat, x, y, z, sx, sy, sz);
        const segment = (
          parent: Three.Object3D,
          mat: Three.Material,
          top: number,
          bottom: number,
          length: number,
          x = 0,
          y = 0,
          z = 0,
        ) =>
          put(
            parent,
            new T.CylinderGeometry(top, bottom, length, 12),
            mat,
            x,
            y - length / 2,
            z,
          );
        function makeAthlete(p: Player): Athlete {
          const root = new T.Group();
          scene.add(root);
          const body = new T.Group();
          root.add(body);
          const home = p.team_id === "home";
          const keeper = (p.goalkeeper ?? p.number === 1);
          const skin = material(
            ["#c18e6b", "#704a34", "#d4a381", "#956447"][p.number % 4],
            0.68,
          );
          const hair = material(p.number % 5 === 0 ? "#69482d" : "#24201e");
          const jersey = material(
            keeper
              ? home
                ? "#d8bf54"
                : "#a688c2"
              : home
                ? "#eaece2"
                : "#71b1dc",
          );
          const shorts = material(
            keeper
              ? home
                ? "#68602f"
                : "#4a3b61"
              : home
                ? "#1e2d39"
                : "#ebedf0",
          );
          const socks = keeper ? jersey : home ? white : jersey;
          // Shoulder, chest and waist contours form an athletic torso.
          const profile = [
            [0.19, 0.99],
            [0.23, 1.05],
            [0.235, 1.25],
            [0.29, 1.46],
            [0.26, 1.53],
            [0.13, 1.57],
          ];
          put(
            body,
            new T.LatheGeometry(
              profile.map(([r, y]) => new T.Vector2(r, y)),
              20,
            ),
            jersey,
            0,
            0,
            0,
            1,
            1,
            0.62,
          );
          ellipsoid(body, shorts, 0, 1.01, 0, 0.245, 0.17, 0.17);
          const neck = segment(body, skin, 0.075, 0.085, 0.13, 0, 1.68, 0);
          neck.castShadow = false;
          ellipsoid(body, skin, 0, 1.79, 0.015, 0.122, 0.16, 0.115);
          ellipsoid(body, skin, 0, 1.735, 0.057, 0.09, 0.085, 0.085);
          ellipsoid(body, skin, 0, 1.79, 0.122, 0.027, 0.036, 0.033);
          for (const side of [-1, 1]) {
            ellipsoid(
              body,
              skin,
              side * 0.12,
              1.79,
              0.006,
              0.025,
              0.046,
              0.027,
            );
            ellipsoid(
              body,
              eye,
              side * 0.044,
              1.815,
              0.119,
              0.012,
              0.009,
              0.007,
            );
          }
          const hairCap = put(
            body,
            new T.SphereGeometry(
              0.126,
              16,
              12,
              0,
              Math.PI * 2,
              0,
              Math.PI * 0.55,
            ),
            hair,
            0,
            1.81,
            0.005,
            1,
            1.04,
            0.96,
          );
          hairCap.rotation.x = -0.12;
          if (p.number % 3 === 0)
            ellipsoid(body, hair, -0.025, 1.92, 0.015, 0.115, 0.045, 0.095);
          if (p.number % 4 === 0)
            ellipsoid(body, hair, 0, 1.705, 0.064, 0.075, 0.029, 0.065);
          const legs: Three.Group[] = [],
            knees: Three.Group[] = [],
            arms: Three.Group[] = [];
          for (const side of [-1, 1]) {
            const hip = new T.Group();
            hip.position.set(side * 0.125, 1.01, 0);
            body.add(hip);
            legs.push(hip);
            segment(hip, shorts, 0.135, 0.12, 0.22);
            segment(hip, skin, 0.103, 0.075, 0.24, 0, -0.19);
            const knee = new T.Group();
            knee.position.y = -0.43;
            hip.add(knee);
            knees.push(knee);
            ellipsoid(knee, skin, 0, 0, 0, 0.078, 0.079, 0.077);
            segment(knee, skin, 0.07, 0.055, 0.14);
            segment(knee, socks, 0.074, 0.044, 0.32, 0, -0.1);
            ellipsoid(knee, boot, 0, -0.415, 0.055, 0.071, 0.065, 0.145);
            ellipsoid(knee, white, 0, -0.46, 0.06, 0.073, 0.018, 0.145);
            const arm = new T.Group();
            arm.position.set(side * 0.275, 1.46, 0);
            arm.rotation.z = side * 0.17;
            body.add(arm);
            arms.push(arm);
            ellipsoid(arm, jersey, 0, -0.045, 0, 0.105, 0.13, 0.11);
            segment(arm, skin, 0.074, 0.055, 0.24, 0, -0.12);
            const elbow = new T.Group();
            elbow.position.y = -0.35;
            elbow.rotation.x = -0.35;
            arm.add(elbow);
            ellipsoid(elbow, skin, 0, 0, 0, 0.055, 0.055, 0.055);
            segment(elbow, skin, 0.054, 0.034, 0.25);
            ellipsoid(
              elbow,
              keeper ? white : skin,
              0,
              -0.28,
              0,
              0.045,
              0.075,
              0.034,
            );
          }
          // Small front and back shirt numbers remain readable in the wide view.
          const label = document.createElement("canvas");
          label.width = 128;
          label.height = 128;
          const ctx = label.getContext("2d")!;
          ctx.fillStyle = home ? "#152536" : "#19364e";
          ctx.font = "bold 98px Arial";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(p.number), 64, 68);
          const texture = new T.CanvasTexture(label);
          texture.colorSpace = T.SRGBColorSpace;
          resources.push(texture);
          const numberMat = new T.MeshStandardMaterial({
            map: texture,
            transparent: true,
            roughness: 0.9,
            depthWrite: false,
          });
          put(body, new T.PlaneGeometry(0.26, 0.27), numberMat, 0, 1.29, 0.173);
          const back = put(
            body,
            new T.PlaneGeometry(0.28, 0.3),
            numberMat,
            0,
            1.3,
            -0.173,
          );
          back.rotation.y = Math.PI;
          const ring = new T.Mesh(
            new T.RingGeometry(0.35, 0.4, 32),
            new T.MeshBasicMaterial({
              color: 0xc6ef82,
              transparent: true,
              opacity: 0.8,
              side: T.DoubleSide,
            }),
          );
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = 0.012;
          root.add(ring);
          root.rotation.y = home ? Math.PI / 2 : -Math.PI / 2;
          return {
            root,
            body,
            legs,
            knees,
            arms,
            ring,
            target: new T.Vector3(),
            phase: p.number * 1.7,
            motion: { x: p.x, y: p.y, vx: 0, vy: 0, heading: root.rotation.y },
          };
        }
        for (const p of current.current.pitch.players)
          athletes.set(p.player_id, makeAthlete(p));
        let game = createFootballPlay(onPitch(current.current.pitch.players));
        let lastDescription = "";
        let clockMinute = current.current.pitch.minute ?? 0,
          clockAt = performance.now();
        const ball = new T.Group();
        scene.add(ball);
        put(
          ball,
          new T.SphereGeometry(0.135, 20, 16),
          new T.MeshStandardMaterial({
            color: 0xfff7bd,
            emissive: 0x5b531e,
            roughness: 0.45,
          }),
          0,
          0.135,
          0,
        );
        const patchMat = material("#223128");
        for (const [x, y, z] of [
          [0, 0.135, 0.129],
          [0.12, 0.135, 0],
          [-0.12, 0.135, 0],
          [0, 0.26, 0],
          [0, 0.135, -0.129],
        ])
          ellipsoid(ball, patchMat, x, y, z, 0.055, 0.05, 0.025);
        ball.children.forEach((child) => (child.position.y -= 0.135));
        const ballHalo = new T.Mesh(
          new T.RingGeometry(0.46, 0.53, 40),
          new T.MeshBasicMaterial({
            color: 0xf9ffc7,
            transparent: true,
            opacity: 0.7,
            side: T.DoubleSide,
            depthWrite: false,
          }),
        );
        ballHalo.rotation.x = -Math.PI / 2;
        ballHalo.position.y = 0.018;
        scene.add(ballHalo);
        const contactShadow = new T.Mesh(new T.CircleGeometry(0.29,32),new T.MeshBasicMaterial({color:0x071510,transparent:true,opacity:0.5,depthWrite:false}));
        contactShadow.position.z=0.002;
        ballHalo.add(contactShadow);
        const goalGroups: Three.Group[] = [];
        for (const sign of [-1, 1]) {
          const goal = new T.Group();
          goal.position.x = sign * 47.8;
          scene.add(goal);
          goalGroups.push(goal);
          for (const z of [-3.6, 3.6])
            put(
              goal,
              new T.CylinderGeometry(0.1, 0.1, 2.45, 10),
              white,
              0,
              1.225,
              z,
            );
          const bar = put(
            goal,
            new T.CylinderGeometry(0.1, 0.1, 7.2, 10),
            white,
            0,
            2.45,
            0,
          );
          bar.rotation.x = Math.PI / 2;
          const netPoints: number[] = [];
          for (let i = 0; i <= 12; i++) {
            const z = -3.6 + i * 0.6;
            netPoints.push(sign * 1.2, 0, z, sign * 1.2, 2.45, z);
          }
          for (let i = 0; i <= 5; i++) {
            const y = i * 0.49;
            netPoints.push(sign * 1.2, y, -3.6, sign * 1.2, y, 3.6);
          }
          for (const z of [-3.6, 3.6])
            netPoints.push(
              0,
              2.45,
              z,
              sign * 1.2,
              2.45,
              z,
              0,
              0,
              z,
              sign * 1.2,
              0,
              z,
            );
          const net = new T.LineSegments(
            new T.BufferGeometry().setAttribute(
              "position",
              new T.Float32BufferAttribute(netPoints, 3),
            ),
            new T.LineBasicMaterial({
              color: 0xc3d1c6,
              transparent: true,
              opacity: 0.32,
            }),
          );
          goal.add(net);
        }
        const passTrail = new T.Line(
          new T.BufferGeometry().setAttribute(
            "position",
            new T.Float32BufferAttribute(new Float32Array(6), 3),
          ),
          new T.LineBasicMaterial({
            color: 0xd9f6a8,
            transparent: true,
            opacity: 0.4,
          }),
        );
        scene.add(passTrail);
        const detailCamera = new T.PerspectiveCamera(30, 1, 0.1, 30);
        let width = 1,
          height = 1,
          depth = 68,
          settleUntil = performance.now() + 1000;
        const resize = () => {
          width = container.clientWidth;
          height = container.clientHeight;
          if (!width || !height) return;
          const h = (100 * height) / width;
          depth = h / projection;
          camera.left = -50;
          camera.right = 50;
          camera.top = h / 2;
          camera.bottom = -h / 2;
          camera.updateProjectionMatrix();
          camera.updateMatrixWorld();
          renderer.setSize(width, height, false);
          goalGroups.forEach((g) => (g.scale.z = depth / 68));
          settleUntil = performance.now() + 1000;
        };
        const observer = new ResizeObserver(resize);
        observer.observe(container);
        resize();
        const point = (x: number, y: number) =>
          new T.Vector3(x - 50, 0, (y / 100 - 0.5) * depth);
        for (const p of current.current.pitch.players)
          athletes.get(p.player_id)!.root.position.copy(point(p.x, p.y));
        ball.position.copy(point(game.ball.x, game.ball.y));
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
        let previous = performance.now(),
          elapsed = 0,
          frame = 0,
          lastDraw = 0,
          contextLost = false;
        let lastPitch = current.current.pitch,
          lastDetail = detailRef.current,
          lastPortrait = portraitRef.current;
        const onLost = (event: Event) => {
          event.preventDefault();
          contextLost = true;
          readyCallback.current(false);
        };
        renderer.domElement.addEventListener("webglcontextlost", onLost);
        const onRestored = () => {
          contextLost = false;
          settleUntil = performance.now() + 1000;
          readyCallback.current(true);
        };
        renderer.domElement.addEventListener(
          "webglcontextrestored",
          onRestored,
        );
        const tick = (now: number) => {
          frame = requestAnimationFrame(tick);
          if (document.hidden || contextLost || now - lastDraw < 32) return;
          const dt = Math.min((now - previous) / 1000, 0.05);
          previous = now;
          lastDraw = now;
          const state = current.current;
          if (state.pitch !== lastPitch) {
            const next = state.pitch.minute ?? 0;
            const live = onPitch(state.pitch.players);
            if (
              next < clockMinute ||
              (!state.pitch.tracking && live.length !== game.formation.length)
            )
              game = createFootballPlay(live);
            clockMinute = next;
            clockAt = now;
          }
          if (
            state.pitch !== lastPitch ||
            detailRef.current !== lastDetail ||
            portraitRef.current !== lastPortrait
          ) {
            settleUntil = now + (state.moving ? 1000 : 3500);
            lastPitch = state.pitch;
            ((lastDetail = detailRef.current),
              (lastPortrait = portraitRef.current));
          }
          if ((!state.moving || reduced.matches) && now > settleUntil) return;
          const playTime =
            Math.max(0, clockMinute - 1) +
            (state.moving && !reduced.matches
              ? Math.min((now - clockAt) / 1000, 1)
              : 0);
          const previousPlayTime = game.time;
          if (state.pitch.tracking) {
            for (const p of state.pitch.players) {
              game.players.set(p.player_id, {x:p.x,y:p.y,vx:p.vx??0,vy:p.vy??0,heading:p.heading??0});
              game.speeds.set(p.player_id, state.moving ? Math.hypot(p.vx??0,p.vy??0) : 0);
            }
            game.ball = {...state.pitch.ball,z:state.pitch.ballHeight??0};
            game.highlight = state.pitch.players.find(p=>p.active)?.player_id ?? '';
            game.phase = 'dribble'; game.description = 'Recorded tracking · generic player models';
            ball.visible = ballHalo.visible = state.pitch.ballVisible !== false;
            if(ballMarker) ballMarker.style.visibility = ball.visible ? 'visible' : 'hidden';
          } else advanceFootballTo(game, playTime);
          const animationDt = Math.min(
            0.25,
            Math.max(dt, game.time - previousPlayTime),
          );
          if (state.moving && !reduced.matches) elapsed += animationDt;
          if (!state.moving && !state.pitch.tracking)
            stepFootballPlay(
              game,
              state.pitch.players,
              dt,
              false,
              reduced.matches,
            );
          if (game.description !== lastDescription) {
            lastDescription = game.description;
            statusCallback.current?.(game.description);
          }
          container.dataset.playPhase = game.phase;
          container.dataset.ballOwner = game.owner ?? "in-flight";
          if (state.pitch.tracking) {
            const visibleIds = new Set(state.pitch.players.map(p=>p.player_id));
            for(const [id,a] of athletes) a.root.visible = visibleIds.has(id);
          }
          let selected: Athlete | undefined;
          for (const p of state.pitch.players) {
            const a = athletes.get(p.player_id);
            if (!a) continue;
            if (p.on_pitch === false) {
              a.root.visible = false;
              continue;
            }
            if (!state.pitch.tracking) a.root.visible = true;
            a.motion = game.players.get(p.player_id)!;
            const speed = game.speeds.get(p.player_id) ?? 0;
            const kick = kickAmount(game, p.player_id);
            const stride = Math.min(speed / 5.5, 1) * 0.65;
            a.root.position.copy(point(a.motion.x, a.motion.y));
            a.root.rotation.y = a.motion.heading;
            // Preserve leg clearance and avoid enlarging athletes on narrow pitches.
            a.root.scale.setScalar(
              Math.min(
                5,
                Math.max(
                  1.5,
                  Math.min(64, Math.max(24, width * 0.035)) /
                    ((1.55 * width) / 100),
                ),
              ),
            );
            a.body.position.y =
              stride * Math.abs(Math.sin(elapsed * 9 + a.phase)) * 0.07;
            for (let i = 0; i < 2; i++) {
              const swing = Math.sin(elapsed * 9 + a.phase + i * Math.PI);
              a.legs[i].rotation.x = swing * stride;
              a.knees[i].rotation.x = Math.max(0, -swing) * stride * 0.9;
              a.arms[i].rotation.x = -swing * stride * 0.65 - 0.1;
            }
            a.legs[1].rotation.x -= kick * 0.8;
            imported
              .get(p.player_id)
              ?.update(
                animationDt,
                Math.min(speed / 4.5, 1),
                reduced.matches,
                kick,
              );

            a.ring.visible = p.player_id === game.highlight;
            if (p.player_id === game.highlight) selected = a;
          }
          const display=ballDisplay(width,game.ball.z,!!state.pitch.tracking);
          const ballSize=display.scale;
          const targetBall = point(game.ball.x, game.ball.y);
          targetBall.y = display.center;
          const travel = ball.position.distanceTo(targetBall);
          ball.position.copy(targetBall);
          ball.scale.setScalar(ballSize);
          ballHalo.position.copy(point(game.ball.x, game.ball.y));
          ballHalo.position.y = 0.018;
          ballHalo.scale.setScalar(state.pitch.tracking ? ballSize/1.8 : Math.max(1,1200/Math.max(width,1)));
          contactShadow.material.opacity=0.5/(1+display.clearance*0.8);
          if (!reduced.matches)
            ball.rotation.z -= travel / Math.max(0.135 * ballSize, 0.1);
          if (ballMarker) {
            const screen = ball.position.clone().project(camera);
            ballMarker.style.left = `${(screen.x * 0.5 + 0.5) * width}px`;
            ballMarker.style.top = `${(-screen.y * 0.5 + 0.5) * height}px`;
          }
          passTrail.visible = game.phase === "pass" || game.phase === "shot";
          const tail = point(game.from.x, game.from.y);
          tail.y = 0.06;
          const points = passTrail.geometry.attributes.position;
          points.setXYZ(0, tail.x, tail.y, tail.z);
          points.setXYZ(
            1,
            targetBall.x,
            Math.max(0.06, targetBall.y),
            targetBall.z,
          );
          points.needsUpdate = true;
          passTrail.geometry.computeBoundingSphere();
          renderer.setScissorTest(false);
          renderer.setViewport(0, 0, width, height);
          renderer.render(scene, camera);
          if (detailRef.current && selected && width > 240) {
            const size = Math.min(300, width * 0.4),
              left = width - size - 14;
            const bottom =
              window.innerWidth <= 600 ? Math.max(44, height - 130 - size) : 44;
            const center = selected.root.position.clone();
            const angle = selected.root.rotation.y;
            const scale = selected.root.scale.x;
            const face = portraitRef.current;
            const distance = face ? 1.7 : 4.9;
            detailCamera.position
              .copy(center)
              .add(
                new T.Vector3(
                  Math.sin(angle + 0.2) * distance * scale,
                  (face ? 1.76 : 2.5) * scale,
                  Math.cos(angle + 0.2) * distance * scale,
                ),
              );
            detailCamera.lookAt(
              center.x,
              (face ? 1.62 : 1.05) * scale,
              center.z,
            );
            renderer.setScissorTest(true);
            renderer.setScissor(left, bottom, size, size);
            renderer.setViewport(left, bottom, size, size);
            renderer.setClearColor(0x10221e, 0.96);
            renderer.clear();
            // Isolate the selected athlete for a readable human detail view.
            for (const a of athletes.values()) a.root.visible = a === selected;
            ball.visible = false;
            ballHalo.visible = false;
            passTrail.visible = false;
            goalGroups.forEach((g) => (g.visible = false));
            ground.visible = false;
            renderer.render(scene, detailCamera);
            for (const [id,a] of athletes) {
              const p = state.pitch.players.find((p) => p.player_id === id);
              a.root.visible = p ? p.on_pitch !== false : !state.pitch.tracking;
            }
            ball.visible = true;
            ballHalo.visible = true;
            goalGroups.forEach((g) => (g.visible = true));
            ground.visible = true;
            renderer.setClearColor(0x000000, 0);
            renderer.setScissorTest(false);
          }
        };
        tick(performance.now());
        readyCallback.current(true);
        const assetAbort = new AbortController();
        import("./athleteAsset")
          .then(({ loadAthleteAsset }) => loadAthleteAsset(assetAbort.signal))
          .then((asset) => {
            if (!asset) return;
            if (disposed) {
              asset.dispose();
              return;
            }
            disposeAsset = asset.dispose;
            for (const p of current.current.pitch.players) {
              const athlete = athletes.get(p.player_id);
              if (!athlete) continue;
              const instance = asset.instantiate(
                p.team_id,
                (p.goalkeeper ?? p.number === 1),
                p.number,
              );
              imported.set(p.player_id, instance);
              athlete.root.add(instance.object);
              athlete.body.visible = false;
            }
            setTextured(true);
            settleUntil = performance.now() + 1000;
          })
          .catch((error) => {
            if (!disposed && !assetAbort.signal.aborted)
              console.warn(
                "Detailed player model unavailable; using local figures.",
                error,
              );
          });
        cleanup = () => {
          cancelAnimationFrame(frame);
          observer.disconnect();
          assetAbort.abort();
          imported.forEach((a) => a.dispose());
          disposeAsset();
          renderer.domElement.removeEventListener("webglcontextlost", onLost);
          renderer.domElement.removeEventListener(
            "webglcontextrestored",
            onRestored,
          );
          const geometries = new Set<Three.BufferGeometry>(),
            materials = new Set<Three.Material>();
          scene.traverse((obj) => {
            if (obj instanceof T.Mesh || obj instanceof T.Line) {
              geometries.add(obj.geometry);
              (Array.isArray(obj.material)
                ? obj.material
                : [obj.material]
              ).forEach((m) => materials.add(m));
            }
          });
          geometries.forEach((g) => g.dispose());
          materials.forEach((m) => m.dispose());
          resources.forEach((t) => t.dispose());
          key.shadow.dispose();
          renderer.dispose();
          renderer.domElement.remove();
        };
      })
      .catch(() => readyCallback.current(false));
    return () => {
      disposed = true;
      cleanup();
    };
  }, []);
  return (
    <div
      className="human-player-scene"
      ref={host}
      data-renderer={textured ? "textured-rig" : "procedural"}
    >
      <span className="ball-tracker" aria-hidden="true">
        BALL
      </span>
      <button
        type="button"
        className="human-detail-toggle"
        aria-pressed={detail}
        onClick={() => setDetail((v) => !v)}
      >
        {detail ? "Close player detail" : "Player detail"}
      </button>
      {detail && (
        <button
          type="button"
          className="human-portrait-toggle"
          aria-pressed={portrait}
          onClick={() => setPortrait((v) => !v)}
        >
          {portrait ? "Full body" : "Face close-up"}
        </button>
      )}
      {detail && (
        <span className="human-detail-label">
          {textured ? "TEXTURED PLAYER" : "ACTIVE PLAYER"} · 3D SIMULATION
        </span>
      )}
    </div>
  );
}
