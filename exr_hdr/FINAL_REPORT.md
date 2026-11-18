# Final report: v2e fed with scene-linear HDR EXR luminance

ROOT = /home/wonny/jack/v2e_rebuild. Every number below comes from a command run by a worker or the verifier; evidence paths are given.

## Pass/fail table

| Test | Result | Evidence |
|---|---|---|
| T1 Guardian | PASS. Manifest equals baseline, 656 checks, 0 violations. The verifier's interim check was also CLEAN. | `guard/guard_final.md`, `guard/guard.log`, `reports/verifier/work/guard_interim.txt` |
| T2 Import audit | PASS. The only runtime patch is the rebinding of `v2ecore.emulator.rescale_intensity_frame`. `modified_functions.py` differs from the original function by 1 line. | `reports/verifier/work/t2/t2.txt` |
| T3 Legacy equivalence | PASS. Event streams are bit-identical to the real v2e CLI for clean (242213 events) and noisy (295543 events). The CLI's gray round trip is exact and the timebase matches (frame i at i/fps). | `reports/verifier/work/t3/cmp.txt`, `roundtrip_cli.txt` |
| T4 HDR run, 200 EXR frames | PASS. clean: 1,666,893 events; noisy: 2,013,404 events. The h5, aedat4 and avi files open. | `outputs/hdr_clean`, `outputs/hdr_noisy`, `reports/verifier/work/t3/roundtrip_cli.txt` |
| T5 HDR evidence | PASS, with the caveats below. | `reports/verifier/work/t5/t5.txt` |
| T6 Clean-shell reproduction | PASS. md5 of events.h5, dvs-video.avi and events.aedat4 equal the author's outputs for both presets. | `reports/verifier/work/t6/t6_compare.txt` |

### T5 key numbers
- **Nothing clipped:** max DN_f = 309903.6 (white = 255). 1.95% of pixels are above 255. The maximum log value is 12.644, against ln 255 = 5.541.
- **inten01 for bright pixels (Y > 50x card):** unpatched 46.5 to 1127. Patched is exactly 1.0. The original problem (hdr=True with log input) gives 0.107 to 0.119.
- **inten01 for dark pixels:** 0.0727 to 0.1191 in all variants.
- **Event rates (events/pixel/s), HDR vs legacy with DN clipped to 255:**

| Run | Glint set | Static shadow | Total events |
|---|---|---|---|
| HDR clean | 112.8 | 0.688 | 1,666,893 |
| Legacy clean | 42.6 | 0.706 | 1,227,026 |
| HDR noisy | 119.8 | 5.43 | 2,013,404 |
| Legacy noisy | 45.5 | 5.48 | 1,549,480 |

  The glint set is 3773 pixels and the static-shadow set is 17886 pixels. The pixel sets are defined in `reports/verifier/work/t5/t5.py`.
- **What HDR gains:** about 2.7x more events in the glint set, and about 140x (clean) or 74x (noisy) in frames where the pixel is above 50x card. It gains nothing measurable in the static shadows, because those shadows (below 0.05x card, DN < 12.75) already fall in lin_log's linear region.

## Single run command
`pipeline/RUN.md` holds the one documented command. It is a bash block that loops over `--dvs_params clean` and `--dvs_params noisy`. It uses `python -P` with `PYTHONPATH=v2e_pristine`, not `python -I`, because `-I` ignores PYTHONPATH.

## Guard summary
v2e_pristine stayed at commit cac6384 and was never modified: no `__pycache__`, no egg-info, and `git status --porcelain --ignored` is empty. The watcher ran 656 checks with 0 violations.

## Changed lines
One copied function: `rescale_intensity_frame` (emulator_utils.py:48-54). One changed line:
`return (new_frame+20)/275.` -> `return torch.clamp((new_frame+20)/275., max=1.)  # CHANGED(emulator_utils.py:54)`
See `pipeline/MODIFIED_FUNCTIONS_CHANGELOG.md` and `pipeline/modified_functions.diff`.

