# Real data providers

Pitchlight's analytics run on its own event contract (`core.Event`). A **provider adapter** maps a provider's events into that contract. The same `StreamValidator` that guards the synthetic feed then checks every adapted event, so claims, statistics, pass networks, narratives and tactical analysis run unchanged on real data.

## StatsBomb (open-data format)

[app/providers/statsbomb.py](../backend/app/providers/statsbomb.py) adapts StatsBomb's JSON event format:

| StatsBomb | Pitchlight |
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
| **Accepted by Pitchlight's validator** | **1,561**: 1,263 passes, 30 shots, 57 tackles, 143 recoveries, 48 fouls, 7 cards, 13 substitutions |
| **Rejected** | **0** |
| Stoppage-time events kept | 163 |
| Score | 3–3 before the shoot-out, as in the match |
| xG | 2.76 – 2.27 |
| Pass networks | hub Enzo Fernández (Argentina), Dayot Upamecano (France) |

### A whole competition: all 64 matches of the 2022 World Cup

`tools/validate-statsbomb-competition.py` runs every match of a competition through the adapter and Pitchlight's validator. It compares Pitchlight's score with the official result. Only totals are saved, in [validation/statsbomb-wc2022.json](validation/statsbomb-wc2022.json), never provider events.

| Check | Result |
| --- | --- |
| Matches | 64 (group stage to final) |
| Source events | 234,637 |
| **Accepted by Pitchlight's validator** | **81,931** |
| **Rejected** | **0** |
| **Scores matching the official result** | **64 of 64** |
| Matches with extra time | 5 |
| Own goals | 3 |
| Stoppage-time events kept | 8,093 |
| Time | 12 s for all 64 matches (at most 0.07 s per match to adapt and validate) |

Real data exposed five gaps, all now fixed and covered by tests:
1. **Stoppage and extra time.** Events now carry an optional `period`. The validator orders by period and accepts minutes beyond 90 when a period is present; synthetic streams are unchanged.
2. **Cards for players who have gone off.** A substituted player can still be booked, but still cannot play the ball.
3. **Substitutes booked on the bench before coming on.** Weghorst was booked at 45+2′ of Netherlands v Argentina and came on at 78′. A card no longer counts as having been on the pitch, so the later substitution is valid.
4. **A card in the same second as a pass.** An adapter bug gave Bad Behaviour cards the provider's raw sequence number. Fixed.
5. **Own goals.** The contract has no own-goal event, so the adapter counts own goals in its report and adds them to the score. It does not invent a shot that never happened.

`tests/test_providers.py` uses a hand-written fixture in StatsBomb's format with fictional teams. It covers every mapped type, both halves with stoppage time, a penalty goal, a second yellow card, a bench card, a substitution, unsupported types and the shoot-out.

## Independent cross-check: Sportmonks

Sportmonks does not publish every pass with pitch coordinates, so it is used as a **referee** rather than a feed. [app/providers/sportmonks.py](../backend/app/providers/sportmonks.py) fetches Sportmonks' official record of a match and compares it with what Pitchlight computed from another provider's events for the same match:

