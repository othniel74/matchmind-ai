"""Vision auto-eventing: recover match events, positions and speeds from broadcast video.

detect -> calibrate -> track -> identify -> ball -> events, then score against ground truth.
Runs in its own environment (backend/requirements-vision.txt); the API does not import it.
"""
