"""Pinhole broadcast camera and the pitch line model, in pitch metres.

Pitch coordinates: x along the 105 m length from the home goal line, y across the 68 m width
from the near touchline, z up. The main camera sits at a surveyed position behind the near
touchline; per frame it pans, tilts and zooms. Those three are what calibration recovers.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

L, W = 105.0, 68.0
WIDTH, HEIGHT = 1280, 720
POSITION = np.array([52.5, -30.0, 18.0])  # surveyed main-camera position (x, y, z)


@dataclass
class Camera:
    target_x: float          # pan: where on the pitch the camera points
    target_y: float = 30.0   # tilt
    fov: float = 30.0        # vertical field of view in degrees (zoom)

    def matrices(self):
        """World-to-camera rotation and the intrinsic focal length in pixels."""
        target = np.array([self.target_x, self.target_y, 0.0])
        forward = target - POSITION
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        rotation = np.stack([right, up, forward])  # rows: camera x (right), y (up), z (forward)
        focal = (HEIGHT / 2) / np.tan(np.radians(self.fov) / 2)
        return rotation, focal

    def project(self, points: np.ndarray) -> np.ndarray:
        """Pitch points (N, 3) -> image pixels (N, 2); points behind the camera give NaN."""
        rotation, focal = self.matrices()
        cam = (points - POSITION) @ rotation.T
        depth = cam[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'):
            u = WIDTH / 2 + focal * cam[:, 0] / depth
            v = HEIGHT / 2 - focal * cam[:, 1] / depth
        out = np.stack([u, v], axis=1)
        out[depth <= 0.1] = np.nan
        return out

    def homography(self) -> np.ndarray:
        """Ground plane (x, y, 1) -> image pixels (u, v, 1)."""
        rotation, focal = self.matrices()
        k = np.array([[focal, 0, WIDTH / 2], [0, -focal, HEIGHT / 2], [0, 0, 1.0]])
        r = rotation
        t = -r @ POSITION
        h = k @ np.stack([r[:, 0], r[:, 1], t], axis=1)
        return h / h[2, 2]

    def to_pitch(self, pixels: np.ndarray) -> np.ndarray:
        """Image pixels (N, 2) on the ground -> pitch metres (N, 2)."""
        inverse = np.linalg.inv(self.homography())
        p = np.concatenate([pixels, np.ones((len(pixels), 1))], axis=1) @ inverse.T
        return p[:, :2] / p[:, 2:3]


def line_model(step: float = 0.5) -> np.ndarray:
    """Points sampled along every regulation pitch marking, on the ground (z = 0)."""
    segments = [((0, 0), (L, 0)), ((L, 0), (L, W)), ((L, W), (0, W)), ((0, W), (0, 0)), ((L / 2, 0), (L / 2, W))]
    for x0, d in ((0.0, 1), (L, -1)):
        for depth, half in ((16.5, 20.16), (5.5, 9.16)):
            a, b = (x0, W / 2 - half), (x0 + d * depth, W / 2 - half)
            c, e = (x0 + d * depth, W / 2 + half), (x0, W / 2 + half)
            segments += [(a, b), (b, c), (c, e)]
    pts = []
    for (x1, y1), (x2, y2) in segments:
        n = max(2, int(np.hypot(x2 - x1, y2 - y1) / step))
        pts.append(np.stack([np.linspace(x1, x2, n), np.linspace(y1, y2, n)], axis=1))
    angles = np.linspace(0, 2 * np.pi, 160)
    pts.append(np.stack([L / 2 + 9.15 * np.cos(angles), W / 2 + 9.15 * np.sin(angles)], axis=1))
    xy = np.concatenate(pts)
    return np.concatenate([xy, np.zeros((len(xy), 1))], axis=1)
