import { ExternalLink, ShieldCheck } from "lucide-react";
import "./proof.css";

// Measured, not claimed: every result here comes from a script in the repository that anyone can rerun.

const REPO = "https://github.com/othniel74/pitchlight/blob/main";

type Row = { what: string; result: string; how: string; link: string };

const GROUPS: { title: string; note: string; rows: Row[] }[] = [
  {
    title: "Trustworthy AI",
    note: "Agents write; code verifies every statement; nothing unverified is published.",
    rows: [
      { what: "Live AI recaps, 7 languages × half-time, minute 70, full time", result: "62 of 63 published",
        how: "3 live runs of 21; 14 recaps corrected by the agents before publication, 1 blocked, 0 published with an error", link: "docs/EVALUATION.md" },
      { what: "Fact checker on held-out sentences (test set, 56 cases × 3 runs)", result: "155 / 162 correct",
        how: "No false statement passed; every miss was a safe-side block", link: "docs/EVALUATION.md" },
      { what: "Fact checker, all live checks", result: "0 unsafe passes in 264", how: "Three held-out sets; code decides, the model only extracts",
        link: "docs/EVALUATION.md" },
      { what: "Microsoft Foundry release evaluation", result: "Groundedness 4.71 / 5",
        how: "Azure AI Evaluation on 21 published outputs; 0 unsupported numbers", link: "docs/FOUNDRY.md" },
    ],
  },
  {
    title: "Ready for real data",
    note: "The product runs on synthetic data. These checks ran offline, on real data, to prove the path to production.",
    rows: [
      { what: "All 64 matches of the 2022 World Cup (StatsBomb open data)", result: "81,931 events, 0 rejected",
        how: "64 / 64 scores match the official result", link: "docs/PROVIDERS.md" },
      { what: "Every finished Premier League, Bundesliga, La Liga and Carabao Cup match since 2024 (Sportmonks)",
        result: "2,605 / 2,605 scores match", how: "193 own goals, 493 penalty goals, 47 shootouts handled", link: "docs/PROVIDERS.md" },
    ],
  },
  {
    title: "Production on Azure",
    note: "Measured on the live deployment.",
    rows: [
      { what: "Scaling: 80 concurrent viewers for 170 s, 1 to 3 replicas sharing Azure Managed Redis", result: "11,016 requests, 0 errors",
        how: "Scaled out in about a minute; failover mid-match: the same match finished with 1,079 accepted, 0 rejected",
        link: "docs/PATH_TO_PRODUCTION.md" },
      { what: "Load test: 25 concurrent viewers for 60 s", result: "0 errors",
        how: "31.8 requests/s, 95th percentile 0.7 s (8.3/s and 8.8 s before caching)", link: "docs/PATH_TO_PRODUCTION.md" },
      { what: "Live match through Azure Event Hubs", result: "1,079 / 1,079 events accepted",
        how: "Validated one by one as they arrive", link: "docs/EVENT_DRIVEN.md" },
      { what: "Automated tests", result: "313 backend · 7 browser", how: "Browser tests run against the live site; CI on every push",
        link: "README.md" },
    ],
  },
  {
    title: "Video AI (research prototype)",
    note: "Scored against exact ground truth on synthetic broadcast video; not yet validated on real footage.",
    rows: [
      { what: "Camera calibration · players detected", result: "3 cm · 87%", how: "From the pixels alone", link: "docs/VISION.md" },
      { what: "Team · identity · ball", result: "98% · 79% · 74%", how: "Identity and ball tracking are the limits today",
        link: "docs/VISION.md" },
      { what: "Events recovered", result: "87.5% precision", how: "Favours precision: a false event costs more than a missed one",
        link: "docs/VISION.md" },
    ],
  },
];

export function ProofPanel() {
  return (
    <section className="panel proof-panel" aria-label="Proof">
      <div className="panel-title">
        <h2><ShieldCheck size={17} />Measured, not claimed</h2>
        <span className="panel-kicker">EVERY RESULT CAN BE RERUN FROM THE REPOSITORY</span>
      </div>
      {GROUPS.map((g) => (
        <div key={g.title} className="proof-group">
          <h3>{g.title}</h3>
          <p className="subtle-note">{g.note}</p>
          <table className="proof-table">
            <tbody>
              {g.rows.map((r) => (
                <tr key={r.what}>
                  <td>{r.what}</td>
                  <td className="proof-result">{r.result}</td>
                  <td className="proof-how">{r.how}</td>
                  <td><a href={`${REPO}/${r.link}`} target="_blank" rel="noreferrer" aria-label={`Evidence: ${r.link}`}>
                    <ExternalLink size={13} /></a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
