# exr_v2e

Event-camera simulation and 8-bit RGB extraction from Blender EXR frames (16-bit half float, ZIP, scene-linear RGB).
The v2e source tree around this folder is unmodified; `modified_functions.py` holds the one function that is copied
and changed.


| File | Content |
|---|---|
| `exr_io.py` | frame listing, format check (ZIP, HALF), RGB and luminance |
| `rgb_camera.py` | exposure rule, sRGB 8-bit conversion, `extract_rgb_frames` |
| `events.py` | `convert_exr_to_events` (runs `pipeline.py` in a subprocess), `read_events_h5` |
| `pipeline.py` | command-line driver: EXR frames to v2e events and RGB frames |
| `modified_functions.py` | `rescale_intensity_frame` with the intensity clamped to 1 |

## Exposure
`--white` is the scene-linear luminance that maps to 255 in the RGB frames and to DN 255 in the event simulator, so both
sensors share one exposure. `median` maps the clip's median luminance to 18 % mid-gray; `--ev` shifts it in stops.

## Event input
The event simulator needs densely sampled frames, so the scene is rendered at a high frame rate and not upsampled.
The RGB frames are built from the same frames at a lower rate (`--rgb_fps`) with a shutter window (`--rgb_shutter`).

## Command line
```bash
PYTHONPATH=<repo> python -m exr_v2e.pipeline --exr_dir FRAMES --fps 480 --white median \
    --dvs346 --dvs_params noisy --dvs_h5 events.h5 --skip_video_output --rgb_dir rgb --rgb_fps 60 -o OUT
```
Run it from a folder outside the repository. Requirements: `requirements.txt` (plus the v2e dependencies).
