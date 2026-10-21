# Synthetic match simulator and evaluation — 19 October 2026

Generator version `possession-v3` replaces the earlier fixed four-events-per-minute stream. It is still synthetic: teams, players and events are invented, and nothing is fitted to a licensed dataset.

## What the simulator models

- **Clock:** two 45-minute halves on a seconds-resolution clock. Each half starts with a kick-off (home first, away second). Stoppage time is not modelled.
- **Possessions:** each possession starts with a set piece, a recovery or a won tackle. It continues as passes until a turnover, foul, shot or the ball going out of play. Time between actions and restart delays are drawn per action.
- **Passing:** the passer and recipient are chosen by pitch zone from an illustrative 4-3-3. Completion depends on destination zone, pass length, opponent pressing and missing players.
- **Set pieces:** kick-offs, throw-ins, goal kicks, corners, free kicks (including direct shots) and penalties are carried on the `set_piece` field.
- **Shots:** each shot carries a distance- and angle-based `xg`. The outcome is goal, saved, blocked or missed, and the restart follows the outcome.
- **Discipline:** fouls lead to free kicks, or to penalties inside the box. Fouls can lead to yellow, second-yellow or straight red cards. Sent-off players leave the lineup.
- **Substitutions:** 3–5 per team in 2–3 second-half windows, made only at dead balls. The incoming player is in `replacement_player_id`.
- **Team quality:** a hidden per-match strength difference between the teams, which produces imbalance in possession and chances.

A match has about 1,100 events. The validator now also rejects:
- players acting after being substituted or sent off
- replacements who appeared before coming on
- inconsistent bookings
- xG on events that aren't shots
- invalid set pieces

## Statistics

`statistics()` adds the following, all computed only from visible events:
- time-based possession share
- shots on target and xG
- corners and fouls
- yellow and red cards
- substitutions and tackles won

A possession runs from its first event to the next possession's first event. The latest possession ends at its own latest event, so no future data is used.

## Hidden scenario labels

`simulate_match(seed)` returns the events plus a `Scenario`. In about 75% of seeds, one team starts a territorial shift between minutes 50 and 70. The rest are controls with no shift. The default demo seed keeps the documented away shift from minute 58.

The label is ground truth for evaluation only. Insight, narrative and API code never receive it, and `/api/match` no longer reports a scenario name.

## Evaluation

`python -m evaluation.run` uses four separate seed sets. Detector thresholds were tuned on seeds 1000–1199, and the interpretation threshold was calibrated on 1000–1399. Both ranges are excluded from all four sets.

| Measurement | Seeds | Result (19 Oct 2026) |
| --- | --- | --- |
| Correctness checks: replay, structure, evidence, overlays, language parity, review routing | 5 fixed seeds | 45/45 pass |
| Realism: 11 per-team averages vs broad top-league ranges | 2000–2099 | 11/11 within range |
| Count-change alerts, scored as if they claimed a shift | 3000–3199 | precision 0.30 (95% CI 0.25–0.35), recall 0.54 (0.46–0.62), 1.49 false alerts per control match |
| Shift interpretations meeting the calibrated threshold | 3000–3199 | precision 0.52 (0.35–0.68), recall 0.10 (0.06–0.16), 0.11 false alerts per control match |
| Interpretation tier at shift strength 0.5 / 1 / 1.5 / 2 / 3 | 5000–5059 | precision 0.30 / 0.33 / 0.44 / 0.50 / 0.63; recall 0.07 / 0.09 / 0.09 / 0.16 / 0.23 |

## Fact and interpretation

Each insight is now an observed fact (`claim_type: observed_fact`, type `advanced_activity_increase`) with an attached `interpretation`:
- **The fact** is the count change, which the evidence gate recomputes exactly. Overlays, narratives and agent text carry only the fact.
- **The interpretation** is `possible_territorial_shift`. Its z-score is the window difference divided by its overdispersed null spread (overdispersion factor 3.3).
- **Calibrated threshold:** z ≥ 2.5 keeps false alerts to about 0.1 per match.
- **Always reviewed:** its status is always `review_required`, because even strong injected shifts don't reach 0.8 precision.
- **Tamper check:** `validate_insight` recomputes the z-score and status, so a forged confidence fails.

A stronger shift raises recall, but false alerts stay level at about 0.12 per control match. Precision is therefore limited by normal match swings, not by thresholds. Real validation still needs real matches labelled by analysts. Every synthetic result here is partly circular, because the same code defines the shift and detects it.

Realism averages per team:

| Metric | Average |
| --- | --- |
| Passes | 445 |
| Pass completion | 79.9% |
| Shots | 12.2 |
| Shots on target | 4.8 |
| Goals | 1.57 |
| xG | 1.53 |
| Corners | 4.2 |
| Fouls | 9.9 |
| Yellow cards | 1.75 |
| Red cards | 0.055 |
| Substitutions | 4.2 |

How detector scoring works:
- Alerts are grouped into episodes (consecutive minutes for the same team).
- An episode counts as correct only if it names the shifting team and starts 1–20 minutes after the shift begins.
- Mean detection delay is about 11 minutes, with about 1.5 false alert episodes per control match.

## Findings and limits

- **Shift interpretations are not fit for unreviewed publication.** They fall short of the proposed 0.8 precision bar, so they are routed to review. A ten-minute count of advanced-area events varies about 3.3 times as much as Poisson noise, because events cluster within possessions.
- **Other signals didn't fix it.** Tested alternatives, each tuned and then checked on held-out seeds, all stayed at about 0.5 precision or below:
  - counting possessions instead of events
  - counting balls won in the opponent's half
  - CUSUM change detection
  - fifteen-minute windows
- **Possession varies too little.** The spread of possession share between teams (standard deviation about 4.7 points) is narrower than in real matches.
- **The ranges are bounds, not targets.** Reference ranges are broad plausibility bounds from public aggregate statistics. They are not a fit to licensed data.
- **Pitch animation is unchanged in kind.** The pitch view stays an illustrative 4-3-3:
  - Slots now follow substitutions (`occupant_id`) and sending-offs (`on_pitch`).
  - `player_id` remains the stable slot key that the renderers use.
  - The 3D illustrative play is rebuilt without sent-off players.

## Ground-truth tracking and broadcast video (21 October 2026)

The simulator now also produces **positions**, not only events:

- `app/tracking.py` turns the event stream into 25 Hz tracking for the ball and every player on the pitch. The ball is at each event's location at its time and flies along each pass at its ball speed. Players run, speed-limited at 8.5 m/s, between their team's shape and the actions they take part in. Substitutions and red cards are respected, and the output is deterministic.
- `frontend/render.html` renders that tracking as broadcast video: a main camera panning with play, regulation markings, animated players in team kits, and the exact camera parameters recorded for every frame.

Together they make a synthetic dataset that real football cannot provide: broadcast video with **perfect labels** for every player, the ball, the camera and every event. MatchMind uses it to measure auto-eventing from video stage by stage ([VISION.md](VISION.md)).

## Compatibility

- **Replay keys:** stored replays are keyed by generator version (`generator-possession-v3:seed-N`), so earlier SQLite replays are left untouched.
- **Evidence Lab data:** foundation stream IDs include the base event hash, so existing Evidence Lab data stays under the previous stream and new views start a fresh one.
- **Older payloads:** older event payloads without the new fields still load, because all new fields default to `None`.
