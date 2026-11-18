STATUS: DONE

# Verifier phase 3 report (acceptance tests)
ROOT=/home/wonny/jack/v2e_rebuild; W=reports/verifier/work. All runs: `PYTHONDONTWRITEBYTECODE=1`, `python -P`, `PYTHONPATH=ROOT/v2e_pristine`, cwd inside W (never in the repo), outputs under W. Every number below is from a command I ran (outputs in W/t2, t3, t5, t6).

## Summary
| Test | Result |
|---|---|
| T1 guardian | INTERIM PASS (CLEAN, 0 VIOLATION lines in guard.log, 0 `__pycache__` in repo); orchestrator records final |
| T2 import audit | PASS |
| T3 legacy equivalence vs real v2e CLI | PASS (clean and noisy): event streams bit-identical |
| T4 HDR full sequence, clean + noisy | PASS |
| T5 HDR evidence | PASS, with important caveats (see "Suspicious / contradicts expectation") |
| T6 clean-shell reproduction | PASS: byte-identical to the author's outputs |

## T1 Guardian (INTERIM)
`PYTHONDONTWRITEBYTECODE=1 python3 -I ROOT/guard/guard.py check` -> `CLEAN` (W/guard_interim.txt). `grep -c VIOLATION guard/guard.log` -> 0; last log line `2026-11-18 10:50:25 CLEAN check#643`. `find v2e_pristine -name __pycache__ | wc -l` -> 0. Final T1 is for the orchestrator.

## T2 Import audit: PASS (W/t2/t2.txt)
Symbols imported from v2e (AST of `pipeline/exr_v2e_pipeline.py`): `v2ecore`, `v2ecore.emulator` (module, for the rebinding), `EventEmulator`, `EventRenderer`, `v2e_args`, `write_args_info`, `SmartFormatter`, `v2e_check_dvs_exposure_args`, `set_output_folder`, `set_output_dimension`, `v2e_quit`, `check_lowpass`. Not reimplemented: `lin_log`, `low_pass_filter`, `generate_shot_noise` etc. run inside EventEmulator. Local defs in the driver: `get_args` (wraps v2e's `v2e_args`), `read_exr_rgb`, `exr_to_dn` (the new steps A-D), `main` (contains the frame loop that mirrors v2e.py:829-850; the CLI's loop is inside a monolithic main(), so it cannot be imported). `modified_functions.py` defines only `rescale_intensity_frame`.
Diff re-derived by me from the repo text (`sed -n 48,54p v2ecore/emulator_utils.py` vs the def block of modified_functions.py): exactly 1 line removed / 1 added (`return (new_frame+20)/275.` -> `return torch.clamp((new_frame+20)/275., max=1.)  # CHANGED(...)`).
Only runtime patch: `grep` in the driver finds a single assignment, line 160, `v2ecore.emulator.rescale_intensity_frame = ...`; no setattr/monkeypatching of anything else. Skipped with `--legacy_dn`.

