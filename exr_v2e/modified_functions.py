"""Copy of the one v2e function that must behave differently (SensorsINI/v2e @ cac6384, v2ecore/emulator_utils.py)."""
import torch


def rescale_intensity_frame(new_frame):
    """Rescale intensity frames.

    make sure we get no zero time constants
    limit max time constant to ~1/10 of white intensity level
    """
    return torch.clamp((new_frame+20)/275., max=1.)  # intensity clamped to at most 1
