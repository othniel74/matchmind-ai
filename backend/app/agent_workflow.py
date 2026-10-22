"""Microsoft Agent Framework workflow for evidence-constrained match narratives.

Graph, built with WorkflowBuilder and executed by the framework runtime:

    evidence_gate -> insight_ranker -> tactical_analyst -> match_storyteller
                  -> audience_editor <-> fact_checker -> publication_gate
    (any step whose output fails its checks) -> deterministic_fallback

The gates and the ranker are deterministic executors. The writers and the fact checker
are Agent Framework agents on whichever chat client is supplied. Facts (numbers, teams,
evidence IDs) never come from a model: writers may only rephrase, and every generated
text is checked before it is handed on.

Checking has two layers:
- Deterministic filters on every writer output: no digits in any script, bounded length,
  and English/Spanish word lists for causes, certainty, pressure and match timing.
- Semantic fact checking of the final text in any supported language. The fact checker
  agent only *extracts* factual statements as structured JSON; plain code then verifies
  each one against the insight and the claim contracts in claims.py. A model never
  decides whether a statement is true.

This module imports the optional SDK; import it lazily from agents.py.
"""
import asyncio
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any

from typing import Literal, Optional

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel, create_model
from typing_extensions import Never

from .claims import METRICS, make_claim, measure
from .core import TEAMS, Event, validate_insight
from .languages import language as language_spec
from .narratives import publish_narratives
from .recap import FACT_METRICS, recap_facts
from .squads import CLUBS, PLAYERS

AGENT_TIMEOUT_SECONDS = 20
AGENT_ATTEMPTS = 2  # one retry: after a timeout, malformed output, or a rule violation (with feedback)
FACT_CHECK_REVISIONS = 1  # the editor may revise once after a failed fact check
MIN_EXTRACTION_COVERAGE = 0.4  # extracted quotes must cover this share of the final text
MAX_TEXT_LENGTH = 600
# Fast English/Spanish pre-filter for causes, certainty, pressure and interpretations.
# Other languages rely on the fact checker, which treats all of these as unsupported.
UNSUPPORTED = re.compile(
    r'\b(caused|causes|proved|proves|guaranteed|because of|due to|pressure|pressing|dominat\w*|'
    r'shift|tactical change|demostrad[oa]|caus[oó]|presi[oó]n|domin\w*)\b', re.I)
# The clock comes from the overlay, not the text. The first live Spanish run called
# minute 67 "the final minutes of the second half", so match-phase wording is blocked.
TIMING = re.compile(
    r'\b(final|closing|last|dying|opening|early|late|first|second)\s+(minutes?|stages?|half|period|moments?)\b|'
    r'\b(half-?time|full-?time|stoppage|injury time|kick-?off)\b|'
    r'\b(minutos?\s+(finales|iniciales)|[uú]ltimos\s+minutos|primeros\s+minutos|'
    r'(primera|segunda)\s+(mitad|parte)|descanso|tiempo\s+a[nñ]adido|recta\s+final)\b', re.I)
RELATIONS = {'more', 'fewer', 'equal'}
INTENSITIES = ('neutral', 'strong', 'extreme')
# Deterministic backstop for the extractor's intensity label, which varied between runs for
# the same sentence: an amplifying word in any supported language makes a statement at least
# "strong". Over-flagging can only block a narrow claim, never pass an overstated one.
# "far", "way" and "a lot" only amplify before more/fewer/less ("so far" is not emphasis).
# Words for the state of play so far, which are not match times (English and Spanish, where TIMING applies).
TIMING_LANGUAGES = frozenset({'en', 'es'})
STATE_OF_PLAY = re.compile(r'\b(currently|so far|at the moment|right now|still|now|actualmente|hasta ahora|'
                           r'por ahora|en este momento|ahora|todav[ií]a|sigue)\b', re.I)
AMPLIFYING_PHRASE = re.compile(r'\b(far|way|a lot|lots)\s+(more|fewer|less)\b', re.I)
INTENSIFIERS = frozenset('''
    much significantly clearly considerably substantially vastly greatly
    mucho mucha muchos muchas muchísimo muchísima muchísimos muchísimas claramente bastante considerablemente
    beaucoup nettement largement considérablement
    muito muita muitos muitas bastante claramente consideravelmente
    viel viele deutlich erheblich wesentlich weitaus
    molto molta molti molte decisamente nettamente notevolmente parecchio
    بكثير بوضوح بفارق كثيرا
'''.split())
# Emphatic wording must match the size of the change; hyperbole is never supported.
STRONG_CHANGE_RATIO = 1.75      # activity: latest window at least 1.75x the previous one
STRONG_COMPARISON_RATIO = 1.5   # comparison: one team's value at least 1.5x the other's

RULES = (' Respond with only a JSON object of the form {"text": "..."}. Do not use digits, player names, '
         'scores, causes, certainty, predictions or tactical interpretations. Do not say when in the match this '
         'happened (no halves, early, late, final or closing minutes); the broadcast shows the clock. Describe '
         'only the supplied observation about activity in attacking or advanced areas; never mention possession, '
         'chances, goals, shots, pressure, pressing, dominance or a shift. Keep a measured tone: no hype, '
         'superlatives or absolute words (completely, totally, relentless), and no judgement of how well a '
         'team is playing.')