## T3 Legacy equivalence: PASS (W/t3/)
Method: first 40 EXRs (symlinked to W/t3/exr40), `--white` 0.09719756621614625 and fps 120 from the manifest. PNG DN = `clip(rint(Y*255/white),0,255)` uint8, gray, names 00001.png... (so v2e's int-sort works).
- Round trip (`t3_png.txt`): v2e's own `read_image` of all 40 PNGs vs the DN: 0 mismatching frames, max abs diff 0. The CLI actually reads the PNG as colour and converts with `cv2.cvtColor(BGR2GRAY)` (v2e.py:728): checked separately, 0 of 40 frames differ from the gray PNG (`roundtrip_cli.txt`). So the CLI gray round trip is exact. (2.2% of pixels in the last frame are at DN 255: the clipping the HDR path avoids.)
- (a) CLI: `v2e.py -i W/t3/png40 --input_frame_rate 120 --disable_slomo --dvs_params {clean|noisy} --dvs_emulator_seed 1 --dvs346 --dvs_exposure duration 0.01 --dvs_h5 events.h5 --no_preview --overwrite -o W/t3/cli_{M}`; rc=0 (logs cli_*.log). (b) driver: same values from the EXRs with `--legacy_dn` (`drv_{M}`), rc=0.
- Result (`cmp.txt`): clean CLI (242213,4) vs driver (242213,4) **identical**; noisy (295543,4) vs (295543,4) **identical**. Timebase identical: first/last t 308 us/325000 us (clean), 490/325000 (noisy); 800/968 distinct timestamps in both. The CLI timebase is frame i at i/fps (log: 40 frames, 0..0.325 s) = driver's.
- Not covered: CLI's gamma-coded 8-bit gray vs linear luminance is by design not compared (we feed the same DN to both).

## T4 HDR full sequence: PASS
Author's run (`ROOT/outputs/hdr_{clean,noisy}`; I also re-ran it in T6). Opened by me (`t3/roundtrip_cli.txt`):
- clean: events.h5 (1666893, 4), ON fraction 0.5056; dvs-video.avi opens in cv2, 165 frames, first frame (260,346,3); aedat4 opened with `dv_processing.io.MonoCameraRecording`, 1666893 events (equal to h5).
- noisy: h5 (2013404, 4), ON 0.5108; video 165 frames; aedat4 2013404 events (equal to h5).

## T5 HDR evidence (W/t5/t5.py, t5.txt)
All 200 EXRs, DN_f via the driver's own `exr_to_dn`.
(a) Nothing clipped: max DN_f = 309903.6 (white=255); 1.95% of all pixels > 255 (max 2.43% in a single frame); `lin_log` max = 12.644 vs ln(255)=5.541, 1.95% of values above ln255; 34403 distinct values above 255; `lin_log` inverted recovers DN_f with max rel. error 6.1e-7 (so no saturation); assertion passed.
(b) inten01 (v2e's own `rescale_intensity_frame`; patched = modified_functions), computed over real pixels:
| pixel set | unpatched, hdr=False (DN) | patched (DN) | hdr=True, unpatched (log input; the original problem) |
|---|---|---|---|
| dark (Y<0.05 card), n=8.5M | 0.0727 .. 0.1191 | same | 0.0727 .. 0.0797 |
| bright (Y>50 card), n=77k | 46.5 .. 1127 (median 613) | 1.0 exactly | 0.1071 .. 0.1187 |
| all pixels | 0.0727 .. 1127 (p99 1.04) | 0.0727 .. 1.0 | 0.0727 .. 0.1187 |
Reference points DN 0/20/255/1000/30000: unpatched 0.0727/0.1455/1.0/3.71/109.2; patched 0.0727/0.1455/1.0/1/1; hdr=True 0.0727/0.0836/0.0929/0.0978/0.1102. 0.585% of pixel-frames exceed 1.3333 unpatched (shot-noise factor negative there). Expectation (0.07-1.0 patched vs 0.07-0.13 hdr=True) confirmed.
(c)/(d) Event rates (events/pixel/s), duration 199/120 s. Sets (explicit, reproducible, from the EXR luminance, card = white): glint = pixels with Y>50 card in at least one frame (3773 px); static shadow = Y<0.05 card in ALL 200 frames, eroded with a 7x7 box and excluded within a 7x7 dilation of the glint set (17886 px, of 89960). "Glint-active pixel-frames" = events whose pixel has Y>50 card in the frame interval the event falls in, divided by those pixel-frames x dt.
| run | total events | glint set | glint-active pixel-frames | static shadow | whole frame |
|---|---|---|---|---|---|
| HDR clean | 1,666,893 | 112.81 | 282.0 | 0.688 | 11.17 |
| legacy (DN clipped to 255) clean | 1,227,026 | 42.55 | 1.96 | 0.706 | 8.22 |
| HDR noisy | 2,013,404 | 119.83 | 302.6 | 5.431 | 13.50 |
| legacy noisy | 1,549,480 | 45.54 | 4.10 | 5.480 | 10.39 |
Plain statement: the HDR path gains events from over-white pixels: ~2.7x more events in the glint set, and in frames where the pixel is above 50x card ~140x (clean) / ~74x (noisy) the legacy rate, because a clipped pixel sits at DN 255 and produces nothing. It gains **nothing measurable in the static shadows**: 0.688 vs 0.706 (clean) and 5.431 vs 5.480 (noisy) ev/px/s, the shadow rate in noisy is dominated by the 5 Hz shot-noise parameter. Reason (from the code, not tested separately): shadows here are below 0.05x card = DN<12.75, i.e. inside lin_log's linear region, and 8-bit integer DN already resolves them; the HDR benefit would show only for far darker content or with a dark-floor log model (a listed follow-up). The DN rounding difference is small at those levels. Overall event totals +36% (clean) / +30% (noisy).

## T6 Clean-shell reproduction: PASS (W/t6/)
RUN.md code block extracted (`t6/run_orig.sh`), adapted only by changing `cd $ROOT/outputs` -> `cd W/t6` and the `-o`/tee paths to `W/t6/hdr_{M}` (`diff` shown in my shell; `t6/run_t6.sh`). Run as `env -i HOME=$HOME PATH=/usr/bin:/bin bash t6/run_t6.sh` -> rc=0 (ran with the shell's PYTHONPATH empty, so the block's own export was exercised). Compare (`t6/t6_compare.txt`): clean (1666893,4) and noisy (2013404,4) events.h5 arrays identical to the author's; md5 of events.h5, dvs-video.avi and events.aedat4 equal for both presets.

## Suspicious / contradicts expectations (important)
1. **The patch is a no-op for `--dvs_params clean`.** In clean the emulator sets cutoff_hz=0 and shot_noise_rate_hz=0 (emulator.py:514-525), so `inten01` is never computed (`emulator.py:671` condition is False). I ran the driver with the patch neutralised (my wrapper `t5/unpatched.py`, rebinding the original function): clean events are bit-identical (1666893, identical True). Noisy unpatched: 2012185 events vs 2013404 patched (identical False, -0.06%), glint rate 119.70 vs 119.83. So in these runs the HDR gain comes almost entirely from feeding unclipped DN through `lin_log`, not from the rescale patch; the patch's only visible effect is the shot-noise factor/filter eps at very bright pixels: unpatched IIR warning `eps=1371.29` (inten01 up to ~1127) vs `eps=1.57` patched (`unpatched_noisy.log`, `hdr_noisy.log`). I do not claim the patch is unnecessary: unpatched shot-noise factor goes negative for 0.585% of pixel-frames; it just has a very small measured event effect here.
2. Filter saturation in noisy: at 120 Hz and 30 Hz cutoff, dt/tau=1.57, so eps is capped at 1 for any pixel with inten01 >= 0.64 (DN >= ~156): the low-pass is a pass-through for all bright pixels (Euler step; exact-exponential is the listed follow-up). The bandwidth also saturates at white (design choice noted in gate 1).
3. Warning `check_lowpass ... eps=15.7` appears in the clean run: it uses `--cutoff_hz` (default 300), while `--dvs_params clean` sets cutoff 0 inside the emulator. Misleading but identical to the CLI behaviour.
4. Glint-set event rate is dominated by motion/edges; "glint-active pixel-frames" 282 ev/px/s at 120 fps sampling means >2 events per pixel per frame there; since each frame can produce several events per pixel, the temporal ordering within a frame is interpolated by v2e only. Fine, but treat the absolute rates as model output, not truth.
5. Driver minor bug/risk (repro by reading the code): `sorted(glob('*.exr'))` sorts lexicographically, while the CLI's image reader sorts by integer. `python3 -c "print(sorted(['frame_999.exr','frame_1000.exr']))"` -> `['frame_1000.exr', 'frame_999.exr']`. Fine for the current 4-digit names (frame_0001..0200), wrong for unpadded names or >9999 frames. Not fixed (report only).
6. The CLI log line "done processing 80 frames" for 40 input frames (v2e's own count message; the 40 frames and 242213/295543 events are correct). Not a driver issue.
7. Duration of events from the first frame: first output frame is None (v2e init), as in the CLI; both agree (T3).

## Commands (all from W, see logs there)
```
T3: python -P (inline) -> t3_png.txt; v2e.py CLI and driver --legacy_dn runs (cli_*.log, drv_*.log); python -P compare -> cmp.txt; roundtrip_cli.txt
T4: h5py/cv2/dv_processing inline script -> t3/roundtrip_cli.txt
T5: python -P t5/t5.py > t5/t5.txt ; driver --legacy_dn full 200 frames clean/noisy -> t5/legacy_*; t5/unpatched.py full runs -> t5/unpatched_*, unpatched_cmp.txt
T6: env -i HOME=$HOME PATH=/usr/bin:/bin bash t6/run_t6.sh ; t6_compare.txt
T2: t2/t2.txt (AST import list, diff -u of orig vs copy)
PYTHONDONTWRITEBYTECODE=1 python3 -I ROOT/guard/guard.py check   -> CLEAN
```
No pipeline file was modified. No pip installs were needed. Guard (interim, at end): CLEAN
