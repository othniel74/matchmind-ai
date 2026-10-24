import { useState } from "react";
import { withMatch } from "./match";
import { Check, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { reasonText } from "./AgentRun";
import type { Profile } from "./Experience";
import "./agent-run.css";
import { Feedback } from "./Feedback";

// Try to fool the fact checker: the viewer writes any sentence about the match, the workflow's fact
// checker agent lists its statements, and code verifies each one against the match so far.

type Verdict = { quote: string; type: string; supported: boolean; reason: string | null };
type Result = { available: boolean; publishable: boolean; statements: Verdict[]; failure?: string | null; minute: number };

const TRIES = [
  "Merridge won thanks to a Pedro Valença hat-trick.",
  "Calderbrook won the match.",
  "Pedro Valença scored twice, and Merridge had more shots.",
  "Merridge dominated and won 5-0.",
];

export function FactCheckPanel({ minute, profile }: { minute: number; profile: Profile }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const at = Math.min(90, Math.max(1, minute));
  const check = (value: string) => {
    if (value.trim().length < 3) return;
    setBusy(true); setError("");
    fetch(withMatch(`/api/factcheck?${new URLSearchParams({ text: value.trim(), minute: String(at), language: profile.language })}`))
      .then(async (r) => (r.ok ? r.json() : Promise.reject(r.status === 429 ? "Too many checks: try again in a minute." : "The check failed.")))
      .then(setResult).catch((e) => { setResult(null); setError(String(e)); }).finally(() => setBusy(false));
  };
  return (
    <section className="panel factcheck-panel" aria-label="Try to fool the fact checker">
      <div className="panel-title">
        <h2><ShieldCheck size={17} />Try to fool the fact checker</h2>
        <span className="panel-kicker">NOTHING UNVERIFIED IS PUBLISHED</span>
      </div>
      <p className="subtle-note">
        Write anything about the match. The fact checker agent lists each statement; code checks it against the
        match up to minute {at}. This is the same check every AI recap passes before anyone sees it.
      </p>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); check(text); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={400} dir="auto"
               placeholder="e.g. Calderbrook won thanks to a hat-trick" aria-label="A claim about the match" />
        <button className="button primary" disabled={busy}>{busy ? "Checking…" : "Check"}</button>
      </form>
      <div className="ask-suggestions">
        {TRIES.map((t) => (
          <button key={t} className="player-chip" onClick={() => { setText(t); check(t); }}>{t}</button>
        ))}
      </div>
      {error && <p className="subtle-note">{error}</p>}
      {result && !result.available && (
        <p className="subtle-note">The AI model is unavailable right now, so nothing can be checked.</p>
      )}
      {result?.available && (
        <div className={`factcheck-result ${result.publishable ? "ok" : "bad"}`} data-testid="factcheck-result">
          <p className="factcheck-verdict">
            {result.publishable ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
            {result.publishable ? "Verified: this could be published" : "Blocked: this would never be published"}
          </p>
          {result.statements.length ? (
            <ul className="run-checks">
              {result.statements.map((v, i) => (
                <li key={i} className={v.supported ? "ok" : "bad"}>
                  {v.supported ? <Check size={12} /> : <X size={12} />}
                  <span>“{v.quote}”</span>
                  {!v.supported && <em>{reasonText(v.reason)}</em>}
                </li>
              ))}
            </ul>
          ) : <p className="subtle-note">No checkable statement found ({reasonText(result.failure)}).</p>}
          <Feedback key={result.statements.map((v) => v.quote).join("|")} feature="fact_checker" language={profile.language} />
        </div>
      )}
    </section>
  );
}
