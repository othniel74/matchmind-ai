import { useEffect, useRef, useState } from "react";
import { ScanEye } from "lucide-react";
import "./vision.css";

// Auto-eventing from video: MatchMind renders a synthetic match as broadcast video, a vision
// pipeline recovers players, ball and events from the pixels, and every number is scored against
// the renderer's ground truth. Static artefacts from backend/vision (run offline on CPU).

type OverlayFrame = { t: number; p: [number, number, number, number, string, string, number, number][];
                      b: [number, number] | null; g: [number, number, string][]; gb: [number, number] };
type Overlay = { fps: number; frames: OverlayFrame[] };
type Recovered = { t: number; clock: string; type: string; outcome: string; team: string; player: string;
                   recipient: string | null; speed_kmh: number | null; matched: boolean; truth_speed_kmh: number | null };
type Events = { recovered: Recovered[]; truth_count: number; validated: number };
type Report = {
  calibration_ground_error_m: { median: number }; player_detection_recall: number;
  player_position_error_m: { median: number }; team_accuracy: number; identity_accuracy: number;
  ball_detection_rate: number; ball_position_error_m: number;
  events: { precision: number; recall: number; f1: number; true: number; matched: number; ball_speed_error_kmh: number | null;
            goals: { true: number; found: number } };
  top_speed_error_kmh: number | null; processing: { per_frame_s: number; stride: number };
};

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const metres = (v: number | null | undefined) => (v == null ? "—" : v < 1 ? `${Math.round(v * 100)} cm` : `${v.toFixed(1)} m`);

