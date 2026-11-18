STATUS: DONE

# blender-agent, phase 1: river scene + 200-frame EXR sequence

All paths below are under ROOT=/home/wonny/jack/v2e_rebuild. Nothing in v2e_pristine was touched (only ever read via `ls`/guard).
Guard at the end: `PYTHONDONTWRITEBYTECODE=1 python3 -I ROOT/guard/guard.py check` -> **CLEAN** (also run before finishing).

## Deliverables (ROOT/blender/)
- `renders/frame_0001.exr … frame_0200.exr` (200 frames, 51 MB)
- `make_scene.py` (reproducible scene builder), `scene.blend`, `manifest.json`, `exr_stats.json`, `motion_estimate.json`, `scene_settings.json`
- `exr_check.py` (EXR check, uses ROOT/venv + OpenEXR), `verify_settings.py`, `shade_diag.py`, `sweep_count.py` (look-development helper)
- logs in `blender/logs/` (render.log, mask.log, calib.log, exr_check.log, verify_settings.log, estimates.txt, blender_version.txt); debug renders in `blender/debug/`
- Blender: `blender/bin/blender-4.5.16-linux-x64/blender`, official tarball from download.blender.org, sha256 `23432b06…10c11` matched the published .sha256 (no sudo, no system change). `--version` -> "Blender 4.5.16 LTS" (logs/blender_version.txt).

## Scene (what make_scene.py builds)
- Cycles, **CPU** (12 cores, 8 threads fixed). GPU not tried: CPU was ~1-2 s/frame at 128 spp, enough.
- 346x260, 128 samples, adaptive sampling ON (threshold 0.01, min 16), **denoiser OFF**, seed 0, **Animated Seed OFF** (same noise pattern every frame, so no frame-to-frame noise flicker), sample clamping off.
- Water: Ocean modifier (GENERATE, `resolution` 16 = 256x256 grid over 60 m, `viewport_resolution` also 16 so the motion estimate uses the render mesh, wave_scale 0.5, wave_scale_min 0.2 m, choppiness 0.8, wind 4, alignment 0.8, seed 3, depth 200); object rotated -90° about Z so waves travel toward the camera (flow). Ocean `time` = (frame-1)/fps, linear keyframes: a deterministic function of time. Mantaflow not used (not needed). Water: Principled, dark base, roughness 0.03, IOR 1.33, smooth shaded.
- Static: textured (voronoi colour+bump) banks inner faces at x=±5, far low hill, two displaced rocks, round bridge pier, bridge deck at y=18, z 3.15-3.85. Deck and pier cast a static diagonal/banded shadow onto the water (shaded region).
- Sun lamp: strength 8 (W/m²), elevation 14°, azimuth 25° from +Y (in front of camera, slightly right), **angular diameter 8°** (see deviations). World: constant (0.55,0.65,0.85) at strength 0.02 (dim sky so shadows are truly dark).
- Gray card: 1.5 m square, **horizontal** at (-1.4,1.8,0.4) on a post, diffuse albedo 0.18, in view and sunlit. (Horizontal because the sun is in front of the camera: any vertical card lit by the sun faces away from the camera.)
- Camera at (0,-3,1.5), 35 mm lens, 36 mm sensor, pitch 4° down; hfov 54.43°.
- Output: OPEN_EXR, 16-bit half, ZIP, RGB, single layer, no alpha, no extra passes. View transform **Standard**, look None, exposure 0, gamma 1 (scene_settings.json / logs/verify_settings.log).

## EXR layout (what the pipeline must read)
Header (exr_stats.json): one channel group, `OpenEXR.File(p).channels()` -> `{'RGB': float16 (260,346,3)}` (raw channels B,G,R, pixel type HALF), compression ZIP, data/display window 0..345 x 0..259, no alpha, no Z/AOV. Values are scene-linear Rec.709 radiance. Luminance used in all stats: Y = 0.2126R+0.7152G+0.0722B.

## No display transform baked in: how verified
1. scene_settings.json: view_transform Standard, look None, exposure 0, gamma 1 (EXR output of a float format is scene-linear regardless).
2. Isolated calibration render (only the gray card visible, same sun/world, `make_scene.py --calib`, debug/calib/frame_0001.exr): measured card Y **0.113204** vs analytic albedo·(S·cosθ/π + L_sky) = 0.18·(8·0.24192/π + 0.02·0.6426) = **0.113204** (manifest fields; agreement to 7 digits). A baked sRGB/Filmic curve would give ~0.38+. Also establishes Blender's convention: sun strength = irradiance, white diffuse facing the sun = S/π.
3. Values range 1.9e-6 … 118 with no clipping at 1.0.

## Gray card / white reference
In the real sequence the card reads **0.09720** (mean over 200 frames, std 1.25e-6 over frames; eroded 5x5 mask). This is 86% of the unoccluded 0.1132 because the bridge deck partially occludes the lowest part of the 8° sun disc as seen from the card (sun-only white-card mask render gives 0.525 vs 0.616 analytic, same ratio). Use 0.09720 as the in-scene white reference (manifest `white_reference_gray_card_luminance_in_scene`); 0.113204 is the unoccluded value.

