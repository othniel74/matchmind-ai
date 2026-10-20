# Local real-data research — 18 October 2026

Broadcast Studio > Preview source now includes Synthetic demo, SkillCorner, Metrica, and StatsBomb. Each research match has its own clock and evidence. The surrounding synthetic dashboard and overlay queue are not combined with a research match. These historical datasets do not provide live feeds or licensed match video.

## StatsBomb

Source: https://github.com/statsbomb/open-data (now redirected to Hudl's official open-data repository). Match 3869685: Argentina v France, World Cup final, 18 December 2022. Imported the full 4,407-event file, lineups, competition match metadata, official logo, README and published user agreement.

`/app?view=statsbomb` shows an event-order cutoff, source score, pass counts, shot map, source expected goals and NetworkX directed weighted passing networks. Select a shot or passing connection to inspect the originating source event ID. Source 120 x 80 coordinates are normalized for display. Network nodes are average event locations, not tracked positions or a formation. Only completed passes with an explicit recipient become edges. Every edge retains its source event IDs.

The complete match produces 3-3, plus a separate 4-2 shootout. Argentina: 560/693 completed passes, 20 shots, 2.7583 xG. France: 434/570, 10 shots, 2.2726 xG. The graph includes 994 completed pass events across 272 directed connections. Period 5 is excluded from match goals, shots and xG. Own goals are credited to the opposing team. Cutoffs follow event order because stoppage-time clocks overlap later periods.

StatsBomb's published agreement restricts raw-data redistribution and commercial exploitation. This integration is a local noncommercial research demo with official attribution/logo; it is not licensed as a commercial feed. Source files remain in backend/data/research/statsbomb, excluded from Git and Docker context, and are not bundled as frontend public assets. No publication or deployment was performed. Review the retained LICENSE.pdf and obtain appropriate permissions before changing that scope.

## Metrica Sports

Source: https://github.com/metrica-sports/sample-data. Imported the first 3,001 synchronized 25 Hz tracking frames of anonymous Sample Game 1 (source frame 1–3001, source time 0.04–120.04 seconds), and 35 events whose start is inside that excerpt. The complete event CSV is retained locally for provenance; only excerpt events are served by the adapter. Source README usage notice is preserved. No blanket commercial or redistribution license is assumed.

`/app?view=metrica` renders both teams and ball from recorded positions and exposes clickable synchronized events, actor highlighting and event-path cues. Play/pause, seek, reset and speed controls use the same tracking clock. Selecting evidence seeks to `(source_frame - 1) / 25`, with the source 0.04-second offset removed. Events sharing a frame can still be selected individually.

The source coordinate system is 0–1 over a 105 x 68 m pitch; the adapter converts this into the shared centered-metre tracking schema, then the renderer normalizes positions. Tracking quality flags and ball height are unavailable and labeled accordingly. Player names are anonymized. Goalkeeper roles (Player11/Player25) are inferred from starting positions. Models, kits, body orientation and animations are illustrative.

The excerpt includes a Home shot with source subtype HEAD-ON TARGET-GOAL. Source-derived score and event counts follow the replay clock; the goal is counted only at the shot's source end frame (2309), not in advance at its start frame. Recorded pass counts do not claim completion rates.

## Reproduce and run

From the project root, run `python tools/import-research-data.py`. It downloads from official repositories and retains SHA-256 hashes and source URLs in each provider's provenance.json. Upstream master may change; retained hashes identify the local snapshot. Restart the backend after replacing the sample (the StatsBomb source loader caches one match).

Run the existing local backend and Vite frontend. No Azure, credentials, subscriptions or paid assets are used. Local API resources are allowlisted; unknown names return 404 and absent datasets return 503. Docker excludes backend/data; the research samples must not be added to a public image without resolving provider permissions.

## Verification

55 backend tests passed across the full run and a rerun of the storage test with a writable temporary directory; the first runs encountered Windows temporary-directory setup errors. Three pre-existing optional SDK deprecation warnings remain. New tests cover complete-pass evidence, shootout/own-goal treatment, event cutoffs, API validation, final-match result and all Metrica event/frame alignments.

`node --experimental-strip-types tools/check-tracking.ts` verifies all 1,201 SkillCorner frames and 3,001 Metrica frames, coordinate round trips, frame rates, interpolation, absent ball handling, seek bounds and Metrica goal timing. Local sample import is required for the Metrica portion. The production frontend build passes. Browser QA verifies source selection, StatsBomb cutoff changes, network evidence selection and Metrica event seeking/playback.
