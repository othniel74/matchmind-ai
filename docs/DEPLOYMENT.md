# Public demo deployment — updated 21 October 2026

**URL:** https://pitchlight.mangograss-8c9a0131.uksouth.azurecontainerapps.io

The app's routes:

| Path | Page |
| --- | --- |
| `/` | landing |
| `/app` | workspace: personalization, Ask the match, recaps, match graph, the Event Hubs feed, auto-eventing from video |
| `/app?view=studio` | Broadcast Studio |

## What runs where

All resources are in resource group `rg-othniel.obasi-9233`, UK South.

| Resource | Name | Purpose | Cost model |
| --- | --- | --- | --- |
| Container App | `matchmind-demo` | The app container serves the API, WebSockets and the built frontend. A Memgraph sidecar holds the match knowledge graph. | Consumption; 1 vCPU and 2 GiB for the app plus 0.5 vCPU and 1 GiB for Memgraph, always one replica |
| Container Apps environment | `matchmind-env` | Hosting environment | Included |
| Event Hubs | `matchmind-feed-ca7835` (Basic), hub `match-events` | The live match feed; local (SAS) auth disabled | About $11 per month |
| Container Apps Job | `matchmind-feed` (manual trigger) | Publishes a synthetic match to Event Hubs when a viewer kicks off a feed | Per second while running |
| Container Apps Job | `matchmind-vision` (manual trigger, 4 vCPU, 8 GiB) | Runs auto-eventing on the broadcast clip and publishes the recovered events to Event Hubs | Per second while running (about 10 minutes per run) |
| Container registry | `ca7835cfc7a5acr` (Basic) | Images `matchmind-demo:v11` and `matchmind-vision:v2`, plus imported `memgraph/memgraph:3.13.1`, `neo4j:5.26.32-community` and `python:3.12-slim` for graph tests | About $5 per month |
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
- **Model-cost control.** Model-backed endpoints (`/api/agents/run`, `/api/recap/agent`, the agent route of `/api/ask`) are cached per match state or fall back to the keyword router, and are limited to 4 new runs per visitor per minute; excess requests get HTTP 429.
- **Job control.** One synthetic feed runs at a time (60 s cooldown), and one vision run at a time (20-minute cooldown).
- **Production stays release-blocked.** `MATCHMIND_ENV=production` still refuses to start.

## Verified after deployment

- **Health and pages.** `/health`, `/ready` (mode `demo`), `/` and `/app` load.
- **API.** The squads, experience and recap APIs work, research returns 404 and writes are refused.
- **Live AI from the cloud.** An agent recap was written through the managed identity and fact-checked (FoundryChatClient, `live: true`, about 17 s).
- **Browser.** All 5 Playwright smoke tests pass against the public URL. They cover WebSocket streaming, Arabic right-to-left, the match graph, the "Why?" explanations and Ask the match.
- **Graph database (20 October 2026).** Memgraph holds 1,487 nodes and 7,118 relationships, projected in 0.4 s, and its counts match NetworkX. `/api/graph/impact` and `/api/graph/why` answer from Memgraph, and `/api/graph/roles` reports that the database's pass lanes agree. Graph rebuild over the API returns 403.
- **Ask the match from the cloud.** A Foundry agent calls Pitchlight's MCP tools through the managed identity (`router: mcp_agent`), in English, Spanish and French; answers come from the tools.
- **MCP (20 October 2026).** All 13 tools answer at `/mcp` from an external MCP client.
- **Event Hubs feed (20 October 2026).** One kick-off streamed a full match: 1,079 of 1,079 events accepted, 0 rejected.
- **Vision job (21 October 2026).** 601 frames processed in 10.3 minutes; 12 events recovered, and all 12 accepted by the app from Event Hubs.
- **Foundry tracing.** Agent, model and MCP tool spans from `matchmind-backend` appear in the Foundry project's Application Insights.

To re-run the browser tests against the deployment:

```
cd frontend
MATCHMIND_URL=<url> npx playwright test -c playwright.remote.config.ts
```

## Update the deployment

From the repository root, in PowerShell:

```powershell
az acr build --registry ca7835cfc7a5acr --image matchmind-demo:<tag> --no-logs .
az containerapp update -n pitchlight -g rg-othniel.obasi-9233 --container-name matchmind-demo --image ca7835cfc7a5acr.azurecr.io/matchmind-demo:<tag>

# the vision job
az acr build --registry ca7835cfc7a5acr --image matchmind-vision:<tag> -f Dockerfile.vision --no-logs .
az containerapp job update -n matchmind-vision -g rg-othniel.obasi-9233 --image ca7835cfc7a5acr.azurecr.io/matchmind-vision:<tag>
```

`--no-logs` avoids an Azure CLI crash on Windows: streaming Vite's "✓" output fails under the cp1252 console encoding.

## The pitchlight app and the old address

The live app is the Container App **`pitchlight`** (its main container keeps the name `matchmind-demo`). It was created on 22 October 2026 from the old app's configuration. Its own managed identity holds the same roles: AcrPull on the registry, Foundry User on the Foundry resource, Azure Event Hubs Data Receiver on `match-events`, and Contributor on the `matchmind-feed` and `matchmind-vision` jobs. The old app `matchmind-demo` runs the same image with `PITCHLIGHT_REDIRECT_URL` set. It answers every HTTP request with a 301 to the same path on the new address, and starts no data store, graph, MCP session or Event Hubs consumer, so the two apps never compete for the feed.

Verified on the new address after the move: health and readiness, Memgraph in sync (1,487 nodes), Ask the match through the Foundry agent and MCP, a live multi-agent recap, MCP `initialize` (server `pitchlight`, 15 tools), an Event Hubs match (1,079 of 1,079 events accepted), a vision job run (12 events accepted), all 6 browser tests, and a load test with 0 errors.

## Stop or remove

- **Pause.** Scale to zero to stop compute charges while keeping everything:

  ```
  az containerapp update -n pitchlight -g rg-othniel.obasi-9233 --min-replicas 0
  ```

- **Remove.** Delete the app, environment, registry and Application Insights resources. Leave the Foundry resource if the local app still uses it.

## Demo video

`docs/demo/pitchlight-submission.mp4` (1:47) is the submission video, recorded against the live deployment with `MATCHMIND_URL=<url> npx playwright test -c playwright.video.config.ts`. The story replays the match at `?speed=2` and requests the full-time AI recap in advance, one request at a time, so nothing waits on camera. The recording is trimmed at the start and encoded as H.264.