## Targets (exr_stats.json, all 200 frames, 346x260x200 px)
| quantity | value |
|---|---|
| max | 118.125 (< 65504: **met**, no inf/NaN) |
| 99.9th percentile (all pixels) | 84.375 |
| min positive | 1.913e-6 (sub-half-normal range, 6.1e-5 is the half normal minimum; zero pixels: 0) |
| max/min-positive in dB (20·log10) | 155.8 dB |
| p99.9/min-positive in dB | 152.9 dB |
| fraction of pixels > 10x card | 0.00507 |
| fraction of pixels < 0.05x card | 0.4726 (includes dark sky/hill/bank pixels, not only water) |
| glint (sunlit-water max) / card | 1215x (p99.9 of sunlit water 938x) **met (>=50x)**, in all 200 frames |
| frames with sunlit-water pixel >50x card | 200 / 200 |
| fraction of sunlit-water pixels >50x card | 0.0130 |
| shaded water / card | mean 0.0143, median 0.0124 (shade_diag.json), p99.9 0.100 |
| fraction of shaded-water pixels >0.05x card | 0.0151 (0.0057 after eroding the shaded mask by 6 px) |
| shaded water max / card | 109.7 |

Target "shaded water below 0.05x card": **met for the typical shaded pixel (median 0.012x, 98.5% of shaded pixels), NOT met for the tail**: 1.5% of shaded-water pixels exceed 0.05x and the all-frames max is 110x. Likely cause (not verified in detail): glints at the shadow boundary / penumbra misclassified by the per-frame sun-only mask, and reflections of lit objects; the mask is a direct-light (0-bounce, 64 spp) white-diffuse render per frame (`debug/mask/`), shaded = unlit and eroded 2 px. Note water px are sunlit/shaded by this mask; sunlit mean 29.6k px/frame, shaded 8.0k px/frame. Because of the dim world, 47% of all pixels are below 0.05x card.

Dynamic range caveat: the 155.8 dB figure is max/min-positive over the whole clip and is dominated by a few extreme glint pixels and the dimmest sky/reflection pixels; the typical glint (p99.9) to typical shaded water (median) ratio is 938x / 0.012x ≈ 7.7e4 (≈ 98 dB) — computed from the figures above, not a separate command.

## "Exposed region" assumption
Read as the full camera view, which contains both sunlit glinting water (lower right/centre) and shadowed water (the bridge/pier shadow band across the middle); the stats above pool all pixels, with water split into sunlit/shaded by the per-frame sun-only mask.

## fps / pixel-motion estimate
- fps = 120, 200 frames (1.66 s of simulated time; manifest). Pixel angle = hfov/346 = 0.002746 rad (logs/estimates.txt); lateral ground footprint 0.0137 m at 5 m, 0.055 m at 20 m.
- Computation (`make_scene.py --motion`, motion_estimate.json, run in the same invocation as the final render): project every evaluated water-mesh vertex (66,049 vertices, the render mesh) through the camera at frame f and f+1, for 11 frames spaced across the clip, vertices in view only; pixel displacement |Δ|. Result: **max 0.621 px/frame, max of per-frame p99 0.228 px/frame at 120 fps** (earlier runs of the same code at 60 fps gave 0.8-1.7 px max for other wave settings, which is why 120 was chosen).
- Caveat: this is material-point (vertex) motion of the surface, which is what the brief specified. Glint *highlights* can move faster than the surface points (they hop between facets); I did not measure glint motion in the rendered frames.

## Deviations / judgment calls (please review)
1. **Sun angular diameter 8°** (real sun 0.53°). With a small sun, glints with a 256-grid Ocean were present in only ~30-60% of sampled frames; 8° gave glints in all 200 frames and lowers peaks (max 118 instead of ~1900), far from the half-float limit. Consequence: glints are bigger and softer than real sun glints.
2. Horizontal gray card (reason above); in-scene card partly occluded by the deck, so two references are recorded.
3. Ocean mesh spacing is 0.23 m (256 grid over 60 m); "coarse" because wave_scale_min 0.2 m and spatial scale are large, but it is not a very low-res grid.
4. The sun-only per-frame masks use a white diffuse material override and 0 bounces, with Index passes; these are debug renders (debug/mask/), not part of the deliverable sequence.
5. `scene.blend` is saved by every invocation of make_scene.py before optional blocks (mask/calib hide/override happen after the save), so scene.blend is the clean build; manifest.json fields were also augmented by a small python snippet after the render (white reference, notes, motion estimate), commands below.

## Commands run (all with `export PYTHONDONTWRITEBYTECODE=1`; B=blender/bin/blender-4.5.16-linux-x64/blender, cwd=ROOT/blender, python=ROOT/venv/bin/python -I)
- download/verify/extract Blender 4.5.16 (curl + sha256sum + tar xf) into blender/bin; `$B --version`
- `$B -b --factory-startup -P make_scene.py -- --mask` (per-frame masks) then `$B -b --factory-startup -P make_scene.py -- --motion --render` (final EXRs) [defaults: fps 120, 200 frames, 128 spp, sun 8, elev 14, az 25, sunangle 8, res 16, wscale 0.5, camz 1.5]
- `$B -b --factory-startup -P make_scene.py -- --calib --samples 128` (card-only calibration)
- `python -I exr_check.py renders debug/mask exr_stats.json debug/final_prev.png`; `python -I shade_diag.py`; `$B -b scene.blend -P verify_settings.py`
- look-development sweeps (`--sweep`, `sweep_count.py`) preceded the final choice; their outputs are in debug/sw_*/ and logs/sw_*.log. Earlier non-final full renders (different sun/wave/bank/card settings) were overwritten by the final run.
- `python3 -I ROOT/guard/guard.py check` -> CLEAN
- Reproduce: rerun the two main commands above; every number in this report is in exr_stats.json, shade_diag.json, motion_estimate.json, manifest.json, scene_settings.json, logs/*.

## Follow-ups (out of scope, not done)
float32 switch, exact-exponential filter, sub-stepping/interpolation, adaptive sampling, motion-vector warping, dark-current/dark-floor log model, spectral/QE weighting, noise-model recalibration; also: measure glint motion directly, tighten the shaded-water tail (penumbra classification), optionally a smaller sun angle with a finer water mesh.
