import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import "./tour.css";

// "See it in 60 seconds": a guided path for first-time viewers and judges. Each stop opens a section,
// spotlights one panel and says, in a sentence or two, why it matters.

export type TourSection = "match" | "analysis" | "video" | "live" | "studio" | "proof";

const STOPS: { section: TourSection; region: string; title: string; text: string }[] = [
  { section: "match", region: "Try to fool the fact checker", title: "The idea: nothing unverified goes on air",
    text: "Write any claim about the match, or pick one. An agent lists each statement; code checks it against the events. False claims are struck out with the reason." },
  { section: "match", region: "Your moments", title: "Moments that explain themselves",
    text: "As the match plays, each moment says why it matters. Press Why? for the build-up, the players' roles in the pass network and the evidence events." },
  { section: "match", region: "Ask the match", title: "Ask anything, in seven languages",
    text: "A Microsoft Foundry agent picks the intent and calls Pitchlight's own MCP tools. You see the tool's verified answer, never the model's own text." },
  { section: "match", region: "Match recap", title: "Recaps written by agents, checked by code",
    text: "Press AI recap, then open the run: a researcher agent chooses the angle through MCP, writers draft, and the fact checker's verdict on every statement is shown." },
  { section: "analysis", region: "Match graph", title: "Who the play runs through",
    text: "Directed passing lanes, forward passes highlighted. Click a player for their partners; in Last 15 min, Show change compares with the previous fifteen minutes." },
  { section: "proof", region: "Proof", title: "Measured, not claimed",
    text: "Every result here can be rerun from the repository: live agent runs, 2,669 real matches from two providers, the load test and the video AI scores." },
];

export function Tour({ open, onClose, setSection }: { open: boolean; onClose: () => void;
                                                       setSection: (s: TourSection) => void }) {
  const [stop, setStop] = useState(0);
  // The app recreates setSection on every render; a ref keeps each step from re-running.
  const show = useRef(setSection);
  show.current = setSection;
  useEffect(() => { if (open) setStop(0); }, [open]);
  useEffect(() => {
    if (!open) return;
    const current = STOPS[stop];
    show.current(current.section);
    let target: Element | null = null;
    // The section renders after the switch; look for the panel until it appears.
    const find = window.setInterval(() => {
      // Panels are sections; the sidebar link to a section can share its label.
      target = document.querySelector(`section[aria-label="${current.region}"]`);
      if (!target) return;
      window.clearInterval(find);
      target.classList.add("tour-focus");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
    return () => { window.clearInterval(find); target?.classList.remove("tour-focus"); };
  }, [open, stop]);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setStop((s) => Math.min(STOPS.length - 1, s + 1));
      if (e.key === "ArrowLeft") setStop((s) => Math.max(0, s - 1));
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [open, onClose]);
  if (!open) return null;
  const current = STOPS[stop];
  const last = stop === STOPS.length - 1;
  return (
    <aside className="tour-card" role="dialog" aria-label="Guided tour" aria-live="polite">
      <div className="tour-head">
        <span>{stop + 1} / {STOPS.length}</span>
        <button className="tour-close" onClick={onClose} aria-label="Close the tour"><X size={15} /></button>
      </div>
      <h3>{current.title}</h3>
      <p>{current.text}</p>
      <div className="tour-progress" aria-hidden="true">
        {STOPS.map((_, i) => <i key={i} className={i <= stop ? "done" : ""} />)}
      </div>
      <div className="tour-actions">
        <button className="button secondary" onClick={() => setStop(stop - 1)} disabled={stop === 0}>
          <ArrowLeft size={14} /> Back
        </button>
        <button className="button primary" onClick={() => (last ? onClose() : setStop(stop + 1))}>
          {last ? "Finish" : "Next"} {!last && <ArrowRight size={14} />}
        </button>
      </div>
    </aside>
  );
}
