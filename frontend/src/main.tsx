import StudioEvidence, {type ReviewContext} from "./StudioEvidence";
import {signOut} from "./localAccess";
import EvidenceLab from "./EvidenceLab";
import React, { Suspense, lazy, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  BarChart3,
  CloudLightning,
  ScanEye,
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  CircleDot,
  GitBranch,
  LayoutDashboard,
  LogOut,
  MonitorPlay,
  Maximize2,
  Minimize2,
  ExternalLink,
  X,
  Radio,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";
import "./style.css";
import Landing from "./Landing";
import { LANGUAGES, directionOf, type LanguageCode } from "./languages";
import { ExperiencePanels, LiveStreamPanel, ProfilePanel, RecapPanel, useProfile, useSquads } from "./Experience";
import { AskPanel, GraphExplorer } from "./GraphExplorer";
import { EventFeedPanel } from "./EventFeed";
import { VisionPanel } from "./VisionPanel";
import { TacticsPanel } from "./TacticsPanel";

import { eventLabel, empty, initial, type Insight, type Overlay, type Frame, type Graph, type Sample } from "./matchTypes";
import { Crest, PanelTitle, Comparison } from "./MatchWidgets";
import { BroadcastCanvas, PreviewWindow, type PreviewPayload } from "./Broadcast";

// Real-data research views are local-only; the product itself uses synthetic data, and the
// research components load only when enabled.
const RESEARCH = import.meta.env.VITE_ENABLE_RESEARCH === "true";
const LazyStatsBomb = lazy(() => import("./StatsBombResearch"));
const LazyTracking = lazy(() => import("./TrackingReplay.tsx"));
const StatsBombResearch = (props: { standalone?: boolean }) =>
  RESEARCH ? <Suspense fallback={null}><LazyStatsBomb {...props} /></Suspense> : null;
const TrackingReplay = (props: { standalone?: boolean; source?: "skillcorner" | "metrica" }) =>
  RESEARCH ? <Suspense fallback={null}><LazyTracking {...props} /></Suspense> : null;

type Section = "match" | "analysis" | "video" | "live" | "studio";
const SECTIONS: { id: Section; label: string; title: string; summary: string; scoreboard: boolean; icon: React.ReactNode }[] = [
  { id: "match", label: "Match centre", title: "Match centre", scoreboard: true, icon: <LayoutDashboard size={18} />,
    summary: "Live moments, answers and recaps, shaped for you. Every fact is verified." },
  { id: "analysis", label: "Analysis", title: "Analysis", scoreboard: true, icon: <BarChart3 size={18} />,
    summary: "Team statistics, pass networks and the evidence behind every number." },
  { id: "video", label: "Video AI", title: "Video AI", scoreboard: false, icon: <ScanEye size={18} />,
    summary: "Events recovered from broadcast video, scored against ground truth." },
  { id: "live", label: "Live data", title: "Live data", scoreboard: false, icon: <CloudLightning size={18} />,
    summary: "The match feed through Azure Event Hubs, validated event by event." },
  { id: "studio", label: "Broadcast Studio", title: "Broadcast Studio", scoreboard: true, icon: <MonitorPlay size={18} />,
    summary: "Turn verified observations into broadcast-ready moments." },
];

function App() {
  const [reviewWindow,setReviewWindow]=useState<ReviewContext|null>(null);
  const openReview=()=>setReviewWindow({minute:frame.minute,seed:frame.context?.seed??20261020});
  const [frame, setFrame] = useState<Frame>(initial);
  const [run, setRun] = useState(0);
  const [connected, setConnected] = useState(false);
  const [mode, setMode] = useState<"analyst" | "fan">("analyst");
  const [history, setHistory] = useState<Insight[]>([]);
  const [section, setSectionState] = useState<Section>(() => {
    const view = new URLSearchParams(location.search).get("view");
    return SECTIONS.some((x) => x.id === view) ? (view as Section) : "match";
  });
  const setSection = (next: Section) => {
    setSectionState(next);
    const url = new URL(location.href);
    if (next === "match") url.searchParams.delete("view"); else url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
    window.scrollTo({ top: 0 });
  };
  const studio = section === "studio";
  const setStudio = (on: boolean) => setSection(on ? "studio" : "match");
  const page = SECTIONS.find((x) => x.id === section)!;
  const [readOnlyDemo, setReadOnlyDemo] = useState(false);
  useEffect(() => {
    fetch("/ready").then((r) => r.json()).then((j) => setReadOnlyDemo(j.mode === "demo")).catch(() => undefined);
  }, []);
  const [profile, setProfile] = useProfile();
  const squads = useSquads();
  const [momentCount, setMomentCount] = useState(0);
  const [language, setLanguage] = useState<LanguageCode>("en");
  const [audience, setAudience] = useState<"fan" | "analyst" | "broadcast">(
    "broadcast",
  );
  const [queue, setQueue] = useState<Overlay[]>([]);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [selected, setSelected] = useState("");
  const [selectedInsight, setSelectedInsight] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [overlayError, setOverlayError] = useState(false);
  const [previewSource, setPreviewSource] = useState('synthetic');
  const trackingMode = previewSource !== 'synthetic';
  const [expanded, setExpanded] = useState(false);
  const [previewNotice, setPreviewNotice] = useState("");
  const [popupHref, setPopupHref] = useState("");
  const previewRef = useRef<HTMLElement>(null);
  const expandButtonRef = useRef<HTMLButtonElement>(null);
  const previewChannel = useRef<BroadcastChannel | null>(null);
  const popupRef = useRef<Window | null>(null);
  const popupTimer = useRef<ReturnType<typeof setInterval> | undefined>();
  const latestPreview = useRef<PreviewPayload>({ frame: initial });
  const closeExpanded = async () => {
    if (document.fullscreenElement)
      await document.exitFullscreen().catch(() => {});
    setExpanded(false);
    expandButtonRef.current?.focus();
  };
  const expandPreview = async () => {
    setExpanded(true);
    setPreviewNotice("");
    try {
      await previewRef.current?.requestFullscreen();
    } catch {
      /* The expanded layout remains available when fullscreen is blocked. */
    }
  };
  const popOutPreview = () => {
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus();
      return;
    }
    previewChannel.current?.close();
    const id = `matchmind-preview-${crypto.randomUUID()}`;
    const channel = new BroadcastChannel(id);
    previewChannel.current = channel;
    channel.onmessage = (event) => {
      if (event.data?.type === "ready")
        channel.postMessage({
          type: "preview",
          payload: latestPreview.current,
        });
    };
    const href = `${location.origin}/?preview=1&channel=${encodeURIComponent(id)}`;
    setPopupHref(href);
    const popup = window.open(
      href,
      "matchmind-broadcast-preview",
      "popup=yes,width=1280,height=820",
    );
    if (!popup) {
      setPreviewNotice(
        "The preview window was blocked. Allow pop-ups, or open the preview in a tab.",
      );
      return;
    }
    popupRef.current = popup;
    setPreviewNotice(
      "Preview opened in a separate window. It stays synced with this studio.",
    );
    clearInterval(popupTimer.current);
    popupTimer.current = setInterval(() => {
      if (popup.closed) {
        clearInterval(popupTimer.current);
        popupRef.current = null;
        setPopupHref("");
        channel.close();
        if (previewChannel.current === channel) previewChannel.current = null;
        setPreviewNotice("Preview window closed. The studio is ready.");
      }
    }, 500);
  };
  useEffect(
    () => () => {
      clearInterval(popupTimer.current);
      previewChannel.current?.close();
      popupRef.current?.close();
    },
    [],
  );
  useEffect(() => {
    const changed = () => {
      if (!document.fullscreenElement) setExpanded(false);
    };
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panel = previewRef.current;
    panel?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        void closeExpanded();
      }
      if (event.key === "Tab" && panel) {
        const controls = [
          ...panel.querySelectorAll<HTMLElement>(
            'button,a[href],select,[tabindex="0"]',
          ),
        ];
        const first = controls[0],
          last = controls[controls.length - 1];
        if (
          event.shiftKey &&
          (document.activeElement === first || document.activeElement === panel)
        ) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", key);
      expandButtonRef.current?.focus();
    };
  }, [expanded]);
  useEffect(() => {
    if (!studio) setExpanded(false);
  }, [studio]);
  useEffect(() => {
    setHistory([]);
    setQueue([]);
    setSelected("");
    setSelectedInsight("");
    setSamples([]);
    setFrame(initial);
    setConnected(false);
    let disposed = false,
      lastMinute = 0,
      lastVersion = 0,
      socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(
        `${scheme}://${location.host}/ws/match?speed=1&start_minute=${lastMinute + 1}`,
      );
      socket.onopen = () => {
        if (!disposed) setConnected(true);
      };
      socket.onmessage = (e) => {
        if (disposed) return;
        const next: Frame = JSON.parse(e.data);
        if (next.minute <= lastMinute) return;
        if(lastVersion && next.context?.state_version !== lastVersion){setHistory([]);setQueue([]);setGraph(null);setSamples([]);setSelected("");setSelectedInsight("");}
        lastVersion=next.context?.state_version??0;
        lastMinute = next.minute;
        setFrame(next);
        setSamples((prev) => [
          ...prev,
          {
            minute: next.minute,
            home: next.statistics.home.advanced_events,
            away: next.statistics.away.advanced_events,
          },
        ]);
        setHistory((prev) => {
          const items = new Map(prev.map((x) => [x.id, x]));
          next.insights.forEach((x) => items.set(x.id, x));
          return [...items.values()].slice(-30);
        });
      };
      socket.onclose = () => {
        if (disposed) return;
        setConnected(false);
        if (lastMinute < 90) retry = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [run]);
  useEffect(() => {
    if (!studio) return;
    let cancelled = false;
    setOverlayError(false);
    fetch(
      `/api/overlays?minute=${frame.minute}&language=${language}&audience=${audience}` +
        (profile.club ? `&club=${profile.club}` : "") +
        (profile.players.length ? `&players=${profile.players.join(",")}` : "") +
        (profile.focus ? `&focus_player=${profile.focus}` : ""),
    )
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setQueue(data.context?.state_version===frame.context?.state_version ? data.overlays : []);
      })
      .catch(() => {
        if (!cancelled) {
          setQueue([]);
          setOverlayError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [studio, frame.minute, frame.context?.state_version, language, audience, profile]);
  useEffect(() => {
    if (frame.minute < 20) {
      setGraph(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/graph/compare?minute=${frame.minute}&team=away`)
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((v) => {
        if (!cancelled) setGraph(v.context?.state_version===frame.context?.state_version ? v : null);
      })
      .catch(() => {
        if (!cancelled) setGraph(null);
      });
    return () => {
      cancelled = true;
    };
  }, [frame.minute, frame.context?.state_version]);
  useEffect(() => {
    if(connected || frame.minute===0) return;
    const controller=new AbortController();
    const timer=setInterval(()=>{
      fetch(`/api/state?minute=${frame.minute}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(next=>{
        if(controller.signal.aborted || next.context?.state_version===frame.context?.state_version)return;
        setFrame(prev=>prev.minute===next.minute?{...prev,...next}:prev);
        setHistory(next.insights);setQueue([]);setGraph(null);setSamples([]);setSelected("");setSelectedInsight("");
      }).catch(()=>{});
    },2000);
    return()=>{controller.abort();clearInterval(timer)};
  },[connected,frame.minute,frame.context?.state_version]);
  const currentOverlay =
    queue.find((o) => o.overlay_id === selected) || queue[queue.length - 1];
  latestPreview.current = { frame, overlay: currentOverlay };
  useEffect(() => {
    previewChannel.current?.postMessage({
      type: "preview",
      payload: { frame, overlay: currentOverlay },
    });
  }, [frame, currentOverlay]);
  const isActive = (o: Overlay) =>
    frame.minute * 60 >= o.match_clock_seconds &&
    frame.minute * 60 < o.match_clock_seconds + o.duration_ms / 1000;
  const insight =
    history.find((i) => i.id === selectedInsight) ||
    history[history.length - 1];
  const home = frame.statistics.home,
    away = frame.statistics.away;
  const totalPasses = home.passes + away.passes;
  const completion = totalPasses
    ? (
        ((home.completed_passes + away.completed_passes) / totalPasses) *
        100
      ).toFixed(1)
    : "0.0";
  const status =
    frame.minute === 90
      ? "Full time"
      : connected
        ? "Simulation live"
        : frame.minute
          ? "Reconnecting"
          : "Connecting";
  const exportSnapshot = () => {
    const blob = new Blob(
      [
        JSON.stringify(
          { source: "synthetic", frame, insights: history, graph },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = `matchmind-minute-${frame.minute}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const [accessError,setAccessError]=useState("");
  const exitWorkspace = async () => {
    try{await signOut()}catch{setAccessError("Could not sign out. Please retry.");return;}
    clearInterval(popupTimer.current);
    previewChannel.current?.postMessage({ type: "studio_closed" });
    previewChannel.current?.close();
    popupRef.current?.close();
    window.location.assign("/");
  };
  return (
    <div className="workspace">
      {reviewWindow&&<StudioEvidence context={reviewWindow} onDismiss={()=>setReviewWindow(null)}/>} 
      <a className="skip-link" href="#main">
        Skip to match intelligence
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Pitchlight home">
          <div className="brand-mark">
            <AudioLines size={23} />
          </div>
          <span>
            matchmind<span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="workspace-label">Match workspace</div>
        <nav className="side-nav" aria-label="Workspace">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              title={item.label}
              className={section === item.id ? "active" : ""}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => setSection(item.id)}
            >
              {item.icon}
              <span>{item.label}</span>
              {section === item.id && <i />}
            </button>
          ))}
        </nav>
        <div className="sidebar-session">
          <div className="section-label">
            CURRENT SESSION <span className="tiny-dot" />
          </div>
          <div className="session-match">
            <Crest small />
            <span>
              Calderbrook<small>vs Merridge</small>
            </span>
          </div>
          <div className="session-meta">
            <span>Synthetic match</span>
            <span>
              {frame.minute === 90 ? "Completed" : `${frame.minute}′ / 90′`}
            </span>
          </div>
          <div className="session-progress">
            <i style={{ width: `${(frame.minute / 90) * 100}%` }} />
          </div>
        </div>
        <div className="sidebar-bottom">
          <div className="trust-icon">
            <ShieldCheck size={19} />
          </div>
          <strong>Every insight. Evidenced.</strong>
          <p>Inspect the source behind every match observation.</p>
          <div className="environment">
            <span className="tiny-dot" /> DEMO WORKSPACE <span>v0.1</span>
          </div>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <div className="breadcrumbs">
            <span className="breadcrumb-root">Workspace</span>{" "}
            <ChevronRight size={13} />
            <span>{page.label}</span>
          </div>
          <div className="topbar-right">
            <span className="synthetic-label">Synthetic data</span>
            {readOnlyDemo ? (
              <span className="synthetic-label">Read-only demo</span>
            ) : (
              <>
                <button
                  className="workspace-exit"
                  onClick={exitWorkspace}
                  title="Sign out of the local session and return to the landing page"
                >
                  <LogOut size={14} />
                  <span>Sign out & exit</span>
                </button>
                {accessError&&<span role="alert">{accessError}</span>}
                <button className="button secondary" onClick={()=>setReviewWindow({minute:frame.minute,seed:frame.context?.seed??20261020,accountOnly:true})}>Account & access</button>
              </>
            )}
            <div className="avatar" aria-label="Pitchlight workspace">
              MM
            </div>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span /> THE GAME, EXPLAINED
              </div>
              <h1>
                {page.title}
                {page.scoreboard && <span className="live-pill">
                  <i className={connected ? "pulsing" : ""} />
                  {status}
                </span>}
              </h1>
              <p>{page.summary}</p>
            </div>
            {page.scoreboard && <div className="page-actions">
              {section !== "match" && <button
                className="button ghost"
                onClick={exportSnapshot}
                title="Download current match state as JSON"
              >
                <ArrowDownToLine size={15} />
                <span>Export snapshot</span>
              </button>}
              <button
                className="button primary"
                onClick={() => setRun((x) => x + 1)}
              >
                <RotateCcw size={15} />
                Replay match
              </button>
              {section !== "match" && <button className="button ghost" onClick={openReview} disabled={frame.minute<20||trackingMode} title={trackingMode?"Research playback uses a different source; this review is for the synthetic match.":frame.minute<20?"Two complete ten-minute windows are needed before review.":"Inspect and review the current passing observation"}><ShieldCheck size={15}/> Inspect evidence</button>}
            </div>}
          </div>
          {page.scoreboard && <>
          <section className="match-card" aria-label="Match scoreboard">
            <div className="match-card-top">
              <span>
                <span className="tiny-dot" /> SYNTHETIC MATCHDAY
              </span>
              <span>
                {frame.minute === 90 ? "MATCH COMPLETE" : "90-MINUTE REPLAY"}{" "}
                <span className="separator">/</span> DEMO 001
              </span>
            </div>
            <div className="scoreboard">
              <div className="score-team home-team">
                <Crest />
                <div>
                  <h2>Calderbrook</h2>
                  <span>
                    <i /> HOME
                  </span>
                </div>
              </div>
              <div className="score-center">
                <div className="score-numbers">
                  <span>{home.goals}</span>
                  <span className="score-colon">:</span>
                  <span>{away.goals}</span>
                </div>
                <div className="match-clock">
                  <span className="tiny-dot" />
                  {frame.minute === 90
                    ? "FULL TIME"
                    : `${String(frame.minute).padStart(2, "0")}:00`}
                </div>
              </div>
              <div className="score-team away-team">
                <div>
                  <h2>Merridge</h2>
                  <span>
                    AWAY <i />
                  </span>
                </div>
                <Crest away />
              </div>
            </div>
            <div
              className="match-progress"
              aria-label={`${frame.minute} of 90 minutes played`}
            >
              <i style={{ width: `${(frame.minute / 90) * 100}%` }} />
              <span className="half-marker" />
            </div>
            <div className="match-card-bottom">
              <span>
                <ShieldCheck size={13} /> Deterministic simulation
              </span>
              <span>Fictional teams. Real calculations.</span>
              <span>
                00′ <span className="timeline-end">90′</span>
              </span>
            </div>
          </section>
          <section className="metric-grid" aria-label="Match summary">
            <div className="metric">
              <span className="metric-label">
                Events processed
                <Activity size={16} />
              </span>
              <div>
                {home.events + away.events}
                <small>so far</small>
              </div>
              <span className="metric-note">Match events recorded</span>
            </div>
            <div className="metric">
              <span className="metric-label">
                Pass completion
                <GitBranch size={16} />
              </span>
              <div>
                {completion}
                <small>%</small>
              </div>
              <span className="metric-note">
                {home.completed_passes + away.completed_passes} completed passes
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">
                Total shots
                <Target size={16} />
              </span>
              <div>
                {home.shots + away.shots}
                <small>attempts</small>
              </div>
              <span className="metric-note">
                {home.goals + away.goals} goals · xG {(home.xg + away.xg).toFixed(2)}
              </span>
            </div>
            <div className="metric accent-metric">
              <span className="metric-label">
                {studio ? "Verified overlays" : section === "analysis" ? "Expected goals" : "Key moments"}
                <Sparkles size={16} />
              </span>
              <div>
                {studio ? queue.length : section === "analysis" ? `${home.xg.toFixed(2)} – ${away.xg.toFixed(2)}` : momentCount}
                <span className="verified-chip">
                  <Check size={12} /> Evidence linked
                </span>
              </div>
              <span className="metric-note">{studio ? "Ready for the rendering partner" : section === "analysis" ? "Calderbrook – Merridge" : "Verified, for your profile"}</span>
            </div>
          </section>
          </>}
          <div id="match-view">
            {studio ? (
              <div className="studio-grid">
                <section
                  ref={previewRef}
                  tabIndex={expanded ? -1 : undefined}
                  role={expanded ? "dialog" : undefined}
                  aria-modal={expanded ? true : undefined}
                  aria-label="Broadcast preview"
                  className={`panel preview-panel ${expanded ? "preview-expanded" : ""}`}
                >
                  <div className="preview-controls">
                    <button
                      ref={expandButtonRef}
                      className="button secondary"
                      onClick={() =>
                        expanded ? void closeExpanded() : void expandPreview()
                      }
                      aria-label={
                        expanded
                          ? "Reset preview size"
                          : "Expand preview to full screen"
                      }
                    >
                      {expanded ? (
                        <Minimize2 size={15} />
                      ) : (
                        <Maximize2 size={15} />
                      )}{" "}
                      {expanded ? "Reset view" : "Full screen"}
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => trackingMode ? window.open(`/app?view=${previewSource}`, "_blank", "noopener") : popOutPreview()}
                    >
                      <ExternalLink size={15} /> Pop out
                    </button>
                    {expanded && (
                      <button
                        className="button secondary"
                        onClick={() => void closeExpanded()}
                        aria-label="Close expanded preview"
                      >
                        <X size={16} />
                      </button>
                    )}
                  </div>
                  {previewNotice && (
                    <p className="preview-notice" role="status">
                      {previewNotice}
                      {popupHref && (
                        <>
                          {" "}
                          <a href={popupHref} target="_blank" rel="noopener">
                            Open preview in a tab <ExternalLink size={12} />
                          </a>
                        </>
                      )}
                    </p>
                  )}
                  <PanelTitle
                    icon={<MonitorPlay size={17} />}
                    title="Broadcast preview"
                    kicker={previewSource==='statsbomb'?"SOURCE EVENT ANALYSIS":trackingMode ? "RECORDED TRACKING" : "MATCH-CLOCK SYNC"}
                  />
                  {RESEARCH && <label className="tracking-source">Preview source
                    <select aria-label="Preview source" value={previewSource} onChange={e=>setPreviewSource(e.target.value)}>
                      <option value="synthetic">Synthetic demo</option>{RESEARCH && <><option value="tracking">Real tracking - SkillCorner</option><option value="metrica">Metrica - tracking + events</option><option value="statsbomb">StatsBomb - real event analysis</option></>}
                    </select>
                  </label>}
                  {previewSource==='statsbomb' ? <StatsBombResearch/> : trackingMode ? <TrackingReplay key={previewSource} source={previewSource==='metrica'?'metrica':'skillcorner'}/> : <BroadcastCanvas frame={frame} overlay={currentOverlay} />}
                  <div className="preview-caption">
                    <span>
                      <CircleDot size={13} /> {trackingMode ? "Real data research view" : "Illustrative match play"}
                    </span>
                    <span>Preview canvas</span>
                  </div>
                  <p className="subtle-note">
                    {trackingMode ? "Real data uses a separate source clock. The surrounding score, insights and overlay queue belong to the synthetic demo, not the selected research match." : "Players and ball share an illustrative gameplay simulation; source statistics use the match clock. Historical selections are previews. Only overlays within their eight-second match-clock window are marked on air."}
                  </p>
                </section>
                <section className="panel control-panel">
                  <PanelTitle
                    icon={<Radio size={17} />}
                    title="Overlay control room"
                    kicker={`${queue.length} MESSAGES`}
                  />
                  <div className="studio-filters">
                    <label>
                      Audience
                      <select
                        aria-label="Audience"
                        value={audience}
                        onChange={(e) =>
                          setAudience(e.target.value as typeof audience)
                        }
                      >
                        <option value="broadcast">Broadcast</option>
                        <option value="analyst">Analyst</option>
                        <option value="fan">Fan</option>
                      </select>
                    </label>
                    <label>
                      Language
                      <select
                        aria-label="Language"
                        value={language}
                        onChange={(e) =>
                          setLanguage(e.target.value as typeof language)
                        }
                      >
                        {LANGUAGES.map((l) => (
                          <option key={l.code} value={l.code}>
                            {l.native}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="queue-label">
                    VERIFIED OVERLAY QUEUE
                    <span>{queue.length.toString().padStart(2, "0")}</span>
                  </div>
                  <div className="overlay-queue">
                    {queue.length ? (
                      queue
                        .slice()
                        .reverse()
                        .map((o) => (
                          <button
                            className={`overlay-item ${currentOverlay?.overlay_id === o.overlay_id ? "selected" : ""}`}
                            key={o.overlay_id}
                            onClick={() => setSelected(o.overlay_id)}
                            aria-pressed={
                              currentOverlay?.overlay_id === o.overlay_id
                            }
                          >
                            <span className="overlay-minute">
                              {Math.floor(o.match_clock_seconds / 60)}′
                            </span>
                            <span>
                              <strong dir={directionOf(o.language)} lang={o.language}>
                                {(o.favourite_player || o.favourite_club) && "★ "}
                                {o.headline}
                              </strong>
                              <small>
                                {o.evidence_event_ids.length} source events ·{" "}
                                {isActive(o) ? "On air" : "Historical"}
                              </small>
                            </span>
                            <ChevronRight size={15} />
                          </button>
                        ))
                    ) : (
                      <div className="empty-state">
                        <Radio size={25} />
                        <h3>
                          {overlayError
                            ? "Overlays unavailable"
                            : "Waiting for a moment"}
                        </h3>
                        <p>
                          {overlayError
                            ? "The overlay request failed. Switch views or replay to retry."
                            : "The queue fills as evidence-backed insights are detected."}
                        </p>
                      </div>
                    )}
                  </div>
                  {currentOverlay && (
                    <div className="payload">
                      <div className="evidence-label">
                        <ShieldCheck size={15} /> VERIFIED CONTENT
                      </div>
                      <p>{currentOverlay.body}</p>
                      <details>
                        <summary>
                          Inspect synchronized JSON payload
                          <ChevronRight size={14} />
                        </summary>
                        <pre>{JSON.stringify(currentOverlay, null, 2)}</pre>
                      </details>
                    </div>
                  )}
                </section>
              </div>
            ) : (
              <>
                {section === "match" && (
                <div className="experience-grid">
                  <ProfilePanel profile={profile} onChange={setProfile} squads={squads} />
                  <ExperiencePanels minute={frame.minute} stateVersion={frame.context?.state_version} profile={profile}
                                    onMoments={setMomentCount} />
                  <div className="experience-side">
                    <AskPanel minute={frame.minute} profile={profile} />
                    <RecapPanel minute={frame.minute} profile={profile} />
                  </div>
                </div>
                )}
                {section === "video" && <div className="section-stack"><VisionPanel /></div>}
                {section === "live" && (
                  <div className="section-stack">
                    {squads && <EventFeedPanel clubs={squads.clubs} />}
                    <LiveStreamPanel profile={profile} />
                  </div>
                )}
                {section === "analysis" && (<>
                <div className="section-stack">
                  {squads && <GraphExplorer minute={frame.minute} stateVersion={frame.context?.state_version} clubs={squads.clubs} />}
                  {squads && <TacticsPanel minute={frame.minute} language={profile.language} clubs={squads.clubs} />}
                </div>
                <div className="dashboard-grid">
                  <div className="main-column">
                    <section className="panel team-panel">
                      <PanelTitle
                        icon={<Activity size={17} />}
                        title="The match in numbers"
                        kicker="TEAM COMPARISON"
                      />
                      <div className="comparison-teams">
                        <span>
                          <i className="home-dot" />
                          Calderbrook
                        </span>
                        <span>
                          Merridge
                          <i className="away-dot" />
                        </span>
                      </div>
                      <Comparison
                        label="Possession (time)"
                        home={home.possession_pct}
                        away={away.possession_pct}
                        suffix="%"
                      />
                      <Comparison
                        label="Pass completion"
                        home={home.pass_completion_pct}
                        away={away.pass_completion_pct}
                        suffix="%"
                      />
                      <Comparison
                        label="Shots"
                        home={home.shots}
                        away={away.shots}
                      />
                      <Comparison
                        label="Shots on target"
                        home={home.shots_on_target}
                        away={away.shots_on_target}
                      />
                      <Comparison
                        label="Expected goals (xG)"
                        home={home.xg}
                        away={away.xg}
                      />
                      <Comparison
                        label="Corners"
                        home={home.corners}
                        away={away.corners}
                      />
                      <Comparison
                        label="Fouls"
                        home={home.fouls}
                        away={away.fouls}
                      />
                      <Comparison
                        label="Yellow / red cards"
                        home={home.yellow_cards + home.red_cards}
                        away={away.yellow_cards + away.red_cards}
                      />
                      <Comparison
                        label="Recoveries"
                        home={home.recoveries}
                        away={away.recoveries}
                      />
                      <Comparison
                        label="Final-third entries"
                        home={home.final_third_entries}
                        away={away.final_third_entries}
                      />
                    </section>
                  </div>
                  <div className="side-column">
                    {history.length > 0 && (
                  <section className="panel insight-panel" id="insight">
                    <PanelTitle
                      icon={<Sparkles size={17} />}
                      title="Match intelligence"
                      kicker="RULE-BASED"
                    />
                    <div
                      className="mode-switch"
                      role="group"
                      aria-label="Insight audience"
                    >
                      <button
                        aria-pressed={mode === "analyst"}
                        className={mode === "analyst" ? "selected" : ""}
                        onClick={() => setMode("analyst")}
                      >
                        Analyst mode
                      </button>
                      <button
                        aria-pressed={mode === "fan"}
                        className={mode === "fan" ? "selected" : ""}
                        onClick={() => setMode("fan")}
                      >
                        Fan mode
                      </button>
                    </div>
                    {insight ? (
                      <>
                        <div className="insight-label">
                          <span>
                            <Zap size={13} /> MORE ADVANCED ACTIVITY
                          </span>
                          <span>{insight.minute}′</span>
                        </div>
                        <h2 className="insight-headline">
                          {insight.team_id === "away"
                            ? "The away side is playing more often in advanced areas."
                            : "The home side is playing more often in advanced areas."}
                        </h2>
                        <p className="insight-copy">
                          {mode === "analyst"
                            ? insight.explanation
                            : `${insight.team_id === "away" ? "Merridge" : "Calderbrook"} is recording more actions in advanced areas than in the previous ten minutes.`}
                        </p>
                        {insight.interpretation && (
                          <p className="insight-copy subtle-note">
                            Shift interpretation: needs human review · z{" "}
                            {insight.interpretation.z_score.toFixed(2)} (calibrated
                            threshold {insight.interpretation.z_threshold}
                            {insight.interpretation.meets_calibrated_threshold
                              ? ", met"
                              : ", not met"}
                            )
                          </p>
                        )}
                        <div className="evidence-card">
                          <div className="evidence-label">
                            <ShieldCheck size={15} /> EVIDENCE VERIFIED
                          </div>
                          <div className="evidence-values">
                            <div>
                              <span>Previous 10 min</span>
                              <strong>{insight.previous_count}</strong>
                            </div>
                            <ArrowRight size={23} />
                            <div>
                              <span>Latest 10 min</span>
                              <strong>{insight.current_count}</strong>
                            </div>
                            <span className="difference">
                              +{insight.current_count - insight.previous_count}
                            </span>
                          </div>
                          <div className="evidence-foot">
                            <span>
                              {insight.evidence_event_ids.length} source events
                            </span>
                            <span>
                              <Check size={12} /> References verified
                            </span>
                          </div>
                        </div>
                        <details className="source-details">
                          <summary>
                            Explore the evidence
                            <ChevronRight size={15} />
                          </summary>
                          <div className="source-ids">
                            {insight.evidence_event_ids.map((id) => (
                              <span key={id}>{id}</span>
                            ))}
                          </div>
                        </details>
                      </>
                    ) : (
                      <div className="empty-state insight-empty">
                        <div className="waiting-orbit">
                          <Sparkles size={29} />
                        </div>
                        <span className="eyebrow">WATCHING THE MATCH</span>
                        <h3>Good insights take context.</h3>
                        <p>
                          We compare consecutive ten-minute windows to find
                          meaningful changes. Verified observations will appear
                          here as the match develops.
                        </p>
                        <span className="watching-label">
                          <i />
                          Evaluating match events
                        </span>
                      </div>
                    )}
                    <div className="insight-disclaimer">
                      <ShieldCheck size={14} />
                      <span>
                        Deterministic observations. Traceable evidence. No
                        unsupported causal claims.
                      </span>
                    </div>
                  </section>
                    )}
                  <section className="panel events-panel">
                    <PanelTitle
                      icon={<AudioLines size={17} />}
                      title="The latest actions"
                      kicker="EVENT FEED"
                    />
                    {frame.events.length ? (
                      <div className="event-feed">
                        {frame.events
                          .slice()
                          .reverse()
                          .map((e) => (
                            <div className="event-row" key={e.event_id}>
                              <span className="event-time">
                                {String(e.minute).padStart(2, "0")}:
                                {String(e.second).padStart(2, "0")}
                              </span>
                              <span className={`event-symbol ${e.team_id}`}>
                                <CircleDot size={16} />
                              </span>
                              <div>
                                <strong>{eventLabel(e)}</strong>
                                <span>
                                  {e.team_id === "home"
                                    ? "Calderbrook"
                                    : "Merridge"}{" "}
                                  <span>·</span> {e.player_name ?? `#${e.player_id.split("-")[1]}`}
                                </span>
                              </div>
                              <ChevronRight size={14} />
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div className="empty-state">
                        <Activity size={25} />
                        <p>Waiting for the first match events.</p>
                      </div>
                    )}
                  </section>
                  <section className="panel activity-panel">
                    <PanelTitle
                      icon={<TrendingUp size={17} />}
                      title="Advanced-area activity"
                      kicker="CUMULATIVE EVENTS"
                    />
                    <div className="activity-legend">
                      <span>
                        <i className="home-dot" />
                        Calderbrook <b>{home.advanced_events}</b>
                      </span>
                      <span>
                        <i className="away-dot" />
                        Merridge <b>{away.advanced_events}</b>
                      </span>
                    </div>
                    <svg
                      className="activity-chart"
                      viewBox="0 0 500 120"
                      role="img"
                      aria-label="Cumulative advanced-area events through the current match minute"
                    >
                      <path
                        d="M0 24H500M0 60H500M0 96H500"
                        className="chart-grid"
                      />
                      {(["home", "away"] as const).map((team) => (
                        <polyline
                          key={team}
                          className={`chart-line ${team}`}
                          points={samples
                            .map(
                              (s) =>
                                `${(s.minute / 90) * 500},${110 - (s[team] / Math.max(10, home.advanced_events, away.advanced_events)) * 96}`,
                            )
                            .join(" ")}
                        />
                      ))}
                    </svg>
                    <div className="chart-axis">
                      <span>00′</span>
                      <span>30′</span>
                      <span>60′</span>
                      <span>90′</span>
                    </div>
                    <p className="subtle-note">
                      Event activity in advanced areas, rather than possession
                      or causal tactical pressure.
                    </p>
                  </section>
                  </div>
                </div>
                {history.length > 0 && (
                <section className="panel timeline-panel">
                  <PanelTitle
                    icon={<Zap size={17} />}
                    title="Key observations"
                    kicker={`${history.length} DETECTED`}
                  />
                  {history.length ? (
                    <div className="insight-timeline">
                      {history
                        .slice(-5)
                        .reverse()
                        .map((x) => (
                          <button
                            key={x.id}
                            className={insight?.id === x.id ? "selected" : ""}
                            aria-pressed={insight?.id === x.id}
                            onClick={() => {
                              setSelectedInsight(x.id);
                              document
                                .getElementById("insight")
                                ?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                });
                            }}
                          >
                            <span className="timeline-minute">{x.minute}′</span>
                            <div>
                              <strong>{x.headline}</strong>
                              <span>
                                {x.previous_count} → {x.current_count}{" "}
                                advanced-area events
                              </span>
                            </div>
                            <ShieldCheck size={15} />
                            <ChevronRight size={15} />
                          </button>
                        ))}
                    </div>
                  ) : (
                    <p className="timeline-empty">
                      Meaningful moments will be collected here as the match
                      unfolds.
                    </p>
                  )}
                </section>
                )}
                </>)}
              </>
            )}
          </div>
          <footer>
            <span>
              <AudioLines size={14} /> PITCHLIGHT{" "}
              <span className="footer-divider">/</span> Explain the game.
            </span>
            <span>
              {trackingMode ? "Preview: real research data. Surrounding analytics: synthetic demo." : "All teams and events are synthetic. Not affiliated with the Premier League."}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(location.search).get("view") === "evidence" ? <EvidenceLab/> : RESEARCH && new URLSearchParams(location.search).get("view") === "statsbomb" ? <StatsBombResearch standalone/> : RESEARCH && new URLSearchParams(location.search).get("view") === "metrica" ? <TrackingReplay standalone source="metrica"/> : RESEARCH && ["tracking","skillcorner"].includes(new URLSearchParams(location.search).get("view")??'') ? <TrackingReplay standalone/> : new URLSearchParams(location.search).get("preview") === "1" ? (
      <PreviewWindow />
    ) : location.pathname.startsWith("/app") ? (
      <App />
    ) : (
      <Landing />
    )}
  </React.StrictMode>,
);