## Findings the human should know
1. **The patch has no effect with `--dvs_params clean`.** Clean sets cutoff_hz = 0 and shot noise = 0, so `inten01` is never computed. The clean HDR gain comes entirely from feeding unclipped DN through `lin_log`. With the patch removed, clean events are bit-identical. In noisy the patch changes 1219 events (2,013,404 patched vs 2,012,185 unpatched), but it matters for correctness: unpatched, the shot-noise factor goes negative for 0.585% of pixel-frames and the IIR step logs eps = 1371.
2. **The noisy low-pass is a pass-through for bright pixels.** At 120 fps with a 30 Hz cutoff, dt/tau = 1.57, so eps is capped at 1 for DN of roughly 156 and above. Cause: Euler-step filter (the exact-exponential filter is a listed follow-up). Bandwidth also saturates at white, by the approved clamp.
3. **The `check_lowpass` warning in the clean run is misleading.** It uses the default `--cutoff_hz` (300), while the clean preset overrides the cutoff to 0. The CLI behaves the same way.
4. **Known minor driver issue (not fixed, per C4).** `sorted(glob('*.exr'))` sorts lexicographically, while the CLI sorts by integer. This is fine for the 4-digit names used here and wrong for unpadded names.

## Open decisions for the human
- **lin_log knee vs the chosen white.** lin_log is unchanged, as instructed. The knee is at DN 20, which is 7.8% of white. `--white` is the in-scene gray-card luminance, 0.0972. Moving it moves the point where the log mapping starts to saturate low-end detail.
- **Runtime-rebinding approach.** I used a one-line copy bound at runtime. The alternative is a subclass that copies about 400 lines of `generate_events`.
- **Whether bandwidth should saturate at white.** The bandwidth clamp at white is approved but physically arguable. A real photoreceptor's bandwidth keeps rising with photocurrent. Clamping only the shot-noise term is an alternative that would need a 55-line copy.
- **Out-of-scope follow-ups (not done):** float32 switch, exact-exponential filter, sub-stepping or interpolation, adaptive sampling, motion-vector warping, dark-current/dark-floor log model, spectral/QE weighting, noise-model recalibration. Also: `--dvs_text`, `--start_time/--stop_time`, glint-motion measurement, shaded-water tail.

## Deviations from the prompt
1. **hdr=False instead of hdr=True.** The driver feeds float unclipped DN and lets v2e's own `lin_log` run inside the emulator. The verifier confirmed events are identical to the hdr=True route.
2. **Negative luminance clipped to 0 and NaN set to 0 in the driver.** Approved.
3. **`--dvs_text` unsupported.** Upstream `ae_text_output.py:90` uses `np.float`, which fails on numpy 1.24 and later. The driver exits with an explanatory error. Option (i), approved.
4. **No SuperSloMo.** The driver matches the CLI with `--disable_slomo`. The driver warns on `--start_time`, `--stop_time`, `--timestamp_resolution`, `--input_frame_rate`, `--ddd_output` and `--output_in_place`.
5. **Args file name.** The driver writes `exr_v2e_pipeline-args.txt`, not the CLI's `v2e-args.txt`.
6. **Clone source.** v2e_pristine was cloned from the fork `jackha02/v2e`, not `SensorsINI/v2e`. Its HEAD is exactly the pinned commit cac6384.
7. **Guardian is a script, not an agent.** The orchestrator reviewed the scripts. The verifier ran its own audits.
8. **Supplementary material not available.** The paper PDF is the 10-page main paper only. Step E was checked against the code and the main text.
9. **Blender scene deviations.**
   - The sun disc is 8° (the real sun is 0.53°). Smaller discs gave glints in only 30 to 60% of frames. Glints are therefore larger and softer than real ones.
   - The gray card is horizontal. The in-scene card luminance is 0.0972 (partly occluded by the bridge deck), against 0.1132 unoccluded.
   - The "shaded water below 0.05x card" target is met for 98.5% of shaded pixels (median 0.012x), not for the tail (all-frames max 110x). This is likely penumbra misclassification, not verified.
   - The 155.8 dB figure is max over min-positive across the whole clip, dominated by a few extreme pixels.
   - The motion estimate (max 0.62 px/frame) is vertex-based. Glint highlights can move faster, and this was not measured.
10. **Exposed-region assumption.** I read it as the full camera view, which contains both sunlit glinting water and shadowed water. The human did not confirm it.
11. **Verifier shell cwd.** Twice the verifier's shell sat in `v2e_pristine` while it ran read-only commands (grep, sed, ls, find). The guard stayed CLEAN.
12. **Push route.** Per your choice, v2e_pristine stays untouched. The deliverables are pushed from a separate clone, `v2e_push`, under `exr_hdr/`.
