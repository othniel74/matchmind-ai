"""Ask the match: answer a viewer's question from verified facts only.

The question is mapped to a structured intent (by the model when one is configured, by a
multilingual keyword match otherwise). The answer is then computed by code from the match
knowledge graph, claims and player statistics, worded from fixed templates, and returned
with the event IDs it rests on. The model never writes the answer, so it cannot add facts.
Answers are time-scoped: nothing after `minute` is used.
"""
from __future__ import annotations
import json
import re
import unicodedata
from typing import Any
from .claims import METRICS, make_claim
from .core import TEAMS, Event
from .dynamics import state_at
from .knowledge import buildup_chains, network_roles, why, xg_chain
from .languages import format_number
from .moment_text import MOMENT_TEXT
from .moments import render
from .players import player_stats
from .squads import CLUBS, PLAYERS, name

INTENTS = ('score', 'scorers', 'stat', 'player', 'why_moment', 'key_player', 'buildup', 'momentum', 'unsupported')


def _fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


# Keyword fallback, checked in order; the first intent with a matching word wins.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ('buildup', ('build-up', 'build up', 'buildup', 'construccion', 'construction', 'construcao', 'aufbau',
                 'costruzione', 'بناء')),
    ('why_moment', ('why', 'por que', 'porque', 'pourquoi', 'warum', 'perche', 'لماذا')),
    ('scorers', ('who scored', 'scorer', 'goleador', 'marco', 'buteur', 'a marque', 'marcou', 'artilheiro',
                 'torschutze', 'getroffen', 'marcatore', 'segnato', 'سجل', 'هداف')),
    ('key_player', ('key player', 'key link', 'connector', 'hub', 'most important', 'clave', 'cle', 'chave',
                    'schlussel', 'wichtigste', 'chiave', 'الأهم', 'مفتاح')),
    ('momentum', ('momentum', 'on top', 'control', 'dominat', 'impulso', 'dominio', 'temps fort', 'domine',
                  'dominando', 'oberwasser', 'kontrolle', 'slancio', 'domina', 'زخم', 'سيطرة')),
    ('stat', ('shot', 'xg', 'possession', 'corner', 'foul', 'pass completion', 'tiro', 'posesion', 'esquina',
              'falta', 'tir', 'faute', 'chute', 'posse', 'escanteio', 'schuss', 'schusse', 'ballbesitz', 'ecke',
              'foul', 'possesso', 'calci d', 'falli', 'تسديد', 'استحواذ', 'ركني', 'أخطاء')),
    ('score', ('score', 'winning', 'result', 'marcador', 'resultado', 'ganando', 'gagne', 'placar', 'ganhando',
               'spielstand', 'stand', 'fuhrt', 'risultato', 'punteggio', 'vince', 'النتيجة', 'يفوز')),
]
METRIC_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ('shots_on_target', ('on target', 'a puerta', 'cadrés', 'cadres', 'no alvo', 'aufs tor', 'in porta', 'على المرمى')),
    ('xg', ('xg', 'expected goals', 'goles esperados', 'buts attendus', 'gols esperados', 'erwartete tore')),
    ('possession', ('possession', 'posesion', 'posse', 'ballbesitz', 'possesso', 'استحواذ')),
    ('pass_completion', ('pass completion', 'pases completados', 'passes reussies', 'passes certos', 'passquote',
                         'passaggi riusciti', 'دقة التمرير')),
    ('corners', ('corner', 'esquina', 'escanteio', 'ecke', 'calci d', 'ركني')),
    ('fouls', ('foul', 'falta', 'faute', 'falli', 'أخطاء')),
    ('shots', ('shot', 'tiro', 'tir', 'chute', 'schuss', 'schusse', 'تسديد')),
]


def find_player(question: str) -> str | None:
    folded = _fold(question)
    best = None
    for pid, p in PLAYERS.items():
        full = _fold(p.name)
        parts = [w for w in re.split(r'[\s-]+', full) if len(w) >= 4]
        if full in folded:
            return pid
        if best is None and any(re.search(rf'\b{re.escape(w)}\b', folded) for w in parts[1:] or parts):
            best = pid
    return best


def find_team(question: str) -> str | None:
    folded = _fold(question)
    for team, club in CLUBS.items():
        if any(_fold(n) in folded for n in (club.name, club.short)) or _fold(club.name.split()[0]) in folded:
            return team
    return None


def keyword_intent(question: str) -> dict[str, Any]:
    folded = _fold(question)
    player, team = find_player(question), find_team(question)
    metric = next((m for m, words in METRIC_WORDS if any(_fold(w) in folded for w in words)), None)
    intent = next((i for i, words in KEYWORDS if any(_fold(w) in folded for w in words)), None)
    if intent is None and player:
        intent = 'player'
    if intent == 'stat' and player:
        intent = 'player'
    return {'intent': intent or 'unsupported', 'team': team, 'player_id': player, 'metric': metric}


