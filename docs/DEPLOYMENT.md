# Public demo deployment — 20 October 2026

**URL:** https://matchmind-demo.mangograss-8c9a0131.uksouth.azurecontainerapps.io

The app's routes:

| Path | Page |
| --- | --- |
| `/` | landing |
| `/app` | workspace (personalization, recaps, live stream) |
| `/app?view=studio` | Broadcast Studio |

## What runs where

All resources are in resource group `rg-othniel.obasi-9233`, UK South.

| Resource | Name | Purpose | Cost model |
| --- | --- | --- | --- |
| Container App | `matchmind-demo` | The app container serves the API, WebSockets and the built frontend. A Memgraph sidecar holds the match knowledge graph. | Consumption; 1 vCPU and 2 GiB for the app plus 0.5 vCPU and 1 GiB for Memgraph, always one replica |
| Container Apps environment | `matchmind-env` | Hosting environment | Included |
| Event Hubs | `matchmind-feed-ca7835` (Basic), hub `match-events` | The live match feed; local (SAS) auth disabled | About $11 per month |
| Container Apps Job | `matchmind-feed` (manual trigger) | Publishes a synthetic match to Event Hubs when a viewer kicks off a feed | Per second while running |
| Container registry | `ca7835cfc7a5acr` (Basic) | Image `matchmind-demo:v6`, plus imported `memgraph/memgraph:3.13.1`, `neo4j:5.26.32-community` and `python:3.12-slim` for graph tests | About $5 per month |
| Foundry resource / project | `matchmind-ai-studio` / `matchmind-ai` | Model deployment `gpt-4.1-mini`, GlobalStandard, 100 units | Per token |
| Application Insights | `matchmind-ai-studio-appinsights` (connected to the Foundry project) | Agent and app traces, also visible in Foundry → Tracing; connection string stored as a Container App secret | Per GB ingested |

The app authenticates to Foundry with its **system-assigned managed identity**, which holds Foundry User on `matchmind-ai-studio` and AcrPull on the registry. No API keys are stored. The image contains no `.env`, tests, research data or documentation.

## Graph database sidecar

Memgraph 3.13.1 runs in the same Container App as a second container, with a 768 MiB memory limit and telemetry off. The app reaches it at `bolt://localhost:7687` (`GRAPH_BACKEND=memgraph`, `GRAPH_URI`). Ingress only goes to the app's port 8000, so Bolt is not reachable from outside. At startup the app projects the match knowledge graph into Memgraph, retrying while the sidecar starts. It projects again if the corrected source changes. `/api/graph/knowledge` shows the backend, the projected state version, and whether the stored counts match NetworkX. If Memgraph is unavailable, the app keeps working on NetworkX and reports that.

The sidecar was added by a PATCH of the app template (`az rest`). `az containerapp update --image` changes only one container, so name it with `--container-name matchmind-demo` when updating the app image.

## Vision job

`matchmind-vision` (Container Apps Job, manual trigger, 4 vCPU and 8 GiB, image `matchmind-vision:v2`) runs auto-eventing on the broadcast clip and publishes the recovered events to Event Hubs. Its identity holds AcrPull on the registry and Event Hubs Data Sender on the hub. The app holds Contributor on the job, so `POST /api/feed/kickoff?source=vision` can start it, with a 20-minute cooldown. See [VISION.md](VISION.md).

## Event-driven feed

The app consumes the `match-events` hub in a background task, and `POST /api/feed/kickoff` starts the `matchmind-feed` job through Azure Resource Manager. Roles: the job holds Event Hubs Data Sender on the hub and AcrPull on the registry; the app holds Data Receiver on the hub and Contributor on the job only. See [EVENT_DRIVEN.md](EVENT_DRIVEN.md). Verified in production on 20 October 2026: one kick-off streamed a full match, with 1,079 of 1,079 events accepted, 0 rejected, 59 moments detected live and a final score of 2–3.

## Demo-mode safeguards (`MATCHMIND_ENV=demo`)

- **Read-only.** Corrections, review, publication, graph rebuilds and external ingestion are forced off whatever the environment says.
- **Synthetic data only.** Research datasets are off in the API, and absent from the image and the frontend bundle.
- **Model-cost control.** Model-backed endpoints (`/api/agents/run`, `/api/recap/agent`) are cached per match state and limited to 4 new runs per visitor per minute; excess requests get HTTP 429.
- **Production stays release-blocked.** `MATCHMIND_ENV=production` still refuses to start.

## Verified after deployment

- **Health and pages.** `/health`, `/ready` (mode `demo`), `/` and `/app` load.
- **API.** The squads, experience and recap APIs work, research returns 404 and writes are refused.
- **Live AI from the cloud.** An agent recap was written through the managed identity and fact-checked (FoundryChatClient, `live: true`, about 17 s).
- **Browser.** All 5 Playwright smoke tests pass against the public URL. They cover WebSocket streaming, Arabic right-to-left, the match graph, the "Why?" explanations and Ask the match.
- **Graph database (20 October 2026).** Memgraph holds 1,487 nodes and 7,118 relationships, projected in 0.4 s, and its counts match NetworkX. `/api/graph/impact` and `/api/graph/why` answer from Memgraph, and `/api/graph/roles` reports that the database's pass lanes agree. Graph rebuild over the API returns 403.
- **Ask the match from the cloud.** Questions are routed by the live model through the managed identity (`router: model`), and the answers are computed by code.

To re-run the browser tests against the deployment:

```
cd frontend
MATCHMIND_URL=<url> npx playwright test -c playwright.remote.config.ts
```

## Update the deployment

From the repository root, in PowerShell:

```powershell
az acr build --registry ca7835cfc7a5acr --image matchmind-demo:v4 --no-logs .
az containerapp update -n matchmind-demo -g rg-othniel.obasi-9233 --container-name matchmind-demo --image ca7835cfc7a5acr.azurecr.io/matchmind-demo:v4
```

`--no-logs` avoids an Azure CLI crash on Windows: streaming Vite's "✓" output fails under the cp1252 console encoding.

## Stop or remove

- **Pause.** Scale to zero to stop compute charges while keeping everything:

  ```
  az containerapp update -n matchmind-demo -g rg-othniel.obasi-9233 --min-replicas 0
  ```

- **Remove.** Delete the app, environment, registry and Application Insights resources. Leave the Foundry resource if the local app still uses it.

## Demo video

`docs/demo/matchmind-demo.webm` is a 2-minute recorded product tour with on-screen captions for each pipeline stage. It is recorded with `npx playwright test -c playwright.demo.config.ts`.
