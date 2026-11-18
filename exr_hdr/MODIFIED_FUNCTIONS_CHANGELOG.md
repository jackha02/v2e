# Modified v2e functions (v2e @ cac6384)

## rescale_intensity_frame
* Source: `v2ecore/emulator_utils.py` lines 48-54 (copied into `modified_functions.py`, lines 6-12).
* Installed by the driver: `v2ecore.emulator.rescale_intensity_frame = modified_functions.rescale_intensity_frame` (the name is imported at emulator.py:23 and called at :673). Skipped with `--legacy_dn`.

Changed lines (1):
* orig emulator_utils.py:line 54: `return (new_frame+20)/275.` -> `return torch.clamp((new_frame+20)/275., max=1.)` -- driver feeds unclipped float DN (white=255, glints >> 255); inten01 = (DN+20)/275 would exceed 1, making the shot-noise factor (0.25-1)*inten01+1 negative above inten01=1.333 and spamming IIR warnings. Clamp at 1 = full white. Identical to the original for DN in [0,255].

Unchanged: signature (line 48), docstring (lines 49-53), the expression `(new_frame+20)/275.`. Added: `import torch` (module header; emulator_utils.py imports it at line 11).

Evidence: `modified_functions.diff` (diff -u of text extracted from the repo into `reports/pipeline-agent/work/orig_rescale_intensity_frame.py` vs the copy).

Deviation from the original brief (approved): driver uses `hdr=False` with float32 unclipped DN, so v2e's own `lin_log` runs inside the emulator; no lin_log inversion needed.