# Recaps restate verified results, scorers and statistic leaders, so they get their own rules.
RECAP_RULES = (' Respond with only a JSON object of the form {"text": "..."}. Do not use digits. Mention only the '
               'supplied facts: the result, the scorers (names exactly as supplied), which team led each listed '
               'statistic, and any listed passing role (the player\'s name exactly as supplied, described as the '
               'player most involved in that team\'s passing). Do not mention causes, tactics, pressure, dominance, chances, predictions, certainty or '
               'how well anyone played, and do not say when anything happened in the match. Keep a measured tone: '
               'no hype, superlatives or absolute words. Do not describe attacking activity or trends.')

# Every statement answers this checklist; plain code rejects it if any answer is true.
# A single category label proved unstable live (a fix for one sentence moved two others).
CHECKLIST = {
    'mentions_match_time': 'says when in the match (before half-time, late on, as the game went on, in stoppage '
                           'time, juste avant la mi-temps, nos acréscimos, في نهاية الشوط); comparing the latest '
                           'period with the earlier one, or the state of play so far, in any language, is not a match time (now, '
                           'currently, so far, at the moment, still, recently, actualmente, hasta ahora, actuellement, pour le moment, '
                           'atualmente, até agora, aktuell, bisher, attualmente, finora, حاليا, حتى الآن, than before, que antes, ahora, qu\'auparavant, maintenant, do que antes, agora, als zuvor, '
                           'jetzt, rispetto a prima, ora, من قبل, الآن)',
    'gives_cause': 'gives a reason or cause (because, thanks to, due to, after, grâce à, porque, gracias a, weil, '
                   'perché, بسبب, بفضل)',
    'mentions_chances_or_threat': 'mentions chances, opportunities, danger, goal threat or near misses; naming a '
                                  'statistic (shots, shots on target, expected goals, buts attendus, gols esperados) '
                                  'or a goal that was scored is not a mention of chances',
    'is_prediction': 'says what will or may happen next',
    'judges_performance': 'judges how well a team plays (stepped up, playing better, sharp, impressive, '
                          'making things happen, juega mejor, spielt stark)',
    'claims_dominance': 'says a team dominates, controls, takes over, overwhelms or is on top of the match; '
                        'leading or having more of one named statistic (led in shots, más córners, mehr '
                        'Ballbesitz) is a comparison, not dominance',
}

FACT_CHECKER_INSTRUCTIONS = (
    'You are a strict fact extractor for football commentary written in any language. List every factual '
    'statement in the text. Do not judge whether it is true; only describe it. For each statement give: '
    '"quote": the exact words from the text; '
    '"type": "activity_change" if it says a team is more active, more involved or appears more often in attacking '
    'or advanced areas than before, "comparison" if it compares a counted statistic between the two teams '
    '(being level, equal or the same in a named statistic, such as corners, is a comparison with relation '
    '"equal", not a result), '
    '"result" if it says a team won, lost, drew, leads, trails or is level, or that the match ended or finished '
    '(use won, lost or drew for those), "scorer" if it says a named player scored, "role" if it says a named '
    'player is central to, the key figure in or the most involved in a team\'s passing (relation "hub"), or '
    'explicitly that most of its passing routes run through them (relation "key_link"), or "other" for anything '
    'else; '
    '"team": "home" or "away" (home, local or host team versus away, visiting or guest team); '
    '"relation": "increase" for activity_change, "more", "fewer" or "equal" for comparison, "won", "lost", '
    '"drew", "leads", "trails" or "level" for result, and "hub" or "key_link" for role; '
    '"count": for scorer only, how many goals the statement says the player scored (2 for twice or a brace, 3 for '
    'a hat-trick), or null when it does not say; '
    '"player": for scorer and role, the matching name from the roster supplied with the text, whatever the script '
    'or spelling in the text (for example a transliteration); '
    '"metric": for comparison only, one of ' + ', '.join(METRICS) + '; '
    '"intensity": "neutral" for a plain statement (more often, more active, slightly more, a little more), '
    '"strong" whenever any word amplifies the difference in any language (much more, far more, clearly, '
    'significantly, mucho más, claramente, beaucoup plus, nettement, muito mais, bem mais, viel mehr, deutlich, '
    'molto più, nettamente, أكثر بكثير, بوضوح), "extreme" for absolute or hyperbolic wording '
    '(completely, totally, relentless, overwhelming, a siege, non-stop); '
    'and these true/false fields, answered for the whole quoted statement even when it also describes activity: '
    + '; '.join(f'"{flag}": true if it {meaning}' for flag, meaning in CHECKLIST.items()) + '. '
    'Split sentences into separate statements where you can, but always answer every field. '
    'Respond with only JSON: {"statements": [...]}. Purely stylistic words are not statements.')


