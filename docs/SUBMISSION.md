# Submission: Microsoft Premier League Hackathon

## Category

**Best Multi-Agent System**

Pitchlight's agents have distinct roles. The insight ranker, tactical analyst, storyteller and audience editor write; a **fact checker** extracts every statement for code to verify; a publication gate decides what ships. They share state through an Agent Framework workflow, hand off along typed edges, retry when rate limited, and fall back to verified text when a draft fails. A separate Q&A agent reaches the match through Pitchlight's own MCP server. A single agent could not both write fluent narratives in seven languages and guarantee that none of them states an unsupported fact. That guarantee comes from the agents checking each other. Live, 20 of 21 recaps across 7 languages were published and the last was blocked safely; the fact checker has 0 unsafe passes in 264 live checks. **The collaboration is visible**: under every AI recap, the run shows each agent's draft, every statement the fact checker extracted with code's verdict, and any rewrite loop.

It also fits **Best Use of Microsoft Foundry** (models, tracing, release evaluations) and **Best Enterprise Solution** (provenance, corrections, the release gate, managed identity).

## Pitch

**Pitchlight turns synthetic football events into explainable match intelligence for studios, broadcasters and fans, live, in seven languages, on Azure.**

A match feed streams through **Azure Event Hubs** into an app on **Azure Container Apps**. It validates every event, detects the moments that matter and explains why. A goal's build-up, a new key link in the pass network, a momentum swing: each is backed by evidence and a match knowledge graph mirrored in Memgraph.

Narratives and recaps come from a **Microsoft Agent Framework** multi-agent workflow on **Microsoft Foundry**. Writers draft, a fact checker extracts every statement and code verifies it against the data, and a publication gate ships only verified text. Viewers can **ask the match** anything: a Foundry agent calls Pitchlight's own **MCP** tools, so answers come from verified facts, never the model's imagination.

The same intelligence becomes two genuinely different experiences: a data-rich analyst view and a clear fan view, with favourite club and players, follow-one-player and single-metric modes. It also becomes timed, machine-readable overlays for Broadcast Studio, including Arabic right to left.

Foundry evaluations score what is published: groundedness 4.71/5 and no unsupported numbers across 21 outputs in 7 languages. Structured output guarantees every agent reply has the expected shape. Agent, model and tool calls are traced in Foundry. Everything authenticates with managed identity, with no keys.

Pitchlight also does **auto-eventing from video**. It renders its synthetic match as broadcast video, and a vision pipeline (pitch calibration, RT-DETR detection, team and identity tracking, ball tracking) recovers passes, goals and speeds from the pixels. Because the video is synthetic, every number is scored against perfect ground truth: calibration 3 cm, players 87%, events precision 87.5% including the goal. A Container Apps Job runs it in Azure and streams the recovered events through Event Hubs into the same verified pipeline.

For analysts, the **explorable pass network** shows directed passing lanes and which of them move the ball forward. Click a player for their passing partners, or use *Show change* to see which lanes grew or faded against the previous fifteen minutes. **Tactical changes** compare the ten minutes before and after each substitution, covering pressing (PPDA), defensive shape and attacking output, each ranked against the match's own swings and never claimed as the cause.

It is built for production: 25 concurrent viewers are served at 32 requests per second with a 95th percentile of 0.7 s on one vCPU. A provider adapter checked offline on 64 real public matches accepted 81,931 events and rejected none. The product itself runs only on synthetic data.

**The problem it solves:** live sports AI is only as useful as it is trustworthy. Pitchlight makes match intelligence fast and personal enough for live play, and verifiable enough to put on screen.

## Microsoft and Azure technologies

Microsoft Foundry (models, evaluations, tracing) · Microsoft Agent Framework · Model Context Protocol · Azure Container Apps and Container Apps Jobs · Azure Event Hubs · Azure Container Registry (Tasks) · Application Insights / OpenTelemetry · Managed identity and Azure RBAC · GitHub Actions · GitHub Copilot agent mode (via `.vscode/mcp.json`)

## Testing instructions

No sign-in is needed. The demo is free, read-only and uses synthetic data.

1. Open https://matchmind-demo.mangograss-8c9a0131.uksouth.azurecontainerapps.io and choose **Experience the match**, or go straight to `/app`.
2. The match replays in about 90 seconds (add `?speed=2` to the URL for a faster replay). In **Your moments**, press **Why?** on a goal.
3. In **Your view**, change the viewing mode, language (try Arabic), favourite club, followed player or tracked metric.
4. **Ask the match:** try "Who is Merridge's key player?" or a question in Spanish. The answer is labelled *Foundry agent via MCP*.
5. **Analysis** (sidebar): the match graph. Click a player or a passing lane; in *Last 15 min*, press *Show change*. Also team statistics, and **What changed after a substitution** (available once the replay passes about 70′), plus pressing and shape.
6. **Live data** (sidebar): press **Kick off a live match**. Events start arriving in about 30 seconds; one feed runs at a time.
7. **Match recap:** choose **So far**, **Half-time** or **Full-time**, or **AI recap** for the agent-written, fact-checked version. Open *How the agent steps wrote this* to see each agent's draft and every statement with its verdict.
8. **Broadcast Studio** (sidebar, or `/app?view=studio`): pick a language and select an overlay.
9. **Video AI** (sidebar): play the clip. Boxes show what the vision pipeline recovers from the pixels, the minimap compares it with the truth, and the scorecard gives the measured accuracy. **Process this video on Azure** runs the vision job (about 15 minutes on CPU), and its events then arrive in the Event Hubs panel.
10. MCP clients can connect to `/mcp` (streamable HTTP).

Model-backed actions are limited to 4 per visitor per minute, and repeated requests are served from cache.

## Links

- Repository: https://github.com/othniel74/matchmind-ai
- Video: upload `docs/demo/pitchlight-submission.mp4` to YouTube or Vimeo and paste the public link here.
