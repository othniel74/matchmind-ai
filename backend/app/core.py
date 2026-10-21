"""Deterministic synthetic football events and evidence-backed match intelligence.

Pitch coordinates are 0..100. X is attack-relative (each team attacks positive
X); Y is shared across teams. This is a synthetic *event* model with a
possession-based clock, not a tracking-data model or a calibrated replica of
any real competition.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from random import Random
from typing import Any
import math

TEAMS = ('home', 'away')
GENERATOR_VERSION = 'possession-v4'
DEFAULT_SEED = 20261020
HALF_SECONDS = 45 * 60
EVENT_TYPES = frozenset({'pass', 'shot', 'recovery', 'tackle', 'foul', 'card', 'substitution'})
# Actions that move or contest the ball; fouls, cards and substitutions do not.
ON_BALL_TYPES = frozenset({'pass', 'shot', 'recovery', 'tackle'})
SET_PIECES = frozenset({'kick_off', 'throw_in', 'goal_kick', 'corner', 'free_kick', 'penalty'})
SHOT_SET_PIECES = frozenset({'corner', 'free_kick', 'penalty'})
CARD_OUTCOMES = frozenset({'yellow', 'second_yellow', 'red'})
SENDING_OFF = frozenset({'second_yellow', 'red'})

# The same illustrative 4-3-3 as pitch.py: (role, attack-relative x, home y).
SLOTS = (('GK', 8, 50), ('RB', 25, 14), ('RCB', 23, 38), ('LCB', 23, 62), ('LB', 25, 86),
         ('RCM', 44, 25), ('CDM', 42, 50), ('LCM', 44, 75), ('RW', 65, 16), ('ST', 68, 50), ('LW', 65, 84))

@dataclass(frozen=True)
class Event:
    event_id: str
    match_id: str
    sequence: int
    minute: int
    second: int
    team_id: str
    player_id: str
    event_type: str
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    outcome: str = 'success'
    possession_id: str = ''
    recipient_player_id: str | None = None
    set_piece: str | None = None
    xg: float | None = None
    replacement_player_id: str | None = None
    speed_kmh: float | None = None        # ball speed for passes and shots (synthetic)
    under_pressure: bool | None = None    # an opponent was close when a pass or shot was made
    period: int | None = None             # 1 or 2 (3-4 extra time) for provider feeds; None for synthetic streams
    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Scenario:
    """Hidden ground truth for evaluation. Never pass this to insight or narrative code."""
    kind: str  # 'territorial_shift' or 'control'
    team: str | None = None
    start_minute: int | None = None
    intensity: float = 0.0
    def json(self) -> dict[str, Any]:
        return asdict(self)


def scenario_for(seed: int) -> Scenario:
    # The default demo seed keeps its documented away shift after minute 58.
    if seed == DEFAULT_SEED:
        return Scenario('territorial_shift', 'away', 58, 1.0)
    rng = Random(f'scenario:{seed}')
    if rng.random() < .25:
        return Scenario('control')
    return Scenario('territorial_shift', rng.choice(TEAMS), rng.randint(50, 70), round(rng.uniform(.8, 1.2), 3))


def shot_xg(x: float, y: float) -> float:
    """Distance-based chance quality on a 105 x 68 m pitch; illustrative, not a fitted model."""
    distance = math.hypot((100 - x) * 1.05, (y - 50) * .68)
    angle = 1 - min(abs(y - 50) / 50, 1)
    return round(max(.01, min(.6, .85 * math.exp(-distance / 7.5) * (.55 + .45 * angle))), 3)


def _clamp(value: float, low: float = 1, high: float = 99) -> float:
    return max(low, min(high, value))


def _in_box(x: float, y: float) -> bool:
    return x >= 83 and 21 <= y <= 79


class _Simulator:
    def __init__(self, seed: int, match_id: str, scenario: Scenario | None = None):
        self.rng = Random(seed)
        self.match_id = match_id
        self.scenario = scenario or scenario_for(seed)
        # Ball speed and pressure use their own stream so the match itself is unchanged from v3.
        self.aux = Random(f'aux:{seed}')
        self.events: list[Event] = []
        self.half = 1
        self.t = 0.0
        self.possession = 0
        self.lineup = {team: [f'{team}-{i:02}' for i in range(1, 12)] for team in TEAMS}
        self.bench = {team: 12 for team in TEAMS}
        self.booked: set[str] = set()
        self.substituted_in: set[str] = set()
        self.windows = {team: self._substitution_plan() for team in TEAMS}
        # Per-match team quality creates realistic possession and chance imbalance.
        self.quality = {team: max(-1.0, min(1.0, self.rng.gauss(0, .7))) for team in TEAMS}

    def _substitution_plan(self) -> list[list[int]]:
        total = self.rng.choices([3, 4, 5], [.2, .35, .45])[0]
        count = min(total, self.rng.choice([2, 3]))
        minutes = sorted(self.rng.sample(range(56, 88), count))
        sizes = [1] * count
        for _ in range(total - count):
            sizes[self.rng.randrange(count)] += 1
        return [[minute * 60, size] for minute, size in zip(minutes, sizes)]

    # Clock and emission ------------------------------------------------
    @property
    def elapsed(self) -> int:
        return (self.half - 1) * HALF_SECONDS + int(self.t)

    def wait(self, low: float, high: float) -> None:
        self.t += self.rng.uniform(low, high)

    def emit(self, team: str, player: str, kind: str, x: float, y: float, **fields) -> Event:
        elapsed = min(self.elapsed, self.half * HALF_SECONDS - 1)
        if kind in ('pass', 'shot'):
            fields.update(self.ball_context(team, kind, x, y, fields))
        event = Event(f'evt-{len(self.events) + 1:05}', self.match_id, len(self.events) + 1,
                      elapsed // 60, elapsed % 60, team, player, kind, round(x, 2), round(y, 2),
                      possession_id=fields.pop('possession_id', f'poss-{self.possession:04}'), **fields)
        self.events.append(event)
        return event

    def ball_context(self, team: str, kind: str, x: float, y: float, fields: dict) -> dict:
        """Synthetic ball speed and pressure, drawn from the auxiliary stream."""
        aux = self.aux
        opponent = 'away' if team == 'home' else 'home'
        pressing = self.pressing(opponent) if x < 55 else 0.0
        under_pressure = aux.random() < .22 + .25 * pressing + (.12 if x >= 70 else 0)
        set_piece = fields.get('set_piece')
        if kind == 'pass':
            distance = math.hypot(((fields.get('end_x') or x) - x) * 1.05, ((fields.get('end_y') or y) - y) * .68)
            speed = 25 + distance * 1.1 + aux.gauss(0, 5)
            speed = max(15.0, min(110.0, speed))
        else:
            distance = math.hypot((100 - x) * 1.05, (y - 50) * .68)
            if set_piece == 'penalty':
                speed = aux.gauss(95, 8)
            elif set_piece == 'corner':  # headed or volleyed from a cross
                speed = aux.gauss(58, 10)
            else:
                speed = 98 - distance * .55 + aux.gauss(0, 10)
            speed = max(35.0, min(135.0, speed))
        return {'speed_kmh': round(speed, 1), 'under_pressure': under_pressure and set_piece != 'penalty'}

    # Team context -------------------------------------------------------
    def pressing(self, team: str) -> float:
        s = self.scenario
        if s.kind == 'territorial_shift' and s.team == team and self.elapsed >= s.start_minute * 60:
            return s.intensity
        return 0.0

    def missing(self, team: str) -> int:
        return sum(p is None for p in self.lineup[team])

    def pick(self, team: str, x: float, y: float, exclude: str | None = None, outfield: bool = False) -> str:
        candidates, weights = [], []
        for (role, ax, ay), player in zip(SLOTS, self.lineup[team]):
            if player is None or player == exclude:
                continue
            anchor_y = ay if team == 'home' else 100 - ay
            if role == 'GK':
                weight = 0.0 if outfield else (3.0 if x < 18 else 0.0)
            else:
                weight = math.exp(-abs(x - ax) / 22) * math.exp(-abs(y - anchor_y) / 30)
            if weight > 0:
                candidates.append(player)
                weights.append(weight)
        return self.rng.choices(candidates, weights)[0]

    def keeper(self, team: str) -> str:
        return self.lineup[team][0] or self.pick(team, 6, 50, outfield=True)

    # Dead-ball administration ---------------------------------------------
    def substitutions(self) -> None:
        for team in TEAMS:
            for window in self.windows[team]:
                if window[1] and window[0] <= self.elapsed:
                    for _ in range(window[1]):
                        self.substitute(team)
                    window[1] = 0
                    self.wait(15, 30)

    def substitute(self, team: str) -> None:
        slots = [i for i, p in enumerate(self.lineup[team]) if i and p and p not in self.substituted_in]
        if not slots:
            return
        index = self.rng.choices(slots, [3 if i >= 8 else 2.5 if i >= 5 else 1 for i in slots])[0]
        replacement = f'{team}-{self.bench[team]:02}'
        self.bench[team] += 1
        self.emit(team, self.lineup[team][index], 'substitution', 50, 0, possession_id='',
                  replacement_player_id=replacement)
        self.lineup[team][index] = replacement
        self.substituted_in.add(replacement)

    # Match flow ------------------------------------------------------------
    def run(self) -> list[Event]:
        for half in (1, 2):
            self.half, self.t = half, 0.0
            restart = ('home' if half == 1 else 'away', 'kick_off', 50.0, 50.0)
            while restart is not None and self.t < HALF_SECONDS:
                if restart[1] in SET_PIECES and half == 2:
                    self.substitutions()
                    if self.t >= HALF_SECONDS:
                        break
                restart = self.play(*restart)
        return self.events

    def play(self, team: str, start: str, x: float, y: float):
        """Run one possession and return the next possession's (team, start, x, y)."""
        self.possession += 1
        opponent = 'away' if team == 'home' else 'home'
        if start in ('recovery', 'tackle'):
            self.emit(team, self.pick(team, x, y), start, x, y)
            self.wait(1.5, 3)
        else:
            outcome = self.set_piece(team, opponent, start, x, y)
            if outcome[0] == 'next':
                return outcome[1]
            x, y = outcome[1]
        holder = self.events[-1].recipient_player_id or self.events[-1].player_id
        while self.t < HALF_SECONDS:
            pressure = self.pressing(opponent) if x < 55 else 0.0
            roll = self.rng.random()
            foul_rate = .024 * (.3 if _in_box(x, y) else 1)
            tackle_rate = .033 + .05 * pressure + .012 * (self.quality[opponent] - self.quality[team])
            if roll < foul_rate:
                return self.foul(team, opponent, x, y)
            if roll < foul_rate + tackle_rate:
                self.wait(1, 2.5)
                return opponent, 'tackle', 100 - x, y
            if x >= 72:
                chance = (.08 + .5 * max(0, (x - 78) / 22)) * (1 - abs(y - 50) / 50) ** .5
                if self.rng.random() < chance:
                    return self.shot(team, opponent, holder, x, y)
            result = self.open_pass(team, opponent, holder, x, y, pressure)
            if result[0] == 'next':
                return result[1]
            holder, x, y = result[1]
        return None

    def open_pass(self, team, opponent, holder, x, y, pressure):
        boost = self.pressing(team) + .8 * self.quality[team]
        long_ball = self.rng.random() < .12
        if long_ball:
            dx, dy = self.rng.gauss(22 + 3 * boost, 11), self.rng.gauss(0, 26)
        else:
            mu = 6 if x < 35 else 4 if x < 65 else .5
            dx, dy = self.rng.gauss(mu + 3 * boost, 11), self.rng.gauss(0, 16)
        ex, ey = _clamp(x + dx), _clamp(y + dy)
        complete = .925 if ex < 40 else .85 if ex < 70 else .69
        complete += .05 * self.quality[team]
        complete -= (.17 if long_ball else 0) + .1 * pressure * (x < 50) + .02 * self.missing(team)
        return self.pass_(team, opponent, holder, x, y, ex, ey, complete)

    def pass_(self, team, opponent, holder, x, y, ex, ey, complete, set_piece=None):
        ex, ey = _clamp(ex), _clamp(ey)
        success = self.rng.random() < complete
        recipient = self.pick(team, ex, ey, exclude=holder) if success else None
        self.emit(team, holder, 'pass', x, y, end_x=round(ex, 2), end_y=round(ey, 2),
                  outcome='success' if success else 'failed', recipient_player_id=recipient, set_piece=set_piece)
        self.wait(2, 5)
        if success:
            return 'continue', (recipient, ex, ey)
        if ex >= 80 and self.rng.random() < .1:
            return 'next', (team, 'corner', 100.0, ey)
        if ex >= 97 or (self.rng.random() < .28):
            if ex >= 97:
                return 'next', (opponent, 'goal_kick', 6.0, 50.0)
            side = 0.5 if ey < 50 else 99.5
            return 'next', (opponent, 'throw_in', 100 - ex, side)
        return 'next', (opponent, 'recovery', 100 - ex, ey)

    def set_piece(self, team, opponent, start, x, y):
        rng = self.rng
        if start == 'kick_off':
            self.wait(2, 4)
            holder = self.pick(team, 50, 50, outfield=True)
            return self._continue(self.pass_(team, opponent, holder, 50, 50, 38 + rng.uniform(-4, 4),
                                             50 + rng.uniform(-15, 15), .97, 'kick_off'))
        if start == 'throw_in':
            self.wait(6, 14)
            holder = self.pick(team, x, y, outfield=True)
            return self._continue(self.pass_(team, opponent, holder, x, y, _clamp(x + rng.gauss(2, 6)),
                                             _clamp(y + (12 if y < 50 else -12) + rng.gauss(0, 5)), .8, 'throw_in'))
        if start == 'goal_kick':
            self.wait(14, 24)
            holder = self.keeper(team)
            if rng.random() < .5:
                return self._continue(self.pass_(team, opponent, holder, 6, 50, 45 + rng.gauss(0, 10),
                                                 _clamp(50 + rng.gauss(0, 25)), .55, 'goal_kick'))
            return self._continue(self.pass_(team, opponent, holder, 6, 50, 18, rng.choice([30, 70]), .97, 'goal_kick'))
        if start == 'corner':
            self.wait(18, 32)
            holder = self.pick(team, 90, y, outfield=True)
            corner_y = 0.5 if y < 50 else 99.5
            result = self.pass_(team, opponent, holder, 100, corner_y, 90 + rng.gauss(0, 3),
                                _clamp(50 + rng.gauss(0, 12)), .33, 'corner')
            if result[0] == 'continue' and rng.random() < .55:
                receiver, ex, ey = result[1]
                return 'next', self.shot(team, opponent, receiver, ex, ey, factor=.7, set_piece='corner')
            return self._continue(result)
        if start == 'penalty':
            self.wait(50, 80)
            return 'next', self.shot(team, opponent, self.pick(team, 89, 50, outfield=True), 89, 50,
                                     fixed=.76, set_piece='penalty')
        # Free kick
        self.wait(12, 25)
        holder = self.pick(team, x, y, outfield=True)
        if x >= 72 and abs(y - 50) < 25 and rng.random() < .35:
            return 'next', self.shot(team, opponent, holder, x, y, fixed=round(min(.1, shot_xg(x, y) * .5), 3),
                                     set_piece='free_kick')
        if x >= 65:
            return self._continue(self.pass_(team, opponent, holder, x, y, 90 + rng.gauss(0, 3),
                                             _clamp(50 + rng.gauss(0, 12)), .4, 'free_kick'))
        return self._continue(self.pass_(team, opponent, holder, x, y, _clamp(x + rng.gauss(8, 8)),
                                         _clamp(y + rng.gauss(0, 12)), .88, 'free_kick'))

    @staticmethod
    def _continue(result):
        if result[0] == 'next':
            return result
        _, ex, ey = result[1]
        return 'continue', (ex, ey)

    def shot(self, team, opponent, shooter, x, y, factor=1.0, fixed=None, set_piece=None):
        rng = self.rng
        xg = fixed if fixed is not None else round(max(.01, shot_xg(x, y) * factor), 3)
        if rng.random() < xg:
            outcome = 'goal'
        else:
            outcome = rng.choices(['blocked', 'saved', 'missed'], [.27, .31, .42])[0]
            if set_piece == 'penalty' and outcome == 'blocked':
                outcome = 'saved'
        self.emit(team, shooter, 'shot', x, y, outcome=outcome, xg=xg, set_piece=set_piece)
        if outcome == 'goal':
            self.wait(45, 70)
            return opponent, 'kick_off', 50.0, 50.0
        self.wait(2, 5)
        if outcome == 'missed':
            return opponent, 'goal_kick', 6.0, 50.0
        if rng.random() < (.25 if outcome == 'saved' else .35):
            return team, 'corner', 100.0, y
        if outcome == 'saved':
            return opponent, 'recovery', 6.0, 50.0
        return opponent, 'recovery', 100 - x, y

    def foul(self, team, opponent, x, y):
        rng = self.rng
        defender_x = 100 - x
        fouler = self.pick(opponent, defender_x, y, outfield=defender_x >= 18)
        penalty = _in_box(x, y) and rng.random() < .9
        self.emit(opponent, fouler, 'foul', defender_x, y, outcome='penalty' if penalty else 'free_kick')
        roll = rng.random()
        # Referees are more lenient with players already on a yellow card.
        booked = fouler in self.booked
        card = 'red' if roll < .004 else None
        if card is None and roll < (.004 + (.07 if booked else .19)):
            card = 'second_yellow' if booked else 'yellow'
        if card:
            self.wait(10, 25)
            self.emit(opponent, fouler, 'card', defender_x, y, outcome=card)
            if card == 'yellow':
                self.booked.add(fouler)
            else:
                self.lineup[opponent][self.lineup[opponent].index(fouler)] = None
        return team, 'penalty' if penalty else 'free_kick', x, y


