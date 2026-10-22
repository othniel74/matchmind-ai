import { useState } from "react";
import { Bot, Check, ChevronDown, Cpu, RotateCcw, ShieldCheck, X } from "lucide-react";
import "./agent-run.css";

// The multi-agent run behind an AI recap, made visible: which agent did what, in what order, how
// long it took, every statement the fact checker extracted and how code judged it, and any rewrite.

export type AgentStep = {
  agent: string; status: string; attempts?: number; latency_ms?: number; reason?: string | null;
  output?: string | null; statements?: number; mode?: string;
  checked?: { quote: string; type: string; supported: boolean; reason: string | null }[];
  tool_calls?: { tool: string; arguments: Record<string, unknown> }[];
  chose?: { metrics: string[]; roles: { team: string; role: string; player: string }[] };
  angle?: string;
};
export type AgentTraceView = { engine: string; steps: AgentStep[]; handoffs: string[]; duration_ms: number;
                               fallback_reason: string | null };

const ROLES: Record<string, { label: string; kind: "agent" | "code"; does: string }> = {
  evidence_gate: { label: "Evidence gate", kind: "code", does: "Admits only facts recomputed from the events" },
  insight_ranker: { label: "Insight ranker", kind: "code", does: "Picks the insight to write about" },
  match_researcher: { label: "Match researcher", kind: "agent", does: "Investigates through Pitchlight's MCP tools and chooses the angle" },
  tactical_analyst: { label: "Tactical analyst", kind: "agent", does: "Drafts from the verified facts" },
  match_storyteller: { label: "Match storyteller", kind: "agent", does: "Rewrites it for viewers, adding nothing" },
  audience_editor: { label: "Audience editor", kind: "agent", does: "Adapts it to your audience and language" },
  fact_checker: { label: "Fact checker", kind: "agent", does: "Extracts every statement; code verifies each one" },
  publication_gate: { label: "Publication gate", kind: "code", does: "Re-validates evidence and text before release" },
};

const REASONS: Record<string, string> = {
  contradicts_result: "contradicts the score",
  contradicts_scorers: "contradicts the scorers",
  contradicts_claims: "contradicts the statistics",
  contradicts_roles: "contradicts the pass network",
  unsupported_number: "a number: Pitchlight publishes numbers only from verified claims",
  unsupported_timing: "states a match time",
  no_factual_statement: "no factual statement",
  extraction_mismatch: "the statements could not be matched to the text",
  incomplete_extraction: "part of the text could not be checked",
  no_mcp_server: "no MCP server here, so the standard facts were used",
  contradicts_evidence: "contradicts the evidence",
  unsupported_statement: "not in the verified facts",
  overstated: "overstated",
  unsupported_mentions_match_time: "states a match time",
  unsupported_gives_cause: "claims a cause",
  unsupported_mentions_chances_or_threat: "mentions chances",
  unsupported_is_prediction: "a prediction",
  unsupported_judges_performance: "judges performance",
  unsupported_claims_dominance: "claims dominance",
  invalid_output: "unreadable model output",
  rate_limited: "model rate limited",
  timeout: "model timed out",
};
export const reasonText = (r?: string | null) => (r ? REASONS[r.split(":").pop() ?? r] ?? r.replace(/_/g, " ") : "");

const STATUS: Record<string, { text: string; tone: "ok" | "warn" | "bad" | "muted" }> = {
  passed: { text: "Passed", tone: "ok" }, completed: { text: "Done", tone: "ok" }, verified: { text: "Verified", tone: "ok" },
  approved: { text: "Published", tone: "ok" }, skipped: { text: "Not needed", tone: "muted" },
  revision_requested: { text: "Sent back", tone: "warn" }, blocked: { text: "Blocked", tone: "bad" },
  fallback: { text: "Verified text shown", tone: "warn" },
};