# Structured output: the model service guarantees these shapes, so a reply can no longer arrive as
# malformed JSON (seen live: escaped quotes inside the fact checker's JSON). Checking is unchanged.
class WriterOutput(BaseModel):
    text: str


Statement = create_model(
    'Statement',
    quote=(str, ...),
    type=(Literal['activity_change', 'comparison', 'result', 'scorer', 'role', 'other'], ...),
    team=(Optional[Literal['home', 'away']], ...),
    relation=(Optional[Literal['increase', 'more', 'fewer', 'equal', 'won', 'lost', 'drew', 'leads', 'trails',
                               'level', 'hub', 'key_link']], ...),
    player=(Optional[str], ...),
    count=(Optional[int], ...),
    metric=(Optional[Literal[tuple(METRICS)]], ...),
    intensity=(Literal[INTENSITIES], ...),
    **{flag: (bool, ...) for flag in CHECKLIST},
)


class Statements(BaseModel):
    statements: list[Statement]  # type: ignore[valid-type]


# The match researcher investigates with Pitchlight's read-only MCP tools and chooses the recap's
# angle. It chooses; code computes every fact it chose, so no number or name comes from a model.
RESEARCH_TOOLS = ['match_state', 'list_claims', 'network_roles', 'key_moments', 'goal_buildups']
RESEARCH_TIMEOUT_SECONDS = 45
MAX_RESEARCH_METRICS = 3
MAX_RESEARCH_ROLES = 2


class RoleChoice(BaseModel):
    # One role only: "most involved in the team's passing" reads the same in every language, while
    # "hub" and "key link" were confused once translated (6 rejected statements in a live run).
    team: Literal['home', 'away']
    role: Literal['hub']


class ResearchBrief(BaseModel):
    angle: str
    metrics: list[Literal[FACT_METRICS]]  # type: ignore[valid-type]
    roles: list[RoleChoice]


RESEARCHER_INSTRUCTIONS = (
    'You are a football match researcher. Use the tools to investigate the match up to the given minute: the '
    'state and score, the verified statistic claims, both teams\' pass networks, the key moments and how the goals '
    'were built. Then choose the angle of a short recap. Choose up to ' + str(MAX_RESEARCH_METRICS) + ' statistics, '
    'from ' + ', '.join(FACT_METRICS) + ', that best tell the story of this match, and up to '
    + str(MAX_RESEARCH_ROLES) + ' teams whose hub, the player most involved in its passing, is worth '
    'mentioning. Do not write the recap. "angle" is one short '
    'sentence saying why you chose these.')


@dataclass
class NarrativeJob:
    events: list[Event]
    insights: list[dict[str, Any]]
    audience: str
    language: str
    recap_minute: int | None = None          # set to write a match recap instead of an insight narrative
    recap_fallback: dict[str, Any] | None = None
    mcp_url: str | None = None               # the match researcher's MCP server; None skips research


@dataclass
class Draft:
    job: NarrativeJob
    verified: list[dict[str, Any]]
    fallback: list[dict[str, Any]]
    insight: dict[str, Any] | None = None
    text: str | None = None
    failure: str | None = None
    feedback: str = ''
    revisions: int = 0
    needs_revision: bool = False
    claim_ids: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    brief: dict[str, Any] | None = None      # the researcher's choices, resolved to facts by code

    def handoff(self) -> 'Draft':
        # Edge conditions are evaluated after delivery, so each step hands on its own copy.
        return replace(self, steps=list(self.steps), claim_ids=list(self.claim_ids))


@dataclass
class WorkflowOutcome:
    narratives: list[dict[str, Any]]
    engine: str
    fallback_reason: str | None
    steps: list[dict[str, Any]]


def claim_check(text: str) -> str | None:
    """Deterministic filter: return why generated text may not be published, or None."""
    if not text.strip():
        return 'empty_output'
    if len(text) > MAX_TEXT_LENGTH:
        return 'output_too_long'
    if re.search(r'\d', text):  # Unicode-aware: also catches Arabic-Indic and other digits
        return 'unsupported_number'
    if UNSUPPORTED.search(text):
        return 'unsupported_claim'
    if TIMING.search(text):
        return 'unsupported_timing'
    return None


