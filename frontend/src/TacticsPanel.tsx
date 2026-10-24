import { useEffect, useState } from "react";
import { withMatch } from "./match";
import { ArrowDown, ArrowUp, Repeat2, Shield } from "lucide-react";
import { directionOf } from "./languages";
import "./tactics.css";

// What changed after a substitution or a red card, ranked against the match's own swings, and
// pressing and defensive shape for both teams. Coincidence, never cause.

type Metric = { metric: string; label: string; before: number | null; after: number | null; delta: number | null;
                swing_percentile: number | null; notable: boolean; unit?: string; source?: string };
type TeamImpact = { metrics: Metric[]; statements: string[]; risers: { name: string; before: number; after: number }[];
                    incoming: { name: string; pass_share: number }[] };
type Change = { id: string; team_id: string; clock: number; available: boolean; label?: string; reason?: string;
                caveat?: string; teams?: Record<string, TeamImpact>; changes: { kind: string }[] };
type Pressing = { window: [number, number]; teams: Record<string, { ppda: number | null; high_turnovers: number;
                  line_height: number | null; width: number | null; compactness: number | null }> };

const fmt = (v: number | null | undefined, unit = "") => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`);

export function TacticsPanel({ minute, language, clubs }: { minute: number; language: string;
                                                            clubs: Record<string, { short: string }> }) {
  const [changes, setChanges] = useState<Change[]>([]);
  const [pressing, setPressing] = useState<Pressing | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const bucket = Math.max(1, Math.floor(minute / 5) * 5);  // refresh every five minutes of match time
  useEffect(() => {
    let cancelled = false;
    fetch(withMatch(`/api/tactics/changes?minute=${bucket}&language=${language}`)).then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d) setChanges(d.changes); }).catch(() => undefined);
    if (bucket >= 5)
      fetch(withMatch(`/api/tactics/pressing?minute=${bucket}`)).then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (!cancelled) setPressing(d); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [bucket, language]);
  const current = changes.find((c) => c.id === selected) ?? [...changes].reverse().find((c) => c.available) ?? changes[0];
  const clock = (s: number) => `${Math.floor(s / 60) + 1}′`;
  return (
    <section className="panel tactics-panel" aria-label="Tactical changes">
      <div className="panel-title">
        <h2><Repeat2 size={17} />What changed after a substitution</h2>
        <span className="panel-kicker quiet">Ten minutes before vs after</span>
      </div>
      {changes.length === 0 ? (
        <p className="subtle-note">Substitutions and red cards appear here once they happen.</p>
      ) : (
        <>
          <div className="tactics-changes" role="group" aria-label="Changes">
            {changes.map((c) => (
              <button key={c.id} type="button" className={`player-chip ${current?.id === c.id ? "on" : ""}`}
                      aria-pressed={current?.id === c.id} onClick={() => setSelected(c.id)}>
                {clock(c.clock)} {clubs[c.team_id]?.short} · {c.changes.length > 1 ? `${c.changes.length} changes` :
                  c.changes[0].kind === "red_card" ? "red card" : "substitution"}
              </button>
            ))}
          </div>
          {current && !current.available && (
            <p className="subtle-note">{current.label ?? "This change"}: comparable once ten minutes have passed after it.</p>
          )}
          {current?.available && current.teams && (
            <div className="tactics-body" dir={directionOf(language)} lang={language}>
              <p className="tactics-label">{current.label}</p>
              {Object.values(current.teams).some((t) => t.statements.length) ? (
                <ul className="tactics-findings" data-testid="tactics-findings">
                  {Object.values(current.teams).flatMap((t) => t.statements).map((s) => <li key={s}>{s}</li>)}
                </ul>
              ) : <p className="subtle-note">Nothing unusual: every swing was within the normal range for this match.</p>}
              <div className="tactics-tables">
                {(["home", "away"] as const).map((team) => (
                  <table key={team} className="graph-table" aria-label={`${clubs[team]?.short} before and after`}>
                    <thead><tr><th>{clubs[team]?.short}</th><th>Before</th><th>After</th><th>Swing</th></tr></thead>
                    <tbody>
                      {current.teams![team].metrics.map((m) => (
                        <tr key={m.metric} className={m.notable ? "is-notable" : ""}>
                          <td>{m.label}</td>
                          <td>{fmt(m.before, m.unit === "m" ? " m" : "")}</td>
                          <td>{fmt(m.after, m.unit === "m" ? " m" : "")}</td>
                          <td>
                            {m.delta ? (m.delta > 0 ? <ArrowUp size={12} aria-label="up" /> : <ArrowDown size={12} aria-label="down" />) : null}
                            {m.swing_percentile != null ? ` ${m.swing_percentile}th` : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ))}
              </div>
              <p className="subtle-note">
                Swing: how this change ranks among all ten-minute swings of that measure in this match; highlighted rows are
                in the top 20%. Shape comes from synthetic 25 Hz tracking. <strong>{current.caveat}</strong>
              </p>
            </div>
          )}
        </>
      )}
      {pressing && (
        <div className="tactics-pressing" aria-label="Pressing and shape">
          <h3><Shield size={14} /> Pressing and shape, {pressing.window[0]}′–{pressing.window[1]}′</h3>
          <div className="tactics-press-grid">
            {(["home", "away"] as const).map((team) => {
              const t = pressing.teams[team];
              return (
                <div key={team}>
                  <b>{clubs[team]?.short}</b>
                  <span>PPDA <strong>{fmt(t.ppda)}</strong></span>
                  <span>High turnovers <strong>{t.high_turnovers}</strong></span>
                  <span>Line height <strong>{fmt(t.line_height, " m")}</strong></span>
                  <span>Width <strong>{fmt(t.width, " m")}</strong></span>
                  <span>Compactness <strong>{fmt(t.compactness, " m")}</strong></span>
                </div>
              );
            })}
          </div>
          <p className="subtle-note">PPDA: opponent passes allowed per defensive action in the pressing zone; lower means more intense pressing.</p>
        </div>
      )}
    </section>
  );
}