export function VisionPanel() {
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [events, setEvents] = useState<Events | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [now, setNow] = useState(0);
  const [azure, setAzure] = useState<{ available: boolean; notice: string }>({ available: false, notice: "" });
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const minimap = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const get = (f: string) => fetch(`/vision/${f}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([get("overlay.json"), get("events.json"), get("report.json")]).then(([o, e, r]) => {
      setOverlay(o); setEvents(e); setReport(r);
    });
    fetch("/api/feed").then((r) => (r.ok ? r.json() : null))
      .then((f) => setAzure((a) => ({ ...a, available: !!f?.vision_available }))).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!overlay) return;
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const v = video.current, c = canvas.current, m = minimap.current;
      if (!v || !c || !m) return;
      const t = v.currentTime;
      setNow(t);
      const f = overlay.frames[Math.min(Math.round(t * overlay.fps), overlay.frames.length - 1)];
      const g = c.getContext("2d")!;
      const sx = c.width / 1280, sy = c.height / 720;
      g.clearRect(0, 0, c.width, c.height);
      g.lineWidth = 2;
      g.font = "600 11px Inter, sans-serif";
      for (const [x1, y1, x2, y2, team, number] of f.p) {
        g.strokeStyle = team === "h" ? "#f2f5ea" : "#7cc3ee";
        g.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
        g.fillStyle = "rgba(10,14,12,0.8)";
        g.fillRect(x1 * sx, y1 * sy - 14, 30, 13);
        g.fillStyle = team === "h" ? "#f2f5ea" : "#7cc3ee";
        g.fillText(`${team === "h" ? "CAL" : "MER"} ${Number(number)}`, x1 * sx + 2, y1 * sy - 4);
      }
      if (f.b) {
        g.strokeStyle = "#c5f277";
        g.beginPath(); g.arc(f.b[0] * sx, f.b[1] * sy, 9, 0, 2 * Math.PI); g.stroke();
      }
      // Minimap: recovered positions (filled) over ground truth (rings).
      const mg = m.getContext("2d")!;
      const k = m.width / 105;
      mg.fillStyle = "#1f5a2c"; mg.fillRect(0, 0, m.width, m.height);
      mg.strokeStyle = "rgba(255,255,255,0.5)"; mg.lineWidth = 1;
      mg.strokeRect(1, 1, m.width - 2, m.height - 2);
      mg.beginPath(); mg.moveTo(m.width / 2, 0); mg.lineTo(m.width / 2, m.height); mg.stroke();
      const P = (x: number, y: number): [number, number] => [x * k, m.height - y * k];
      for (const [x, y, team] of f.g) {
        mg.strokeStyle = team === "h" ? "#f2f5ea" : "#7cc3ee";
        mg.beginPath(); mg.arc(...P(x, y), 5, 0, 2 * Math.PI); mg.stroke();
      }
      for (const p of f.p) {
        mg.fillStyle = p[4] === "h" ? "#f2f5ea" : "#7cc3ee";
        mg.beginPath(); mg.arc(...P(p[6], p[7]), 3, 0, 2 * Math.PI); mg.fill();
      }
      mg.fillStyle = "#c5f277";
      mg.beginPath(); mg.arc(...P(f.gb[0], f.gb[1]), 2.5, 0, 2 * Math.PI); mg.fill();
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [overlay]);

  if (!overlay || !report || !events) return null;
  const recent = events.recovered.filter((e) => e.t <= now).slice(-6).reverse();
  return (
    <section className="panel vision-panel" aria-label="Auto-eventing from video">
      <div className="panel-title">
        <h2><ScanEye size={17} />Auto-eventing from video</h2>
        <span className="panel-kicker">SCORED AGAINST GROUND TRUTH</span>
      </div>
      <p className="subtle-note">
        MatchMind renders the synthetic match as broadcast video. A vision pipeline then works only from the pixels: it
        calibrates the camera from the pitch lines, detects and tracks every player (RT-DETR), splits teams by kit,
        follows the ball, and detects passes and shots. Because the video is synthetic, every result is checked
        against the exact truth.
      </p>
      <div className="vision-body">
        <div className="vision-video">
          <video ref={video} muted playsInline controls loop preload="metadata">
            <source src="/vision/clip.webm" type="video/webm" />
            <source src="/vision/clip.mp4" type="video/mp4" />
          </video>
          <canvas ref={canvas} width={640} height={360} aria-hidden="true" />
        </div>
        <div className="vision-side">
          <canvas ref={minimap} className="vision-minimap" width={315} height={204}
                  aria-label="Recovered positions (dots) over ground truth (rings)" />
          <p className="subtle-note">Dots: recovered from video · rings: ground truth</p>
          <ol className="vision-events" aria-label="Events recovered from video">
            {recent.map((e) => (
              <li key={`${e.t}-${e.type}`} className={e.matched ? "matched" : "unmatched"}>
                <span>{e.clock}</span> {e.type === "shot" ? (e.outcome === "goal" ? "GOAL" : "Shot") : "Pass"} · {e.player}
                {e.recipient ? ` → ${e.recipient}` : ""}{e.speed_kmh ? ` · ${Math.round(e.speed_kmh)} km/h` : ""}
                <b>{e.matched ? "✓ true event" : "✗ not in truth"}</b>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="vision-scores" data-testid="vision-scores">
        <div><span>Camera calibration</span><b>{metres(report.calibration_ground_error_m.median)}</b><i>median ground error</i></div>
        <div><span>Players detected</span><b>{pct(report.player_detection_recall)}</b><i>of visible players</i></div>
        <div><span>Position accuracy</span><b>{metres(report.player_position_error_m.median)}</b><i>median error</i></div>
        <div><span>Team / identity</span><b>{pct(report.team_accuracy)} / {pct(report.identity_accuracy)}</b><i>correct</i></div>
        <div><span>Ball found</span><b>{pct(report.ball_detection_rate)}</b><i>{metres(report.ball_position_error_m)} median error</i></div>
        <div><span>Passes and shots</span><b>F1 {report.events.f1.toFixed(2)}</b><i>{report.events.matched}/{report.events.true} recovered · precision {pct(report.events.precision)}</i></div>
      </div>
      {azure.available && (
        <div className="vision-azure">
          <button className="button secondary" onClick={() => {
            setAzure((a) => ({ ...a, notice: "Starting the vision job on Azure…" }));
            fetch("/api/feed/kickoff?source=vision", { method: "POST" })
              .then(async (r) => {
                const notice = r.ok
                  ? "The vision job is processing this video on Azure Container Apps (about 15 minutes on CPU). Its recovered events arrive in the Event Hubs panel, labelled as recovered from video."
                  : (await r.json().catch(() => ({}))).detail ?? "Could not start the vision job.";
                setAzure((a) => ({ ...a, notice }));
              })
              .catch(() => setAzure((a) => ({ ...a, notice: "Could not start the vision job." })));
          }}>Process this video on Azure</button>
          {azure.notice && <p className="subtle-note" role="status">{azure.notice}</p>}
        </div>
      )}
      <p className="subtle-note">
        {events.validated} recovered events pass the same validation as a data provider's feed and can enter the
        MatchMind pipeline. CPU processing: {report.processing.per_frame_s.toFixed(1)} s per frame at
        {` ${25 / report.processing.stride}`} frames per second of video; live use needs a GPU.
      </p>
    </section>
  );
}
