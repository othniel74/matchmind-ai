# Hackathon brief coverage — 20 October 2026

This document maps each requirement of the brief to what MatchMind does, where the code lives, and how it is verified. All data is synthetic, and all clubs and players are fictional.

## (i) One pipeline with five stages

| Stage | What MatchMind does | Where | Verified by |
| --- | --- | --- | --- |
| **(a) Ingest** | Events arrive one at a time through **Azure Event Hubs**: a Container Apps Job publishes the match and the app consumes it live ([EVENT_DRIVEN.md](EVENT_DRIVEN.md)). They can also arrive through `/ws/live`, or from an external feed through `POST /api/live/sessions/{id}/events` (token-guarded). `StreamValidator` checks each event against the stream so far; an invalid event is refused without corrupting state. | `app/live.py`, `app/core.py` | `test_intelligence.py`: the live pipeline produces exactly the same 101 moments as batch analysis, rejects bad events, and the ingest API is guarded. |
| **(b) Interpret** | Team statistics (possession by time, xG, shots, passing, cards, set pieces), player statistics and ratings, passing networks, and control/chaos, tempo and momentum states. | `core.py`, `players.py`, `dynamics.py`, `graph/` | Player totals reconcile with team totals; dynamics states match their definitions; all are causal. |
| **(b+) Knowledge graph** | One typed graph of everything verified: matches, teams, players, possessions, events, moments and claims. On it run network roles for both teams (hub, key link, PageRank), xG chain and build-up, goal build-up chains and network-change moments. A Memgraph copy is queried in Cypher in the deployment. | `knowledge.py`, `graph/` | `test_knowledge.py`. `test_graph_db.py` checks Memgraph and Neo4j for exact parity with NetworkX, in Azure. |
| **(c) Explain** | Each moment carries why it matters: opener, equaliser, go-ahead, extends lead or pulls one back, with chance quality and assist; "down to ten players"; control, chaos and momentum with the measured numbers behind them. | `moments.py` | Goal explanations match the score sequence; every moment cites evidence events. |
| **(d) Render** | Timed, machine-readable overlays with clock, duration, priority, evidence IDs, player IDs and personalization flags, rendered in Broadcast Studio and a detached preview. | `overlays.py`, `/api/overlays` | Overlay tests; browser tests including Arabic right-to-left. |
| **(e) Personalize** | Viewing modes (fan, analyst, broadcast), favourite club, favourite players, follow-one-player mode, track-one-metric mode, and 7 languages. Personalization changes selection and emphasis, never facts. | `experience.py`, `Experience.tsx` | `test_personalization_changes_selection_not_facts`; browser test of the full profile in Spanish. |

## (ii) Real-time match intelligence

| Feature | Status |
| --- | --- |
| Player identification and name tagging | Named fictional squads (32 players with shirt numbers and positions). Names appear in events, the pitch, overlays and the live stream. |
| Speed and distance indicators at thresholds | Synthetic physical model (distance and top speed per player-minute, causal, respecting substitutions and red cards). Tags fire at 33 km/h and at 5 km and 10 km covered; they are labelled synthetic. |
| Pass quality | Pass distance, accuracy, and a deterministic 1–10 difficulty rating (length, direction, final-third target, pressure, set-piece type). |
| Ball speed and shot speed | Every pass and shot carries a synthetic ball speed; team mean pass speed and maximum shot speed are reported. |
| Auto-eventing from video | Not implemented. The brief lists it as a feature to consider; the product works from event feeds. |

## (iii) Narrative generation

- **Key narratives:** live moments with explanations.
- **Player-performance context:** the player-focus card shows rating, goals, assists, xG, passes, pass difficulty, tackles, distance and top speed.
- **Milestones:** 25, 50 and 75 completed passes, braces, hat-tricks, speed and distance.
- **Why this moment:** each goal, big chance and key-link moment can be expanded. It shows the build-up, the players' network roles in the 15 minutes before, the previous moment, and the evidence.
- **Ask the match:** viewers ask in any of the 7 languages. The model only routes the question to a fixed intent, and code answers from the graph, claims and statistics, with evidence. It refuses questions outside the match data.
- **Correction impact:** a correction lists every moment, claim, overlay and recap that it changes.
- **Match recaps:** half-time, full-time and so-far recaps, deterministic, in 7 languages, with every number a validated claim. An agent-written recap is fact-checked against verified results, scorers and statistic leaders.

## (iv) Explainability

Control vs chaos (turnovers per minute, passes per possession, pass share), tempo (on-ball events per minute) and momentum (share of attacking-area actions). The thresholds are percentiles of the simulator's own distribution. Tactical interpretations stay in review, because their measured precision is below the bar for unreviewed publication (see `SYNTHETIC_SIMULATOR.md`).

## (v) Data innovation

The possession-based synthetic generator produces:
- halves, set pieces, fouls, cards and substitutions
- shot xG, ball and shot speed, and pressure flags
- hidden scenario labels for evaluation

Realism checks: all 11 per-team averages fall within broad top-league ranges on held-out seeds.

## (vi) Multi-language storytelling

Seven languages: English, Spanish, French, Portuguese (Brazil), German, Italian and Arabic (right to left). One registry holds every template, and facts are identical in every language.

Agent text in any language is checked by a fact checker: a model extracts statements, and code verifies them against data.

| Live fact-check result | Value |
| --- | --- |
| Wrong statements let through | 0, across 264 scored checks on three held-out sets |
| Correct sentences wrongly blocked (safe side) | about 4–7% |

## Compliance

- **Synthetic data only.**
  - Real research views are off by default (`MATCHMIND_RESEARCH_ENABLED`, `VITE_ENABLE_RESEARCH`).
  - Research data is excluded from builds and images.
  - Research code loads only when enabled.
- **Fictional names.** Clubs (Calderbrook FC, Merridge Athletic) and players are fictional. No Premier League names, logos or data.
- **Public demo.** It runs read-only (`MATCHMIND_ENV=demo`), and model calls are cached and rate-limited per visitor.