def simulate_match(seed: int = DEFAULT_SEED, match_id: str = 'demo-001',
                   scenario: Scenario | None = None) -> tuple[list[Event], Scenario]:
    """Return a reproducible match and its hidden scenario label.

    `scenario` overrides the seed's label for evaluation sweeps only; product code never sets it."""
    simulator = _Simulator(seed, match_id, scenario)
    return simulator.run(), simulator.scenario


def generate_match(seed: int = DEFAULT_SEED, match_id: str = 'demo-001') -> list[Event]:
    """Reproducible possession-based synthetic match (about 1,000 events)."""
    return simulate_match(seed, match_id)[0]


class StreamValidator:
    """Validates events one at a time, as a live feed delivers them.

    `add` checks an event against everything accepted so far and changes no state when it
    rejects one, so a bad event from a feed can be refused without corrupting the stream.
    """
    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.match_id: str | None = None
        self.previous = (-1, -1, -1, -1)
        self.seen_players: set[str] = set()
        self.unavailable: set[str] = set()
        self.booked: set[str] = set()

    def add(self, e: Event) -> None:
        if self.match_id is not None and e.match_id != self.match_id:
            raise ValueError('Mixed match identifiers')
        if e.event_id in self.ids:
            raise ValueError('Duplicate event ID')
        if e.team_id not in TEAMS or e.event_type not in EVENT_TYPES:
            raise ValueError('Unsupported team or event type')
        # Provider feeds carry a period, so stoppage time (45+2', 90+4') and extra time are valid;
        # synthetic streams have no period and stay within the 90 regulation minutes.
        max_minute = 130 if e.period else 90
        if e.period is not None and e.period not in (1, 2, 3, 4):
            raise ValueError('Invalid period')
        if not (0 <= e.minute < max_minute and 0 <= e.second < 60 and 0 <= e.x <= 100 and 0 <= e.y <= 100):
            raise ValueError('Invalid clock or pitch coordinates')
        # A player who has gone off can still be shown a card (from the bench), but cannot play the ball.
        if (e.event_type != 'card' and e.player_id in self.unavailable) or e.recipient_player_id in self.unavailable:
            raise ValueError('Player is no longer on the pitch')
        if e.event_type == 'pass':
            if e.end_x is None or e.end_y is None or not (0 <= e.end_x <= 100 and 0 <= e.end_y <= 100):
                raise ValueError('Pass must have valid destination')
            if e.outcome not in {'success','failed'}:
                raise ValueError('Invalid pass outcome')
            if e.recipient_player_id is not None and (e.outcome != 'success' or
                    not e.recipient_player_id.startswith(e.team_id + '-') or
                    e.recipient_player_id == e.player_id):
                raise ValueError('Invalid pass recipient')
        elif e.recipient_player_id is not None:
            raise ValueError('Only passes can have recipients')
        if e.set_piece is not None and not (
                (e.event_type == 'pass' and e.set_piece in SET_PIECES - {'penalty'}) or
                (e.event_type == 'shot' and e.set_piece in SHOT_SET_PIECES)):
            raise ValueError('Invalid set piece')
        if e.event_type == 'shot':
            if e.outcome not in {'success', 'goal', 'saved', 'missed', 'blocked'}:
                raise ValueError('Invalid shot outcome')
            if e.xg is not None and not 0 <= e.xg <= 1:
                raise ValueError('Invalid shot xG')
        elif e.xg is not None:
            raise ValueError('Only shots can have xG')
        if e.speed_kmh is not None and (e.event_type not in {'pass', 'shot'} or not 0 < e.speed_kmh <= 140):
            raise ValueError('Invalid ball speed')
        if e.under_pressure is not None and e.event_type not in {'pass', 'shot'}:
            raise ValueError('Only passes and shots record pressure')
        if e.event_type == 'foul' and e.outcome not in {'free_kick', 'penalty'}:
            raise ValueError('Invalid foul outcome')
        if e.event_type == 'card':
            if e.outcome not in CARD_OUTCOMES:
                raise ValueError('Invalid card outcome')
            if e.outcome != 'red' and (e.outcome == 'second_yellow') != (e.player_id in self.booked):
                raise ValueError('Inconsistent booking')
        if e.event_type == 'substitution':
            on = e.replacement_player_id
            if on is None or not on.startswith(e.team_id + '-') or on == e.player_id or on in self.seen_players:
                raise ValueError('Invalid substitution')
        elif e.replacement_player_id is not None:
            raise ValueError('Only substitutions can have replacements')
        if (e.period or 0, e.minute, e.second, e.sequence) <= self.previous:
            raise ValueError('Events out of order')
        # Every check passed: commit.
        self.match_id = e.match_id
        self.ids.add(e.event_id)
        if e.event_type == 'card':
            self.booked.add(e.player_id)
            if e.outcome in SENDING_OFF:
                self.unavailable.add(e.player_id)
        if e.event_type == 'substitution':
            self.unavailable.add(e.player_id)
            self.seen_players.add(e.replacement_player_id)
        if e.event_type != 'card':  # substitutes can be booked on the bench before they come on
            self.seen_players.add(e.player_id)
        if e.recipient_player_id:
            self.seen_players.add(e.recipient_player_id)
        self.previous = (e.period or 0, e.minute, e.second, e.sequence)


