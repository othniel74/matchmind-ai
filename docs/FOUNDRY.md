# Pitchlight on Microsoft Foundry

Pitchlight uses one Foundry project (`matchmind-ai` on the `matchmind-ai-studio` resource, UK South) for three things: the models its agents run on, the traces of every agent run, and release evaluations.

## 1. Models for the agent workflow

| What | How |
| --- | --- |
| Model | `gpt-4.1-mini` deployment, GlobalStandard, 100 units |
| Client | Agent Framework `FoundryChatClient` (Responses API), authenticated with Entra ID: `az login` locally, the Container App's managed identity in Azure. No keys are stored. |
| Agents | The narrative workflow (insight ranker, tactical analyst, storyteller, audience editor, fact checker, publication gate; see [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md)), the recap writers, and the **match-qa** agent, which calls Pitchlight's MCP tools ([MCP.md](MCP.md)) |

## 2. Tracing in Foundry

The app exports OpenTelemetry traces (`MATCHMIND_TRACING=azure_monitor`) to the Application Insights resource connected to the Foundry project (`matchmind-ai-studio-appinsights`). The traces therefore appear in **Foundry → Tracing** as well as in Application Insights.

Agent Framework records spans with the OpenTelemetry GenAI conventions. One Ask the match request produces this trace:

```
invoke_agent match-qa
├── chat gpt-4.1-mini              (POST …/openai/v1/responses)
└── execute_tool answer_question
    └── POST /mcp → tools/call answer_question   (Pitchlight's own MCP server)
```

Narrative and recap runs show each workflow executor and handoff (`edge_group.process…`), the model calls, and the publication gate's decision. Prompts and generated text are **not** exported unless `MATCHMIND_TRACE_SENSITIVE=true`.

Verified on 20 October 2026: after live requests to the deployment, the project's Application Insights held `invoke_agent match-qa`, `chat gpt-4.1-mini`, `execute_tool answer_question` and `tools/call answer_question` spans from `matchmind-backend`.

## 3. Release evaluations

`backend/evaluation/foundry_eval.py` evaluates exactly what viewers would see:

1. **Generate.** It runs the live workflow for 21 outputs: a half-time recap, a full-time recap and an insight narrative in each of the 7 languages. When the fact checker blocks a draft, the verified fallback is what gets published, so that is what is scored.
2. **Score.** It uses Azure AI Evaluation:
   - Microsoft's AI-assisted evaluators: **groundedness** (against the verified facts the writers receive), **relevance**, **coherence** and **fluency**, judged by the project's own deployment;
   - Pitchlight's code evaluator **numbers_verified**: the share of numbers in the text that appear in the verified facts.
3. **Log.** It logs the run to the Foundry project, where it appears under **Evaluations** as `matchmind-release-evaluation`, with every row's scores and reasons.
4. **Gate.** It checks the release thresholds. The exit code is non-zero when one fails, so the script can block a release in CI.

```bash
cd backend
python -m venv .venv-eval && .venv-eval/Scripts/python -m pip install -r requirements-eval.txt
.venv-eval/Scripts/python -m evaluation.foundry_eval --output ../foundry-eval-report.json
```

### Results, 20 October 2026 ([foundry-eval-report.json](../foundry-eval-report.json))

| Metric | Mean (1–5; numbers 0–1) | Release threshold | Pass |
| --- | --- | --- | --- |
| Groundedness | **4.71** | 4.0 | ✅ |
| Numbers verified | **1.00**, no unsupported number in any of the 21 outputs | 1.0 | ✅ |
| Relevance | 4.19 | 3.0 | ✅ |
| Coherence | 3.95 | 3.0 | ✅ |
| Fluency | 3.29 | 3.0 | ✅ |

- **Published by the agent workflow: 13 of 21.** The fact checker blocked 8 drafts: unsupported time or chance statements, one contradiction, and extraction mismatches. The verified fallback was published instead each time. The report lists every blocked draft and its reason.
- **Groundedness by language:** 5.0 in en, es, pt and it; 4.67 in de; 4.33 in fr; 4.0 in ar.
- **Honest notes:**
  - The thresholds were set after the first run. Style metrics use the SDK's default pass mark of 3; groundedness and numbers are stricter because they are the product's promise.
  - Fluency is the weakest metric, because short recaps read like lists. It is the next quality target.
  - Judge scores vary slightly between runs on identical text: fluency was 3.38, then 3.29.
  - The first run under-scored the fallback texts because the judge's context lacked the recap record. The judge now receives exactly the verified facts the writers receive.
