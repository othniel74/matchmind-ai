"""Reproducible offline release checks for Pitchlight synthetic demo.

Run: cd backend && python -m evaluation.run --output ../evaluation-report.json
No cloud account, live feed, or model is required.

Seed sets are disjoint: detector thresholds in app/core.py were tuned on seeds
1000-1199, so calibration and detector measurements use other seeds.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics as st
from pathlib import Path
from app.core import (GENERATOR_VERSION, Scenario, scenario_for, simulate_match, generate_match,
                      validate_event_stream, detect_insights, validate_insight, statistics)
from app.overlays import create_overlays, active_overlays
from app.languages import SUPPORTED

SEEDS = (20261020, 20261021, 20261022, 20261023, 20261024)
CALIBRATION_SEEDS = tuple(range(2000, 2100))
DETECTOR_SEEDS = tuple(range(3000, 3200))
STRENGTH_SEEDS = tuple(range(5000, 5060))
STRENGTHS = (0.5, 1.0, 1.5, 2.0, 3.0)

# Broad per-team, per-match plausibility ranges drawn from public aggregate
# statistics for top European leagues. They bound realism; they are not fitted targets.
REFERENCE_RANGES = {
    'passes': (350, 550), 'pass_completion_pct': (74, 86), 'shots': (9, 16),
    'shots_on_target': (3, 6), 'goals': (1.0, 1.8), 'xg': (1.0, 1.8), 'corners': (3.5, 6.5),
    'fouls': (8, 14), 'yellow_cards': (1.2, 2.6), 'red_cards': (0.02, 0.15), 'substitutions': (3, 5),
}
# A detection counts as correct when its episode starts within this many minutes after the shift.
DETECTION_WINDOW = 20
# Proposed bar for publishing an insight without human review; not an approved target.
UNREVIEWED_PRECISION_BAR = 0.8


def wilson(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if not total:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(max(0, centre - margin), 3), round(min(1, centre + margin), 3)]


def calibration(seeds: tuple[int, ...] = CALIBRATION_SEEDS) -> dict:
    rows = [statistics(generate_match(seed))[team] for seed in seeds for team in ('home', 'away')]
    metrics = {}
    for name, (low, high) in REFERENCE_RANGES.items():
        values = [row[name] for row in rows]
        mean = st.mean(values)
        metrics[name] = {'mean': round(mean, 3), 'sd': round(st.pstdev(values), 3),
                         'reference_range': [low, high], 'within_range': low <= mean <= high}
    possession = [row['possession_pct'] for row in rows]
    return {'seeds': [seeds[0], seeds[-1]], 'team_matches': len(rows), 'metrics': metrics,
            'possession_pct_sd': round(st.pstdev(possession), 2)}


def _fires(tier: str):
    if tier == 'interpretation':
        return lambda i: i['interpretation']['meets_calibrated_threshold']
    return lambda i: True


def detector(seeds: tuple[int, ...] = DETECTOR_SEEDS, tier: str = 'count_change',
             matches: list | None = None) -> dict:
    """Score alert episodes against hidden scenario labels.

    tier='count_change' scores every observed-fact alert as if it claimed a shift;
    tier='interpretation' scores only alerts whose calibrated z-score supports one."""
    fires = _fires(tier)
    true_positive = false_positive = detected = shifts = controls = control_alerts = 0
    latencies: list[int] = []
    for events, scenario in matches if matches is not None else (simulate_match(seed) for seed in seeds):
        found = False
        alerts = 0
        for team in ('home', 'away'):
            last = None
            for minute in range(20, 91):
                # Windows end at `minute`, so the full stream gives the same causal result.
                if not any(i['team_id'] == team and fires(i) for i in detect_insights(events, minute)):
                    continue
                if last is None or last < minute - 1:
                    alerts += 1
                    if (scenario.kind == 'territorial_shift' and scenario.team == team
                            and scenario.start_minute < minute <= scenario.start_minute + DETECTION_WINDOW):
                        true_positive += 1
                        latencies.append(minute - scenario.start_minute)
                        found = True
                    else:
                        false_positive += 1
                last = minute
        if scenario.kind == 'territorial_shift':
            shifts += 1
            detected += found
        else:
            controls += 1
            control_alerts += alerts
    alerts_total = true_positive + false_positive
    precision = true_positive / alerts_total if alerts_total else 0.0
    return {'tier': tier, 'seeds': [seeds[0], seeds[-1]], 'labelled_shifts': shifts, 'control_matches': controls,
            'alert_episodes': alerts_total, 'true_positive': true_positive, 'false_positive': false_positive,
            'precision': round(precision, 3), 'precision_ci95': wilson(true_positive, alerts_total),
            'recall': round(detected / shifts, 3) if shifts else 0.0, 'recall_ci95': wilson(detected, shifts),
            'mean_latency_minutes': round(st.mean(latencies), 1) if latencies else None,
            'false_alerts_per_control_match': round(control_alerts / controls, 2) if controls else None,
            'unreviewed_publication_bar': UNREVIEWED_PRECISION_BAR,
            'fit_for_unreviewed_publication': precision >= UNREVIEWED_PRECISION_BAR}


def strength_curve(seeds: tuple[int, ...] = STRENGTH_SEEDS, strengths: tuple[float, ...] = STRENGTHS) -> list[dict]:
    """Interpretation-tier precision and recall as the injected shift gets stronger."""
    rows = []
    for strength in strengths:
        matches = []
        for seed in seeds:
            label = scenario_for(seed)
            if label.kind == 'territorial_shift':
                label = Scenario('territorial_shift', label.team, label.start_minute, strength)
            matches.append(simulate_match(seed, scenario=label))
        result = detector(seeds, 'interpretation', matches)
        rows.append({'strength': strength, **{k: result[k] for k in (
            'precision', 'precision_ci95', 'recall', 'recall_ci95', 'false_alerts_per_control_match')}})
    return rows


def evaluate(seeds: tuple[int, ...] = SEEDS, calibration_seeds: tuple[int, ...] = CALIBRATION_SEEDS,
             detector_seeds: tuple[int, ...] = DETECTOR_SEEDS,
             strength_seeds: tuple[int, ...] = STRENGTH_SEEDS) -> dict:
    checks: list[dict] = []
    def record(name: str, passed: bool, detail: str = '') -> None:
        checks.append({'check': name, 'passed': bool(passed), 'detail': detail})

    for seed in seeds:
        events = generate_match(seed)
        validate_event_stream(events)
        record(f'{seed}: repeatable replay', events == generate_match(seed))
        record(f'{seed}: stream structure', len({e.event_id for e in events}) == len(events)
               and [e.sequence for e in events] == list(range(1, len(events) + 1)), f'{len(events)} events')
        full_stats = statistics(events)
        record(f'{seed}: basic statistics', all(
            0 <= full_stats[t]['completed_passes'] <= full_stats[t]['passes']
            and 0 <= full_stats[t]['pass_completion_pct'] <= 100
            and full_stats[t]['shots_on_target'] <= full_stats[t]['shots']
            and full_stats[t]['goals'] <= full_stats[t]['shots_on_target'] for t in ('home', 'away'))
            and abs(full_stats['home']['possession_pct'] + full_stats['away']['possession_pct'] - 100) <= .2)
        insights = []
        for minute in range(20, 91):
            visible = [e for e in events if e.minute < minute]
            insights.extend(detect_insights(visible, minute))
        record(f'{seed}: evidence integrity', all(validate_insight(i, events) for i in insights),
               f'{len(insights)} detected insights')
        record(f'{seed}: rejection of forged metrics', all(not validate_insight({**i, 'current_count': i['current_count'] + 1}, events)
            and not validate_insight({**i, 'interpretation': {**i['interpretation'], 'z_score': 9.9}}, events)
            for i in insights))
        record(f'{seed}: interpretations held for review', all(
            i['claim_type'] == 'observed_fact' and i['interpretation']['status'] == 'review_required' for i in insights))
        en = create_overlays(events, insights, 'broadcast', 'en')
        localized = {code: create_overlays(events, insights, 'fan', code) for code in SUPPORTED}
        record(f'{seed}: overlay publication', len(en) == len(insights)
               and all(len(queue) == len(insights) for queue in localized.values())
               and all(o.validation_status == 'approved' for o in en))
        facts = lambda queue: [(o.insight_id, o.previous_value, o.current_value, o.evidence_event_ids) for o in queue]
        record(f'{seed}: multilingual factual parity', all(facts(queue) == facts(en) for queue in localized.values()),
               f'{len(SUPPORTED)} languages')
        record(f'{seed}: overlay lifetime', all(
            o in active_overlays([o], o.match_clock_seconds)
            and o not in active_overlays([o], o.match_clock_seconds + 9)
            for o in en))

    realism = calibration(calibration_seeds)
    for name, metric in realism['metrics'].items():
        low, high = metric['reference_range']
        record(f'calibration: {name}', metric['within_range'], f"mean {metric['mean']} vs range {low}-{high}")
    matches = [simulate_match(seed) for seed in detector_seeds]
    detection = {tier: detector(detector_seeds, tier, matches) for tier in ('count_change', 'interpretation')}
    return {
        'evaluation': 'synthetic_offline_v2', 'generator_version': GENERATOR_VERSION, 'seeds': list(seeds),
        'checks_passed': sum(c['passed'] for c in checks), 'checks_total': len(checks),
        'passed': all(c['passed'] for c in checks), 'checks': checks,
        'calibration': realism, 'detector': detection, 'strength_curve': strength_curve(strength_seeds),
        'publication_policy': 'Observed count changes publish after exact evidence validation. '
                              'Shift interpretations are always routed to human review.',
        'limitations': ['Synthetic distributions are bounded by broad reference ranges, not fitted to a licensed dataset.',
                        f"Possession share varies less between teams than in real matches (sd {realism['possession_pct_sd']} points).",
                        'Detector measurements use synthetic scenario labels; they are not accuracy against real tactical events.',
                        'This does not validate Foundry connectivity, browser rendering, or Azure deployment.',
                        'Advanced-area activity is not a causal or possession-based pressure metric.'],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='evaluation-report.json')
    args = parser.parse_args()
    report = evaluate()
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Offline checks: {report['checks_passed']}/{report['checks_total']} passed; report: {args.output}")
    for tier, d in report['detector'].items():
        print(f"{tier}: precision {d['precision']} {d['precision_ci95']}, recall {d['recall']} {d['recall_ci95']}, "
              f"false alerts/control match {d['false_alerts_per_control_match']}")
    for row in report['strength_curve']:
        print(f"  strength {row['strength']}: precision {row['precision']}, recall {row['recall']}, "
              f"false alerts/control match {row['false_alerts_per_control_match']}")
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
