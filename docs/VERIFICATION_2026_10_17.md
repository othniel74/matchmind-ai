> **Historical document.** It records MatchMind at the date it was written; its test counts, limitations and plans are not current. For the current state see the [README](../README.md) and the [documentation index](README.md).

# Verification 17 October 2026

## Implemented and checked locally

- Local Vite proxy targets `127.0.0.1:8000`; nginx retains the Compose service hostname.
- `npm ci` dependency lockfile added; production TypeScript/Vite build passes.
- Synthetic shots now have goal/saved outcomes. The scoreboard is derived from goals; the default full replay ends 1–2.
- Generated completed passes contain explicit same-team recipient IDs. NetworkX includes the last completed pass without requiring a successor action. Legacy recipient-free fixtures retain a labeled proxy fallback.
- SQLite replay storage is opt-in through `MATCHMIND_EVENT_DB`. Atomic inserts, content hashes, seed/generator isolation, restart persistence and conflicting-write rejection are tested. Compose mounts the file on a named volume. This stores complete synthetic replays, not incremental provider ingestion.
- WebSocket clients can resume at `start_minute`; the frontend reconnects automatically and discards duplicate minute frames. Invalid replay parameters close with code 1008. Backend restart recovery was observed locally.
- Graph comparison is withheld until minute 20, preventing future-window data from appearing early in the replay.
- Graph projection replacement now uses a single transaction and creates recipient-only players. Mocked tests verify transaction calls and no commit on failure; they do not prove real database rollback or Cypher compatibility.
- `/api/runtime` reports configuration and storage mode. `/api/agents/run?require_live=true` rejects deterministic fallback with HTTP 503.
- Optional Microsoft adapter imports `AzureAIClient` directly from `agent_framework_azure_ai`, uses the installed release's `as_agent` API, and closes owned client/credential transports. SDK imports and client/agent construction were tested without cloud calls. Compatible Framework rc6, Azure Projects 2.0.0 and Azure Identity versions are pinned; `pip check` passes. AzureAIClient emits a deprecation warning, so migration to FoundryAgent remains future work. A separate CI job now checks this optional dependency set. Set `INSTALL_AGENTS=true` for the optional container build; real container authentication is still unverified.

## Verification results

- Backend: 44 tests passed in the isolated Python 3.12 Microsoft SDK environment, including actual SDK client/agent construction. The base environment passes 43 tests and skips the SDK-only check.
- Offline evaluation: 40/40 checks passed across five fixed seeds; root evaluation JSON refreshed.
- Frontend: production build passed after final UI changes.
- Browser: full replay reaches minute 90, 360 events, 14 insights and the same 1–2 score. Replay resets score/history/queue. Fan mode, graph metrics, Broadcast Studio, English/Spanish audience switching and evidence JSON inspected. No console errors observed in clean replay checks. Backend interruption/reconnection was checked separately.

## Remaining external verification

- Docker is not installed on this machine. Compose build/start and live Memgraph/Neo4j parity/restart tests were not run.
- Azure CLI has a cached subscription, but resource access fails with an expired refresh token. User sign-in through `az login` is required.
- Foundry project endpoint and model deployment are not configured. Real inference, real agent execution and Azure hosting remain unverified. SDK import/construction checks are not proof of live integration.
- Production ingestion, PostgreSQL migrations, distributed concurrency, authentication, telemetry, continuous possession and calibrated match realism remain future work. SQLite replay persistence does not satisfy all of those requirements.

## Reproduce

From `backend`: `python -m pytest -q`, then `python -m evaluation.run --output ../evaluation-report.json`.

From `frontend`: `npm ci`, then `npm run build`. Start the backend and frontend using the current README's Windows commands; open `http://127.0.0.1:5173`.

The original Word requirements files remain unchanged; this report records implementation progress against them. Microsoft API reference: https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.azure.azureaiclient?view=agent-framework-python-latest

## Interface redesign verification

The local dashboard now uses a responsive navigation rail, a redesigned scoreboard, team-comparison bars, cumulative event-activity chart, SVG passing network and selectable historical observations. Broadcast Studio includes a rebuilt preview and queue. Snapshot export downloads the current state as JSON.

The production frontend build passes. Browser checks covered desktop at 1440 pixels and mobile at 390 pixels with no horizontal overflow, replay and score updates, analyst/fan mode, historical insight selection, English/Spanish overlays, keyboard arrow navigation between tabs, and JSON download. No browser console errors or warnings were observed during the final checks. This work remains local; no Azure or Sites deployment was performed.

## Broadcast preview presentation modes

Broadcast Studio now offers Full screen, Reset view, Escape-to-restore and Pop out. The detached preview receives match state and the selected/localized overlay from the studio through a same-origin BroadcastChannel. A tab link is available when a separate window is unsuitable; popup-blocking notices are explicit. Expanded mode traps keyboard focus, restores focus and page scrolling when closed, and falls back to filling the application viewport if the browser rejects native fullscreen.

