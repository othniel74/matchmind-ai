# Real data providers

MatchMind's analytics run on its own event contract (`core.Event`). A **provider adapter** maps a provider's events into that contract. The same `StreamValidator` that guards the synthetic feed then checks every adapted event, so claims, statistics, pass networks, narratives and tactical analysis run unchanged on real data.

## StatsBomb (open-data format)

[app/providers/statsbomb.py](../backend/app/providers/statsbomb.py) adapts StatsBomb's JSON event format:

| StatsBomb | MatchMind |
| --- | --- |
| Home team (given, or the first Starting XI) | `home`, the other team `away` |
| Players, with shirt numbers from lineups or the Starting XI | `<team>-<shirt>`, provider names kept in the returned roster |
| 120 × 80 pitch, each team attacking left to right | team-relative 0–100 |
| period, minute, second | the same, with the new `period` field, so stoppage and extra time are valid |
| Pass (recipient, end location, kick-off/corner/free kick/throw-in/goal kick) | `pass` with recipient and set piece |
| Shot (outcome, xG, penalty/free kick) | `shot` with outcome, xG and set piece |
| Duel (tackle), Ball Recovery, Interception | `tackle`, `recovery` |
| Foul Committed, cards on fouls and Bad Behaviour | `foul` (free kick or penalty), `card` (yellow, second yellow, red) |
| Substitution | `substitution` with the replacement |

Types the contract does not model (carries, pressures, ball receipts, clearances, goalkeeper actions, the shoot-out) are counted in the report, never dropped silently.

Run it on a downloaded open-data match (no provider data is stored in this repository):

```bash
cd backend
python -m app.providers.statsbomb events/<match_id>.json --lineups lineups/<match_id>.json --home-team-id <id>
```

### Verified on a real match

Checked locally on the StatsBomb open-data file for the 2022 World Cup final (that data is not in the repository):

| Check | Result |
| --- | --- |
| Source events | 4,407 |
| **Accepted by MatchMind's validator** | **1,561**: 1,263 passes, 30 shots, 57 tackles, 143 recoveries, 48 fouls, 7 cards, 13 substitutions |
| **Rejected** | **0** |
| Stoppage-time events kept | 163 |
| Score | 3–3 before the shoot-out, as in the match |
| xG | 2.76 – 2.27 |
| Pass networks | hub Enzo Fernández (Argentina), Dayot Upamecano (France) |

Real data exposed two contract gaps, and both are now fixed:
1. **Stoppage and extra time.** Events now carry an optional `period`. The validator orders by period and accepts minutes beyond 90 when a period is present; synthetic streams are unchanged.
2. **Bench cards.** A player who has gone off can still be booked, but a player who has gone off still cannot play the ball.

`tests/test_providers.py` uses a hand-written fixture in StatsBomb's format with fictional teams. It covers every mapped type, both halves with stoppage time, a penalty goal, a second yellow card, a bench card, a substitution, unsupported types and the shoot-out.

## Live feeds

A live provider feed enters the same way as the synthetic one: an adapter publishes MatchMind events to Azure Event Hubs, and the consumer validates and interprets them ([EVENT_DRIVEN.md](EVENT_DRIVEN.md)).

## Still open

- **Licensing:** production use of league data needs a data agreement with the provider.
- **Richer types:** carries, pressures and goalkeeper actions would need new event types; pressures would sharpen PPDA.
- **Per-match squads:** the demo's player names come from the fictional squads. Running a real match end to end through the narratives needs the provider's roster loaded per match. The adapter already returns it.
- **Tracking providers** (positions at 25 Hz) need their own adapter into the tracking format the shape measures use.
