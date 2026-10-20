# Agent workflow — 19 October 2026 (updated 20 October)

## Update — 20 October 2026

**Recap mode.** The same graph writes match recaps (`run_recap`, `/api/recap/agent`).
- The analyst receives verified facts from `recap_facts`: the result by club, the scorers with goal counts, and the leader for each statistic.
- Recap writers get their own rules: state the result, the scorers and the statistic leaders, with no digits, causes, predictions, timing or activity trends.
- Two statement types were added for recaps, and both are verified by code:
  - **result:** won, lost, drew, leads, trails or level. Saying the match "ended" counts as a result statement, so it is rejected before full-time.
  - **scorer:** checked against goal events.
- The deterministic recap is always returned alongside the agent version.

**Grounding by words.** A quote is grounded when every word of it appears in the text, not only as an exact substring, so list sentences can be split into one claim per statistic. A quote word also matches a text word that carries a one- or two-letter attached prefix (Arabic و / ب / ل).

**Roster.** The fact checker receives the club names and the full roster. It maps player names written in any script or spelling (for example Arabic transliterations) to the roster name, which code then verifies.

**Intensity backstop.** The extractor's intensity label varied between runs for the same sentence, letting "muito mais" / "muchísima más" pass a narrow comparison. A deterministic list of amplifying words in all seven languages now raises a statement to at least "strong". "Far", "way" and "a lot" count only before more, fewer or less, so "so far" is not treated as emphasis.

**Measurement fixes.**
- The live evaluation runner now uses the product's rate-limit-aware call path.
- It reports service errors separately: they were previously counted as correct blocks.
- It saves every row in its report.

**Live results, 20 October 2026** (gpt-4.1-mini, three runs per case, service errors excluded):

| Set | Correct | Wrong statements let through | Notes |
| --- | --- | --- | --- |
| Original held-out test (56) | 155/162 (95.7%) | 0 | 6 service errors |
| Holdout2 (14, written after the intensity fix) | 42/42 | 0 | After the backstop. An earlier run scored 41/42 with 1 unsafe pass, which prompted the backstop, so this set is no longer unseen |
| Holdout3 (21, never seen before measurement) | 56/60 (93.3%) | 0 | 3 service errors |

Every remaining error is a safe-side false block. The usual cause is that comparing with earlier play ("so far", "que antes", "qu'avant") gets flagged as a match-time reference; the cost is a revision or a fallback.

**Live AI recaps:** 9 of 11 runs published (all seven languages at full-time, plus half-time and mid-match runs).
- Every published recap was fact-checked and correct.
- One German mid-match recap said the match "ended" and was correctly blocked.

`backend/app/agent_workflow.py` builds the narrative pipeline with **Microsoft Agent Framework 1.22** (stable), using `agent-framework-foundry` 1.15. The graph is built with `WorkflowBuilder`, `Executor` and `@handler`, and the framework runtime executes it.

```
evidence_gate -> insight_ranker -> tactical_analyst -> match_storyteller -> audience_editor <-> fact_checker -> publication_gate
                                         \_________________ \____________________ \_____________ \--> deterministic_fallback
```

## Steps

- **Deterministic steps:**
  - `evidence_gate` validates insights against source events.
  - `insight_ranker` picks the largest verified change.
  - `publication_gate` re-validates the evidence, the text and the linked claims.
  - `deterministic_fallback` publishes the template narrative in the requested language.
- **Writer agents:**
  - `tactical_analyst` writes in English from the verified counts. It never sees the match minute.
  - `match_storyteller` rewrites that English text for viewers.
  - `audience_editor` writes the final text in any supported language (see `LANGUAGES.md`).
- **Fact checker:** `fact_checker` is an agent that only extracts statements as JSON, at temperature 0. Plain code verifies every statement.

## Checking

1. **Deterministic filters on every writer output:**
   - no digits in any script, including Arabic-Indic
   - a length limit
   - English and Spanish word lists for causes, certainty, pressure and match timing
   - Each writer gets one retry for a timeout, malformed JSON or a rule violation, with the reason as feedback.
