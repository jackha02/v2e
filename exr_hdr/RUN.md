# Reproduction (HDR EXR -> v2e events)

From a clean shell (cwd anywhere OUTSIDE `v2e_pristine`). `--white` = in-scene gray-card luminance measured in the EXRs, `blender/manifest.json` key `white_reference_gray_card_luminance_in_scene` (0.0972; the unoccluded value is 0.1132); `--fps` from the manifest. No SloMo is used (as CLI `--disable_slomo`); `--dvs_text` is unsupported.

```bash
export PYTHONDONTWRITEBYTECODE=1
ROOT=/home/wonny/jack/v2e_rebuild
export PYTHONPATH=$ROOT/v2e_pristine      # overrides any ROS PYTHONPATH; do not use python -I (it ignores PYTHONPATH)
cd $ROOT/outputs
FPS=$($ROOT/venv/bin/python -P -c "import json;print(json.load(open('$ROOT/blender/manifest.json'))['fps'])")
WHITE=$($ROOT/venv/bin/python -P -c "import json;print(json.load(open('$ROOT/blender/manifest.json'))['white_reference_gray_card_luminance_in_scene'])")
for M in clean noisy; do
  $ROOT/venv/bin/python -P $ROOT/pipeline/exr_v2e_pipeline.py \
    --exr_dir $ROOT/blender/renders --fps $FPS --white $WHITE \
    --dvs346 --dvs_params $M --no_preview --dvs_h5 events.h5 --dvs_aedat4 events.aedat4 \
    --dvs_exposure duration 0.01 --dvs_emulator_seed 1 --overwrite \
    -o $ROOT/outputs/hdr_$M 2>&1 | tee $ROOT/outputs/hdr_$M.log
done
```
Outputs per folder: `events.h5`, `events.aedat4`, `dvs-video.avi`, `dvs-video-frame_times.txt`, `exr_v2e_pipeline-args.txt`.
Legacy (unmodified v2e path, 8-bit-clipped DN) for comparison: add `--legacy_dn`.
