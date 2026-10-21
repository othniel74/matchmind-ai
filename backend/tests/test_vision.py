"""Vision auto-eventing: camera geometry, calibration from pixels, team colours, event derivation
and conversion into validated MatchMind events. Needs requirements-vision.txt (skipped otherwise)."""
import math

import pytest

np = pytest.importorskip('numpy')
cv2 = pytest.importorskip('cv2')
pytest.importorskip('scipy')

from vision.camera import Camera, line_model  # noqa: E402
from vision.calibrate import Calibrator  # noqa: E402
from vision.pipeline import TeamModel, derive_events  # noqa: E402
from vision.to_events import to_match_events  # noqa: E402


def render_lines(camera: Camera) -> np.ndarray:
    """A grass image with the pitch markings drawn through `camera`."""
    img = np.zeros((720, 1280, 3), np.uint8)
    img[:] = (53, 122, 47)  # BGR grass
    uv = camera.project(line_model(step=0.2))
    for u, v in uv:
        if np.isfinite(u) and 0 <= u < 1280 and 0 <= v < 720:
            cv2.circle(img, (int(u), int(v)), 1, (240, 245, 240), -1)
    return img


def test_projection_round_trip():
    cam = Camera(40.0, 31.0, 28.0)
    pts = np.array([[10.0, 5.0], [52.5, 34.0], [90.0, 60.0]])
    uv = cam.project(np.concatenate([pts, np.zeros((3, 1))], axis=1))
    assert np.allclose(cam.to_pitch(uv), pts, atol=1e-6)


@pytest.mark.parametrize('truth', [Camera(35.0, 29.0, 31.0), Camera(70.0, 32.0, 26.0)])
def test_calibration_recovers_pan_tilt_zoom_from_lines(truth):
    cam, quality = Calibrator()(render_lines(truth))
    grid = np.array([[u, v] for u in range(100, 1280, 200) for v in range(320, 720, 100)], float)
    error = np.median(np.hypot(*(truth.to_pitch(grid) - cam.to_pitch(grid)).T))
    assert quality > 0.5 and error < 0.5


def test_team_colours_are_clustered_then_named_from_the_team_sheet():
    # Measured on the rendered clip: white home shirts in shade read as tan (hue ~20),
    # sky-blue away shirts drift towards cyan (hue ~88). Fixed thresholds misread both.
    rng = np.random.default_rng(1)
    home = [np.array([20 + rng.normal(0, 4), 55 + rng.normal(0, 6), 125 + rng.normal(0, 15)]) for _ in range(60)]
    away = [np.array([88 + rng.normal(0, 4), 52 + rng.normal(0, 8), 135 + rng.normal(0, 15)]) for _ in range(60)]
    model = TeamModel(home + away)
    assert sum(model(c)[0] == 'home' for c in home) >= 57
    assert sum(model(c)[0] == 'away' for c in away) >= 57
    assert model(np.array([25, 150, 200])) == ('home', True)   # yellow goalkeeper
    assert model(np.array([140, 90, 180])) == ('away', True)   # purple goalkeeper
    assert model(np.array([60, 200, 40]))[0] is None           # nothing like either kit


def frames_for(sequence):
    """Build tracked frames: the ball moves between players at given times."""
    frames = []
    players = [{'player_id': 'home-04', 'team': 'home', 'x': 30.0, 'y': 30.0},
               {'player_id': 'home-07', 'team': 'home', 'x': 50.0, 'y': 40.0},
               {'player_id': 'away-05', 'team': 'away', 'x': 70.0, 'y': 34.0}]
    for t, (x, y) in sequence:
        frames.append({'t': t, 'players': players, 'ball': {'x': x, 'y': y}})
    return frames


def test_passes_and_interceptions_are_derived_with_ball_speed():
    path = [(t / 10, (30.0, 30.0)) for t in range(0, 10)]
    path += [(1.0 + k / 10, (30 + 20 * k / 10, 30 + 10 * k / 10)) for k in range(1, 11)]  # 22.4 m in 1 s
    path += [(2.0 + t / 10, (50.0, 40.0)) for t in range(1, 6)]
    path += [(2.5 + k / 10, (50 + 20 * k / 10, 40 - 6 * k / 10)) for k in range(1, 11)]
    path += [(3.5 + t / 10, (70.0, 34.0)) for t in range(1, 6)]
    events = derive_events(frames_for(path))
    passes = [e for e in events if e['type'] == 'pass']
    assert passes[0]['player_id'] == 'home-04' and passes[0]['recipient_player_id'] == 'home-07'
    assert 70 < passes[0]['speed_kmh'] < 95  # 22.4 m over about 1 s
    assert passes[1]['outcome'] == 'failed' and any(e['type'] == 'recovery' and e['team'] == 'away' for e in events)


def test_recovered_events_pass_matchmind_validation():
    recovered = [{'type': 'pass', 't': 455.2, 'team': 'home', 'player_id': 'home-04', 'recipient_player_id': 'home-07',
                  'outcome': 'success', 'x': 30.0, 'y': 30.0, 'end_x': 50.0, 'end_y': 40.0, 'speed_kmh': 81.0},
                 {'type': 'shot', 't': 461.0, 'team': 'away', 'player_id': 'away-03', 'outcome': 'goal',
                  'x': 12.0, 'y': 33.0, 'speed_kmh': 230.0}]
    accepted, rejected = to_match_events(recovered)
    assert len(accepted) == 2 and not rejected
    assert accepted[1]['x'] == pytest.approx(100 - 12 / 105 * 100, abs=0.1)  # away attacks the other way
    assert accepted[1]['speed_kmh'] == 140.0 and accepted[0]['minute'] == 7 and accepted[0]['source'] == 'vision'


def test_ground_truth_tracking_is_consistent_with_events():
    from app.core import generate_match
    from app.tracking import metres, track
    clip = track(generate_match(), 450, 480)
    frames = clip['frames']
    assert len(frames) == 750 and all(len(f['players']) == 22 for f in frames)
    for e in clip['events']:
        if e['event_type'] in ('pass', 'shot'):
            f = min(frames, key=lambda fr: abs(fr['t'] - e['t']))
            assert math.dist(f['ball'][:2], metres(e['team_id'], e['x'], e['y'])) < 6
    speeds = [math.dist(a['players'][p], b['players'][p]) * 25 for a, b in zip(frames, frames[1:]) for p in a['players']]
    assert max(speeds) < 9.5  # nobody runs faster than a footballer can
