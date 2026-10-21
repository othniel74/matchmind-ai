"""Tactical change impact, pressing and defensive shape: what changed after a substitution or
a red card, measured, put in context, and never presented as cause.

For each change point (substitutions and red cards, simultaneous ones grouped) the ten minutes
before and after are compared for both teams:

- attacking output: final-third entries, shots, xG, pass completion, possession share;
- pressing: PPDA (opponent passes allowed per defensive action in the pressing zone) and high
  turnovers (balls won in the opponent's last 40%);
- defensive shape from the 25 Hz tracking: line height, width and compactness;
- the pass network: who gained involvement, and how involved the incoming player was.

Every swing is ranked against all ten-minute swings of that metric in the match so far, so a
change is called notable only when it is unusual for this match. Statements say what coincided
with the change and state plainly that this does not show the change caused it.
"""
from __future__ import annotations
import math
from dataclasses import replace
from functools import lru_cache
from typing import Any
from .core import SENDING_OFF, TEAMS, Event
from .graph.analytics import passing_graph, roles
from .languages import format_number
from .squads import CLUBS, name

WINDOW = 600            # seconds: ten minutes either side of a change
FINAL_THIRD = 66.7      # team-relative x where the final third starts
PRESS_ZONE = 40.0       # defensive actions at or beyond this team-relative x count as pressing
HIGH_TURNOVER = 60.0    # balls won at or beyond this team-relative x are high turnovers
NOTABLE_PERCENTILE = 80

# Higher is better for the team unless listed here (fewer passes allowed per action = more pressing).
LOWER_IS_MORE = {'ppda'}
COUNT_METRICS = ('final_third_entries', 'shots', 'high_turnovers')

