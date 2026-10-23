# Evidence plan for judging

## What is measured now

The [offline recap comparison](validation/recap-comparison-offline.json) records template generation on nine synthetic cases: three seeds at half-time, minute 70 and full-time. It includes individual outputs, elapsed times and sample percentiles. These are local timings, not model latency, network latency or a production SLO.

An initial [live Azure smoke comparison](validation/recap-comparison-live.json) used one English full-time case. The single writer took 11.36 seconds and failed the product checker; the workflow took 19.62 seconds and passed. The workflow's researcher was skipped with a tool error, so this run does not demonstrate the complete research workflow. Checker rejection is not proof that an output is factually wrong: for example, the single writer's correct statement that Calderbrook scored twice was rejected by the checker. This tiny sample establishes that the measurement path works, not that either approach is superior.

A subsequent [comparison with functioning MCP research](validation/recap-comparison-live-mcp.json) used the same seed at minutes 45, 70 and 90 in English. All three research steps completed, each recording six tool calls.

| Mode | Cases | Accepted by product checker | Median generation time | Maximum generation time |
| --- | --- | --- | --- | --- |
| Template | 3 | Not scored by free-text checker | 0.11 s | 0.26 s |
| Single writer | 3 | 1 / 3 | 4.59 s | 11.76 s |
| Workflow with researcher | 3 | 3 / 3 | 24.47 s | 26.23 s |

No service errors or workflow fallbacks occurred in this three-case run. Output-generation times exclude the additional evaluation check; they include the workflow's internal checks. These are one sequential run on one seed and one language, with no independent quality review. The workflow was slower, and checker acceptance must not be described as an independently measured accuracy rate. Cost remains unmeasured.

Regression tests cover a Redis outage during feed kickoff, partial multilingual claim extraction, and a mixture of true and false scorer claims. The extraction tests use scripted model responses: they test the publication boundary, not the ability of a live model to extract statements.

## Compare the agents on identical cases

From `backend`, run the offline baseline:

```powershell
.venv-agents/Scripts/python -m evaluation.compare_recaps --output ../docs/validation/recap-comparison-offline.json
```

With Azure configured and the backend MCP server running, explicitly enable paid model calls:

```powershell
.venv-agents/Scripts/python -m evaluation.compare_recaps --live --languages en,es,fr,pt,de,it,ar --output ../docs/validation/recap-comparison-live.json
```

The live command compares templates, one writer and the full workflow on the same cases. It records output-generation latency separately from an additional evaluation check. Errors and workflow fallbacks are explicit. Inspect workflow steps to confirm research actually used MCP. Repeat the experiment with additional seeds before drawing conclusions.

The automatic checker is also part of the product, so its acceptance is not independent evidence of correctness. A reviewer must check anonymized outputs against the match record and score factual errors, readability and usefulness. Templates contain verified numbers while free-text agents are constrained to avoid digits; record this difference when interpreting quality scores. Fixed execution order and small samples also limit latency comparisons.

Cost remains unmeasured. Use an isolated Azure deployment or billing window and record model/version, actual input/output usage, price effective date, retries and research calls. Separate benchmark evaluation-check costs from generation costs. Divide generation cost by attempted and successfully published recaps; do not assign zero cost to errors or fallbacks without checking usage.

## Human evaluation — pending real participants

Recruit sports content editors, commentators or analysts. Obtain permission to record anonymized feedback. Do not present developer rehearsals as customer validation.

Give each participant the same tasks:

1. Explain what Pitchlight does after ten seconds on the landing page.
2. Check an incorrect claim and explain its verdict.
3. Generate a recap, inspect its evidence and identify whether it used AI or a template.
4. Switch language or follow a player, then describe what changed.
5. Compare anonymized baseline and workflow recaps with the same source match record.

Record participant role, task completion without help, elapsed time, factual errors found, usefulness (1–5), readability (1–5), preferred output and reason. Vary output order between participants. Report the sample size, recruitment method, failures and limitations alongside averages. Keep recordings and personal details out of the public repository.

## A two-minute demonstration

- **0–15 s:** explain the problem and label the match as synthetic.
- **15–40 s:** submit an incorrect claim and show the verdict against the match record.
- **40–85 s:** generate an AI recap; show a recorded rejection/revision if it occurs, with the actual run trace. Do not stage a successful live correction using template output.
- **85–105 s:** change language and inspect the resulting recap and evidence.
- **105–115 s:** show one measured result with its sample size and limitation.

Record the functioning Azure-backed app. Verify the final duration, public video link, public repository access and permission for third-party assets before submitting.

## Production pilot — pending

Use human approval for a first broadcaster pilot. The existing production release gate remains in force. Identity, tenant isolation, durable shared storage, delivery acknowledgements, release evaluations and operational controls in [PATH_TO_PRODUCTION.md](PATH_TO_PRODUCTION.md) must be completed before describing this as production-ready.
