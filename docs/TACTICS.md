# Tactical change impact, pressing and defensive shape

Coaches, analysts and broadcasters ask "what changed after the substitution?". Pitchlight answers with measurements, puts each one in context, cites the evidence, and never says the change *caused* what followed.

## What it measures

For every **change point** (substitutions and red cards, with a team's simultaneous changes grouped) Pitchlight compares the **ten minutes before** with the **ten minutes after**, for both teams ([app/tactics.py](../backend/app/tactics.py)):

| Group | Measures |
| --- | --- |
| Attacking output | final-third entries, shots, xG, pass completion, possession share |
| Pressing | **PPDA**: opponent passes in their own 60% per tackle, recovery or foul in the pressing zone (lower means more intense pressing); **high turnovers**: balls won in the opponent's last 40% |
| Defensive shape, from the 25 Hz tracking | **line height** (the four deepest outfield players' distance from goal), **width**, **compactness** (average distance to the team centre) |
| Pass network | who gained the biggest share of completed passes, and the incoming player's share |

## Context, not just numbers

A swing means little without knowing what is normal for the match. Each before/after change is ranked against **every ten-minute swing of that measure in the match so far**. A change is called notable only if it is in the top 20%; for counts it must also be at least 3. Findings are worded in 7 languages:

> Merridge: pass completion rose from 64.9% to 75.8% in the ten minutes after the change (Tariq Benali on for Amadou Fofanah-Clarke); a bigger swing than 86% of ten-minute periods in this match.

For PPDA the direction is interpreted, because a rise means *less* pressing. Every finding comes with the caveat: *"This coincides with the change; it does not show that the change caused it."*

## On a real match: the 2022 World Cup final

`tools/tactics-on-statsbomb.py` runs the same analysis on a StatsBomb match. Provider events are first moved onto one continuous clock of time played (`played_time`). Without this, first-half stoppage time would overlap the second half's 45:00, and extra time would be cut off. Change points are labelled with the scoreboard minute (45+2′, 120+1′). The shape measures are left out because the match has no tracking data, and Pitchlight does not simulate it for real matches.

| Change | What Pitchlight found in the ten minutes of play after it |
| --- | --- |
| 41′ France: Kolo Muani and Thuram on for Dembélé and Giroud | Possession swung from 80% Argentina to 64% France; France's PPDA fell from 17.2 to 3.2 (much more pressing); Upamecano's part in France's passing rose from 18% to 43% |
| 64′ Argentina: Acuña on for Di María | France's final-third entries rose from 2 to 8 |
| 102′ Argentina: Paredes and Lautaro Martínez on | Argentina's shots rose from 1 to 6 and xG from 0.02 to 1.01; France's possession fell to 9% (Messi scored at 108′) |
| 113′ France: Konaté on for Varane | France's xG rose from 0 to 0.81, mostly Mbappé's 118′ penalty |
| 116′, 120+1′ | Not compared: fewer than ten minutes of play followed |

Each finding is ranked against the match's own ten-minute swings, and none is attributed to the change as its cause. The result also matches how the final is usually told: France's 41′ substitutions turned the game.

## Where it appears

- **Analysis → What changed after a substitution:** each change point, its findings, a before/after table for both teams with the swing ranking, and pressing and shape for the last 15 minutes.
- **API:** `GET /api/tactics/changes?minute=&language=` and `GET /api/tactics/pressing?minute=&window=`.
- **MCP tools:** `tactical_changes` and `pressing_and_shape`.
- **Ask the match:** "What changed after the substitution?" and "Who is pressing more?" in any of the 7 languages.

## Tested

`tests/test_tactics.py` checks that:
- simultaneous changes are grouped;
- nothing is compared until ten minutes have passed;
- evidence matches each count and stays inside its window;
- notable findings are in the top 20%;
- no causal language is used, and the caveat is always present;
- no event after the comparison window is used;
- the incoming player and the risers are reported;
- pressing and shape values are plausible;
- the API, MCP tools and Ask intents work.

## Limits

- Ten-minute windows are small samples; the swing ranking makes that visible rather than hiding it.
- The shape measures come from synthetic tracking. They are left out for real matches without a tracking feed; with one, the same code applies.
- PPDA here counts tackles, recoveries and fouls. Provider feeds with pressure events allow a richer pressing measure (see [PROVIDERS.md](PROVIDERS.md)).
