# Auto-eventing from video, scored against perfect ground truth

The brief asks for "running a model over an incoming video feed to generate the pass and speed metrics automatically, rather than tagging them by hand". Pitchlight does this, and it can also **prove how well it does it**.

Real broadcast footage has no perfect labels: no one knows every player's exact position in every frame. Synthetic video does. Pitchlight renders its own synthetic match as broadcast video, runs a vision pipeline on the pixels alone, and scores every stage against the exact truth the renderer knows.

```
synthetic events ──▶ ground-truth tracking (25 Hz, every player and the ball; app/tracking.py)
                 ──▶ broadcast renderer: main-camera angle, panning with play (frontend/render.html)
                 ──▶ vision pipeline, pixels only (backend/vision)
                       pitch calibration from the line markings → pan, tilt, zoom per frame
                       player detection: RT-DETR (transformer real-time detector)
                       team from kit colour (the team sheet) · identity from the announced line-up
                       ball: small round white blobs of the size a ball has at that point on the pitch
                       events: possession, passes, interceptions, shots; ball speed; player speed and distance
                 ──▶ standard Pitchlight events (StreamValidator) ──▶ Azure Event Hubs ──▶ the live app
                 ──▶ scored against the truth, stage by stage (vision/evaluate.py)
```

The pipeline follows the structure of SoccerNet Game State Reconstruction, the research benchmark for recovering the game from broadcast video: calibration, detection, tracking, team and identity, then the game state. What is different here is the ground truth. Every metric below is exact, not an annotator's estimate.

## What the pipeline is given

Only the video and the team sheet: who plays for which team, and the starting formation. That matches real broadcasting, where line-ups are announced before kick-off. It is given no positions, no events and no camera parameters, apart from the main camera's surveyed installation point (fixed in real stadiums).

## Results

Two minutes of broadcast video (the build-up to and the first goal, match time 7:30–9:30), processed at 6.25 frames per second of video. These are from [vision-report.json](../vision-report.json).

| Stage | Result vs ground truth |
| --- | --- |
| Camera calibration (pan, tilt, zoom from the pitch lines) | **3.2 cm** median ground-position error (p95 5.6 cm) |
| Player detection (RT-DETR-R50) | **87%** of visible players kept as tracked players. On spot checks the detector alone found 45 of 45 with no false positives; the rest are lost to occlusion and team gating. |
| Player position on the pitch | **18 cm** median error (p95 62 cm) |
| Team (kit colour) | **97.8%** correct |
| Identity (line-up and team shape) | **79.2%** correct |
| Ball | found in **74%** of frames where it is visible on the ground, 0.9 m median error |
| Passes and shots | precision **87.5%**, recall 54% (7 of 13), F1 0.67; **the goal is detected** |
| Passer identified correctly | 86% of recovered events |
| Ball speed of recovered passes | **2.6 km/h** median error |
| Player top speed | **2.8 km/h** median error |
| Recovered events accepted by Pitchlight's validator | 12 of 12 |

How it got there, measured at each step on the same clip:

- **Team colours.** Fixed colour thresholds kept only two thirds of players, because a white shirt in shade reads as tan. Clustering the clip's kit colours and naming the clusters from the team sheet raised player recall from 67% to 80%.
- **Identity.** Predicting a player who is out of view at their place in the team's current shape, instead of where they were last seen, raised identity from 65% to 79% and recall to 87%.
- **Goals.** A close-range finish crosses the line in less than one sampled frame. Detecting the ball beyond the goal line between the posts found the goal that a flight-based shot detector missed.
- **Precision first.** Requiring a pass's ball to travel faster than 8 km/h removes possession flicker between close players. Precision rose from 69% to 87.5% and recall fell from 69% to 54%. For on-screen graphics a false event costs more than a missed one, the same principle as Pitchlight's fact checker.

## In Azure

The same pipeline runs as the **`matchmind-vision` Container Apps Job** (image `Dockerfile.vision`: CPU PyTorch with the RT-DETR weights baked in; 4 vCPU, 8 GiB). It processes the broadcast clip, converts what it recovers into validated Pitchlight events, and publishes them to **Azure Event Hubs** as a run whose source is `vision`. The app consumes that run exactly as it consumes a data provider's feed. In the app, **Process this video on Azure** starts the job through Azure Resource Manager with the app's managed identity, one run at a time.

Verified on 21 October 2026: one run processed 601 frames (5 fps of video) in 10.3 minutes. It recovered 12 events, all 12 passed validation, and the app accepted all 12 from Event Hubs (0 rejected) and turned them into moments, including the goal. For a run recovered from video, the app shows only video-derived moments; speed tags from the synthetic physical model are left out.

## Honest limits

- **Rendered video is cleaner than real broadcast:** there is no crowd, no motion blur, no camera cuts or replays, and the kits are simple. Real footage would need these handled: shot-boundary detection, replay filtering and a detector fine-tuned on broadcast frames.
- **Identity** comes from the line-up and formation. The renderer prints shirt numbers, but at main-camera distance they are only a few pixels tall; jersey-number recognition needs close-ups.
- **The ball** is hidden at a player's feet much of the time. Passes are recovered from the ball in flight between players.
- **Speed:** on a 4-core CPU detection takes 2.5 s per frame (32 minutes for this clip at 6.25 fps). Everything after detection re-runs in about 1 s from cached detections. Live use needs a GPU.
- **Recall over precision:** about half of the true passes are recovered. The misses are mostly passes made while the ball is hidden in a crowd.

## Run it

```bash
cd backend
python -m venv .venv-vision
.venv-vision/Scripts/python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.venv-vision/Scripts/python -m pip install -r requirements-vision.txt

# 1. ground truth for a clip (match seconds 450-570, the first goal)
python -c "import json; from app.core import generate_match; from app.tracking import track; json.dump(track(generate_match(), 450, 570), open('tracking.json', 'w'))"
# 2. render it (frontend dev server running): node ../frontend/tools/render-video.mjs http://127.0.0.1:5173/render.html tracking.json clip
# 3. recover and score
.venv-vision/Scripts/python -m vision.run --clip clip --tracking tracking.json --out ../vision-report.json --result result.json --stride 4
# 4. export for the app
.venv-vision/Scripts/python -m vision.export --result result.json --report ../vision-report.json --tracking tracking.json --clip clip --out ../frontend/public/vision
```

Tests: `tests/test_vision.py` checks the camera geometry, calibration recovering pan, tilt and zoom from lines alone, team colours, event derivation, conversion into validated Pitchlight events, and the consistency of the ground-truth tracking.
