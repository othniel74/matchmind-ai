"""Pitch calibration from pixels: recover each frame's pan, tilt and zoom.

The white line markings are segmented, and the camera is chosen so the regulation pitch lines,
projected through it, fall on them (a distance-transform alignment score). The first frame is
found by a coarse global search; later frames refine from the previous frame's camera, as
broadcast calibration trackers do. The camera's position is the surveyed installation point.
"""
from __future__ import annotations
import cv2
import numpy as np
from .camera import HEIGHT, WIDTH, Camera, line_model

MODEL = line_model(step=0.75)
SIGMA = 4.0  # pixels


def line_mask(image: np.ndarray) -> np.ndarray:
    """White, unsaturated pixels that sit on grass: the painted markings."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 185)
    grass = (hsv[:, :, 0] > 35) & (hsv[:, :, 0] < 85) & (hsv[:, :, 1] > 80)
    near_grass = cv2.dilate(grass.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    mask = (white & near_grass).astype(np.uint8)
    # Painted lines are thin; drop blobs (players' white kits) by opening with a small kernel in both axes.
    thick = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    thin = (mask & (1 - thick)).astype(np.uint8)
    # Painted markings are long; small compact blobs (the ball, a boot, a spot) are not lines.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(thin, 8)
    long = np.zeros(n, bool)
    long[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) >= 20
    return long[labels].astype(np.uint8)


def distance_field(mask: np.ndarray) -> np.ndarray:
    return cv2.distanceTransform(1 - mask, cv2.DIST_L2, 3)


def score(camera: Camera, field: np.ndarray, sigma: float = SIGMA) -> float:
    uv = camera.project(MODEL)
    ok = np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < WIDTH - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < HEIGHT - 1)
    if ok.sum() < 60:
        return 0.0
    d = field[uv[ok, 1].astype(int), uv[ok, 0].astype(int)]
    # Mean alignment of visible model points, weighted by how much of the model is in view.
    return float(np.exp(-(d / sigma) ** 2).mean() * min(1.0, ok.sum() / 400))


def refine(camera: Camera, field: np.ndarray, steps=(1.0, 0.4, 0.15, 0.05), rounds: int = 2,
           sigma: float = SIGMA) -> Camera:
    best = camera
    best_score = score(best, field, sigma)
    for step in steps:
        for _ in range(rounds):
            improved = False
            for name, scale in (('target_x', 1.0), ('target_y', 0.6), ('fov', 0.3)):
                for sign in (-1, 1):
                    trial = Camera(**{**vars(best), name: getattr(best, name) + sign * step * scale})
                    s = score(trial, field, sigma)
                    if s > best_score:
                        best, best_score, improved = trial, s, True
            if not improved:
                break
    return best


def initial(field: np.ndarray) -> Camera:
    """Coarse global search over pan, tilt and zoom for the first frame."""
    candidates = [Camera(x, y, f) for x in np.arange(16, 90, 2.0) for y in np.arange(24.0, 37.0, 2.5)
                  for f in np.arange(20.0, 40.0, 3.0)]
    # Coarse to fine: rank with a wide tolerance so near misses still point the way, then tighten.
    scored = sorted(candidates, key=lambda c: score(c, field, 24.0), reverse=True)[:6]
    refined = []
    for c in scored:
        for sigma, steps in ((16.0, (1.5, 0.6)), (8.0, (0.6, 0.25)), (SIGMA, (0.25, 0.1, 0.04))):
            c = refine(c, field, steps, rounds=3, sigma=sigma)
        refined.append(c)
    return max(refined, key=lambda c: score(c, field))


class Calibrator:
    def __init__(self):
        self.camera: Camera | None = None

    def __call__(self, image: np.ndarray) -> tuple[Camera, float]:
        field = distance_field(line_mask(image))
        self.camera = initial(field) if self.camera is None else refine(self.camera, field)
        quality = score(self.camera, field)
        if quality < 0.25:  # lost: re-initialise from scratch
            self.camera = initial(field)
            quality = score(self.camera, field)
        return self.camera, quality