2. **Semantic verification of the final text, in any language.** For every statement the extractor gives:
   - its type: an activity change, a comparison of a claims metric, or other
   - its team, relation and metric
   - its intensity: neutral, strong or extreme
   - a checklist of yes/no answers: does it mention match time, give a cause, mention chances or goal threat, predict, judge performance, or claim dominance?

   Plain code then decides. A statement is rejected when:
   - any checklist answer is yes
   - its type is other
   - an activity change names the wrong team or a non-increase
   - a comparison is false when recomputed from source events (a true one is linked to its claim ID)
   - the tone doesn't fit the data: extreme wording is never allowed, and strong wording needs a large change (activity at least 1.75 times the previous window, or one team at least 1.5 times the other)

   Extraction fails closed when:
   - it finds no statements
   - a quote isn't in the text
   - the quotes cover less than 40% of the text
   - the output isn't valid JSON or misses checklist fields

   A failure sends the editor back once, with the rejected quotes. A second failure falls back to the template.

The checklist replaced a single category label. Live tests showed that one label was unstable: a fix for one sentence moved two others.

## Rate limits

- **Deployment capacity:** `gpt-4.1-mini` was raised to 100 units, which is 100 requests and 100,000 tokens per minute. It is billed per token; the subscription's quota is 200.
- **429 responses:** an HTTP 429 response makes the call wait for `Retry-After` (at most 10 seconds) and retry, up to 3 times. Each step records `rate_limit_waits`. A 429 that persists falls back with the reason `rate_limited`.

## Provider and tracing

- **Foundry:** `FoundryChatClient` calls the project's model deployment through the Responses API. It replaces the deprecated `AzureAIClient`.
  - Agents stay defined in code next to their checks, so no server-side agent is created.
  - A new agent object is built for every call.
- **Azure OpenAI:** a resource can be used instead, with a key or Entra ID.
- **Tracing:** `MATCHMIND_TRACING` selects the exporter.

| Mode | Exporter |
| --- | --- |
| `console` | prints spans |
| `otlp` | OTLP over HTTP to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `azure_monitor` | Application Insights via `APPLICATIONINSIGHTS_CONNECTION_STRING` |

- **Run ID:** each run has a `matchmind.narrative_run` span carrying the API trace's `run_id`, language, audience, engine and live flag. The framework's workflow, executor, agent, chat and HTTP spans nest under it.
- **No content:** prompts and generated text are not exported unless `MATCHMIND_TRACE_SENSITIVE=true`.
- **Azure Monitor settings:**
  - Sampling is fixed at 100%, because the distro's default of 5 per second dropped most spans of a live run. Set `OTEL_TRACES_SAMPLER` to override.
  - The service name is `matchmind-backend`.
  - The Azure VM metadata probe is skipped off Azure. When hosting in Azure, set `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`.
- **Shutdown:** the backend flushes and closes exporters when it stops.

## Verified — 19 October 2026

| Check | Result |
| --- | --- |
| Offline agent tests (`tests/test_agents.py`): real `Agent` objects and runtime, scripted client | 43 cases pass |
| Telemetry unit and nesting tests | pass |
| Real OTLP export (`tests/test_otlp_export.py`): real exporter sends protobuf to a local receiver | full span tree, run ID matched, no content exported |
| Application Insights (`matchmind-insights`, live Foundry run) | all 7 executors, 4 agents and 4 model calls in one trace under `matchmind-backend` |
| Live fact checker, held-out test set (56 sentences, 7 languages, 3 runs each) | 168/168 correct, 95% CI 97.8–100%; no wrong statement passed; identical across runs |
| Live fact checker, tuning set (28 sentences, 3 runs) | 81–84/84; the only errors were a correct German sentence blocked in some runs (safe direction); no wrong statement passed |
| Live workflow, all 7 languages (before the checklist) | 7/7 published; 3 needed one revision |
| Browser smoke tests (Playwright, Chromium) | 3/3: landing in all 7 languages with Arabic right-to-left, dashboard, Studio Arabic overlays right-to-left; no page errors |

**Re-running the live evaluation.** It calls a paid model, so it isn't part of CI:

```
cd backend
python -m evaluation.live_fact_check --split test --repeat 3 --output ../fact-check-report.json
```

## Limits

- **Model variance.** Azure doesn't guarantee identical output at temperature 0. One correct German sentence was sometimes blocked. This error direction is safe: it costs a revision or a fallback, not a false statement.
- **Coverage.** The fact checker's accuracy is measured on 84 sentences for one match state. New match situations and phrasings need new cases in `fact_check_cases.json`.
- **Statement scope.** The checker verifies activity changes and statistic comparisons. Any other kind of factual statement is blocked, even if it's true.
- **Pre-filters.** The deterministic word-list pre-filters cover English and Spanish only.
