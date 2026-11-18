STATUS: DONE

# Verifier GATE 1 design review

All line numbers: v2e @ cac6384 (read by absolute path). Evidence: `reports/verifier/work/numeric.txt`, `reports/verifier/work/h1h2.txt` (scripts were inline heredocs; commands below). Env: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ROOT/v2e_pristine ROOT/venv/bin/python -P -`, cwd `reports/verifier/work`.

Process note: twice my shell `cd`'d (for reading) into `v2e_pristine`; only grep/sed/ls/find were run there, no python, no writes, and `find ... -name __pycache__` returned nothing. Guard says CLEAN (below).

## (1) inten01 claims: AGREE
- grep over all *.py in repo: `rescale_intensity_frame` appears only at emulator.py:23 (import), :673 (call) and its def emulator_utils.py:48. Only emulator.py uses it.
- `inten01` consumers: emulator.py:689 (`low_pass_filter`) and :899 (`generate_shot_noise`, via emulator.py:893-901). Nothing else.
- Rebinding works at call time: I set `v2ecore.emulator.rescale_intensity_frame = mod`, ran two `generate_events` calls on an EventEmulator: `rebound calls: 2` (numeric.txt). Name is a module global of `v2ecore.emulator` (:23 `from ... import`).
- Note: rebinding must happen before/independent of emulator construction; it is a module-global, so it also affects any other EventEmulator in-process (fine for a driver).

## (2) Numeric claims: AGREE
From numeric.txt: `lin_log(255)=5.541263580322266` (ln255=5.5412635); `lin_log(25500)=10.1464` (no clip). `inten01` true DN [0,20,255,366,1e4] = [0.0727, 0.1455, 1.0, 1.4036, 36.436]. With hdr=True (log input fed to rescale): 0.0727 .. 0.0929 for DN 0..255 (so brief's 0.07-0.13 is slightly off, memo right; 0.106 at DN 1e4). Shot factor `(0.25-1)*i+1` (SHOT_NOISE_INTEN_FACTOR=0.25, emulator.py:210): 0.25 at 1.0, 0.0 at 4/3, -26.3 at 36.4. IIR warning at eps>0.3 reproduced (`eps=1.88`). Also the code comment at emulator_utils.py:328 itself flags this logic as a TODO.

## (3) h2 (hdr=False + float DN) vs h1 (hdr=True): AGREE (equivalent), with notes
- Every use of hdr/log_input (grep emulator.py): :113, :155 (doc), :304-306 (`self.log_input`, log message), :659 (float32 warning only), :666 (`lin_log` skipped when log_input). No other file in v2ecore/ uses hdr besides v2e_args.py:340 (help text). So hdr changes only :666 and the :659 warning.
- Nothing in generate_events assumes 8-bit except: :645 uint8 dump (only if `frame_h5_dataset` set, i.e. `prepare_storage()`, driver doesn't call), :673 (the TODO), MODEL_STATES display ranges :42-48 (cosmetic), :381 uint8 dataset dtype (same h5 path). lin_log has "TODO assumes 8 bit" in docstring but does no clipping.
- Empirical: same random 16x16 float-DN frames (30 frames, bright 30x spots on alternate frames, cutoff 200 Hz, shot noise 5 Hz, seed 1), both with a clamp replacement (h2: clamp only; h1: inverts lin_log then clamps): `h2 events (38884, 4) h1 events (38884, 4)`, `identical: True` (h1h2.txt). Dtypes: lp_log_frame float64 in both; log_new_frame float32 (h2) vs float64 (h1); no effect on events here.
- Caveat on the h1 test: it used my own 5-line inversion; the claim is that h2 is the same as h1 and simpler. h2 additionally matches the CLI exactly (lin_log runs inside the emulator, incl. its 1e-8 rounding). I agree h2 is the better route and is justified as a documented deviation from the brief.
- Memo's claim that the negative-luminance clip is in the driver: confirmed in `exr_to_dn` (np.maximum(...,0)). Clip of negatives at 0 is a design decision for the human/orchestrator (note: lin_log is linear below DN 20, so negatives would otherwise be passed through).

## (4) Naming reproduces CLI: PARTLY DISAGREE
- Event files / dvs-video.avi / `dvs-video-frame_times.txt`: produced by v2e's own EventEmulator/EventRenderer with the same args: AGREE (renderer.py:48,154).
- Args file: `write_args_info` (v2e_args.py:491-498) names it from `__main__.__file__`: `basename.strip('.py') + '-args.txt'`. CLI gives `v2e-args.txt`; driver gives `exr_v2e_pipeline-args.txt` (strip of chars {'.','p','y'} leaves `exr_v2e_pipeline` unchanged, OK, but beware names ending in p/y). Memo already says this; it is a difference from the CLI, not a reproduction. Acceptable but the claim "same names as the CLI" in phase1.md is not exactly true for this file. If an identical name matters, wrap or rename the driver (not required).
- Timestamps: v2e.py:792-797 gives interpTimes = duration/(max-min)*index = i/srcFps (with --disable_slomo equivalent); driver `i/(fps*input_slowmotion_factor)`. Agree for the no-slomo case. CLI's srcFrameIntervalS (:404) uses the same slowmotion factor.
- Missing vs CLI: `check_lowpass(cutoff_hz, 1/avgTs, logger)` (v2e.py:450/766, v2e_utils.py:199) is not called. It is a v2e function and should be imported/called (it only logs), since the IIR warning is otherwise the only cue. No default-output-folder handling issue seen (set_output_folder imported from v2e).

## (5) Driver skeleton: mostly AGREE, with required changes
- No local re-implementation of v2e logic except: EXR reader, luminance, crop/resize (all required new steps A-D), plus the frame loop copied from v2e.py:829-850 (inline in main, unavoidable since the CLI's main() is monolithic). `set_output_folder`, `set_output_dimension`, `write_args_info`, `v2e_check_dvs_exposure_args`, `EventEmulator`, `EventRenderer`, `v2e_args`, `SmartFormatter` are imported. OK.
- No writes to cwd or repo path: outputs go to `-o` folder via `set_output_folder`. BUT if `-o` is not given, `output_folder` default is used relative to the cwd (v2e_args default, `make_output_folder` makes it relative to startup folder, v2e_utils.py:98). Require/validate `-o` is an absolute path outside the repo, or document "never run with cwd inside the repo". No pip -e anywhere (grep for pip/setup.py: only a docstring/comment). 
- Docstring in skeleton line 5-6 shows `python -I` with PYTHONPATH; that does not work (the -I flag ignores PYTHONPATH). Change to `python -P`.
- Crop is applied after luminance; the CLI crop semantics (v2e.py:640-650, `--crop` is left,right,top,bottom order; driver uses c[0],c[1],c[2],c[3] consistently with `[c[2]:h-c[3], c[0]:w-c[1]]`) look right; needs a test in phase 2 (I did not execute it).
- `--dvs_text` crashes upstream at ae_text_output.py:90 (np.float); I did not re-run it. Verified by reading: line exists in the file.

## OVERALL GATE 1 RECOMMENDATION: APPROVE (with changes)
Approve: copy only `rescale_intensity_frame` with the one-line clamp `torch.clamp((new_frame+20)/275., max=1.)`, rebinding `v2ecore.emulator.rescale_intensity_frame`; hdr=False + float unclipped DN (h2) as a documented deviation.
Required changes before Phase 2 sign-off:
1. Call v2e's `check_lowpass(args.cutoff_hz, args.fps*args.input_slowmotion_factor, logger)` (import from v2ecore.v2e_utils) as the CLI does.
2. Fix docstring (`python -P`, not `-I`); refuse to run if the output folder resolves inside ROOT/v2e_pristine (resolve path) and if `-o` is missing.
3. Warn (not silently ignore) on slomo/--start_time/--stop_time/--ddd_output/--output_in_place args; correct phase1 claim about args-file name.
4. Decide `--dvs_text`: choose option (i) (unsupported, documented) unless the human needs it; do not touch it by default.
5. Human decision needed: negative luminance clipped to 0; bandwidth saturation at inten01=1 (follow-up).
Not tested by me: crop path, real EXR, GPU, `--dvs_text`, full CLI-vs-driver equivalence.

## Commands run
```
grep -rn "rescale_intensity_frame\|inten01" --include=*.py ROOT/v2e_pristine
grep -n "hdr\|log_input" ROOT/v2e_pristine/v2ecore/emulator.py ; grep -rn ... v2ecore/*.py
python -P - (numeric script)  > work/numeric.txt
python -P - (h1 vs h2 comparison)  > work/h1h2.txt
sed/grep of v2e.py, v2e_utils.py, v2e_args.py, renderer.py (read-only)
PYTHONDONTWRITEBYTECODE=1 python3 -I ROOT/guard/guard.py check
```
Guard output: CLEAN