AGENT_INSTRUCTIONS = """You route a football viewer's question about one match to the answer_question tool.
Call answer_question exactly once. Pass the question in clear English, plus the structured intent:
- score: the current score or who is winning
- scorers: who scored
- stat: a team statistic; set metric (%s)
- player: how a named player is doing; set player to the name as written
- why_moment: why a goal happened or why it mattered
- key_player: the key player, main man, playmaker or who the team plays through
- buildup: how a goal was built
- momentum: who is on top, in control or has momentum
- unsupported: anything else (other matches, predictions, opinions, the weather)
Set team to home (%s) or away (%s) when the question names a club. Pass minute and language exactly as
given. Never answer the question yourself; the tool's answer is shown to the viewer.""" % (
    ', '.join(METRICS), CLUBS['home'].name, CLUBS['away'].name)


def validate_intent(raw: dict[str, Any] | None, question: str) -> dict[str, Any]:
    """Check a model-chosen intent against the contract; anything off-contract, or a refusal
    the keyword router can answer, falls back to keywords (answers are computed by code)."""
    if not isinstance(raw, dict) or raw.get('intent') not in INTENTS or raw['intent'] == 'unsupported':
        return keyword_intent(question)
    player = find_player(str(raw.get('player') or '')) if raw.get('player') else None
    if raw['intent'] == 'player' and player is None:
        player = find_player(question)
    return {'intent': raw['intent'], 'team': raw.get('team') if raw.get('team') in TEAMS else None,
            'player_id': player, 'metric': raw.get('metric') if raw.get('metric') in METRICS else None}


def parse_intent(text: str, question: str) -> dict[str, Any]:
    """Validate an intent given as JSON text."""
    match = re.search(r'\{.*\}', text or '', re.S)
    try:
        raw = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        raw = None
    return validate_intent(raw, question)


async def mcp_agent_answer(client: Any, question: str, minute: int, language: str, url: str) -> dict[str, Any] | None:
    """An Agent Framework agent calls MatchMind's answer_question tool over MCP. The viewer gets
    the tool's verified result, never the model's own text. None if the tool was not called."""
    from agent_framework import MCPStreamableHTTPTool
    from .agent_workflow import _run_agent
    tool = MCPStreamableHTTPTool(name='matchmind', url=url, allowed_tools=['answer_question'], load_prompts=False,
                                 request_timeout=20)
    async with tool:
        agent = client.as_agent(name='match-qa', instructions=AGENT_INSTRUCTIONS, tools=[tool])
        response = await agent.run(f'{question[:300]}\n(minute={minute}, language={language})')
    results = [c for m in response.messages for c in m.contents if c.type == 'function_result']
    calls = [c for m in response.messages for c in m.contents if c.type == 'function_call']
    if not results:
        return None
    payload = results[-1].result
    if not isinstance(payload, dict):
        text = payload if isinstance(payload, str) else getattr(payload[0], 'text', '') if payload else ''
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None
    if not isinstance(payload, dict) or 'answer' not in payload:
        return None
    arguments = calls[-1].parse_arguments() if calls else {}
    return {**payload, 'tool_call': {'tool': 'answer_question', 'arguments': arguments}}


def _club(team: str, code: str) -> str:
    return CLUBS[team].short


