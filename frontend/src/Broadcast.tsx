import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, AudioLines, MonitorPlay, Maximize2, GripVertical, Eye, EyeOff, Minimize2, X, RotateCcw, Sparkles } from "lucide-react";
import { directionOf } from "./languages";
import { initialPitch, initial, type Overlay, type Frame } from "./matchTypes";
import { PitchPlayers } from "./PitchPlayers";

export type PreviewPayload = { frame: Frame; overlay?: Overlay };
export function BroadcastCanvas({ frame, overlay }: PreviewPayload) {
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
        CAL{" "}
        <b>
          {home.goals} : {away.goals}
        </b>{" "}
        MER <span>{frame.minute}′</span>
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
export function PreviewWindow() {
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
