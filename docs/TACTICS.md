# Tactical change impact, pressing and defensive shape

Coaches, analysts and broadcasters ask "what changed after the substitution?". MatchMind answers with measurements, puts each one in context, cites the evidence, and never says the change *caused* what followed.

## What it measures

For every **change point** (substitutions and red cards, with a team's simultaneous changes grouped) MatchMind compares the **ten minutes before** with the **ten minutes after**, for both teams ([app/tactics.py](../backend/app/tactics.py)):

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
- The shape measures come from synthetic tracking. With a real tracking feed, the same code applies.
- PPDA here counts tackles, recoveries and fouls. Provider feeds with pressure events allow a richer pressing measure (see [PROVIDERS.md](PROVIDERS.md)).
