"""8-bit RGB camera built from scene-linear EXR frames.

pixel = round(255 * sRGB_OETF(clip(rgb_linear / white, 0, 1)))

`white` is the scene-linear value that maps to 255. The event simulator uses the same number as its DN 255, so both
sensors see the scene at the same exposure. Clipping at white and 8-bit quantisation are the only limits applied.
"""
from pathlib import Path

import cv2
import numpy as np

from .exr_io import REC709, list_exr_frames, luminance, read_exr_rgb, validate_frames

MID_GRAY = 0.18  # linear value the clip median is mapped to by the "median" exposure rule


def median_white(exr_files, weights=REC709, max_frames=30):
    """Exposure rule "median": the clip's median luminance (over at most max_frames frames) maps to 18 % mid-gray."""
    picks = np.unique(np.linspace(0, len(exr_files) - 1, min(max_frames, len(exr_files))).astype(int))
    values = np.concatenate([luminance(read_exr_rgb(exr_files[i], validate=False), weights).ravel() for i in picks])
    return float(np.median(values) / MID_GRAY)


def resolve_white(exr_files, white="median", ev=0.0, weights=REC709):
    """Scene-linear white level: a number, or "median" for the exposure rule above, shifted by ev stops."""
    base = median_white(exr_files, weights) if white == "median" else float(white)
    return base / 2.0 ** ev


def srgb_oetf(linear):
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(np.maximum(linear, 0), 1 / 2.4) - 0.055)


def linear_to_uint8(rgb_linear, white):
    return np.rint(255.0 * srgb_oetf(np.clip(rgb_linear / white, 0.0, 1.0))).astype(np.uint8)


def extract_rgb_frames(exr_dir, out_dir, exr_fps, rgb_fps=None, white="median", ev=0.0, shutter=0.5, weights=REC709,
                       n_frames=None):
    """Write 8-bit sRGB PNG frames (0001.png, 0002.png, ...) from a folder of EXR frames.

    Each RGB frame is the linear mean of the EXR frames inside its shutter window, which opens at the start of the
    frame interval and stays open for the fraction `shutter` of it (0.5 = 180 degrees). With rgb_fps equal to exr_fps
    every EXR frame becomes one RGB frame. n_frames limits the EXR frames used (default: all).

    Returns
    -------
    info (dict): white (scene-linear level mapped to 255), rgb_fps, n_frames (PNG frames written).
    """
    files = list_exr_frames(exr_dir)[:n_frames]
    validate_frames(files)
    rgb_fps = rgb_fps or exr_fps
    per_frame = int(round(exr_fps / rgb_fps))
    open_frames = max(1, int(round(per_frame * shutter)))
    white_level = resolve_white(files, white, ev, weights)
    n_rgb = len(files) // per_frame
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in range(n_rgb):
        mean = sum(read_exr_rgb(files[k * per_frame + j], validate=False) for j in range(open_frames)) / open_frames
        cv2.imwrite(str(out_dir / f"{k + 1:04d}.png"), linear_to_uint8(mean, white_level)[..., ::-1])
    return {"white": white_level, "rgb_fps": rgb_fps, "n_frames": n_rgb}