def _json_object(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.strip('`').removeprefix('json').strip()
    return json.loads(raw)


def parse_output(raw: str) -> str:
    """Writers must answer with a JSON object {"text": "..."}."""
    value = _json_object(raw)
    if not isinstance(value, dict) or set(value) != {'text'} or not isinstance(value['text'], str):
        raise ValueError('Output does not match the {"text": string} schema')
    return value['text'].strip()


def parse_statements(raw: str) -> list[dict[str, Any]]:
    value = _json_object(raw)
    if not isinstance(value, dict) or not isinstance(value.get('statements'), list):
        raise ValueError('Output does not match the {"statements": [...]} schema')
    for item in value['statements']:
        if not isinstance(item, dict) or not isinstance(item.get('quote'), str) or item.get('type') not in {
                'activity_change', 'comparison', 'result', 'scorer', 'role', 'other'} \
                or item.get('intensity', 'neutral') not in INTENSITIES \
                or any(not isinstance(item.get(flag), bool) for flag in CHECKLIST):
            raise ValueError('Malformed statement')
    return value['statements']


def _normal(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def _grounded(word: str, body_words: set[str]) -> set[str]:
    """Text words a quote word stands for: itself, or a text word that is the quote word with a
    short attached prefix (Arabic attaches "and"/"by"/"to": والركنيات = و + الركنيات)."""
    if word in body_words:
        return {word}
    return {b for b in body_words if b.endswith(word) and 0 < len(b) - len(word) <= 2 and len(word) >= 3}


def _words(text: str) -> set[str]:
    """Normalized word set (Unicode-aware, so Arabic and accented words work)."""
    return set(re.findall(r'\w+', _normal(text)))


def verify_statements(statements: list[dict[str, Any]], text: str, insight: dict[str, Any] | None,
                      events: list[Event], minute: int | None = None,
                      verdicts: list[dict[str, Any]] | None = None,
                      language: str | None = None) -> tuple[str | None, list[str], list[str]]:
    """Check extracted statements against verified data. Returns (failure, claim_ids, rejected quotes);
    `verdicts`, when given, receives each statement's outcome for the run trace."""
    if not statements:
        return 'no_factual_statement', [], []
    # A quote is grounded when every one of its words appears in the text. Exact substrings
    # are too strict: a list sentence ("led in shots, xG and corners") yields one claim per item.
    body_words = _words(text)
    quote_words = [_words(s['quote']) for s in statements]
    matched = [{m for w in words for m in _grounded(w, body_words)} for words in quote_words]
    if any(not words or any(not _grounded(w, body_words) for w in words) for words in quote_words):
        return 'extraction_mismatch', [], []
    if len(set().union(*matched)) < MIN_EXTRACTION_COVERAGE * len(body_words):
        return 'incomplete_extraction', [], []
    minute = insight['minute'] if insight else minute
    claim_ids, rejected, failure = [], [], None
    facts = recap_facts(events, minute)
    scorers = {(_normal(s['player']), s['team_id']): s['goals'] for s in facts['scorers']}
    for statement in statements:
        team, relation = statement.get('team'), statement.get('relation')
        intensity = statement.get('intensity', 'neutral')
        if intensity == 'neutral' and (_words(statement['quote']) & INTENSIFIERS
                                       or AMPLIFYING_PHRASE.search(_normal(statement['quote']))):
            intensity = 'strong'
        ok, large = False, False
        if statement['type'] == 'result' and statement.get('metric') in METRICS and relation in ('level', 'equal'):
            # "Level in corners" compares a statistic; it is not the score.
            statement = {**statement, 'type': 'comparison', 'relation': 'equal'}
            relation = 'equal'
        if statement['type'] == 'activity_change' and insight is not None:
            ok = team == insight['team_id'] and relation == 'increase'
            reason = 'contradicts_evidence'
            large = insight['current_count'] >= STRONG_CHANGE_RATIO * max(insight['previous_count'], 1)
        elif statement['type'] == 'result' and team is None and relation in ('level', 'drew'):
            # "The teams are level" names no single team: both results must say so.
            ok = all(r == relation for r in facts['result'].values())
            reason = 'contradicts_result'
            if ok:
                claim_ids.append(make_claim(events, 'score', 'goals', minute)['claim_id'])
        elif statement['type'] == 'result' and team in TEAMS:
            ok = facts['result'][team] == relation
            reason = 'contradicts_result'
            large = abs(facts['goals']['home'] - facts['goals']['away']) >= 2
            if ok:
                claim_ids.append(make_claim(events, 'score', 'goals', minute)['claim_id'])
        elif statement['type'] == 'role' and team in TEAMS and relation in ('hub', 'key_link'):
            holder = role_holder(events, team, minute, relation)
            ok = holder is not None and _normal(holder) == _normal(statement.get('player') or '')
            reason = 'contradicts_roles'
        elif statement['type'] == 'scorer' and team in TEAMS:
            goals = scorers.get((_normal(statement.get('player') or ''), team), 0)
            claimed = statement.get('count')
            # "Scored a hat-trick" must match the count, not just the fact that the player scored.
            ok = goals > 0 and (claimed is None or claimed == goals)
            reason, large = 'contradicts_scorers', goals >= 2
        elif statement['type'] == 'comparison' and statement.get('metric') in METRICS and relation in RELATIONS \
                and (team in TEAMS or (team is None and relation == 'equal')):
            team = team or 'home'  # "both teams had the same number of corners"
            mine = measure(events, statement['metric'], team, minute)[0]
            other = measure(events, statement['metric'], 'away' if team == 'home' else 'home', minute)[0]
            ok = {'more': mine > other, 'fewer': mine < other, 'equal': mine == other}[relation]
            reason = 'contradicts_claims'
            high, low = max(mine, other), min(mine, other)
            large = relation != 'equal' and high >= STRONG_COMPARISON_RATIO * max(low, 1e-9)
            if ok:
                claim_ids.append(make_claim(events, 'compare', statement['metric'], minute)['claim_id'])
        else:
            reason = 'unsupported_statement'
        flagged = [flag for flag in CHECKLIST if statement.get(flag)]
        if flagged == ['mentions_match_time'] and language in TIMING_LANGUAGES and STATE_OF_PLAY.search(statement['quote']) \
                and not TIMING.search(statement['quote']):
            # "Currently leading" is the state of play, not a match time. In English and Spanish the
            # deterministic TIMING filter is authoritative, so a flag raised only by such a word is cleared.
            flagged = []
        if flagged:
            ok, reason = False, f'unsupported_{flagged[0]}'
        elif ok and (intensity == 'extreme' or (intensity == 'strong' and not large)):
            ok, reason = False, 'overstated'
        if not ok:
            rejected.append(statement['quote'])
            failure = failure or reason
        if verdicts is not None:
            verdicts.append({'quote': statement['quote'], 'type': statement['type'], 'supported': ok,
                             'reason': None if ok else reason})
    return failure, sorted(set(claim_ids)), rejected


RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 10.0


def rate_limit_wait(exc: BaseException) -> float | None:
    """Seconds to wait if `exc` (or anything it wraps) is an HTTP 429, else None."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if getattr(exc, 'status_code', None) == 429 or type(exc).__name__ == 'RateLimitError':
            headers = getattr(getattr(exc, 'response', None), 'headers', None) or {}
            try:
                wait = float(headers.get('retry-after') or headers.get('Retry-After') or 2)
            except (TypeError, ValueError):
                wait = 2.0
            return min(max(wait, 0.5), MAX_RATE_LIMIT_WAIT_SECONDS)
        exc = exc.__cause__ or exc.__context__
    return None


def call_failure(exc: BaseException) -> str:
    """Name a model-call failure that should fall back safely; re-raise anything unexpected."""
    if isinstance(exc, asyncio.TimeoutError):
        return 'timeout'
    if isinstance(exc, ValueError):
        return 'invalid_output'
    if rate_limit_wait(exc) is not None:
        return 'rate_limited'
    raise exc


def recap_prompt(facts: dict[str, Any], brief: dict[str, Any] | None = None) -> str:
    """Verified recap facts for the analyst, by club name; numbers stay in the deterministic recap.
    With a research brief, only the statistics it chose and the passing roles it asked for."""
    club = lambda t: CLUBS[t].short
    scorers = '; '.join(f"{s['player']} ({club(s['team_id'])}, goals={s['goals']})" for s in facts['scorers']) or 'none'
    chosen = brief['metrics'] if brief and brief['metrics'] else list(facts['leaders'])
    leaders = '; '.join(f"{metric}: {club(facts['leaders'][metric]) if facts['leaders'][metric] else 'equal'}"
                        for metric in chosen)
    roles = '; '.join(f"most involved in {club(r['team'])}'s passing: {r['player']}"
                      for r in (brief or {}).get('roles', []))
    state = 'full time' if facts['final'] else 'so far'
    progress = ('' if facts['final'] else ' The match is still being played: describe the score as leading, '
                'trailing or level, never as won, lost, drawn or finished.')
    return (f"Verified match facts ({state}): result: {club('home')} {facts['result']['home']}, "
            f"{club('away')} {facts['result']['away']}. Scorers: {scorers}. Statistic leaders: {leaders}. "
            + (f"Passing roles: {roles}. " if roles else '')
            + "Write a short match recap in English using only these facts, without numbers or match times."
            + progress)


async def check_claims(client: Any, text: str, events: list[Event], minute: int, language: str = 'en') -> dict[str, Any]:
    """Fact-check any text about the match, as the workflow checks its own drafts: the extractor (a model)
    lists the statements, and code verifies each one against the match up to `minute`. Statements with a
    number are not publishable: Pitchlight publishes numbers only from verified claims, never free text."""
    agent = client.as_agent(name='fact-checker', instructions=FACT_CHECKER_INSTRUCTIONS,
                            default_options={'temperature': 0, 'response_format': Statements})
    statements = parse_statements(await _run_agent(agent, checker_prompt(text)))
    verdicts: list[dict[str, Any]] = []
    failure, claim_ids, _ = verify_statements(statements, text, None, events, minute, verdicts, language)
    for v in verdicts:
        if v['supported'] and re.search(r'\d', v['quote']):
            v.update(supported=False, reason='unsupported_number')
    return {'text': text, 'minute': minute, 'statements': verdicts, 'claim_ids': claim_ids,
            'failure': None if verdicts else failure,
            'publishable': bool(verdicts) and all(v['supported'] for v in verdicts)}


def role_holder(events: list[Event], team: str, minute: int, role: str) -> str | None:
    """Who holds a pass-network role for a team, from the events before `minute` (code, not a model)."""
    from .graph.analytics import passing_graph, roles
    from .squads import name
    net = roles(passing_graph([e for e in events if e.minute < minute], team, 0, 200), team, 0, 200)
    pid = net['hub'] if role == 'hub' else net['connector']
    return name(pid) if pid else None


def resolve_brief(brief: ResearchBrief, events: list[Event], minute: int) -> dict[str, Any]:
    """Turn the researcher's choices into facts computed by code; drop anything not resolvable."""
    metrics = list(dict.fromkeys(brief.metrics))[:MAX_RESEARCH_METRICS]
    roles, seen = [], set()
    for choice in brief.roles:
        if (choice.team, choice.role) in seen or len(roles) >= MAX_RESEARCH_ROLES:
            continue
        seen.add((choice.team, choice.role))
        player = role_holder(events, choice.team, minute, choice.role)
        if player:
            roles.append({'team': choice.team, 'role': choice.role, 'player': player})
    return {'metrics': metrics, 'roles': roles}


async def run_research(client: Any, url: str, minute: int) -> tuple[ResearchBrief, list[dict[str, Any]]]:
    """The researcher agent investigates through MCP; returns its brief and the tool calls it made."""
    from agent_framework import MCPStreamableHTTPTool
    tool = MCPStreamableHTTPTool(name='pitchlight', url=url, allowed_tools=RESEARCH_TOOLS, load_prompts=False,
                                 request_timeout=20)
    async with tool:
        agent = client.as_agent(name='match-researcher', instructions=RESEARCHER_INSTRUCTIONS, tools=[tool],
                                default_options={'response_format': ResearchBrief})
        response = await agent.run(f'Investigate the match up to minute {minute}, then choose the recap angle.')
    calls = [{'tool': c.name, 'arguments': c.parse_arguments()}
             for m in response.messages for c in m.contents if c.type == 'function_call']
    return ResearchBrief.model_validate_json(response.text), calls


def checker_prompt(text: str) -> str:
    """The extractor needs the club names (to map statements to home and away) and the roster
    (to map player names written in any script or spelling to the canonical name)."""
    roster = ', '.join(f'{p.name} ({CLUBS[p.team_id].short})' for p in PLAYERS.values())
    return f"clubs: home={CLUBS['home'].short}, away={CLUBS['away'].short}; roster: {roster}; text={text}"


async def _run_agent(agent: Any, prompt: str, waits: list[float] | None = None) -> str:
    """One agent call with a timeout; HTTP 429 responses wait as instructed and retry."""
    for retry in range(RATE_LIMIT_RETRIES + 1):
        try:
            response = await asyncio.wait_for(agent.run(prompt), timeout=AGENT_TIMEOUT_SECONDS)
            return getattr(response, 'text', None) or str(response)
        except Exception as exc:
            wait = rate_limit_wait(exc)
            if wait is None or retry == RATE_LIMIT_RETRIES:
                raise
            if waits is not None:
                waits.append(wait)
            await asyncio.sleep(wait)
    raise RuntimeError('unreachable')


def in_progress_note(draft: 'Draft') -> str:
    """Every recap writer must know when the match is still being played; a rewrite lost it otherwise
    ("the match ended" at minute 45, "won" at minute 75, seen live)."""
    minute = draft.job.recap_minute
    if minute is None or recap_facts(draft.job.events, minute)['final']:
        return ''
    return ('The match is still being played: describe the score only as leading, trailing or level, never as '
            'won, lost, drawn, ended or finished, and without words such as currently or at the moment. ')


class EvidenceGate(Executor):
    @handler
    async def check(self, job: NarrativeJob, ctx: WorkflowContext[Draft, WorkflowOutcome]) -> None:
        if job.recap_minute is not None:
            # A recap's facts come from recap_facts and claims, validated when the recap was built.
            step = {'agent': 'evidence_gate', 'status': 'passed', 'mode': 'recap'}
            await ctx.send_message(Draft(job, [], [job.recap_fallback], steps=[step]))
            return
        verified = [i for i in job.insights if validate_insight(i, job.events)]
        fallback = [n.model_dump() for n in publish_narratives(job.events, verified, job.audience, job.language)]
        step = {'agent': 'evidence_gate', 'status': 'passed', 'verified_insights': len(verified)}
        if not verified:
            await ctx.yield_output(WorkflowOutcome([], 'deterministic_fallback', None, [step]))
            return
        await ctx.send_message(Draft(job, verified, fallback, steps=[step]))


class MatchResearcher(Executor):
    """Recaps only: an agent investigates through Pitchlight's MCP tools and chooses the angle; code
    resolves its choices to facts. Without an MCP server, or if research fails, the writers get the
    standard verified facts and the trace says why."""
    def __init__(self, client: Any):
        super().__init__(id='match_researcher')
        self.client = client

    @handler
    async def research(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        draft = draft.handoff()
        started = time.perf_counter()
        step: dict[str, Any] = {'agent': 'match_researcher'}
        if not draft.job.mcp_url:
            step.update(status='skipped', reason='no_mcp_server')
        else:
            try:
                brief, calls = await asyncio.wait_for(
                    run_research(self.client, draft.job.mcp_url, draft.job.recap_minute), RESEARCH_TIMEOUT_SECONDS)
                draft.brief = resolve_brief(brief, draft.job.events, draft.job.recap_minute)
                step.update(status='completed', tool_calls=calls, chose=draft.brief, angle=brief.angle[:240])
            except Exception as exc:  # research is optional: never block a recap on it
                step.update(status='skipped', reason='timeout' if isinstance(exc, asyncio.TimeoutError)
                            else type(exc).__name__)
        step['latency_ms'] = int((time.perf_counter() - started) * 1000)
        draft.steps.append(step)
        await ctx.send_message(draft)


class InsightRanker(Executor):
    """Deterministic: lead with the strongest verified count change."""
    @handler
    async def rank(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        draft = draft.handoff()
        if draft.job.recap_minute is not None:
            draft.steps.append({'agent': 'insight_ranker', 'status': 'skipped', 'mode': 'recap'})
        else:
            draft.insight = max(draft.verified, key=lambda i: (i['current_count'] - i['previous_count'], i['minute']))
            draft.steps.append({'agent': 'insight_ranker', 'status': 'completed', 'selected': draft.insight['id']})
        await ctx.send_message(draft)


class WriterAgent(Executor):
    """One Agent Framework agent with a timeout, a bounded retry and an output check."""
    def __init__(self, client: Any, role: str, instructions: str, rules: str = RULES):
        super().__init__(id=role)
        self.role = role
        # Foundry agent names allow only letters, digits and inner hyphens; executor IDs keep underscores.
        self.agent = client.as_agent(name=role.replace('_', '-'), instructions=instructions + rules,
                                     default_options={'response_format': WriterOutput})

    def prompt(self, draft: Draft) -> str:
        return in_progress_note(draft) + (draft.text or '')

    @handler
    async def write(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        draft = draft.handoff()
        started = time.perf_counter()
        attempts, error, feedback, waits = 0, None, '', []
        while attempts < AGENT_ATTEMPTS:
            attempts += 1
            try:
                text = parse_output(await _run_agent(self.agent, self.prompt(draft) + feedback, waits))
            except Exception as exc:
                error = call_failure(exc)
                if error == 'rate_limited':
                    break
                continue
            error = claim_check(text)
            if error is None:
                draft.text = text
                break
            # One corrective retry; the rewrite is checked again in full.
            feedback = (f' Your previous answer was rejected ({error.replace("_", " ")}): "{text}". '
                        'Rewrite it following every rule.')
        draft.failure = None if error is None else f'{self.role}:{error}'
        draft.feedback, draft.needs_revision = '', False
        draft.steps.append({'agent': self.role, 'status': 'completed' if error is None else 'blocked',
                            'output': draft.text if error is None else None,
                            'attempts': attempts, 'reason': error, 'rate_limit_waits': len(waits),
                            'latency_ms': int((time.perf_counter() - started) * 1000)})
        await ctx.send_message(draft)


class TacticalAnalyst(WriterAgent):
    def prompt(self, draft: Draft) -> str:
        if draft.job.recap_minute is not None:
            return recap_prompt(recap_facts(draft.job.events, draft.job.recap_minute), draft.brief)
        i = draft.insight
        # The match minute is withheld: models turn it into phase claims the evidence does not support.
        return (f"Verified observation: team={i['team_id']} ({CLUBS[i['team_id']].short}); advanced-area on-ball "
                f"events rose from "
                f"{i['previous_count']} in the previous ten minutes to {i['current_count']} in the latest "
                f"ten minutes. Describe this observation in English without numbers.")


class AudienceEditor(WriterAgent):
    def prompt(self, draft: Draft) -> str:
        spec = language_spec(draft.job.language)
        return (f'audience={draft.job.audience}; write the final text in {spec.name} (language code '
                f'{spec.code}); {in_progress_note(draft)}text={draft.text}{draft.feedback}')


class FactChecker(Executor):
    """Extract statements with a model; verify each one against data with plain code."""
    def __init__(self, client: Any):
        super().__init__(id='fact_checker')
        # Extraction should not vary between runs: a live retest let the same sentence through once.
        self.agent = client.as_agent(name='fact-checker', instructions=FACT_CHECKER_INSTRUCTIONS,
                                     default_options={'temperature': 0, 'response_format': Statements})

    @handler
    async def check(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        draft = draft.handoff()
        started = time.perf_counter()
        attempts, failure, rejected, statements, waits = 0, 'invalid_output', [], [], []
        verdicts: list[dict[str, Any]] = []
        while attempts < AGENT_ATTEMPTS:
            attempts += 1
            try:
                statements = parse_statements(await _run_agent(self.agent, checker_prompt(draft.text), waits))
            except Exception as exc:
                failure = call_failure(exc)
                if failure == 'rate_limited':
                    break
                continue
            failure, draft.claim_ids, rejected = verify_statements(
                statements, draft.text, draft.insight, draft.job.events, draft.job.recap_minute, verdicts,
                draft.job.language)
            break
        step = {'agent': 'fact_checker', 'attempts': attempts, 'statements': len(statements), 'checked': verdicts,
                'reason': failure, 'rate_limit_waits': len(waits),
                'latency_ms': int((time.perf_counter() - started) * 1000)}
        if failure is None:
            step['status'] = 'verified'
        elif rejected and draft.revisions < FACT_CHECK_REVISIONS:
            # Send the editor back once with the statements that failed verification.
            draft.revisions += 1
            draft.needs_revision = True
            # Remove, do not replace: asked to "fix" a statement, the editor once swapped a correct
            # lead for a wrong "level" (seen live). Every other verified statement must survive.
            draft.feedback = (' Your previous text was rejected because these statements are not supported by '
                              'the verified data: ' + '; '.join(f'"{q}"' for q in rejected) +
                              '. Rewrite it without those statements: delete them, do not replace them with new '
                              'facts, and keep every other statement exactly as it was.')
            step['status'] = 'revision_requested'
        else:
            draft.failure = f'fact_checker:{failure}'
            step['status'] = 'blocked'
        draft.steps.append(step)
        await ctx.send_message(draft)


class PublicationGate(Executor):
    """Re-validate evidence, claims and the final text before anything leaves the workflow."""
    @handler
    async def publish(self, draft: Draft, ctx: WorkflowContext[Never, WorkflowOutcome]) -> None:
        draft = draft.handoff()
        recap = draft.job.recap_minute is not None
        reason = None if recap or validate_insight(draft.insight, draft.job.events) else 'evidence_changed'
        reason = reason or claim_check(draft.text or '')
        if reason:
            draft.steps.append({'agent': 'publication_gate', 'status': 'fallback', 'reason': reason})
            await ctx.yield_output(WorkflowOutcome(draft.fallback, 'deterministic_fallback', reason, draft.steps))
            return
        narratives = [dict(n) for n in draft.fallback]
        for narrative in narratives:
            if recap or narrative['insight_id'] == draft.insight['id']:
                narrative.update(body=draft.text, engine='microsoft_agent_framework', claim_ids=draft.claim_ids)
        draft.steps.append({'agent': 'publication_gate', 'status': 'approved', 'evidence_validated': True,
                            'fact_checked': True})
        await ctx.yield_output(WorkflowOutcome(narratives, 'microsoft_agent_framework', None, draft.steps))


class DeterministicFallback(Executor):
    @handler
    async def fall_back(self, draft: Draft, ctx: WorkflowContext[Never, WorkflowOutcome]) -> None:
        draft = draft.handoff()
        draft.steps.append({'agent': 'publication_gate', 'status': 'fallback', 'reason': draft.failure})
        await ctx.yield_output(WorkflowOutcome(draft.fallback, 'deterministic_fallback', draft.failure, draft.steps))


def build_workflow(client: Any, recap: bool = False):
    rules = RECAP_RULES if recap else RULES
    gate = EvidenceGate(id='evidence_gate')
    ranker = InsightRanker(id='insight_ranker')
    analyst = TacticalAnalyst(client, 'tactical_analyst',
        'You are a football analyst. Explain the supplied verified observation conservatively.', rules)
    storyteller = WriterAgent(client, 'match_storyteller',
        'You are a match storyteller. Rewrite the supplied English text clearly for viewers without adding facts.',
        rules)
    editor = AudienceEditor(client, 'audience_editor',
        'You adapt text for the stated audience (fan, analyst or broadcast) and write it in the requested language, '
        'without adding facts.', rules)
    checker = FactChecker(client)
    publication = PublicationGate(id='publication_gate')
    fallback = DeterministicFallback(id='deterministic_fallback')
    ok = lambda draft: draft.failure is None
    failed = lambda draft: draft.failure is not None
    builder = WorkflowBuilder(name='pitchlight-narrative-v3', start_executor=gate).add_edge(gate, ranker)
    if recap:  # recaps: a researcher agent investigates through MCP and chooses the angle first
        researcher = MatchResearcher(client)
        builder.add_edge(ranker, researcher).add_edge(researcher, analyst)
    else:
        builder.add_edge(ranker, analyst)
    for writer, after in ((analyst, storyteller), (storyteller, editor), (editor, checker)):
        builder.add_edge(writer, after, condition=ok).add_edge(writer, fallback, condition=failed)
    builder.add_edge(checker, publication, condition=lambda d: d.failure is None and not d.needs_revision)
    builder.add_edge(checker, editor, condition=lambda d: d.failure is None and d.needs_revision)
    builder.add_edge(checker, fallback, condition=failed)
    return builder.build()


async def run_workflow(client: Any, job: NarrativeJob) -> tuple[WorkflowOutcome, list[str]]:
    """Run the graph; return its outcome and the executor handoff order the runtime observed."""
    language_spec(job.language)  # reject unsupported languages before any model call
    result = await build_workflow(client, recap=job.recap_minute is not None).run(job)
    handoffs = [event.executor_id for event in result if event.type == 'executor_completed']
    outputs = result.get_outputs()
    if len(outputs) != 1:
        raise RuntimeError('Workflow did not produce exactly one outcome')
    return outputs[0], handoffs