Verified locally: production build; expanded viewport layout; Reset view and Escape restoring the normal layout without replay reset; detached preview receiving clock/score and English-to-Spanish overlay changes. No console errors observed. Native fullscreen remains dependent on the browser's Fullscreen API permissions; the in-app browser's expanded fallback was verified.

## Movable overlay controls

Broadcast overlays now use a compact layout and a 35% background opacity by default. An Overlay controls menu adjusts background opacity from 15–80%, hides/shows the overlay and resets its position. Dragging supports pointer/touch input; focused overlays support arrow keys and Home. Normalized positions and ResizeObserver measurements keep the graphic inside the preview when resizing between inline and expanded modes. Background transparency is independent of text readability.

Verified: frontend production build; actual pointer drag; opacity slider changing computed background alpha; hide/show; position reset; keyboard Home; bounds after exiting expanded mode; no console warnings/errors in these checks. The shared canvas applies these controls in the studio and detached preview.

## Landing page verification

The landing page at `/` now leads into `/app` and `/app?view=studio`. It includes custom generated stadium artwork, a backend-driven snapshot explorer and an expandable FAQ. Frontend build and browser checks passed for responsive layout, mobile menu, audience/language changes, match-clock scrubbing and direct studio navigation. See `LANDING_PAGE_DESIGN.md` for the artwork prompt and implementation details. This is a local-only addition.

## Synthetic player preview

Broadcast Studio renders 22 numbered players, team and goalkeeper kits, an active-player ring, ball and pass cues. State and WebSocket frames include deterministic pitch state. Actors and completed-pass recipients use event coordinates; remaining positions are illustrative formation movement. This is not measured tracking or video.

Verification: 48 backend tests pass, offline evaluation 40/40, and frontend production build passes. Browser checks confirmed 22 rendered players, changing ball coordinates during replay, and full-screen layout with readable numbered shirts. The shared BroadcastCanvas also renders detached previews.


## 3D human player rendering

Broadcast Studio now lazily loads Three.js to render 22 procedural human athletes with contoured torsos, faces, hair, articulated arms/knees, numbered kits, socks, boots, lit materials and ground shadows. Player detail opens an optional inset of the active athlete. These are stylized synthetic models, not photorealistic scans or real-player likenesses. Existing event-derived positions and illustrative off-ball movement are unchanged.

The renderer caps pixel density and frame rate, pauses idle drawing after full time, respects reduced motion, disposes GPU resources on unmount and retains the vector fallback when WebGL is unavailable or lost. The Three.js chunk is loaded only when the broadcast canvas mounts. Browser checks covered live movement, expanded view and active-player detail. Production build passes; Vite reports the expected size advisory for the separate Three.js chunk.


## Detailed textured footballers

Two free MIT-licensed Rocketbox footballers now replace the procedural bodies after loading. Each player has an independent skin rig and animation mixer, with shared texture/geometry resources. Converted GLBs total about 10.75 MB; source FBX/TGA and temporary PNG inputs stay outside the production public directory. Full-body and face views expose the actual character detail. Both variants are reused across the teams; this is not 22 unique people or fully photorealistic scans. See PLAYER_ASSETS.md for source paths, conversion and checks.


Verified shipping GLBs in the browser: all eight asset integration checks pass (maps/clips, both rigs, independent clones, run deformation, animation isolation, reduced-motion pause, retained face/body textures and safe instance disposal). Live expanded rendering and face close-up showed no console errors or warnings. Production build passes with the existing separate Three.js chunk size advisory.


## Formation continuity and keeper orientation

Fixed event-driven teleportation that caused zigzag player movement. Player targets now come from a role-constrained 4-3-3: a back four, midfield three and front three shift as a unit with smoothed activity/possession context. Canonical event coordinates remain intact in the action/ball activity cues; they no longer replace individual formation positions. This is an illustrative formation, not an inferred real team's tactics.

The frontend uses field-metre motion with bounded speed, acceleration and turn rate, braking through target reversals and stopping at full time. Motion state is independent of viewport geometry. Keepers remain in their own penalty areas and face the field/ball even while retreating or shuffling. Initial home/away facing directions were corrected.

Verified: 50 backend tests pass (three existing optional-SDK deprecation warnings), including full-replay formation continuity, role-line ordering, goalkeeper bounds/facing and preservation of event evidence. The standalone motion regression checks pass for speed, acceleration, displacement, turning, target reversal, both keepers, full-time braking and reduced motion. Production frontend build passes with the existing separate Three.js chunk advisory. Browser visual checks confirmed formation spacing and keeper orientation in expanded replay.
