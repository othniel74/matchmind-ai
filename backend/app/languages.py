"""Language registry: every user-facing template, label and number format in one place.

Adding a language means adding one entry here; narratives, overlays, claims, agents and
the API read from this registry. Translations were written for this prototype and need
review by native-speaking editors before broadcast use.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str
    name: str            # English name, used in agent instructions
    native: str          # Name shown in the language picker
    direction: str       # 'ltr' or 'rtl'
    decimal: str         # decimal separator
    percent: str         # '{}%' pattern, e.g. '{} %' for a spaced percent sign
    score: str           # separator between scores, e.g. '–' or ':'
    narrative: dict[str, str]      # headline, analyst, fan, broadcast templates
    metric_label: str              # overlay metric label
    claims: dict[str, str]         # score, compare, team_value templates
    percent_joiner: str = ' '      # word between a percentage and its label, e.g. ' de '
    metrics: dict[str, str] = field(default_factory=dict)


LANGUAGES: dict[str, Language] = {}


def _add(language: Language) -> None:
    LANGUAGES[language.code] = language


_add(Language(
    'en', 'English', 'English', 'ltr', '.', '{}%', '–',
    narrative={
        'headline': '{club}: more advanced-area activity',
        'analyst': 'Advanced-area events rose from {prev} to {curr} across consecutive ten-minute windows. '
                   'This is an observed activity change, not proof of tactical causation.',
        'fan': '{club} is getting into advanced areas more often: {prev} actions before, now {curr}.',
        'broadcast': 'Advanced-area activity: {prev} → {curr} (consecutive 10-minute windows).'},
    metric_label='Advanced-area events / 10 min',
    claims={'score': '{home} {h}{sep}{a} {away} before minute {m}.',
            'compare': 'Before minute {m}, {label}: {home} {h}, {away} {a}.',
            'team_value': '{team}: {value}{joiner}{label} before minute {m}.'},
    metrics={'goals': 'goals', 'shots': 'shots', 'shots_on_target': 'shots on target',
             'xg': 'expected goals (xG)', 'pass_completion': 'pass completion', 'possession': 'possession',
             'corners': 'corners', 'fouls': 'fouls', 'yellow_cards': 'yellow cards', 'red_cards': 'red cards',
             'substitutions': 'substitutions'}))

_add(Language(
    'es', 'Spanish', 'Español', 'ltr', ',', '{} %', '–',
    narrative={
        'headline': '{club}: más actividad en zonas avanzadas',
        'analyst': 'Las acciones en zonas avanzadas aumentaron de {prev} a {curr} entre dos intervalos consecutivos '
                   'de diez minutos. Es un cambio de actividad observado, no una prueba de causalidad táctica.',
        'fan': '{club} aparece más a menudo en zonas avanzadas: {prev} acciones antes, ahora {curr}.',
        'broadcast': 'Actividad en zonas avanzadas: {prev} → {curr} (intervalos consecutivos de 10 minutos).'},
    metric_label='Acciones en zona avanzada / 10 min',
    claims={'score': '{home} {h}{sep}{a} {away} antes del minuto {m}.',
            'compare': 'Antes del minuto {m}, {label}: {home} {h}, {away} {a}.',
            'team_value': '{team}: {value}{joiner}{label} antes del minuto {m}.'},
    percent_joiner=' de ',
    metrics={'goals': 'goles', 'shots': 'tiros', 'shots_on_target': 'tiros a puerta',
             'xg': 'goles esperados (xG)', 'pass_completion': 'acierto en el pase', 'possession': 'posesión',
             'corners': 'córneres', 'fouls': 'faltas', 'yellow_cards': 'tarjetas amarillas',
             'red_cards': 'tarjetas rojas', 'substitutions': 'cambios'}))

_add(Language(
    'fr', 'French', 'Français', 'ltr', ',', '{} %', '–',
    narrative={
        'headline': '{club} : plus d’activité dans les zones avancées',
        'analyst': 'Les actions dans les zones avancées sont passées de {prev} à {curr} sur deux tranches consécutives '
                   'de dix minutes. Il s’agit d’un changement d’activité observé, pas d’une preuve de causalité tactique.',
        'fan': '{club} se projette plus souvent dans les zones avancées : {prev} actions avant, {curr} maintenant.',
        'broadcast': 'Activité dans les zones avancées : {prev} → {curr} (tranches consécutives de 10 minutes).'},
    metric_label='Actions en zone avancée / 10 min',
    claims={'score': '{home} {h}{sep}{a} {away} avant la {m}e minute.',
            'compare': 'Avant la {m}e minute, {label} : {home} {h}, {away} {a}.',
            'team_value': '{team} : {value}{joiner}{label} avant la {m}e minute.'},
    percent_joiner=' de ',
    metrics={'goals': 'buts', 'shots': 'tirs', 'shots_on_target': 'tirs cadrés', 'xg': 'buts attendus (xG)',
             'pass_completion': 'précision des passes', 'possession': 'possession', 'corners': 'corners',
             'fouls': 'fautes', 'yellow_cards': 'cartons jaunes', 'red_cards': 'cartons rouges',
             'substitutions': 'remplacements'}))

_add(Language(
    'pt', 'Portuguese (Brazil)', 'Português (Brasil)', 'ltr', ',', '{}%', '–',
    narrative={
        'headline': '{club}: mais atividade em zonas avançadas',
        'analyst': 'As ações em zonas avançadas passaram de {prev} para {curr} em dois intervalos consecutivos de dez '
                   'minutos. É uma mudança de atividade observada, não uma prova de causalidade tática.',
        'fan': '{club} está chegando com mais frequência às zonas avançadas: {prev} ações antes, agora {curr}.',
        'broadcast': 'Atividade em zonas avançadas: {prev} → {curr} (intervalos consecutivos de 10 minutos).'},
    metric_label='Ações em zona avançada / 10 min',
    claims={'score': '{home} {h}{sep}{a} {away} antes do minuto {m}.',
            'compare': 'Antes do minuto {m}, {label}: {home} {h}, {away} {a}.',
            'team_value': '{team}: {value}{joiner}{label} antes do minuto {m}.'},
    percent_joiner=' de ',
    metrics={'goals': 'gols', 'shots': 'finalizações', 'shots_on_target': 'finalizações no gol',
             'xg': 'gols esperados (xG)', 'pass_completion': 'precisão de passe', 'possession': 'posse de bola',
             'corners': 'escanteios', 'fouls': 'faltas', 'yellow_cards': 'cartões amarelos',
             'red_cards': 'cartões vermelhos', 'substitutions': 'substituições'}))

_add(Language(
    'de', 'German', 'Deutsch', 'ltr', ',', '{} %', ':',
    narrative={
        'headline': '{club}: mehr Aktivität in vorderen Zonen',
        'analyst': 'Die Aktionen in vorderen Zonen stiegen von {prev} auf {curr} über zwei aufeinanderfolgende '
                   'Zehn-Minuten-Abschnitte. Das ist eine beobachtete Aktivitätsänderung, kein Beleg für eine taktische Ursache.',
        'fan': '{club} kommt häufiger in vordere Zonen: vorher {prev} Aktionen, jetzt {curr}.',
        'broadcast': 'Aktivität in vorderen Zonen: {prev} → {curr} (aufeinanderfolgende 10-Minuten-Abschnitte).'},
    metric_label='Aktionen in vorderen Zonen / 10 Min.',
    claims={'score': '{home} {h}{sep}{a} {away} vor der {m}. Minute.',
            'compare': 'Vor der {m}. Minute, {label}: {home} {h}, {away} {a}.',
            'team_value': '{team}: {value}{joiner}{label} vor der {m}. Minute.'},
    metrics={'goals': 'Tore', 'shots': 'Schüsse', 'shots_on_target': 'Schüsse aufs Tor', 'xg': 'erwartete Tore (xG)',
             'pass_completion': 'Passquote', 'possession': 'Ballbesitz', 'corners': 'Ecken', 'fouls': 'Fouls',
             'yellow_cards': 'Gelbe Karten', 'red_cards': 'Rote Karten', 'substitutions': 'Auswechslungen'}))

_add(Language(
    'it', 'Italian', 'Italiano', 'ltr', ',', '{}%', '–',
    narrative={
        'headline': '{club}: più attività nelle zone avanzate',
        'analyst': 'Le azioni nelle zone avanzate sono passate da {prev} a {curr} in due intervalli consecutivi di dieci '
                   'minuti. È un cambiamento di attività osservato, non una prova di causalità tattica.',
        'fan': '{club} arriva più spesso nelle zone avanzate: {prev} azioni prima, ora {curr}.',
        'broadcast': 'Attività nelle zone avanzate: {prev} → {curr} (intervalli consecutivi di 10 minuti).'},
    metric_label='Azioni in zona avanzata / 10 min',
    claims={'score': '{home} {h}{sep}{a} {away} prima del {m}° minuto.',
            'compare': 'Prima del {m}° minuto, {label}: {home} {h}, {away} {a}.',
            'team_value': '{team}: {value}{joiner}{label} prima del {m}° minuto.'},
    percent_joiner=' di ',
    metrics={'goals': 'gol', 'shots': 'tiri', 'shots_on_target': 'tiri in porta', 'xg': 'gol attesi (xG)',
             'pass_completion': 'precisione nei passaggi', 'possession': 'possesso palla',
             'corners': "calci d'angolo", 'fouls': 'falli', 'yellow_cards': 'cartellini gialli',
             'red_cards': 'cartellini rossi', 'substitutions': 'sostituzioni'}))

_add(Language(
    'ar', 'Arabic', 'العربية', 'rtl', '.', '{}%', '–',
    narrative={
        'headline': '{club}: نشاط أكبر في المناطق المتقدمة',
        'analyst': 'ارتفعت الأحداث في المناطق المتقدمة من {prev} إلى {curr} عبر فترتين متتاليتين مدة كل منهما عشر دقائق. '
                   'هذا تغيّر ملحوظ في النشاط، وليس دليلاً على سبب تكتيكي.',
        'fan': '{club} يصل إلى المناطق المتقدمة بوتيرة أكبر، حيث ارتفع عدد الأحداث من {prev} إلى {curr}.',
        'broadcast': 'النشاط في المناطق المتقدمة: من {prev} إلى {curr} (فترتان متتاليتان من 10 دقائق).'},
    metric_label='أحداث في المناطق المتقدمة / 10 دقائق',
    claims={'score': '{home} {h}{sep}{a} {away} قبل الدقيقة {m}.',
            'compare': 'قبل الدقيقة {m}، {label}: {home} {h}، {away} {a}.',
            'team_value': '{team}: {label} {value} قبل الدقيقة {m}.'},
    metrics={'goals': 'الأهداف', 'shots': 'التسديدات', 'shots_on_target': 'التسديدات على المرمى',
             'xg': 'الأهداف المتوقعة (xG)', 'pass_completion': 'دقة التمرير', 'possession': 'الاستحواذ',
             'corners': 'الركلات الركنية', 'fouls': 'الأخطاء', 'yellow_cards': 'البطاقات الصفراء',
             'red_cards': 'البطاقات الحمراء', 'substitutions': 'التبديلات'}))

SUPPORTED = tuple(LANGUAGES)
LANGUAGE_PATTERN = '^(' + '|'.join(SUPPORTED) + ')$'


def language(code: str) -> Language:
    if code not in LANGUAGES:
        raise ValueError(f'Unsupported language: {code}')
    return LANGUAGES[code]


def format_number(value: float, unit: str, code: str) -> str:
    spec = language(code)
    text = (f'{value:g}' if isinstance(value, float) else str(value)).replace('.', spec.decimal)
    return spec.percent.format(text) if unit == '%' else text + unit


def catalogue() -> list[dict[str, str]]:
    return [{'code': l.code, 'name': l.name, 'native': l.native, 'direction': l.direction} for l in LANGUAGES.values()]
