"""Running the EXR event simulation from a notebook and reading its events.

Importing this module needs only numpy and h5py. The simulation itself runs in a subprocess (pipeline.py) with the
interpreter that has torch and the v2e dependencies.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAG_ONLY = ("photoreceptor_noise",)  # config entries that are switches without a value


def crop_margins(crop_box, image_size):
    """Convert a crop box (x0, y0, width, height) into the (left, right, top, bottom) margins v2e expects."""
    x0, y0, width, height = crop_box
    image_width, image_height = image_size
    return x0, image_width - x0 - width, y0, image_height - y0 - height


def convert_exr_to_events(exr_dir, event_dir, exr_fps, config, white="median", ev=0.0, crop_box=None, image_size=None,
                          n_frames=None, python=sys.executable):
    """Simulate DVS events from a folder of EXR frames, or reuse an identical earlier run.

    Parameters
    ----------
    exr_dir (str or Path): Folder with the EXR frames.
    event_dir (str or Path): Folder for the runs (must not be inside the v2e source tree). Each distinct set of
        settings gets its own subfolder, named by a hash of the settings.
    exr_fps (frames/s): Frame rate of the EXR frames.
    config (dict): v2e parameters by argument name, e.g. {"pos_thres": 0.1, "cutoff_hz": 0.0, "photoreceptor_noise": False}.
    white (str or float), ev (float): Exposure, see pipeline.py. Use the values of the RGB frames.
    crop_box (x0, y0, width, height) (px), image_size (width, height) (px): Optional crop of the frames.
    n_frames (frames): Use only the first n_frames EXR frames.
    python (str): Interpreter that can run exr_v2e.pipeline (torch, OpenEXR, v2e dependencies).

    Returns
    -------
    run_dir (Path): Folder with events.h5.
    message (str): "reused run <name>" or "created run <name>".
    """
    arguments = ["--exr_dir", str(Path(exr_dir).resolve()), "--fps", str(exr_fps), "--white", str(white), "--ev", str(ev),
                 "--dvs_h5", "events.h5", "--skip_video_output", "--no_preview", "--overwrite"]
    if n_frames:
        arguments += ["--n_frames", str(n_frames)]
    if crop_box is not None:
        arguments += ["--crop", ",".join(str(margin) for margin in crop_margins(crop_box, image_size))]
    for name, value in config.items():
        if name in FLAG_ONLY:
            arguments += [f"--{name}"] if value else []
        else:
            arguments += [f"--{name}", str(value)]

    name = hashlib.sha1(json.dumps(arguments).encode()).hexdigest()[:8]
    run_dir = Path(event_dir).resolve() / name
    if (run_dir / "events.h5").exists():
        return run_dir, f"reused run {name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([python, "-m", "exr_v2e.pipeline"] + arguments + ["-o", str(run_dir)], cwd=run_dir, env=env,
                            capture_output=True, text=True)
    if result.returncode != 0 or not (run_dir / "events.h5").exists():
        shutil.rmtree(run_dir, ignore_errors=True)
        raise RuntimeError("event simulation failed:\n" + result.stderr[-2000:])
    return run_dir, f"created run {name}"


def read_events_h5(events_file, width, height):
    """Read events.h5 into arrays: t_s (s, float64), x_px and y_px (px, int32, 0 = left / top), is_on (bool).

    width, height (px): Sensor size, used to check that every event lies on the sensor.
    """
    with h5py.File(events_file, "r") as f:
        raw = f["events"][:]
    events = {"t_s": raw[:, 0] / 1e6, "x_px": raw[:, 1].astype(np.int32), "y_px": raw[:, 2].astype(np.int32),
              "is_on": raw[:, 3] == 1}
    if events["x_px"].max() >= width or events["y_px"].max() >= height:
        raise ValueError("events lie outside the sensor size given")
    return events
