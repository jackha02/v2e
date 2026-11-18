# Design memo (Gate 1) — pipeline-agent, phase 1

All line numbers are v2e @ cac6384, read from `/home/wonny/jack/v2e_rebuild/v2e_pristine`. Evidence files are in `reports/pipeline-agent/work/`.

## 0. Summary of the proposal

* ONE function is copied: `rescale_intensity_frame` (`v2ecore/emulator_utils.py:48-54`). One changed line.
* It is installed at run time by rebinding the single name `v2ecore.emulator.rescale_intensity_frame`. No subclass, no copy of `generate_events`.
* **Deviation from the brief (needs approval):** the driver feeds the emulator `hdr=False` with float, unclipped DN (`DN_f = Y*255/white`). It does NOT pre-compute the log frame and use `hdr=True`. The emulator then calls v2e's own `lin_log` (emulator.py:666) on the float DN. With this choice the replacement does not need to invert `lin_log`; it only needs the clamp. Justification in section 2.
* `--dvs_text` is broken in the pristine code under any numpy >= 1.24 (`np.float`). Section 6, decision needed.

## 1. Per-function table

| v2e function | copy? | reason |
|---|---|---|
| `lin_log` (emulator_utils.py:18-45) | no | does not clip at 255, returns float32, linear below DN 20 (verified, `facts_check.txt`). Called by the emulator itself at :666. |
| `rescale_intensity_frame` (:48-54) | **yes** | only function that must differ (clamp). |
| `low_pass_filter` (:57-111) | no | already does `torch.clamp(eps, max=1)` (:95); takes `inten01` as input, fixing the input fixes the filter. |
| `generate_shot_noise` (:297-351) | no | takes `inten01` as input; clamp upstream is enough. |
| `compute_event_map`, `subtract_leak_current`, `compute_photoreceptor_noise_voltage` | no | do not touch the input intensity. |
| `EventEmulator.generate_events` (emulator.py:619-1018) | no (see 3) | |
| `EventEmulator.__init__`, `cleanup`, `_init`, `get_event_list_from_coords` | no | |
| `EventRenderer` (renderer.py) | no | operates on events only. |
| `read_image` (v2e_utils.py:335-347) | not used | 8-bit grayscale PNG reader, replaced by the driver's EXR reader (step A-D replacement, in the driver, not a v2e copy). |
| `DVSTextOutput.appendEvents` (output/ae_text_output.py:90) | **open decision**, section 6 | |

## 2. The inten01 problem and the three ways to feed the emulator

Verified facts (`facts_check.txt`):
* `rescale_intensity_frame(x) = (x+20)/275` (emulator_utils.py:54).
* It is called once, at emulator.py:673, on `self.new_frame.clone().detach()`, i.e. the RAW input frame (float64 tensor, :663). Result `inten01` is used in exactly two places: `low_pass_filter(... inten01 ...)` (:686-691) and `generate_shot_noise(... inten01 ...)` (:895-901). There is no other consumer. `rescale_intensity_frame` is imported only by emulator.py (grep over the repo).
* With `hdr=True` the raw input is the log frame, so `inten01` is 0.0727 … 0.0929 for DN 0…255 (log inputs 0…5.54), versus 0.0727 … 1.0 for the true DN. (The brief says 0.07-0.13; the code gives 0.073-0.093 for DN <= 255.) Bandwidth and shot-noise dependence on intensity are lost.
* With unclipped float DN, `inten01` is unbounded: DN 1e4 -> 36.4. The shot-noise factor `(0.25-1)*inten01+1` is 0 at inten01 = 1.333, and −26 at 36 (`facts_check.txt`). The filter `eps = inten01*dt/tau` is already capped at 1 by `low_pass_filter` (:95), but it logs a warning (we saw `eps=875.30` in the smoke run, `work/smoke.log`).

Options:

* **(h1) the brief's design: `hdr=True`, driver passes `lin_log(DN_f)` as float32; replacement inverts lin_log then clamps.**
  Replacement needs about 5 lines: `torch.where(y <= ln20, y/(ln20/20), exp(y))`, then `(DN+20)/275`, then clamp. Round-trip error of the inversion is ≤ 4.6e-7 relative (measured, `facts_check.txt`), so it is harmless but pure overhead. Additional wrinkles: the emulator keeps `log_new_frame` as a float64 alias of the input (:666 with `log_input`), and the `:659` float32 warning must be avoided.
* **(h2) RECOMMENDED: `hdr=False`, driver passes float32 `DN_f` (not clipped, not rounded). Replacement = original line with `torch.clamp(..., max=1.)`.**
  The emulator itself runs v2e's `lin_log` (:666), producing the identical float32 log frame that (h1) would make. `inten01` is computed from the true DN. One changed line. Also keeps `new_frame` meaningful in `--show_dvs_model_state`/single-pixel recording (they show DN, not log).
* **(h3) hdr=False and no replacement.** Rejected: shot-noise factor goes negative above DN 366 (inten01 > 1.333), and the IIR warning is spammed.

The negative-value case: an EXR can contain small negative values (denoiser, ringing). `lin_log` is linear below DN 20 and would pass negatives through; `inten01 < 0` would then freeze the filter. The driver clips Y at 0 (and maps NaN to 0, inf to float32 max) before scaling, so the replacement needs only an upper clamp. Please confirm that clipping negative luminance at 0 is acceptable.

Scientific note (flag only, no change): clamping inten01 to 1 means the photoreceptor bandwidth saturates at `--cutoff_hz` for any pixel brighter than white. A real photoreceptor's bandwidth keeps rising with photocurrent. Because `low_pass_filter` already caps `eps` at 1, clamping only inside shot-noise (not in the filter) would be a possible alternative (rebind `generate_shot_noise` with a copy where one line clamps `inten01`). I did NOT choose it because the brief specifies clamp in [0,1] and it needs a 55-line copy. Raise it as a follow-up for the orchestrator.

## 3. (a) rebinding `rescale_intensity_frame` vs (b) subclass overriding `generate_events`

* (a) Rebind. `emulator.py:23` does `from v2ecore.emulator_utils import rescale_intensity_frame`, so the name lives in `v2ecore.emulator`'s globals; `generate_events` resolves it at call time from those globals (:673). Setting `v2ecore.emulator.rescale_intensity_frame = modified_functions.rescale_intensity_frame` before the first `generate_events` is enough. Copy size: 7 lines (def + docstring + 1 changed line). One changed line.
* (b) Subclass: must copy `generate_events` (400 lines: emulator.py:619-1018) to change one line (:673). Copy drifts from upstream, and the 400 lines make the diff hard to review.

**Choice: (a).** Smaller by two orders of magnitude. Check that (a) takes effect: `v2ecore.emulator.rescale_intensity_frame is modified_functions.rescale_intensity_frame` is asserted in the driver and logged once. The rebinding is skipped with `--legacy_dn`, which keeps the unmodified path (for DN in 0-255 the replacement would be a numerical no-op anyway, but the test is "unmodified").

## 4. EXACT change (to be made only after approval)

Original, `v2ecore/emulator_utils.py`, lines 48-54:

```
48 def rescale_intensity_frame(new_frame):
49     """Rescale intensity frames.
50
51     make sure we get no zero time constants
52     limit max time constant to ~1/10 of white intensity level
53     """
54     return (new_frame+20)/275.
```

Copy in `modified_functions.py` (everything identical except line 54):

```
def rescale_intensity_frame(new_frame):
    """... (docstring unchanged) ..."""
    return torch.clamp((new_frame+20)/275., max=1.)   # CHANGED(emulator_utils.py:54)
```

Needs `import torch` at the top of modified_functions.py (emulator_utils.py already imports it, line 11). Unchanged: signature, docstring, the `(new_frame+20)/275.` expression. For DN in [0,255] output is bit-identical to the original (max is exactly 1.0 at DN 255).

Under (h1) the line would instead be: inversion + clamp (about 5 lines); not proposed.

## 5. Other consumers of `inten01` / raw input under hdr=False with float DN (checked line by line)

