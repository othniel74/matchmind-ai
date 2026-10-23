# Pitchlight documentation

## Start here

| Document | What it covers |
| --- | --- |
| [Submission](SUBMISSION.md) | Pitch, prize category, Microsoft technologies, step-by-step testing instructions |
| [Evaluation results](EVALUATION.md) | Every measured result with its raw report: live recaps, fact checker, Foundry, vision, real data, scaling |
| [Hackathon brief coverage](HACKATHON_COVERAGE.md) | Every requirement of the brief mapped to code and to how it is verified |
| [Demo video (1:49, narrated)](demo/pitchlight-submission.mp4) | Recorded against the live deployment |

## How it works

| Document | What it covers |
| --- | --- |
| [Auto-eventing from video](VISION.md) | Ground-truth tracking, the broadcast renderer, the vision pipeline (calibration, RT-DETR, teams, identity, ball, events), measured accuracy, the Azure job |
| [Agent workflow](AGENT_WORKFLOW.md) | The Agent Framework graph, the fact checker, recaps, rate limits, tracing, live fact-check results |
| [Microsoft Foundry](FOUNDRY.md) | Models, tracing in Foundry, release evaluations and their results |
| [MCP server](MCP.md) | The 15 match tools, the MCP-calling Q&A agent, use from VS Code / Copilot |
| [Event-driven feed](EVENT_DRIVEN.md) | Event Hubs, the producer job, the consumer, delivery guarantees |
| [Knowledge graph](GRAPH_INTELLIGENCE_ARCHITECTURE.md) | The match knowledge graph, network roles, xG chain, Memgraph/Neo4j projection and parity tests |
| [Tactical changes](TACTICS.md) | Before/after impact of substitutions and red cards, pressing and defensive shape, with the swing ranking and causal caveat |
| [Real data providers](PROVIDERS.md) | The StatsBomb adapter, its verification on a real match, the contract changes real data required |
| [Claim contracts](CLAIM_CONTRACTS.md) | Typed, evidence-backed claims with exact recomputation |
| [Languages](LANGUAGES.md) | The seven languages, number formats, right-to-left handling, how to add one |
| [Synthetic simulator](SYNTHETIC_SIMULATOR.md) | The possession-based generator, ground-truth tracking for video, realism checks, scenario labels and detector precision |
| [Local evidence foundation](LOCAL_EVIDENCE_FOUNDATION.md) | Versioned events, provenance, corrections, review and publication |

## Running it

| Document | What it covers |
| --- | --- |
| [Deployment](DEPLOYMENT.md) | The Azure resources, demo safeguards, verification and how to update |
| [Path to production](PATH_TO_PRODUCTION.md) | Controls already in place, what the release gate waits for, rollout |

## Assets and data

| Document | What it covers |
| --- | --- |
| [Player assets](PLAYER_ASSETS.md) | The MIT-licensed Microsoft Rocketbox models and their credits |
| [Landing page design](LANDING_PAGE_DESIGN.md) | Landing page artwork and design provenance |
| [Real data sources](REAL_DATA_SOURCES.md) | Optional local research samples (not in this repository, off in the demo) |
| [Real tracking replay](REAL_TRACKING_REPLAY.md) | The optional local research replay view |

## History

These earlier documents record how the project developed. Their test counts, limitations and plans describe the project at the date they were written; the documents above are current.

[Build history (previous README)](HISTORY.md) · [Implementation status, 15–17 October](IMPLEMENTATION_STATUS.md) · [Verification, 17 October](VERIFICATION_2026_10_17.md) · [VS Code setup and test plan](VSCODE_SETUP_AND_TEST_PLAN.md) · [Future implementation roadmap](FUTURE_IMPLEMENTATION_ROADMAP.md) · [Technical implementation and risk controls](TECHNICAL_IMPLEMENTATION_AND_RISK_CONTROLS.md) ([Word](technical/Pitchlight_AI_Technical_Implementation_and_Risk_Controls.docx)) · [Product strategy v2](product/Pitchlight_AI_Product_Strategy_v2.docx) · [Gameplay preview](GAMEPLAY_PREVIEW.md) · [Production readiness audit](PRODUCTION_READINESS_AUDIT.md) · [Release checklist](RELEASE_CHECKLIST.md) · [Evaluation scorecard register](EVALUATION_SCORECARD.csv) · Earlier requirements: [product requirements](Pitchlight_AI_Product_Requirements_Technical_Architecture.docx), [graph addendum](Pitchlight_Graph_Intelligence_Requirements_Addendum.docx)