TEXT = {
    'en': {'ppda_less': 'less intense pressing', 'ppda_more': 'more intense pressing', 'final_third_entries': 'final-third entries', 'shots': 'shots', 'xg': 'expected goals (xG)',
           'pass_completion': 'pass completion', 'possession': 'possession', 'ppda': 'passes allowed per defensive action (PPDA)',
           'high_turnovers': 'high turnovers', 'line_height': 'defensive line height', 'width': 'team width',
           'compactness': 'compactness (average distance to team centre)',
           'sub': '{on} on for {off}', 'red': '{player} sent off',
           'rise': '{club}: {metric} rose from {before} to {after} in the ten minutes after the change ({change})',
           'fall': '{club}: {metric} fell from {before} to {after} in the ten minutes after the change ({change})',
           'context': 'a bigger swing than {pct} of ten-minute periods in this match',
           'caveat': 'This coincides with the change; it does not show that the change caused it.',
           'riser': '{player} took a bigger part in the passing ({before} → {after} of completed passes)'},
    'es': {'ppda_less': 'presión menos intensa', 'ppda_more': 'presión más intensa', 'final_third_entries': 'entradas en el último tercio', 'shots': 'tiros', 'xg': 'goles esperados (xG)',
           'pass_completion': 'acierto en el pase', 'possession': 'posesión', 'ppda': 'pases permitidos por acción defensiva (PPDA)',
           'high_turnovers': 'recuperaciones altas', 'line_height': 'altura de la línea defensiva', 'width': 'anchura del equipo',
           'compactness': 'compacidad (distancia media al centro del equipo)',
           'sub': 'entra {on} por {off}', 'red': 'expulsión de {player}',
           'rise': '{club}: {metric}, de {before} a {after} en los diez minutos tras el cambio ({change})',
           'fall': '{club}: {metric}, de {before} a {after} en los diez minutos tras el cambio ({change})',
           'context': 'una variación mayor que el {pct} de los tramos de diez minutos del partido',
           'caveat': 'Coincide con el cambio; no demuestra que el cambio lo causara.',
           'riser': '{player} participó más en el pase ({before} → {after} de los pases completados)'},
    'fr': {'ppda_less': 'pressing moins intense', 'ppda_more': 'pressing plus intense', 'final_third_entries': 'entrées dans le dernier tiers', 'shots': 'tirs', 'xg': 'buts attendus (xG)',
           'pass_completion': 'réussite des passes', 'possession': 'possession', 'ppda': 'passes concédées par action défensive (PPDA)',
           'high_turnovers': 'récupérations hautes', 'line_height': 'hauteur de la ligne défensive', 'width': "largeur de l'équipe",
           'compactness': "compacité (distance moyenne au centre de l'équipe)",
           'sub': '{on} remplace {off}', 'red': 'expulsion de {player}',
           'rise': '{club} : {metric}, de {before} à {after} dans les dix minutes après le changement ({change})',
           'fall': '{club} : {metric}, de {before} à {after} dans les dix minutes après le changement ({change})',
           'context': 'un écart plus grand que {pct} des périodes de dix minutes du match',
           'caveat': "Cela coïncide avec le changement ; cela ne montre pas que le changement en est la cause.",
           'riser': '{player} participe davantage au jeu de passes ({before} → {after} des passes réussies)'},
    'pt': {'ppda_less': 'pressão menos intensa', 'ppda_more': 'pressão mais intensa', 'final_third_entries': 'entradas no terço final', 'shots': 'finalizações', 'xg': 'gols esperados (xG)',
           'pass_completion': 'acerto de passes', 'possession': 'posse', 'ppda': 'passes permitidos por ação defensiva (PPDA)',
           'high_turnovers': 'recuperações altas', 'line_height': 'altura da linha defensiva', 'width': 'largura do time',
           'compactness': 'compactação (distância média ao centro do time)',
           'sub': 'entra {on} no lugar de {off}', 'red': 'expulsão de {player}',
           'rise': '{club}: {metric}, de {before} para {after} nos dez minutos após a mudança ({change})',
           'fall': '{club}: {metric}, de {before} para {after} nos dez minutos após a mudança ({change})',
           'context': 'uma variação maior que {pct} dos períodos de dez minutos da partida',
           'caveat': 'Isso coincide com a mudança; não mostra que a mudança foi a causa.',
           'riser': '{player} participou mais da troca de passes ({before} → {after} dos passes certos)'},
    'de': {'ppda_less': 'weniger intensives Pressing', 'ppda_more': 'intensiveres Pressing', 'final_third_entries': 'Vorstöße ins letzte Drittel', 'shots': 'Schüsse', 'xg': 'erwartete Tore (xG)',
           'pass_completion': 'Passquote', 'possession': 'Ballbesitz', 'ppda': 'zugelassene Pässe pro Defensivaktion (PPDA)',
           'high_turnovers': 'hohe Ballgewinne', 'line_height': 'Höhe der Abwehrlinie', 'width': 'Mannschaftsbreite',
           'compactness': 'Kompaktheit (mittlerer Abstand zur Mannschaftsmitte)',
           'sub': '{on} kommt für {off}', 'red': 'Platzverweis für {player}',
           'rise': '{club}: {metric} von {before} auf {after} in den zehn Minuten nach dem Wechsel ({change})',
           'fall': '{club}: {metric} von {before} auf {after} in den zehn Minuten nach dem Wechsel ({change})',
           'context': 'eine größere Veränderung als {pct} der Zehn-Minuten-Abschnitte dieses Spiels',
           'caveat': 'Das fällt mit dem Wechsel zusammen; es zeigt nicht, dass der Wechsel die Ursache war.',
           'riser': '{player} war stärker am Passspiel beteiligt ({before} → {after} der angekommenen Pässe)'},
    'it': {'ppda_less': 'pressing meno intenso', 'ppda_more': 'pressing più intenso', 'final_third_entries': "ingressi nell'ultimo terzo", 'shots': 'tiri', 'xg': 'gol attesi (xG)',
           'pass_completion': 'precisione nei passaggi', 'possession': 'possesso', 'ppda': 'passaggi concessi per azione difensiva (PPDA)',
           'high_turnovers': 'recuperi alti', 'line_height': 'altezza della linea difensiva', 'width': 'ampiezza della squadra',
           'compactness': 'compattezza (distanza media dal centro della squadra)',
           'sub': 'entra {on} per {off}', 'red': 'espulsione di {player}',
           'rise': '{club}: {metric}, da {before} a {after} nei dieci minuti dopo il cambio ({change})',
           'fall': '{club}: {metric}, da {before} a {after} nei dieci minuti dopo il cambio ({change})',
           'context': 'una variazione maggiore del {pct} dei periodi di dieci minuti della partita',
           'caveat': 'Questo coincide con il cambio; non dimostra che il cambio ne sia la causa.',
           'riser': '{player} partecipa di più al giro palla ({before} → {after} dei passaggi riusciti)'},
    'ar': {'ppda_less': 'ضغط أقل شدة', 'ppda_more': 'ضغط أشد', 'final_third_entries': 'الدخول إلى الثلث الأخير', 'shots': 'التسديدات', 'xg': 'الأهداف المتوقعة (xG)',
           'pass_completion': 'دقة التمرير', 'possession': 'الاستحواذ', 'ppda': 'التمريرات المسموحة لكل تدخل دفاعي (PPDA)',
           'high_turnovers': 'استعادات الكرة في مناطق متقدمة', 'line_height': 'ارتفاع خط الدفاع', 'width': 'عرض الفريق',
           'compactness': 'التماسك (متوسط البعد عن مركز الفريق)',
           'sub': 'دخول {on} بدلاً من {off}', 'red': 'طرد {player}',
           'rise': '{club}: {metric} من {before} إلى {after} في الدقائق العشر بعد التغيير ({change})',
           'fall': '{club}: {metric} من {before} إلى {after} في الدقائق العشر بعد التغيير ({change})',
           'context': 'تغيّر أكبر من {pct} من فترات الدقائق العشر في هذه المباراة',
           'caveat': 'يتزامن هذا مع التغيير، لكنه لا يثبت أن التغيير هو السبب.',
           'riser': '{player} شارك أكثر في التمرير ({before} ← {after} من التمريرات الصحيحة)'},
}