def validate_event_stream(events: list[Event]) -> None:
    """Reject malformed, duplicated, out-of-order or inconsistent events."""
    validator = StreamValidator()
    for e in events:
        validator.add(e)


def possession_seconds(events: list[Event]) -> dict[str, float]:
    """Time each team held the ball. A possession runs from its first event to the next
    possession's first event; the latest possession ends at its own latest event, so the
    result never uses future events."""
    starts: list[tuple[str, int]] = []
    last_clock: dict[str, int] = {}
    owner: dict[str, str] = {}
    for e in events:
        if not e.possession_id:
            continue
        clock = e.minute * 60 + e.second
        if e.possession_id not in owner:
            owner[e.possession_id] = e.team_id
            starts.append((e.possession_id, clock))
        last_clock[e.possession_id] = clock
    totals = {team: 0.0 for team in TEAMS}
    for index, (pid, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else last_clock[pid]
        totals[owner[pid]] += max(0, end - start)
    return totals


def pass_difficulty(e: Event) -> float:
    """Pass difficulty rating from 1 (simple) to 10 (very hard), from the pass itself.

    Longer, more forward passes into the final third under pressure are harder; restarts
    such as throw-ins and short goal kicks are easier. Deterministic and explainable.
    """
    if e.event_type != 'pass' or e.end_x is None or e.end_y is None:
        return 0.0
    distance = math.hypot((e.end_x - e.x) * 1.05, (e.end_y - e.y) * .68)
    forward = max(0.0, min((e.end_x - e.x) / 30, 1.0))
    score = (.15 + .35 * min(distance / 40, 1.0) + .2 * forward + .15 * (e.end_x >= 70)
             + .15 * bool(e.under_pressure) - .1 * (e.set_piece in {'throw_in', 'kick_off'}))
    return round(1 + 9 * max(0.0, min(score, 1.0)), 1)


def statistics(events: list[Event]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    held = possession_seconds(events)
    total_held = sum(held.values())
    for team in TEAMS:
        own = [e for e in events if e.team_id == team]
        passes = [e for e in own if e.event_type == 'pass']
        shots = [e for e in own if e.event_type == 'shot']
        cards = [e.outcome for e in own if e.event_type == 'card']
        completed = sum(e.outcome == 'success' for e in passes)
        entries = [e for e in passes if e.outcome == 'success' and e.x < 66.67 and e.end_x is not None and e.end_x >= 66.67]
        distances = [math.hypot((e.end_x-e.x)*1.05, (e.end_y-e.y)*.68) for e in passes if e.end_x is not None and e.end_y is not None]
        result[team] = {
            'events': len(own), 'passes': len(passes), 'completed_passes': completed,
            'pass_completion_pct': round(100*completed/len(passes),1) if passes else 0,
            'shots': len(shots),
            'shots_on_target': sum(e.outcome in {'goal', 'saved'} for e in shots),
            'goals': sum(e.outcome == 'goal' for e in shots),
            'xg': round(sum(e.xg or 0 for e in shots), 2),
            'possession_pct': round(100 * held[team] / total_held, 1) if total_held else 0,
            'recoveries': sum(e.event_type == 'recovery' for e in own),
            'tackles_won': sum(e.event_type == 'tackle' for e in own),
            'corners': sum(e.event_type == 'pass' and e.set_piece == 'corner' for e in own),
            'fouls': sum(e.event_type == 'foul' for e in own),
            'yellow_cards': sum(c in {'yellow', 'second_yellow'} for c in cards),
            'red_cards': sum(c in SENDING_OFF for c in cards),
            'substitutions': sum(e.event_type == 'substitution' for e in own),
            'final_third_entries': len(entries),
            'mean_pass_distance_m': round(sum(distances)/len(distances),1) if distances else 0,
            'advanced_events': sum(e.event_type in ON_BALL_TYPES and e.x >= 60 for e in own),
            'mean_pass_difficulty': round(sum(pass_difficulty(e) for e in passes) / len(passes), 1) if passes else 0,
            'mean_pass_speed_kmh': round(sum(e.speed_kmh or 0 for e in passes) / len(passes), 1) if passes else 0,
            'max_shot_speed_kmh': max((e.speed_kmh or 0 for e in shots), default=0),
        }
    return result


# An insight is two claims with different standards. The observed count change is a
# fact the evidence gate recomputes exactly, so it may publish. Reading that change as
# a tactical shift is an interpretation: on held-out synthetic labels its precision is
# far below the bar for unreviewed publication, so it is always routed to review.
#
# Count thresholds were chosen on tuning seeds 1000-1199. Overdispersion and the z
# threshold were calibrated on seeds 1000-1399 using windows with no shift in progress;
# z >= 2.5 gave about 0.1 false alert episodes per match. All are kept separate from
# the evaluation seeds in evaluation/run.py.
SHIFT_MIN_CURRENT = 35
SHIFT_MIN_INCREASE = 15
SHIFT_MIN_RATIO = 1.5
SHIFT_OVERDISPERSION = 3.3
SHIFT_Z_THRESHOLD = 2.5
INTERPRETATION_STATUS = 'review_required'


def _advanced(events: list[Event], team: str, start: int, end: int) -> list[Event]:
    return [e for e in events if e.team_id == team and start <= e.minute < end
            and e.event_type in ON_BALL_TYPES and e.x >= 60]


def shift_z(current: int, previous: int) -> float:
    """Window difference scaled by its overdispersed null spread (not Poisson)."""
    return round((current - previous) / math.sqrt(SHIFT_OVERDISPERSION * max(current + previous, 1)), 2)


def interpretation(current: int, previous: int) -> dict[str, Any]:
    z = shift_z(current, previous)
    return {'label': 'possible_territorial_shift', 'z_score': z,
            'meets_calibrated_threshold': z >= SHIFT_Z_THRESHOLD, 'z_threshold': SHIFT_Z_THRESHOLD,
            'status': INTERPRETATION_STATUS,
            'reason': 'Measured precision of shift interpretations is below the bar for unreviewed publication.'}


def validate_insight(insight: dict[str,Any], events: list[Event]) -> bool:
    """Recompute claimed activity counts, and any attached confidence, from the source stream."""
    minute = insight['minute']
    team = insight['team_id']
    by_id = {e.event_id:e for e in events}
    current = _advanced(events, team, minute - 10, minute)
    previous = _advanced(events, team, minute - 20, minute - 10)
    refs = insight['evidence_event_ids']
    if 'interpretation' in insight and insight['interpretation'] != interpretation(len(current), len(previous)):
        return False
    return (len(refs) == len(set(refs)) and all(i in by_id for i in refs)
        and set(refs) == {e.event_id for e in current}
        and insight['current_count'] == len(current)
        and insight['previous_count'] == len(previous)
        and insight['previous_count'] >= 0)


def detect_insights(events: list[Event], minute: int) -> list[dict[str, Any]]:
    if minute < 20:
        return []
    insights: list[dict[str,Any]] = []
    for team in TEAMS:
        a = _advanced(events, team, minute - 10, minute)
        b = _advanced(events, team, minute - 20, minute - 10)
        if len(a) >= SHIFT_MIN_CURRENT and len(a) - len(b) >= SHIFT_MIN_INCREASE and len(a) >= SHIFT_MIN_RATIO * len(b):
            insight = {
                'id': f'activity-{team}-{minute}', 'minute': minute,
                'team_id': team, 'type': 'advanced_activity_increase', 'claim_type': 'observed_fact',
                'headline': f'{team.title()} team: more advanced-area activity',
                'explanation': f'Advanced-area on-ball events increased from {len(b)} to {len(a)} across consecutive ten-minute windows. This is an observed count; whether it reflects a tactical shift needs review.',
                'previous_count': len(b), 'current_count': len(a),
                'evidence_event_ids': [e.event_id for e in a],
                'interpretation': interpretation(len(a), len(b)),
            }
            insight['validated'] = validate_insight(insight, events)
            if insight['validated']:
                insights.append(insight)
    return insights
