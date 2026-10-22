"""Synthesize the submission video's narration with Azure AI Speech (neural text to speech).

Authenticates with the signed-in Azure CLI identity (Entra ID), so no key is used or stored.
Reads tools/narration.json ({"voice": ..., "lines": [{"id", "text"}]}), writes one WAV per line to
the output folder and durations.json ({"id": seconds}).

    python tools/narrate.py --out .test-work/narration [--only intro]
"""
import argparse
import json
import subprocess
import urllib.request
import wave
from pathlib import Path
from xml.sax.saxutils import escape

ENDPOINT = 'https://matchmind-ai-studio.cognitiveservices.azure.com/tts/cognitiveservices/v1'
RESOURCE_ID = ('/subscriptions/{sub}/resourceGroups/rg-othniel.obasi-9233/providers/'
               'Microsoft.CognitiveServices/accounts/matchmind-ai-studio')


def token() -> str:
    az = 'az.cmd' if Path('C:/').exists() else 'az'
    return subprocess.run([az, 'account', 'get-access-token', '--resource', 'https://cognitiveservices.azure.com',
                           '--query', 'accessToken', '-o', 'tsv'], capture_output=True, text=True, check=True).stdout.strip()


def synthesize(text: str, voice: str, rate: str, bearer: str) -> bytes:
    ssml = (f"<speak version='1.0' xml:lang='en-GB'><voice name='{voice}'><prosody rate='{rate}'>"
            f"{escape(text)}</prosody></voice></speak>")
    request = urllib.request.Request(ENDPOINT, data=ssml.encode('utf-8'), method='POST', headers={
        'Authorization': f'Bearer {bearer}', 'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'riff-24khz-16bit-mono-pcm', 'User-Agent': 'pitchlight-narration'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def spoken_seconds(path: Path) -> float:
    """Length up to the last audible sample, so trailing silence does not stretch the video."""
    import array
    with wave.open(str(path)) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    samples = array.array('h', frames)
    last = max((i for i in range(len(samples) - 1, -1, -1) if abs(samples[i]) > 500), default=len(samples))
    return round((last + 1) / rate, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--script', default='tools/narration.json')
    parser.add_argument('--out', default='.test-work/narration')
    parser.add_argument('--only')
    args = parser.parse_args()
    script = json.loads(Path(args.script).read_text(encoding='utf-8'))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bearer = token()
    durations = json.loads((out / 'durations.json').read_text()) if (out / 'durations.json').exists() else {}
    for line in script['lines']:
        if args.only and line['id'] != args.only:
            continue
        path = out / f"{line['id']}.wav"
        path.write_bytes(synthesize(line['text'], script['voice'], script.get('rate', '0%'), bearer))
        durations[line['id']] = spoken_seconds(path)
        print(line['id'], durations[line['id']], 's')
    (out / 'durations.json').write_text(json.dumps(durations, indent=1))
    print('total', round(sum(durations.values()), 1), 's')


if __name__ == '__main__':
    main()