function Step({ step, index, rewrite }: { step: AgentStep; index: number; rewrite: boolean }) {
  const [open, setOpen] = useState(step.agent === "fact_checker" || step.agent === "match_researcher");
  const role = ROLES[step.agent] ?? { label: step.agent.replace(/_/g, " "), kind: "code" as const, does: "" };
  const status = STATUS[step.status] ?? { text: step.status, tone: "muted" as const };
  const detail = !!(step.output || step.checked?.length || step.tool_calls?.length);
  const metric = (m: string) => m.replace(/_/g, " ").replace("xg", "expected goals");
  return (
    <li className={`run-step ${role.kind} ${status.tone}`}>
      <span className="run-marker" aria-hidden="true">{role.kind === "agent" ? <Bot size={13} /> : <Cpu size={13} />}</span>
      <div className="run-body">
        <div className="run-head">
          <b>{index + 1}. {role.label}</b>
          <span className="run-kind">{role.kind === "agent" ? "Foundry agent" : "Code"}</span>
          {rewrite && <span className="run-kind rewrite"><RotateCcw size={10} /> Rewrite</span>}
          <span className={`run-status ${status.tone}`}>{status.text}</span>
          {step.latency_ms != null && <span className="run-meta">{(step.latency_ms / 1000).toFixed(1)} s</span>}
          {(step.attempts ?? 1) > 1 && <span className="run-meta">{step.attempts} attempts</span>}
        </div>
        <p className="run-does">{role.does}{step.reason ? ` · ${reasonText(step.reason)}` : ""}</p>
        {detail && (
          <button className="run-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
            <ChevronDown size={12} className={open ? "open" : ""} />
            {step.checked?.length ? `${step.checked.filter((c) => c.supported).length} of ${step.checked.length} statements verified`
              : step.tool_calls?.length ? `${step.tool_calls.length} MCP tool calls · what it chose` : "Draft"}
          </button>
        )}
        {open && step.output && <p className="run-draft">{step.output}</p>}
        {open && !!step.tool_calls?.length && (
          <div className="run-research">
            <div className="run-tools">
              {step.tool_calls.map((c, i) => (
                <code key={i}>{c.tool}({Object.entries(c.arguments).map(([k, v]) => `${k}=${String(v)}`).join(", ")})</code>
              ))}
            </div>
            {step.chose && (
              <p><b>Chose:</b> {step.chose.metrics.map(metric).join(", ") || "no statistics"}
                {step.chose.roles.map((r) => ` · ${r.player} (${r.role === "hub" ? "hub" : "key link"})`).join("")}
                <span className="subtle-note"> Code computed these facts from the events.</span></p>
            )}
            {step.angle && <p className="run-notes"><b>Working notes, never published:</b> {step.angle}</p>}
          </div>
        )}
        {open && !!step.checked?.length && (
          <ul className="run-checks">
            {step.checked.map((c, i) => (
              <li key={i} className={c.supported ? "ok" : "bad"}>
                {c.supported ? <Check size={12} /> : <X size={12} />}
                <span>“{c.quote}”</span>
                {!c.supported && <em>{reasonText(c.reason)}</em>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

export function AgentRunView({ trace }: { trace: AgentTraceView }) {
  const published = trace.engine === "microsoft_agent_framework";
  const agents = trace.steps.filter((s) => ROLES[s.agent]?.kind === "agent").length;
  // A step after a "sent back" fact check is the rewrite loop.
  const rewrites = new Set(trace.steps.map((s, i) => (i > 0 && trace.steps[i - 1].status === "revision_requested" ? i : -1)));
  return (
    <details className="agent-run" data-testid="agent-run">
      <summary>
        <ShieldCheck size={14} />
        <span>How {agents} agent steps wrote this</span>
        <span className={`run-status ${published ? "ok" : "warn"}`}>
          {published ? "Fact-checked and published" : "Blocked: verified recap shown"}
        </span>
        <span className="run-meta">{(trace.duration_ms / 1000).toFixed(1)} s</span>
      </summary>
      <ol className="run-steps">
        {trace.steps.map((s, i) => <Step key={i} step={s} index={i} rewrite={rewrites.has(i)} />)}
      </ol>
      <p className="subtle-note">
        Microsoft Agent Framework workflow on Azure AI Foundry. Agents only write and extract; they never decide what is
        true. Plain code verifies every statement against the events, and anything unverified is never published.
      </p>
    </details>
  );
}
