import { useEffect, useState } from "react";
import { LANGUAGES, directionOf, type LanguageCode } from "./languages";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Check,
  ChevronDown,
  GitBranch,
  Languages,
  Menu,
  MonitorPlay,
  Play,
  Radio,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import "./landing.css";

type Insight = {
  id: string;
  minute: number;
  headline: string;
  previous_count: number;
  current_count: number;
  evidence_event_ids: string[];
};
type TeamStats = {
  goals: number;
  events: number;
  passes: number;
  shots: number;
};
type Snapshot = {
  minute: number;
  event_count: number;
  statistics: { home: TeamStats; away: TeamStats };
  insights: Insight[];
};
type Network = {
  nodes: string[];
  edges: { source: string; target: string; weight: number }[];
  metrics: { edges: number; passes: number };
};
type Narrative = { headline: string; body: string };
type Demo = { state: Snapshot; network: Network; narratives: Narrative[] };
function NetworkFigure({ network }: { network: Network }) {
  const coords = new Map(
    network.nodes.map((id, i) => [
      id,
      {
        x:
          180 +
          122 *
            Math.cos((i / network.nodes.length) * Math.PI * 2 - Math.PI / 2),
        y:
          142 +
          98 * Math.sin((i / network.nodes.length) * Math.PI * 2 - Math.PI / 2),
      },
    ]),
  );
  return (
    <svg
      viewBox="0 0 360 284"
      role="img"
      aria-label="Generated away-team passing connections"
    >
      <rect x="20" y="15" width="320" height="254" rx="2" />
      <path d="M180 15V269M20 91H61V193H20M340 91H299V193H340" />
      <circle className="lp-centre-circle" cx="180" cy="142" r="44" />
      {network.edges.map((e) => {
        const a = coords.get(e.source),
          b = coords.get(e.target);
        return a && b ? (
          <line
            key={`${e.source}-${e.target}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            strokeWidth={0.8 + e.weight * 0.4}
          >
            <title>
              {e.source} to {e.target}: {e.weight} passes
            </title>
          </line>
        ) : null;
      })}
      {network.nodes.map((id) => {
        const p = coords.get(id)!;
        return (
          <g key={id}>
            <circle cx={p.x} cy={p.y} r="12" />
            <text x={p.x} y={p.y + 3.5}>
              {id.split("-")[1]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
export default function Landing() {
  const [menu, setMenu] = useState(false);
  const [minute, setMinute] = useState(67);
  const [audience, setAudience] = useState<"analyst" | "fan" | "broadcast">(
    "analyst",
  );
  const [language, setLanguage] = useState<LanguageCode>("en");
  const [demo, setDemo] = useState<Demo | null>(null);
  const [hero, setHero] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/state?minute=67")
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((v) => {
        if (!cancelled) setHero(v);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    const timer = setTimeout(() => {
      const get = (url: string) =>
        fetch(url).then((r) => {
          if (!r.ok) throw Error("Preview unavailable");
          return r.json();
        });
      Promise.all([
        get(`/api/state?minute=${minute}`),
        get(`/api/graph/network?team=away&minute=${minute}&window=10`),
        get(
          `/api/narratives?minute=${minute}&audience=${audience}&language=${language}`,
        ),
      ])
        .then(([state, network, result]) => {
          if (!cancelled) {
            setDemo({ state, network, narratives: result.narratives });
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setLoading(false);
            setFailed(true);
          }
        });
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [minute, audience, language, retry]);
  const heroInsight = hero?.insights[0];
  const insight = demo?.state.insights[0];
  const narrative = demo?.narratives[0];
  return (
    <div className="landing">
      <a className="lp-skip" href="#landing-content">
        Skip to content
      </a>
      <header className="lp-nav">
        <a className="lp-brand" href="/" aria-label="Pitchlight home">
          <span>
            <AudioLines size={23} />
          </span>
          <strong>
            matchmind<sup>AI</sup>
          </strong>
        </a>
        <nav aria-label="Main navigation" className={menu ? "open" : ""}>
          <a href="#intelligence" onClick={() => setMenu(false)}>
            The intelligence
          </a>
          <a href="#how-it-works" onClick={() => setMenu(false)}>
            How it works
          </a>
          <a href="#broadcast" onClick={() => setMenu(false)}>
            The studio
          </a>
        </nav>
        <a href="/app" className="lp-nav-cta">
          Enter workspace <ArrowUpRight size={15} />
        </a>
        <button
          className="lp-menu"
          aria-label={menu ? "Close navigation" : "Open navigation"}
          aria-expanded={menu}
          onClick={() => setMenu((v) => !v)}
        >
          {menu ? <X size={22} /> : <Menu size={22} />}
        </button>
      </header>
      <main className="lp-main" id="landing-content">
        <section className="lp-hero">
          <img
            className="lp-hero-image"
            src="/images/matchmind-stadium.png"
            alt="An imagined footballer looking across a floodlit stadium at night"
            loading="eager" decoding="async"
          />
          <div className="lp-hero-shade" />
          <div className="lp-hero-copy">
            <div className="lp-eyebrow">
              <span /> FOOTBALL INTELLIGENCE, WITH PERSPECTIVE
            </div>
            <h1>
              The score is only
              <br />
              <em>the beginning.</em>
            </h1>
            <p>
              There’s a story in every shift of play.
              <br />
              Find it. Understand it. Show the evidence.
            </p>
            <div className="lp-hero-actions">
              <a href="/app" className="lp-button lp-button-lime">
                Experience the match <ArrowUpRight size={19} />
              </a>
              <a href="#intelligence" className="lp-text-link">
                <span className="lp-play">
                  <Play size={11} fill="currentColor" />
                </span>{" "}
                See the intelligence
              </a>
            </div>
            <div className="lp-hero-caption">
              <span className="lp-status-dot" /> INTERACTIVE DEMO <i />{" "}
              SYNTHETIC MATCH DATA
            </div>
          </div>
          <div className="lp-hero-coordinate">
            MATCH PERSPECTIVE / 001<span>THE DETAILS CHANGE EVERYTHING.</span>
          </div>
          <div className="lp-floating-insight">
            <div>
              <span>
                <Sparkles size={13} /> A MOMENT, EXPLAINED
              </span>
              <span>67′</span>
            </div>
            <h2>Something is shifting.</h2>
            {heroInsight ? (
              <>
                <p>Merridge · Advanced-area activity</p>
                <div className="lp-float-numbers">
                  <span>{heroInsight.previous_count}</span>
                  <ArrowRight size={22} />
                  <strong>{heroInsight.current_count}</strong>
                  <small>
                    consecutive
                    <br />
                    10-minute windows
                  </small>
                </div>
                <div className="lp-float-proof">
                  <ShieldCheck size={12} />
                  {heroInsight.evidence_event_ids.length} source events. One
                  verifiable observation.
                </div>
              </>
            ) : (
              <p>
                Explore evidence-backed observations in the synthetic match
                demo.
              </p>
            )}
          </div>
          <a className="lp-scroll" href="#intelligence">
            <ArrowDown size={14} /> A CLOSER LOOK
          </a>
        </section>
        <div className="lp-principles">
          <span>
            <Activity size={17} /> The match, in real time
          </span>
          <span>
            <ShieldCheck size={17} /> Every insight, evidenced
          </span>
          <span>
            <Languages size={17} /> Different audiences. Same facts.
          </span>
        </div>
        <section className="lp-intelligence lp-section" id="intelligence">
          <div className="lp-section-top">
            <div>
              <span className="lp-eyebrow">01 / SEE BENEATH THE SURFACE</span>
              <h2>
                Big moments.
                <br />
                <em>Small details.</em>
              </h2>
            </div>
            <p>
              A scoreline can’t tell the whole story. Connect the actions, spot
              the change, and follow an observation all the way back to its
              source.
            </p>
          </div>
          <div className="lp-demo">
            <div className="lp-demo-top">
              <span>
                <AudioLines size={17} /> MATCH INTELLIGENCE
              </span>
              <span>
                <span className="lp-status-dot" />
                {loading ? "UPDATING SNAPSHOT" : "SYNTHETIC REPLAY"} <i />{" "}
                {demo?.state.minute ?? minute}:00
              </span>
            </div>
            <div className="lp-demo-body">
              <div className="lp-demo-network">
                <div className="lp-demo-label">
                  THE CONNECTIONS<span>AWAY · 10-MIN WINDOW</span>
                </div>
                {demo ? (
                  <NetworkFigure network={demo.network} />
                ) : (
                  <div className="lp-demo-loading">
                    <GitBranch size={35} />
                    <span>
                      {failed ? "Preview unavailable" : "Reading the match…"}
                    </span>
                  </div>
                )}
                <div className="lp-network-foot">
                  <span>
                    <i /> Generated pass recipients
                  </span>
                  <span>{demo?.network.metrics.edges ?? "—"} connections</span>
                </div>
                <p className="lp-data-note">
                  Network layout shows connections, not player positions.
                </p>
              </div>
              <div className="lp-demo-story">
                <div className="lp-demo-label">
                  THE INTERPRETATION
                  <span>
                    <ShieldCheck size={12} /> SOURCE VERIFIED
                  </span>
                </div>
                <div
                  className="lp-audience"
                  role="group"
                  aria-label="Preview audience"
                >
                  {(["analyst", "fan", "broadcast"] as const).map((a) => (
                    <button
                      key={a}
                      aria-pressed={audience === a}
                      className={audience === a ? "active" : ""}
                      onClick={() => setAudience(a)}
                    >
                      {a === "analyst"
                        ? "Analyst"
                        : a === "fan"
                          ? "Fan"
                          : "Broadcast"}
                    </button>
                  ))}
                  <button
                    className="lp-language"
                    onClick={() =>
                      setLanguage((l) => {
                        const i = LANGUAGES.findIndex((x) => x.code === l);
                        return LANGUAGES[(i + 1) % LANGUAGES.length].code;
                      })
                    }
                    aria-label={`Preview language: ${LANGUAGES.find((x) => x.code === language)?.native}. Switch to the next language`}
                  >
                    <Languages size={13} />
                    {language.toUpperCase()}
                  </button>
                </div>
                {failed ? (
                  <div className="lp-preview-error" role="status">
                    <h3>The preview needs a moment.</h3>
                    <p>We couldn’t load the match snapshot.</p>
                    <button onClick={() => setRetry((v) => v + 1)}>
                      Try again <ArrowRight size={13} />
                    </button>
                  </div>
                ) : insight ? (
                  <>
                    <div className="lp-observation-label">
                      <span /> ADVANCED ACTIVITY CHANGE{" "}
                      <span>{insight.minute}′</span>
                    </div>
                    <div dir={directionOf(language)} lang={language}>
                      <h3>{narrative?.headline || insight.headline}</h3>
                      <p className="lp-narrative">{narrative?.body}</p>
                    </div>
                    <div className="lp-observation-metrics">
                      <div>
                        <small>Previous 10 min</small>
                        <strong>{insight.previous_count}</strong>
                      </div>
                      <ArrowRight size={21} />
                      <div>
                        <small>Latest 10 min</small>
                        <strong>{insight.current_count}</strong>
                      </div>
                      <span>
                        advanced-area
                        <br />
                        events
                      </span>
                    </div>
                    <details className="lp-proof">
                      <summary>
                        <ShieldCheck size={14} />
                        {insight.evidence_event_ids.length} events behind this
                        insight
                        <ChevronDown size={14} />
                      </summary>
                      <div>
                        {insight.evidence_event_ids.map((id) => (
                          <code key={id}>{id}</code>
                        ))}
                      </div>
                    </details>
                  </>
                ) : (
                  <div className="lp-no-shift">
                    <Target size={27} />
                    <h3>
                      {loading && !demo
                        ? "The story starts with context."
                        : "No meaningful shift. No forced story."}
                    </h3>
                    <p>
                      Move the match clock to explore when a change crosses the
                      publication threshold.
                    </p>
                  </div>
                )}
              </div>
            </div>
            <div className="lp-demo-scrubber">
              <label htmlFor="demo-minute">
                EXPLORE THE MATCH<span>{minute}′</span>
              </label>
              <input
                id="demo-minute"
                type="range"
                min="20"
                max="90"
                value={minute}
                onChange={(e) => setMinute(Number(e.target.value))}
                aria-label="Explore match minute"
              />
              <span>20′</span>
              <span>90′</span>
            </div>
            <div className="lp-demo-bottom">
              <span>
                <Check size={12} /> Real calculations. Fictional match.
              </span>
              <a href="/app">
                Open the full workspace <ArrowUpRight size={13} />
              </a>
            </div>
          </div>
          <div className="lp-demo-explainer">
            <span>
              <span className="lp-status-dot" /> TRY IT FOR YOURSELF
            </span>
            <p>
              Scrub the clock. Switch the audience. Inspect the evidence.
              <br />
              The wording changes. The underlying facts don’t.
            </p>
          </div>
        </section>
        <section className="lp-workflow lp-section" id="how-it-works">
          <div className="lp-workflow-heading">
            <span className="lp-eyebrow">
              02 / FROM THE PITCH TO THE PICTURE
            </span>
            <h2>
              Not more data.
              <br />
              <em>A better perspective.</em>
            </h2>
            <p>
              Football moves quickly. Understanding it should feel effortless.
            </p>
          </div>
          <div className="lp-steps">
            <article>
              <span className="lp-step-number">01</span>
              <div className="lp-step-icon">
                <Activity size={22} />
              </div>
              <h3>Read the match.</h3>
              <p>
                A reproducible event stream builds the match state: passes,
                shots, recoveries and activity in advanced areas.
              </p>
              <span className="lp-step-foot">EVENTS → CONTEXT</span>
            </article>
            <article>
              <span className="lp-step-number">02</span>
              <div className="lp-step-icon">
                <ShieldCheck size={22} />
              </div>
              <h3>Find the signal.</h3>
              <p>
                Compare consecutive windows, detect meaningful changes and
                recalculate every numerical claim against its source events.
              </p>
              <span className="lp-step-foot">PATTERNS → EVIDENCE</span>
            </article>
            <article>
              <span className="lp-step-number">03</span>
              <div className="lp-step-icon">
                <Radio size={22} />
              </div>
              <h3>Tell the story.</h3>
              <p>
                Give analysts the detail, fans the clarity and producers a
                structured overlay, in seven languages. The same verified facts.
              </p>
              <span className="lp-step-foot">INSIGHTS → EXPERIENCE</span>
            </article>
          </div>
        </section>
        <section className="lp-studio" id="broadcast">
          <div className="lp-studio-copy">
            <span className="lp-eyebrow">03 / MADE FOR THE MOMENT</span>
            <h2>
              Give the story
              <br />
              <em>the screen.</em>
            </h2>
            <p>
              Make the insight part of the experience. Preview verified
              overlays, choose your audience, and take the view wherever you
              need it.
            </p>
            <ul>
              <li>
                <Check size={15} /> Evidence-linked overlay queue
              </li>
              <li>
                <Check size={15} /> Movable graphics and adjustable opacity
              </li>
              <li>
                <Check size={15} /> Full-screen and synced pop-out preview
              </li>
            </ul>
            <a href="/app?view=studio" className="lp-button lp-button-dark">
              Explore Broadcast Studio <ArrowUpRight size={18} />
            </a>
          </div>
          <div className="lp-studio-visual">
            <div className="lp-studio-window">
              <div className="lp-window-bar">
                <span>
                  <i />
                  <i />
                  <i />
                </span>
                <span>
                  <MonitorPlay size={12} /> BROADCAST STUDIO
                </span>
                <span>
                  <span className="lp-status-dot" /> PREVIEW
                </span>
              </div>
              <div className="lp-mini-pitch">
                <div className="lp-mini-score">
                  CAL{" "}
                  <b>
                    {hero?.statistics.home.goals ?? "—"} :{" "}
                    {hero?.statistics.away.goals ?? "—"}
                  </b>{" "}
                  MER <span>67′</span>
                </div>
                <svg viewBox="0 0 540 300" aria-hidden="true">
                  <rect x="20" y="18" width="500" height="264" />
                  <path d="M270 18V282M20 82H84V218H20M520 82H456V218H520" />
                  <circle cx="270" cy="150" r="51" />
                </svg>
                <div className="lp-mini-overlay">
                  <span>
                    <Sparkles size={13} /> VERIFIED OBSERVATION
                  </span>
                  <strong>More than a change of pace.</strong>
                  <p>
                    {heroInsight
                      ? `Advanced-area events: ${heroInsight.previous_count} → ${heroInsight.current_count}`
                      : "Every overlay begins with verified evidence."}
                  </p>
                </div>
                <span className="lp-pitch-corner">SYNTHETIC VISUALIZATION</span>
              </div>
              <div className="lp-studio-bottom">
                <span>
                  <ShieldCheck size={12} /> Evidence attached
                </span>
                <a href="/app?view=studio" aria-label="Open Broadcast Studio">
                  <ArrowUpRight size={16} />
                </a>
              </div>
            </div>
            <span className="lp-studio-annotation">
              <span /> YOUR INSIGHT. YOUR VIEW.
            </span>
          </div>
        </section>
        <section className="lp-faq lp-section">
          <div>
            <span className="lp-eyebrow">THE IMPORTANT DETAILS</span>
            <h2>
              Clarity.
              <br />
              <em>On and off the pitch.</em>
            </h2>
          </div>
          <div className="lp-faq-items">
            {[
              [
                "Is this real match data?",
                "This demo uses fictional teams and reproducible synthetic events. It does not use a live football feed, licensed match footage or real player tracking. The stadium artwork is AI-generated.",
              ],
              [
                "What makes an insight trustworthy?",
                "The match engine calculates the statistics. A publication gate recalculates the numerical claims and checks the exact source event IDs. You can inspect those references in the workspace. Observed activity is not proof of tactical causation.",
              ],
              [
                "Is the demo powered by a live AI model?",
                "Yes. The demo runs on Azure Container Apps. Narratives and recaps come from a Microsoft Agent Framework workflow on a Microsoft Foundry model: writers draft, a fact checker extracts every statement and code verifies it, and only verified text is published. Ask the match uses an agent that calls Pitchlight's own MCP tools. When the model is unavailable, verified templates take over.",
              ],
              [
                "What can I try right now?",
                "Replay a full synthetic match. Pick a viewing mode, language, favourite club and players, follow one player or track one metric. Ask the match a question, open a goal's build-up, explore both teams' pass networks, read a verified recap, stream a match through Azure Event Hubs, watch the vision pipeline recover events from broadcast video, and try the full-screen or pop-out Broadcast Studio.",
              ],
            ].map(([q, a]) => (
              <details key={q}>
                <summary>
                  {q}
                  <ChevronDown size={18} />
                </summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="lp-final">
          <span className="lp-eyebrow">THE NEXT MOMENT IS WAITING.</span>
          <h2>
            Don’t just watch.
            <br />
            <em>Read the game.</em>
          </h2>
          <a href="/app" className="lp-button lp-button-lime">
            Step inside Pitchlight <ArrowUpRight size={20} />
          </a>
          <span className="lp-final-note">
            A synthetic match. A real working experience.
          </span>
          <AudioLines className="lp-final-watermark" aria-hidden="true" />
        </section>
      </main>
      <footer className="lp-footer">
        <div>
          <a className="lp-brand" href="/" aria-label="Pitchlight home">
            <span>
              <AudioLines size={21} />
            </span>
            <strong>
              matchmind<sup>AI</sup>
            </strong>
          </a>
          <p>Explain the game. Not just the score.</p>
        </div>
        <nav aria-label="Footer navigation">
          <a href="#intelligence">The intelligence</a>
          <a href="#how-it-works">How it works</a>
          <a href="/app?view=studio">
            Broadcast Studio <ArrowUpRight size={12} />
          </a>
        </nav>
        <div className="lp-footer-bottom">
          <span>© {new Date().getFullYear()} Pitchlight</span>
          <span>
            Synthetic data · AI-generated stadium artwork · Not affiliated with
            the Premier League
          </span>
        </div>
      </footer>
    </div>
  );
}
