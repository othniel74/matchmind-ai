# Claim contracts — 19 October 2026

`backend/app/claims.py` extends evidence checking from the single passing template to typed match claims. Each claim records:
- its kind: `score`, `compare` (home vs away) or `team_value`
- a metric
- a cutoff minute
- its values
- the exact source event IDs that produce them
- fixed English and Spanish wording

## Supported metrics

| Metric | How the value is computed |
| --- | --- |
| goals | goals scored, also expressed as the score claim |
| shots | shots taken |
| shots_on_target | shots that scored or were saved |
| xg | summed xG of all shots |
| pass_completion | completed passes as a % of attempted |
| possession | time-based share; evidence is every possession-start event from both teams |
| corners | corners taken |
| fouls | fouls committed |
| yellow_cards | yellows, including second yellows |
| red_cards | straight reds and second yellows |
| substitutions | substitutions made |

## Validation

`validate_claim` recomputes the claim from the current source, including any corrected events, and reports the first failure:

| Reason | Meaning |
| --- | --- |
| `unsupported_claim` | unknown metric or claim kind |
| `invalid_scope` | team or minute is invalid |
| `malformed_claim` | required fields are missing or have the wrong type |
| `evidence_outside_scope` | evidence is unknown, or at or after the cutoff |
| `value_mismatch` | the value doesn't match the recomputed value |
| `evidence_mismatch` | the evidence IDs don't match the recomputed set |
| `statement_mismatch` | the wording differs from the fixed template |

## API

- `GET /api/claims?minute=67&metric=shots` lists every supported claim (or one metric) that validates against the corrected source.
- `POST /api/claims/validate` checks a submitted claim, for example one proposed by an agent, and returns `{valid, reason}`.

## Limits

These are counted facts with fixed wording. Free-form sentences are not validated; they still go through the agent workflow's checks, and through human review for interpretations. Possession uses the simulator's possession model.

## Next steps

- Feed verified claims to the agents in place of raw counts.
- Build "Ask the match" and recaps on these claims.
