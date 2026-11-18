STATUS: DONE

# pipeline-agent — phase 2 report

Real run on the Blender EXR sequence (blender-agent `reports/blender-agent/phase1.md` STATUS: DONE; 200 frames 346x260, fps 120). Guard check: CLEAN (`work/guard_phase2.txt`, output below).

## Changes
* `pipeline/modified_functions.py`: ONE function, `rescale_intensity_frame` (emulator_utils.py:48-54); one changed line 54 -> `return torch.clamp((new_frame+20)/275., max=1.)  # CHANGED(emulator_utils.py:54)`. Unchanged: signature, docstring, `(new_frame+20)/275.`. Added `import torch`.
* `pipeline/MODIFIED_FUNCTIONS_CHANGELOG.md` (per spec) and `pipeline/modified_functions.diff` (diff -u of the text extracted from the repo, `work/orig_rescale_intensity_frame.py`, vs the copy `work/copy_rescale_intensity_frame.py`): 1 line removed, 1 added.
* `pipeline/exr_v2e_pipeline.py`: finished per the memo. Rebinds `v2ecore.emulator.rescale_intensity_frame` (assert + one log line `installed modified_functions.rescale_intensity_frame`), skipped with `--legacy_dn`. `hdr=False` with float32 unclipped, unrounded DN_f = Y*255/white (approved DEVIATION from the brief's hdr=True). Negative luminance clipped to 0, NaN -> 0.
* Verifier-required changes: (1) v2e's `check_lowpass(args.cutoff_hz, 1/dt, logger)` is called (`dt = 1/(fps*input_slowmotion_factor)`); (2) docstring now `python -P`; `-o` required, refuses an output folder whose realpath is inside the v2e repo; (3) warnings for `--start_time --stop_time --timestamp_resolution --input_frame_rate --ddd_output --output_in_place` and a standing warning that there is no SloMo; phase1 args-file name claim corrected in `phase1.md`; (4) crop tested (below). `--dvs_text`: option (i), the driver exits with an explanatory error; ae_text_output untouched.
* `pipeline/RUN.md`: the one reproduction command. I ran exactly its code block (extracted to `work/run_cmds.sh`).

## Tests (evidence in `reports/pipeline-agent/work/`)
* Refusals: no `-o` -> rc 1 "-o/--output_folder is required" (`t_noo.log`); `-o` inside v2e_pristine -> rc 1 "refusing", and the folder was not created (`t_in.log`); `--dvs_text` -> rc 1 (`t_txt.log`).
* Warnings fire for `--start_time 1 --ddd_output` and the SloMo notice (`crop.log`); the rebinding log line appears; `check_lowpass` output appears (`crop.log`).
* Crop path, SYNTHETIC 34x26 EXRs (`syn_marker`): an 8x8 patch at x=10..17, y=5..12 lights up in frame 2; run with `--crop 2,4,1,3 --output_width 28 --output_height 22` (left,right,top,bottom). Events: x 8..15, y 4..11, all ON (`crop2_result.txt`), i.e. exactly shifted by (-2,-1) as expected.
* Earlier phase-1 smoke runs were also SYNTHETIC.

## Real run (REAL Blender EXRs, `ROOT/blender/renders/*.exr`)
`--white` = `white_reference_gray_card_luminance_in_scene` = 0.09719756621614625 (the in-scene gray-card luminance measured by blender-agent, which reflects the card partially shaded by the bridge; `gray_card_expected_luminance_sun_only` in the manifest is 0.11089 and the unoccluded calibration is 0.11320; I used the in-scene value because it is the luminance the card actually has in the renders). `--fps` 120 from the manifest.
Command: see `pipeline/RUN.md` (loop over `--dvs_params clean` and `noisy`, `--dvs346 --no_preview --dvs_h5 events.h5 --dvs_aedat4 events.aedat4 --dvs_exposure duration 0.01 --dvs_emulator_seed 1 --overwrite`). Full logs: `outputs/hdr_clean.log`, `outputs/hdr_noisy.log` (copies in `work/run_hdr_*.log`).
Outputs: `outputs/hdr_clean/` and `outputs/hdr_noisy/`, each with `events.h5, events.aedat4, dvs-video.avi, dvs-video-frame_times.txt, exr_v2e_pipeline-args.txt`.
* clean: 1.67M events (842.81k on, 824.08k off) from 200 frames in 17.2 s; h5 shape (1666893, 4), x max 345, y max 259, t 170 us .. 1658333 us, ON fraction 0.506.
* noisy: 2.01M events (1.03M on, 985.01k off) in 20.6 s; h5 shape (2013404, 4), same extents, ON fraction 0.511 (`work/events_summary.txt`).
* DVS video: 165 frames written in each run (logs).
* Warnings seen: `check_lowpass` warns (eps=15.7) because it is called with `--cutoff_hz` 300 at 120 Hz; with `--dvs_params clean` the emulator overrides the cutoff to 0, so for `clean` that warning is not applicable (the CLI behaves the same way, it checks `args.cutoff_hz`). For `noisy` (cutoff 30 Hz) the emulator logs `IIR lowpass ... eps=1.57` (dt/tau with inten01 up to 1): at 120 Hz sampling the Euler-step filter is coarse; an exact-exponential filter / higher sample rate (sub-stepping) are the out-of-scope follow-ups.
* I did NOT inspect the events visually or compare against the CLI or a `--legacy_dn` run; no claims about HDR behaviour (e.g. events in the glints/shadows) are made here — that is the verifier's acceptance test.

## Follow-ups (not done)
float32 switch, exact-exponential filter, sub-stepping/interpolation, adaptive sampling, motion-vector warping, dark-current model, spectral/QE weighting, noise recalibration; lin_log knee at DN 20; bandwidth saturation at inten01=1 (cutoff capped for pixels above white); `--dvs_text` (upstream np.float); `--start_time/--stop_time`; MODEL_STATES display ranges.

## Guard
CLEAN
