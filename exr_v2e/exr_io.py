"""Reading Blender EXR frames: 16-bit half-float, ZIP compressed, scene-linear RGB."""
import re
from pathlib import Path

import numpy as np
import OpenEXR

REC709 = (0.2126, 0.7152, 0.0722)


def list_exr_frames(exr_dir):
    """EXR files of a folder in time order (sorted by the number in the file name)."""
    files = sorted(Path(exr_dir).glob("*.exr"), key=lambda f: int(re.findall(r"\d+", f.stem)[-1]))
    if not files:
        raise FileNotFoundError(f"no EXR frames in {exr_dir}")
    return files


def validate_exr(path):
    """Open an EXR file and require ZIP compression and HALF (16-bit float) channels."""
    exr = OpenEXR.File(str(path))
    compression = exr.header().get("compression")
    if compression != OpenEXR.ZIP_COMPRESSION:
        raise ValueError(f"{path}: compression is {compression}, expected ZIP")
    not_half = {name: str(channel.type()) for name, channel in exr.channels().items() if channel.type() != OpenEXR.HALF}
    if not_half:
        raise ValueError(f"{path}: channels are not HALF (16-bit float): {not_half}")
    return exr


def validate_frames(files):
    """Require every frame of a clip to be ZIP compressed with HALF channels."""
    for path in files:
        validate_exr(path)


def read_exr_rgb(path, validate=True):
    """Scene-linear RGB of one frame as float32 (height, width, 3)."""
    exr = validate_exr(path) if validate else OpenEXR.File(str(path))
    channels = exr.channels()
    for key in channels:
        if key in ("RGB", "RGBA") or key.endswith(".Combined"):
            return np.asarray(channels[key].pixels, dtype=np.float32)[..., :3]
    raise ValueError(f"{path}: no RGB, RGBA or <view layer>.Combined channel group in {list(channels)}")


def luminance(rgb, weights=REC709):
    """Scene-linear luminance of an RGB frame. NaN and negative values become 0; nothing is clipped above."""
    y = rgb @ np.asarray(weights, dtype=np.float32)
    return np.maximum(np.nan_to_num(y, nan=0.0, posinf=np.finfo(np.float32).max), 0.0)


def read_exr_info(exr_dir):
    """Frame count and frame size (px) of a folder of EXR frames."""
    files = list_exr_frames(exr_dir)
    validate_frames(files)
    height, width = read_exr_rgb(files[0], validate=False).shape[:2]
    return {"n_frames": len(files), "width_px": width, "height_px": height}
