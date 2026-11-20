"""Orthorectification of EXR frames: warp each frame of a clip with one homography and write EXR frames."""
import json
from pathlib import Path

import cv2
import numpy as np

from .exr_io import list_exr_frames, read_exr_rgb, validate_frames, write_exr_rgb


def ortho_matrix_k(size, extent, res):
    """4x4 camera matrix K of a north-up ortho image, in the layout of the Blender export (X, Y, Z -> column, row).

    size: (width, height) px, extent: (xmin, xmax, ymin, ymax) m, res: m/px. Column = (X - xmin)/res, row = (ymax - Y)/res."""
    (width, height), (xmin, _, _, ymax) = size, extent
    return np.array([[2 / (width * res), 0, 0, -2 * xmin / (width * res) - 1],
                     [0, 2 / (height * res), 0, 1 - 2 * ymax / (height * res)],
                     [0, 0, 0, 0],
                     [0, 0, 0, 1]])


def warp_exr_frames(exr_dir, out_dir, homography, size):
    """Warp every EXR frame of exr_dir with the 3x3 homography (frame px -> ortho px) into out_dir, same file names.

    The warp is bilinear on scene-linear values, so highlights above 1 keep their values. Pixels outside the camera
    view are 0. The folder is rewritten when the settings change, and refuses PNG or EXR files from another source."""
    exr_dir, out_dir = Path(exr_dir), Path(out_dir)
    files = list_exr_frames(exr_dir)
    validate_frames(files)
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = {"source": str(exr_dir), "homography": np.asarray(homography).tolist(), "size": list(size),
                "n_frames": len(files)}
    marker = out_dir / "ortho_frames.json"
    if marker.exists() and json.loads(marker.read_text()) == settings and len(list(out_dir.glob("*.exr"))) == len(files):
        return settings
    if not marker.exists() and any(out_dir.glob("*.exr")):
        raise FileExistsError(f"{out_dir} holds EXR files from another source, use an empty folder")
    for old in out_dir.glob("*.exr"):
        old.unlink()
    for file in files:
        warped = cv2.warpPerspective(read_exr_rgb(file, validate=False), np.asarray(homography, dtype=np.float64),
                                     tuple(size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        write_exr_rgb(out_dir / file.name, warped)
    marker.write_text(json.dumps(settings))
    return settings
