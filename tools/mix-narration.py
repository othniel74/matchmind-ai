"""Put the Azure AI Speech narration onto the recorded submission video.

Each line starts when its scene starts. The recorder's clock drifts from the story's while the page
is busy (about 4 s over the first 40 s in one take), so story times cannot place the audio. Instead
frontend/demo/story.spec.ts sets a 14 px marker in the bottom-right corner to a grey level unique to
each scene, in the same step as its caption; this reads the marker frame by frame, places each line
where its scene begins, and paints the marker corner over in the output.

    python tools/mix-narration.py --video .test-work/story-video/.../video.webm \
        --timeline .test-work/story-timeline.json --narration .test-work/narration \
        --out docs/demo/pitchlight-submission.mp4 --ffmpeg <path to ffmpeg>
"""
import argparse
import json
import subprocess
from pathlib import Path

MARKER = (1269, 709, 8, 8)  # x, y, w, h: the middle of the 14 px marker at the bottom-right corner
FIRST, STEP = 16, 14         # grey level of scene n is FIRST + n * STEP (story.spec.ts `level`)
LEAD_IN = 0.8                # seconds kept before the first scene
VOICE_DELAY = 0.15           # the voice starts just after the caption


def scene_starts(ffmpeg: str, video: str, scenes: int) -> dict[int, float]:
    """When each scene's marker first shows, from every frame of the recording."""
    x, y, w, h = MARKER
    fps = 25
    raw = subprocess.run([ffmpeg, '-v', 'error', '-i', video, '-vf', f'fps={fps},crop={w}:{h}:{x}:{y},format=gray',
                          '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    size, starts = w * h, {}
    for i in range(len(raw) // size):
        t = i / fps
        mean = sum(raw[i * size:(i + 1) * size]) / size
        scene = round((mean - FIRST) / STEP)
        # Scenes come in order, so only the next one counts: the blank page before the story can
        # match a later scene's grey level by chance (scene 8 did, at 0.04 s).
        if scene == len(starts) + 1 and scene <= scenes and abs(mean - (FIRST + scene * STEP)) < STEP / 3:
            starts[scene] = t
    return starts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True)
    parser.add_argument('--timeline', required=True)
    parser.add_argument('--narration', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--ffmpeg', required=True)
    args = parser.parse_args()
    timeline = json.loads(Path(args.timeline).read_text())
    starts = scene_starts(args.ffmpeg, args.video, len(timeline))
    missing = [item['id'] for n, item in enumerate(timeline, start=1) if n not in starts]
    if missing:
        raise SystemExit(f'No marker found for scenes: {missing}')
    trim = max(0.0, starts[1] - LEAD_IN)
    x, y = MARKER[0] - 3, MARKER[1] - 3
    inputs, labels = ['-ss', f'{trim:.3f}', '-i', args.video], []
    filters = [f'[0:v]drawbox=x={x}:y={y}:w=14:h=14:color=black:t=fill[v]']
    for n, item in enumerate(timeline, start=1):
        start = starts[n] - trim + VOICE_DELAY
        inputs += ['-i', str(Path(args.narration) / f"{item['id']}.wav")]
        filters.append(f'[{n}:a]adelay={int(start * 1000)}:all=1[a{n}]')
        labels.append(f'[a{n}]')
        print(f"{item['id']:9} scene starts {starts[n]:7.2f} s in the recording, voice at {start:6.2f} s")
    filters.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[voice]')
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filters),
                    '-map', '[v]', '-map', '[voice]', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart',
                    '-shortest', '-y', args.out], check=True)
    print('trimmed', round(trim, 2), 's; written', args.out)


if __name__ == '__main__':
    main()