* :645 `new_frame.astype(np.uint8)` — only when `frame_h5_dataset` is set, which only `prepare_storage()` does (v2e.py:826, `--ddd_output`). Driver never calls it. If someone passed `--ddd_output` the driver ignores it (it is parsed but unused; the driver will log a warning, to be added in phase 2).
* :659 float32 warning — only if `log_input` (hdr=True). Not hit. The input is float32 anyway.
* :663 `torch.tensor(new_frame, float64)` — fine for any float range. `lin_log` (:30) casts to double, no clip, no uint8 assumption.
* :666 `lin_log` — unclipped (verified: lin_log(25500) = 10.1464).
* :673 inten01 — the fix above. Only the two consumers named in section 2.
* :711 `_init(new_frame)` — only `.shape`.
* :991 single-pixel record `new_frame[...]` — stores DN. Cosmetic.
* `MODEL_STATES` display ranges (:43-50) assume 0-255 DN / ln255 — `--show_dvs_model_state` windows will clip bright pixels. Cosmetic, out of scope.
* Shot-noise `generate_shot_noise` — only uses `inten01.shape` and values; after the clamp the factor is in [0.25, 1].
* Photoreceptor-noise path (:694-704) does not use the input intensity.
* Nothing else in `generate_events` references 255 or uint8 (grep, `work/greps.txt`: only :43-48, :381, :612, :616, :645).

## 6. Things found that need a decision

1. **`--dvs_text` crashes**: `v2ecore/output/ae_text_output.py:90` uses `np.float` (removed in numpy 1.24). v2e's requirements say `numpy<2`, but even numpy 1.26 fails; numpy < 1.24 has no wheels for Python 3.13 (the venv's interpreter). Evidence: `ae_text_output.py:90` and `work/greps.txt`; I observed the crash with numpy 2.5.5 and again with 1.26.4 in the terminal, but that log was overwritten by the later successful run. Options: (i) document that `--dvs_text` is unsupported; use `--dvs_h5/--dvs_aedat2/--dvs_aedat4` (all three ran, section 7); (ii) copy `DVSTextOutput.appendEvents` (≈20 lines) into modified_functions.py with the one-token change `np.float` -> `float` and bind it onto the class; (iii) rebuild the venv with Python ≤ 3.11 and numpy 1.23. Recommendation: (ii) only if the verifier needs text output; else (i). Not done without approval.
2. Brief's `python -I` plus PYTHONPATH does not work: `-I` implies `-E`, so PYTHONPATH is ignored (`ModuleNotFoundError: v2ecore`). I used `python -P` (3.11+, does not prepend script dir/cwd) with `PYTHONPATH=…/v2e_pristine`. Please update other briefs. The system `PYTHONPATH` also contains ROS paths, so always override it, never append.
3. White-level constant: `lin_log(255)` = 5.541264, not 5.5441 (emulator.py:156 docstring and `v2e_args.py:345` both say 5.5441; ln 255 = 5.5413). Documentation error only; no effect on code.

## 7. What the driver must reproduce from the CLI (v2e.py), and what the skeleton does