| Kind | Checks |
| --- | --- |
| Must agree exactly | the score; each goal (team, minute within one, scorer, matched across the providers' name spellings); yellow cards, sendings-off and substitutions per team |
| Reported as differences | shots, shots on target, passes, pass completion, possession, corners, fouls. Providers define these differently, so differences are to be explained, not failed. |

- **Teams:** at neutral venues the two providers can list home and away the other way round, so sides are matched by team name.
- **Goals:** the scoring side comes from Sportmonks' running score, whatever its own-goal convention.
- **Cards:** Pitchlight counts a second yellow as a yellow and a red, while Sportmonks records one yellow-red card. The check converts Sportmonks' record to Pitchlight's rule and labels it.

```bash
cd backend   # SPORTMONKS_API_TOKEN in backend/.env; sent as a header, never printed
python -m app.providers.sportmonks data/research/statsbomb/events.json     --lineups data/research/statsbomb/lineups.json --date 2022-12-18
```

`tests/test_sportmonks.py` uses a hand-written fixture in Sportmonks' v3 format, with no network access. It covers:
- side alignment;
- skipping the shoot-out;
- own goals;
- the card convention;
- name matching;
- reporting a disagreement.

**Status (22 October 2026): tested on real Sportmonks data.**

- **Plan coverage.** The account is on Sportmonks' free plan, which covers the Danish Superliga and the Scottish Premiership. StatsBomb's open data includes neither, so the same-match comparison needs a plan that covers a competition both providers have, such as a World Cup, a Euro or the Bundesliga.
- **Reading a real record.** On Celtic 7–1 Hearts (Scottish Premiership, 18 October 2026), the reference parser returned the final score Sportmonks reports (7–1), all 8 goals with team, minute and scorer, an own goal credited to the right side, 4 yellow cards, 10 substitutions, possession and corners. The free plan's team statistics stop at possession and corners, but it does give 61 player statistics per match (`lineups.details`). So the referee now sums shots, shots on target, passes, accurate passes and fouls from the players when the team figure is missing, and lists which figures it derived. A team figure from the provider always takes precedence, and a pass percentage is derived only from two player sums. On this match: Celtic 18 shots (10 on target), 491 passes at 86.4%, 17 fouls; Hearts 20 shots (5 on target), 525 passes at 86.9%, 8 fouls. Player expected goals (`xGlineup`) is a paid add-on and was refused on this plan.
- **Every finished match of three seasons.** `tools/validate-sportmonks-season.py` reads every finished match in the Premier League, Bundesliga, La Liga and Carabao Cup through Pitchlight's reader, and compares the score it computes from the goal events with Sportmonks' official final score. Only totals are saved, in `validation/`.

  | Season | Matches | Scores agree | Own goals | Penalty goals | Shootouts kept out of the score |
  | --- | --- | --- | --- | --- | --- |
  | 2024/25 | 1,158 | 1,158 | 71 | 176 | 15 |
  | 2025/26 | 1,158 | 1,158 | 90 | 271 | 19 |
  | 2026/27 (to 22 October) | 289 | 289 | 32 | 46 | 13 |
  | **Total** | **2,605** | **2,605** | **193** | **493** | **47** |

  This proves the integration reads real records correctly at scale. It compares two parts of the same provider's record (goal events and the final score), so it is not an independent second source; the StatsBomb comparison below is.
- **Premier League, on a Starter trial.** Manchester United 5–2 Ipswich Town (30 August 2026) parsed correctly: all 7 goals (a Bruno Fernandes hat-trick including a penalty), an own goal by Ipswich's Jacob Greaves credited to Manchester United, cards, substitutions, and team totals from player statistics (Manchester United 33 shots, 561 passes at 89.5%).
- **Why there is still no same-match comparison.** The trial covers the Premier League, Bundesliga, La Liga and Carabao Cup, but only from the 2024/25 season (Bundesliga seasons listed: 2024/25 to 2026/27). StatsBomb's newest free men's club season is the Bundesliga 2023/24, so the two sources share no match. Either historical access to 2023/24 on Sportmonks or newer StatsBomb data would enable it; the command is ready.
- **Club names across providers.** Fixture lookup and side alignment match club names when every distinctive word of one appears in the other ('Bayer Leverkusen' / 'Bayer 04 Leverkusen', 'Bayern Munich' / 'FC Bayern München'), so 'Manchester United' never matches 'Manchester City' (tested).
- **A convention found on real data.** Sportmonks credits an own goal to the team that benefits (Celtic), not to the player's own team. The parser read the side from the running score, so the result was right. Its fallback for records without a running score assumed the opposite and has been corrected, with a test.

## Live feeds

A live provider feed enters the same way as the synthetic one: an adapter publishes Pitchlight events to Azure Event Hubs, and the consumer validates and interprets them ([EVENT_DRIVEN.md](EVENT_DRIVEN.md)).

## Still open

- **Licensing:** production use of league data needs a data agreement with the provider.
- **Richer types:** carries, pressures and goalkeeper actions would need new event types; pressures would sharpen PPDA.
- **Per-match squads:** the demo's player names come from the fictional squads. Running a real match end to end through the narratives needs the provider's roster loaded per match. The adapter already returns it.
- **Tracking providers** (positions at 25 Hz) need their own adapter into the tracking format the shape measures use.
