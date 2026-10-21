"""Run vision auto-eventing on a rendered clip and score it against ground truth.

    python -m vision.run --clip ../.test-work/vision/clip --tracking ../.test-work/vision/tracking.json \
        --out ../vision-report.json [--stride 2] [--limit N]
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.evaluate import evaluate  # noqa: E402
from vision.pipeline import assemble, lineups_from, observe_all  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--clip', required=True)
    parser.add_argument('--tracking', required=True)
    parser.add_argument('--out', default='../vision-report.json')
    parser.add_argument('--result', default=None, help='also save the recovered frames and events')
    parser.add_argument('--stride', type=int, default=2)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--observations', default=None, help='cache of detector output (created if missing)')
    args = parser.parse_args()
    clip = Path(args.clip)
    tracking = json.loads(Path(args.tracking).read_text())
    start = time.perf_counter()
    cache = Path(args.observations) if args.observations else None
    if cache and cache.is_file():
        observations = json.loads(cache.read_text())  # re-assemble without re-running the detector
    else:
        observations = observe_all(clip, tracking['start'], tracking['fps'], args.stride, args.limit)
        if cache:
            cache.write_text(json.dumps(observations))
    result = assemble(observations, lineups_from(tracking), tracking['fps'], args.stride)
    seconds = time.perf_counter() - start
    cameras = [json.loads(line) for line in (clip / 'camera.jsonl').read_text().splitlines()]
    report = evaluate(result, tracking, cameras)
    report['processing'] = {'seconds': round(seconds, 1), 'per_frame_s': round(seconds / max(len(result['frames']), 1), 3),
                            'stride': args.stride, 'device': 'cpu'}
    Path(args.out).write_text(json.dumps(report, indent=2))
    if args.result:
        Path(args.result).write_text(json.dumps(result))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