def _clock(e: Event) -> int:
    return e.minute * 60 + e.second


def played_time(events: list[Event]) -> list[Event]:
    """Provider events carry a period and a scoreboard clock whose stoppage time overlaps the next
    period (first-half 45:00+ and second-half 45:00). Re-time them on one continuous clock of time
    played, so ten-minute windows never mix periods and extra time is included. Synthetic events
    (no period) are returned unchanged."""
    if not any(e.period for e in events):
        return events
    nominal = {1: 0, 2: 45 * 60, 3: 90 * 60, 4: 105 * 60}
    length: dict[int, int] = {}
    for e in events:
        length[e.period] = max(length.get(e.period, 0), _clock(e) - nominal[e.period] + 1)
    offset, total = {}, 0
    for period in sorted(length):
        offset[period] = total
        total += length[period]
    out = []
    for e in events:
        elapsed = offset[e.period] + _clock(e) - nominal[e.period]
        out.append(replace(e, minute=elapsed // 60, second=elapsed % 60, period=None))
    return out


def scoreboard(e: Event) -> str:
    """The minute a scoreboard shows for a provider event: 23', 45+2', 90+4', 105+1'."""
    end = {1: 45, 2: 90, 3: 105, 4: 120}.get(e.period or 0)
    shown = e.minute + 1
    return f"{end}+{shown - end}'" if end and shown > end else f"{shown}'"


def change_points(events: list[Event], minute: int = 90) -> list[dict[str, Any]]:
    """Substitutions and red cards before `minute`, simultaneous changes for a team grouped."""
    points: list[dict[str, Any]] = []
    for e in events:
        if e.minute >= minute:
            break
        sub = e.event_type == 'substitution' and e.replacement_player_id
        red = e.event_type == 'card' and e.outcome in SENDING_OFF
        if not (sub or red):
            continue
        item = ({'kind': 'substitution', 'on': e.replacement_player_id, 'off': e.player_id} if sub
                else {'kind': 'red_card', 'player': e.player_id})
        last = points[-1] if points else None
        if last and last['team_id'] == e.team_id and _clock(e) - last['clock'] <= 60:
            last['changes'].append(item)
            last['event_ids'].append(e.event_id)
        else:
            points.append({'id': f"change:{e.team_id}:{_clock(e)}", 'team_id': e.team_id, 'clock': _clock(e),
                           'changes': [item], 'event_ids': [e.event_id]})
    return points


def window_metrics(events: list[Event], team: str, start: int, end: int) -> dict[str, Any]:
    """Attacking, possession and pressing measures for one team in [start, end) seconds, with evidence."""
    other = 'away' if team == 'home' else 'home'
    inside = [e for e in events if start <= _clock(e) < end]
    own = [e for e in inside if e.team_id == team]
    entries = [e for e in own if e.event_type == 'pass' and e.outcome == 'success' and (e.end_x or 0) >= FINAL_THIRD
               and e.x < FINAL_THIRD]
    shots = [e for e in own if e.event_type == 'shot']
    passes = [e for e in own if e.event_type == 'pass']
    # Pressing: opponent passes in their own 60% vs this team's defensive actions in its pressing zone.
    opp_build_up = [e for e in inside if e.team_id == other and e.event_type == 'pass' and e.x < 100 - PRESS_ZONE]
    actions = [e for e in own if e.event_type in ('tackle', 'recovery', 'foul') and e.x >= PRESS_ZONE]
    high = [e for e in own if e.event_type in ('tackle', 'recovery') and e.outcome == 'success' and e.x >= HIGH_TURNOVER]
    held = {t: 0.0 for t in TEAMS}
    order = sorted(inside, key=lambda e: e.sequence)
    for a, b in zip(order, order[1:]):
        held[a.team_id] += max(0, _clock(b) - _clock(a))
    total = sum(held.values())
    return {
        'final_third_entries': {'value': len(entries), 'evidence': [e.event_id for e in entries]},
        'shots': {'value': len(shots), 'evidence': [e.event_id for e in shots]},
        'xg': {'value': round(sum(e.xg or 0 for e in shots), 2), 'evidence': [e.event_id for e in shots]},
        'pass_completion': {'value': round(100 * sum(e.outcome == 'success' for e in passes) / len(passes), 1) if passes else None,
                            'evidence': [e.event_id for e in passes]},
        'possession': {'value': round(100 * held[team] / total, 1) if total else None, 'evidence': []},
        'ppda': {'value': round(len(opp_build_up) / len(actions), 1) if actions else None,
                 'evidence': [e.event_id for e in actions]},
        'high_turnovers': {'value': len(high), 'evidence': [e.event_id for e in high]},
    }


@lru_cache(maxsize=16)
def _shape_cached(events: tuple, start: int, end: int) -> dict[str, dict[str, float]]:
    from .tracking import LENGTH, track
    clip = track(list(events), start, end, fps=2, warmup=10.0)
    out = {}
    for team in TEAMS:
        lines, widths, compact = [], [], []
        for f in clip['frames']:
            pts = [(x, y) for pid, (x, y) in f['players'].items() if clip['teams'].get(pid) == team]
            outfield = [(x if team == 'home' else LENGTH - x, y) for x, y in pts]
            outfield.sort()
            outfield = outfield[1:]  # the deepest player is the goalkeeper
            if len(outfield) < 6:
                continue
            lines.append(sum(x for x, _ in outfield[:4]) / 4)
            ys = sorted(y for _, y in outfield)
            widths.append(ys[-1] - ys[0])
            cx = sum(x for x, _ in outfield) / len(outfield)
            cy = sum(y for _, y in outfield) / len(outfield)
            compact.append(sum(math.hypot(x - cx, y - cy) for x, y in outfield) / len(outfield))
        mean = lambda v: round(sum(v) / len(v), 1) if v else None
        out[team] = {'line_height': mean(lines), 'width': mean(widths), 'compactness': mean(compact)}
    return out


def shape(events: list[Event], start: int, end: int) -> dict[str, dict[str, float]]:
    """Defensive shape from the 25 Hz tracking (sampled at 2 Hz): metres, each team attacking up the pitch."""
    return _shape_cached(tuple(e for e in events if _clock(e) < end + 5), max(0, start), end)


@lru_cache(maxsize=8)
def _windows(events: tuple, team: str) -> dict[int, dict[str, Any]]:
    """Every ten-minute window of the match, starting on each minute, computed once."""
    last = max((_clock(e) for e in events), default=0)
    return {t: window_metrics(list(events), team, t, t + WINDOW) for t in range(0, max(90 * 60, last) - WINDOW + 1, 60)}


def swing_percentile(events: list[Event], team: str, metric: str, delta: float, upto: int) -> int | None:
    """How unusual a before/after swing is: the share of all ten-minute swings of this metric in
    the match so far (step one minute) that were smaller."""
    if delta is None:
        return None
    windows = _windows(tuple(events), team)
    swings = []
    for t in range(WINDOW, upto - WINDOW + 1, 60):
        if t not in windows:  # past the last event
            break
        a, b = windows[t - WINDOW][metric]['value'], windows[t][metric]['value']
        if a is not None and b is not None:
            swings.append(abs(b - a))
    if len(swings) < 5:
        return None
    return round(100 * sum(s < abs(delta) for s in swings) / len(swings))


def _involvement(events: list[Event], team: str, start: int, end: int) -> dict[str, float]:
    window = roles(passing_graph([e for e in events if start <= _clock(e) < end], team, 0, 90), team, 0, 90)
    return {p['player_id']: p['pass_share'] for p in window['players']}


def impact(events: list[Event], point: dict[str, Any], minute: int, code: str = 'en', names=None, clubs=None,
           with_shape: bool = True) -> dict[str, Any]:
    """Before/after comparison for a change point; available once ten minutes have passed.
    `names`/`clubs` override the demo squads (provider rosters); `with_shape=False` leaves out the
    shape measures when there is no tracking for the match."""
    name = names or globals()['name']
    club_name = (lambda t: clubs[t]) if clubs else (lambda t: CLUBS[t].short)
    t = point['clock']
    upto = minute * 60
    if t + WINDOW > upto or t - WINDOW < 0:
        return {**point, 'available': False, 'reason': 'needs ten minutes either side of the change'}
    text = TEXT[code]
    num = lambda v, unit='': format_number(v, unit, code)
    changes = [text['sub'].format(on=name(c['on']), off=name(c['off'])) if c['kind'] == 'substitution'
               else text['red'].format(player=name(c['player'])) for c in point['changes']]
    label = ', '.join(changes)
    if with_shape:
        shape_before, shape_after = shape(events, t - WINDOW, t), shape(events, t, t + WINDOW)
    teams = {}
    for team in TEAMS:
        before, after = window_metrics(events, team, t - WINDOW, t), window_metrics(events, team, t, t + WINDOW)
        metrics = []
        for key in ('final_third_entries', 'shots', 'xg', 'pass_completion', 'possession', 'ppda', 'high_turnovers'):
            a, b = before[key]['value'], after[key]['value']
            delta = None if a is None or b is None else round(b - a, 2)
            pct = swing_percentile(events, team, key, delta, upto) if delta else None
            notable = bool(pct is not None and pct >= NOTABLE_PERCENTILE
                           and (key not in COUNT_METRICS or abs(delta) >= 3))
            metrics.append({'metric': key, 'label': text[key], 'before': a, 'after': b, 'delta': delta,
                            'swing_percentile': pct, 'notable': notable,
                            'evidence_event_ids': sorted(set(before[key]['evidence'] + after[key]['evidence']))})
        for key in ('line_height', 'width', 'compactness') if with_shape else ():
            a, b = shape_before[team][key], shape_after[team][key]
            metrics.append({'metric': key, 'label': text[key], 'before': a, 'after': b,
                            'delta': None if a is None or b is None else round(b - a, 1), 'unit': 'm',
                            'swing_percentile': None, 'notable': False, 'evidence_event_ids': [],
                            'source': 'synthetic_tracking'})
        statements = []
        club = club_name(team)
        for m in metrics:
            if not m['notable']:
                continue
            unit = '%' if m['metric'] in ('pass_completion', 'possession') else ''
            line = text['rise' if m['delta'] > 0 else 'fall'].format(
                club=club, metric=m['label'], before=num(m['before'], unit), after=num(m['after'], unit), change=label)
            if m['metric'] == 'ppda':  # a higher PPDA means the team pressed less
                line += f" — {text['ppda_less' if m['delta'] > 0 else 'ppda_more']}"
            joiner = '، ' if code == 'ar' else '; '
            statements.append(f"{line}{joiner}{text['context'].format(pct=num(m['swing_percentile'], '%'))}.")
        share_before = _involvement(events, team, t - WINDOW, t)
        share_after = _involvement(events, team, t, t + WINDOW)
        risers = sorted(((share_after.get(p, 0) - share_before.get(p, 0), p) for p in share_after), reverse=True)[:2]
        risers = [{'player_id': p, 'name': name(p), 'before': round(share_before.get(p, 0), 3),
                   'after': round(share_after[p], 3)} for d, p in risers if d >= 0.08]
        for r in risers[:1]:
            if team == point['team_id']:
                statements.append(f'{club}: ' + text['riser'].format(player=r['name'], before=num(round(100 * r['before']), '%'),
                                                       after=num(round(100 * r['after']), '%')) + '.')
        incoming = [c['on'] for c in point['changes'] if c['kind'] == 'substitution' and c['on'].startswith(team)]
        teams[team] = {'metrics': metrics, 'statements': statements, 'risers': risers,
                       'incoming': [{'player_id': p, 'name': name(p), 'pass_share': round(share_after.get(p, 0), 3)}
                                    for p in incoming]}
    return {**point, 'available': True, 'label': label, 'window_seconds': WINDOW, 'teams': teams,
            'caveat': text['caveat'], 'language': code}


def pressing(events: list[Event], minute: int, window_minutes: int = 15, with_shape: bool = True) -> dict[str, Any]:
    """Pressing and shape for both teams over the last `window_minutes`."""
    end = minute * 60
    start = max(0, end - window_minutes * 60)
    sh = shape(events, start, end) if with_shape else {t: {} for t in TEAMS}
    out = {}
    for team in TEAMS:
        m = window_metrics(events, team, start, end)
        out[team] = {'ppda': m['ppda']['value'], 'high_turnovers': m['high_turnovers']['value'],
                     'evidence_event_ids': m['high_turnovers']['evidence'], **sh[team]}
    return {'window': [start // 60, minute], 'teams': out,
            'definitions': {'ppda': 'opponent passes in their own 60% per tackle, recovery or foul in the pressing zone; lower means more intense pressing',
                            'high_turnovers': "balls won in the opponent's last 40%",
                            'line_height': 'average distance of the four deepest outfield players from their own goal (m)',
                            'width': 'distance between the widest outfield players (m)',
                            'compactness': 'average distance of outfield players to the team centre (m); lower is more compact'}}