| CLI behaviour (file:line) | Driver |
|---|---|
| `set_output_folder(args.output_folder, input_file, unique if not overwrite else False, overwrite, output_in_place, logger)` (v2e.py:141-147) | same call, `input_file=exr_dir`, `output_in_place=False` |
| `set_output_dimension(...)` (:150-154); if still None, from first frame (:361-366) | same; fallback to first EXR's size |
| `write_args_info` -> `<basename of __main__>-args.txt` in output folder (:215; v2e_args.py:491-498), then a FileHandler on that file (:217-222) | same; file will be named `exr_v2e_pipeline-args.txt` |
| `v2e_check_dvs_exposure_args` (:326) | same |
| `dvs_vid = args.dvs_vid if not args.skip_video_output else None` (:158) | same |
| `EventEmulator(...)` with args mapping (:545-563), `hdr=args.hdr`, device = cuda if available else cpu (:65) | same mapping; `hdr=False` always; `--dvs_params` -> `emulator.set_dvs_params` (:565-570) |
| `EventRenderer(output_path, dvs_vid, preview, full_scale_count=dvs_vid_full_scale, exposure_mode, exposure_value, area_dimension, avi_frame_rate)` (:572-578) | same |
| frame loop under `torch.no_grad()`: `generate_events(fr, t)`; append non-empty events; `if i % batch_size == 0` render and reset; leftover render after loop (:829-850) | same |
| finalise: `eventRenderer.cleanup(); emulator.cleanup()` (:853-854); both also `atexit` | same |
| File names: events written by the emulator in `output_folder` with suffix added by `checkAddSuffix` (`.h5`, `.aedat`, `.aedat4`, `.txt`; emulator.py:312-346); DVS video `<output>/dvs-video.avi` + `dvs-video-frame_times.txt` (renderer.py:143-159); no `video_orig/video_slomo` when SloMo is not used | produced by the same code; verified with the smoke run: `dvs-video.avi`, `dvs-video-frame_times.txt`, `ev.h5`, `ev.aedat`, `ev.aedat4`, `exr_v2e_pipeline-args.txt` |
| Timestamps: no-SloMo path uses `interpTimes = i*duration/(n-1)` = i/(srcFps) (:794-797); frame 0 at t=0 | `t_i = i/(fps*input_slowmotion_factor)` |
| BGR->gray (:728, 601 weights on gamma-coded 8-bit), crop (:640-650, :711), resize `INTER_AREA` (:719) | EXR luminance (linear, `--weights`), crop and `INTER_AREA` resize done on the float luminance |
| SuperSloMo upsampling (default `--auto_timestamp_resolution True`) | NOT implemented (out of scope: interpolation). Equivalent to the CLI with `--disable_slomo`. The driver should warn when slomo args are given (phase 2) |
| `--start_time/--stop_time`, `--input_frame_rate`, `--output_in_place` | not honoured by the skeleton (listed as follow-ups unless you want them) |
| desktop notification / `desktop.open` (:887-903) | not reproduced (GUI side effects) |

Note on `--legacy_dn`: it rounds and clips the linear luminance DN to 0-255 and runs the unmodified path. It is NOT the CLI's gamma-coded 8-bit gray; it only reproduces the CLI's integer-clipped DN input path. For an exact CLI comparison the verifier should write gray PNGs and run the CLI separately (with cwd outside the repo).

## 8. Paper, step E (supplement not available)

`/home/wonny/jack/v2e_rebuild/v2e_paper` is a 10-page PDF of the main paper only (text extracted to `work/paper_raw.txt`); the supplementary material it refers to for the step-E update is NOT in it, so nothing below is quoted from the supplement. The main text (Sec. 4, step E, `work/paper_raw.txt` line 555-567) says: a first-order IIR low-pass; bandwidth "proportional to the luma intensity values Y"; "the nominal cutoff frequency is f3dBmax for full white pixels"; an additive constant limits the minimum bandwidth to about 10% of the maximum (code: the +20 offset, 20/275 = 7.3%). This agrees with clamping `inten01` to 1: full white = f3dBmax, and the paper does not define what happens above white (the HDR extension). From the code, the update is `lp = (1-eps)*lp + eps*log_new`, `eps = inten01*dt/tau`, `tau = 1/(2*pi*cutoff_hz)`, `eps` capped at 1 (emulator_utils.py:80-100): an Euler step of the RC low-pass, inaccurate when `eps` is large (code warns for `eps>0.3`, :87-93). The brief's "exact-exponential filter" follow-up addresses that and is out of scope.

## 9. Follow-ups (not done)

float32 switch, exact-exponential filter, sub-stepping/interpolation, adaptive sampling, motion-vector warping, dark-current model, spectral/QE weighting, noise recalibration (all per brief); plus: low-end mapping (lin_log knee at DN 20 = 7.8% of white, unchanged); bandwidth-saturation choice (section 2 note); DN-scaled `--show_dvs_model_state` display ranges; `--start_time/--stop_time`; `--dvs_text`.
