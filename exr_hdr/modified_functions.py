"""Copies of v2e functions (SensorsINI/v2e @ cac6384) that must behave differently.
See MODIFIED_FUNCTIONS_CHANGELOG.md. Everything else is imported from v2e untouched."""
import torch


def rescale_intensity_frame(new_frame):
    """Rescale intensity frames.

    make sure we get no zero time constants
    limit max time constant to ~1/10 of white intensity level
    """
    return torch.clamp((new_frame+20)/275., max=1.)  # CHANGED(emulator_utils.py:54)
