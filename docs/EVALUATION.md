# Evaluation results

Every number Pitchlight claims, with how it was measured and the raw report behind it. Live results come from Microsoft Foundry (`gpt-4.1-mini`); the product itself runs on synthetic data, and the real-data checks were run offline.

## Summary

| Area | What was measured | Result | Raw report |
| --- | --- | --- | --- |
| AI recaps, live | 63 recaps through the full multi-agent workflow (3 runs × 21: half-time, minute 70, full time, in 7 languages) | **62 published, 1 blocked**, 0 published with an error; 14 corrected by the agents before publication | [recap-pass-rate.json](validation/recap-pass-rate.json) |
| Fact checker, live | 264 scored checks on three held-out sets, 7 languages, 3 repeats each | **0 wrong statements let through**; 95.7%, 100% and 93.3% correct (every miss is a safe-side block) | [test](../fact-check-test.json) · [holdout2](../fact-check-holdout2.json) · [holdout3](../fact-check-holdout3.json) |
| Foundry release evaluation | 21 outputs scored with Azure AI Evaluation | **Groundedness 4.71 / 5**, relevance 4.19, coherence 3.95, fluency 3.29; 100% of numbers verified; all thresholds passed | [foundry-eval-report.json](../foundry-eval-report.json) |
| Offline evaluation (CI) | 56 checks over 5 fixed seeds: replay, stream structure, statistics, claims, calibration | **56 / 56 passed** | [evaluation-report.json](../evaluation-report.json) |
| Vision vs ground truth | 751 frames of rendered broadcast video | Calibration 3 cm; players 87%; team 98%; events 87.5% precision; goal found; pass speed within 2.6 km/h | [vision-report.json](../vision-report.json) |
| Real data: StatsBomb | All 64 matches of the 2022 World Cup | **81,931 events accepted, 0 rejected; 64 / 64 scores match** | [statsbomb-wc2022.json](validation/statsbomb-wc2022.json) |
| Real data: Sportmonks | 2,605 matches, 4 competitions, 3 seasons | **2,605 / 2,605 scores match**; 193 own goals, 47 shoot-outs handled | [2024-25](validation/sportmonks-2024-25.json) · [2025-26](validation/sportmonks-2025-26.json) · [2026-27](validation/sportmonks-2026-27.json) |
| Scaling, live | 80 concurrent viewers for 170 s | 1 → 3 replicas in about a minute; **11,016 requests, 0 errors** | [load-test-scaled.json](validation/load-test-scaled.json) |
| Failover, live | Feed leader killed at minute 25 | Same match finished: 1,079 accepted, 0 rejected, 0 duplicates | [PATH_TO_PRODUCTION.md](PATH_TO_PRODUCTION.md) |
| Tests | Backend, browser, real graph databases | 313 backend tests; 7 browser tests against the live site; Memgraph and Neo4j parity | CI on every push |

## AI recaps through the multi-agent workflow

`backend/evaluation/recap_pass_rate.py` runs the whole workflow live: the researcher agent chooses the angle through Pitchlight's MCP tools, the writers draft, the fact checker extracts every statement and code verifies each one.

| Run (22 Oct 2026) | Published | Corrected before publication | Blocked |
| --- | --- | --- | --- |
| 1 | 21 / 21 | 4 | 0 |
| 2 | 21 / 21 | 4 | 0 |
| 3 | 20 / 21 | 6 | 1 |
| **Total** | **62 / 63** | **14** | **1** |

The blocked recap (Portuguese, half-time) said the match was level; it was not. The fact checker rejected it, the writer's rewrite repeated the error, and the publication gate showed the verified recap instead. Nothing wrong was published.

Before the researcher and the fixes in [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md), 12 of 21 were published.

## Fact checker on held-out sets

Each case is a sentence about the match that must be either passed or blocked. "Unsafe pass" means a wrong statement was let through.

| Set | Correct | Unsafe passes | Notes |
| --- | --- | --- | --- |
| Test (56 cases × 3) | 155 / 162 (95.7%) | 0 / 99 | 6 service errors excluded |
| Holdout2 (14 × 3) | 42 / 42 (100%) | 0 / 21 | Written after the intensity fix |
| Holdout3 (21 × 3, never seen before measurement) | 56 / 60 (93.3%) | 0 / 33 | 3 service errors excluded |

Every miss is a safe-side false block, which costs a rewrite or the verified fallback, never a wrong publication. [fact-check-report.json](../fact-check-report.json) is the earlier run on the test set, before the intensity backstop: it let one overstated Portuguese statement through in 2 of its 3 repeats, which is why the backstop was added.

## Initial single-writer comparison (23 October 2026)

An English pilot on one synthetic seed at minutes 45, 70 and 90 compared a single writer with the full workflow. The researcher completed six MCP calls per workflow case. The product checker accepted 1 of 3 single-writer outputs and 3 of 3 workflow outputs; median generation times were 4.59 s and 24.47 s respectively. No service errors or workflow fallbacks occurred. This is a small, sequential pilot using the product's own checker, not independent factual accuracy or proof of superiority. Independent human review, more seeds and languages, and cost measurement remain pending. [Raw report](validation/recap-comparison-live-mcp.json) · [Method and initial smoke-run limitation](JUDGE_VALIDATION.md).

## Known limits

- The momentum-shift detector is measured against labelled shifts and does not meet the bar for publication without review (precision 0.52 at the interpretation tier, against a bar of 0.8; [evaluation-report.json](../evaluation-report.json)). Its interpretations are therefore always marked `review_required` (see [SYNTHETIC_SIMULATOR.md](SYNTHETIC_SIMULATOR.md)).
- Vision identity tracking is 79%, and the ball is detected in 74% of frames; see [VISION.md](VISION.md).
- Real-data checks cover scores and event validation, not the AI text on real matches. The product runs on synthetic data, as the brief requires.

## Reproduce

```bash
cd backend
python -m evaluation.run --output ../evaluation-report.json                 # offline, no Azure
python -m evaluation.live_fact_check --split holdout3 --repeat 3            # live, needs Foundry
python -m evaluation.recap_pass_rate                                        # live, needs Foundry
.venv-eval/Scripts/python -m evaluation.foundry_eval --output ../foundry-eval-report.json
```