def answer(g, events: list[Event], seed: int, minute: int, intent: dict[str, Any], code: str) -> dict[str, Any]:
    """Compute the answer for a structured intent from verified data before `minute`."""
    text = MOMENT_TEXT[code]
    visible = [e for e in events if e.minute < minute]
    kind = intent['intent']
    team = intent.get('team')
    out: dict[str, Any] = {'intent': kind, 'answer': text['ask_unsupported'], 'evidence_event_ids': [],
                           'claim_ids': [], 'supported': kind != 'unsupported'}
    goal_moments = sorted((d for _, d in g.nodes(data=True) if d['kind'] == 'Moment' and d['moment_kind'] == 'goal'),
                          key=lambda d: d['clock'])
    if minute < 1 and kind in {'score', 'stat'}:
        kind = 'unsupported'
    if kind == 'score':
        claim = make_claim(events, 'compare', 'goals', minute)
        out.update(answer=claim['statements'][code], claim_ids=[claim['claim_id']],
                   evidence_event_ids=claim['evidence_event_ids'])
    elif kind == 'scorers':
        goals = [e for e in visible if e.event_type == 'shot' and e.outcome == 'goal']
        if not goals:
            out['answer'] = text['ask_no_goal']
        else:
            tally: dict[str, int] = {}
            for e in goals:
                tally[e.player_id] = tally.get(e.player_id, 0) + 1
            parts = [f"{name(p)} ({_club(PLAYERS[p].team_id, code)}) {format_number(n, '', code)}" for p, n in tally.items()]
            out.update(answer=f"{text['recap_scorers']}: " + ', '.join(parts),
                       evidence_event_ids=[e.event_id for e in goals])
    elif kind == 'stat':
        claim = make_claim(events, 'compare', intent.get('metric') or 'shots', minute)
        out.update(answer=claim['statements'][code], claim_ids=[claim['claim_id']],
                   evidence_event_ids=claim['evidence_event_ids'])
    elif kind == 'player' and intent.get('player_id'):
        pid = intent['player_id']
        p_team = PLAYERS[pid].team_id
        stats = player_stats(events, seed, minute)[pid]
        roles = network_roles(g, p_team, 0, minute)
        entry = next((r for r in roles['players'] if r['player_id'] == pid), {'pass_share': 0})
        chain = next((r for r in xg_chain(g, p_team) if r['player_id'] == pid), {'xg_chain': 0})
        out.update(answer=text['ask_player_role'].format(
            player=name(pid), rating=format_number(stats['rating'], '', code), club=_club(p_team, code),
            share=format_number(round(100 * entry['pass_share'], 1), '%', code),
            chain=format_number(chain['xg_chain'], '', code)),
            evidence_event_ids=[e.event_id for e in visible if e.player_id == pid][-25:],
            player=stats, network_role=entry)
    elif kind == 'player':
        out.update(answer=text['ask_unsupported'], supported=False)
    elif kind == 'why_moment':
        if not goal_moments:
            out['answer'] = text['ask_no_goal']
        else:
            target = next((d for d in reversed(goal_moments) if team is None or d['team_id'] == team), goal_moments[-1])
            detail = why(g, target['moment_id'])
            moment = {'id': target['moment_id'], 'kind': 'goal', 'team_id': target['team_id'],
                      'facts': target['facts'], 'why': target['why'], 'player_ids': list(detail['players'])}
            rendered = render(moment, code)
            out.update(answer=f"{rendered['headline']}. {rendered['body']}", moment_id=target['moment_id'],
                       evidence_event_ids=detail['evidence_event_ids'], why=detail)
    elif kind == 'key_player':
        lines, evidence = [], []
        for t in ([team] if team else list(TEAMS)):
            roles = network_roles(g, t, 0, minute)
            chain = xg_chain(g, t)
            if not roles['players'] or roles['completed_passes'] == 0:
                continue
            top = chain[0] if chain else {'name': '-', 'xg_chain': 0}
            lines.append(text['ask_key_player'].format(
                club=_club(t, code), connector=name(roles['connector']), hub=name(roles['hub']),
                chain=top['name'], value=format_number(top['xg_chain'], '', code)))
            evidence += [i for lane in roles['lanes'] for i in lane['event_ids']]
        out.update(answer='. '.join(lines) or text['ask_unsupported'], evidence_event_ids=sorted(set(evidence)))
    elif kind == 'buildup':
        if not goal_moments:
            out['answer'] = text['ask_no_goal']
        else:
            target = next((d for d in reversed(goal_moments) if team is None or d['team_id'] == team), goal_moments[-1])
            chain = why(g, target['moment_id'])['buildup']
            if chain:
                names = []
                for step in chain['steps']:
                    if not names or names[-1] != step['name']:
                        names.append(step['name'])
                out.update(answer=text['ask_buildup'].format(club=_club(target['team_id'], code),
                                                            chain=' → '.join(names)),
                           evidence_event_ids=[s['event_id'] for s in chain['steps']], buildup=chain)
            else:
                out['answer'] = text['ask_no_goal']
    elif kind == 'momentum':
        state = state_at(visible, minute)
        if state and state['momentum'] and state['momentum']['team_id']:
            t = state['momentum']['team_id']
            out['answer'] = '{}. {}'.format(text['momentum'].format(club=_club(t, code)), text['momentum_body'].format(
                share=format_number(round(100 * state['momentum']['share'], 1), '%', code), club=_club(t, code)))
        elif state and state['control']['state'] == 'control':
            out['answer'] = text['control'].format(club=_club(state['control']['team_id'], code))
        elif state and state['control']['state'] == 'chaos':
            out['answer'] = text['chaos']
        else:
            out['answer'] = text['flow_none'][:1].upper() + text['flow_none'][1:]
        out['dynamics'] = state
    if not out['supported'] or kind == 'unsupported':
        out.update(intent='unsupported', supported=False)
    return out
