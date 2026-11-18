#!/usr/bin/env python
"""
Drive v2e's event model from scene-linear OpenEXR frames.

Run with v2e on PYTHONPATH (never installed; cwd outside the v2e repo), e.g.
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<ROOT>/v2e_pristine <ROOT>/venv/bin/python -P \
      exr_v2e_pipeline.py --exr_dir DIR --fps 60 --white 1.0 -o OUT --dvs346 ...
(-I would ignore PYTHONPATH; -P keeps cwd/script dir off sys.path.) -o is required.
Not supported: --dvs_text (v2e's own text writer crashes on numpy>=1.24, np.float),
SuperSloMo upsampling (equivalent to the CLI's --disable_slomo), --start_time/--stop_time.

Per EXR frame i (t_i = i/fps): luminance Y = w . RGB (linear, float, not clipped),
DN_f = Y*255/white, then emulator.generate_events(DN_f, t_i).
Steps E-J are v2e's own code (EventEmulator, EventRenderer). Only rescale_intensity_frame
is copied (modified_functions.py) and rebound;
see MODIFIED_FUNCTIONS_CHANGELOG.md for the one changed function.
"""
import argparse
import glob
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -P: find modified_functions.py

import cv2
import numpy as np
import OpenEXR
import torch
from engineering_notation import EngNumber as eng
from tqdm import tqdm

import v2ecore
import v2ecore.emulator
from v2ecore.emulator import EventEmulator
from v2ecore.renderer import EventRenderer
from v2ecore.v2e_args import (v2e_args, write_args_info, SmartFormatter,
                              v2e_check_dvs_exposure_args)
from v2ecore.v2e_utils import set_output_folder, set_output_dimension, v2e_quit, check_lowpass

import modified_functions

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("exr_v2e_pipeline")

REC709 = (0.2126, 0.7152, 0.0722)


def get_args():
    parser = argparse.ArgumentParser(
        description='exr-v2e: simulated DVS events from scene-linear EXR frames.',
        allow_abbrev=True, formatter_class=SmartFormatter)
    parser = v2e_args(parser)  # v2e's own argument definitions
    parser.set_defaults(output_folder=None)  # -o is required (no cwd-relative default)
    g = parser.add_argument_group('EXR input')
    g.add_argument('--exr_dir', type=str, required=True,
                   help='folder of *.exr frames, sorted by name')
    g.add_argument('--fps', type=float, required=True, help='EXR frame rate in Hz')
    g.add_argument('--white', type=float, default=1.0,
                   help='scene-linear luminance that maps to DN 255')
    g.add_argument('--weights', type=str, default=','.join(str(w) for w in REC709),
                   help='R,G,B luminance weights (default Rec.709)')
    g.add_argument('--legacy_dn', action='store_true',
                   help='TEST ONLY: round/clip DN to 8 bit and use the unmodified v2e path')
    args, other = parser.parse_known_args()
    return args, other, ' '.join(sys.argv)


def read_exr_rgb(path):
    """Return float32 [H,W,3] linear RGB from RGB, RGBA or '<ViewLayer>.Combined' channel group."""
    chans = OpenEXR.File(path).channels()
    for key in ('RGB', 'RGBA'):
        if key in chans:
            return np.asarray(chans[key].pixels, dtype=np.float32)[..., :3]
    for key in chans:
        if key.endswith('.Combined'):
            return np.asarray(chans[key].pixels, dtype=np.float32)[..., :3]
    raise ValueError(f'{path}: no RGB/RGBA/*.Combined channel group in {list(chans)}')


def exr_to_dn(path, weights, white):
    """Scene-linear luminance -> float DN (white -> 255); not clipped above, not rounded."""
    rgb = read_exr_rgb(path)
    y = rgb @ np.asarray(weights, dtype=np.float32)
    y = np.maximum(np.nan_to_num(y, nan=0.0, posinf=np.finfo(np.float32).max), 0.0)
    return (y * (255.0 / white)).astype(np.float32)


def main():
    args, other_args, command_line = get_args()
    files = sorted(glob.glob(os.path.join(args.exr_dir, '*.exr')))
    if len(files) < 2:
        logger.error(f'need >=2 EXR frames in {args.exr_dir}')
        v2e_quit(1)
    weights = [float(w) for w in args.weights.split(',')]
    if args.output_folder is None:
        logger.error('-o/--output_folder is required')
        v2e_quit(1)
    v2e_root = os.path.realpath(os.path.dirname(os.path.dirname(v2ecore.__file__)))
    out_real = os.path.realpath(args.output_folder)
    if os.path.commonpath([out_real, v2e_root]) == v2e_root:
        logger.error(f'output folder {out_real} is inside the v2e repo {v2e_root}; refusing')
        v2e_quit(1)
    if args.dvs_text:
        logger.error('--dvs_text is not supported (v2e text writer crashes: np.float); use --dvs_h5/--dvs_aedat2/--dvs_aedat4')
        v2e_quit(1)
    for name in ('start_time', 'stop_time', 'timestamp_resolution', 'input_frame_rate'):
        if getattr(args, name) is not None:
            logger.warning(f'--{name} is ignored by the EXR driver')
    for name in ('ddd_output', 'output_in_place'):
        if getattr(args, name):
            logger.warning(f'--{name} is ignored by the EXR driver')
    logger.warning('No SloMo upsampling in the EXR driver (as CLI --disable_slomo): '
                   'DVS timestamps have the EXR frame interval; slomo/auto_timestamp_resolution args are ignored')
    if args.hdr or args.synthetic_input or args.input:
        logger.error('--hdr, --synthetic_input and --input are not used by the EXR driver')
        v2e_quit(1)

    output_folder = set_output_folder(
        args.output_folder, args.exr_dir,
        args.unique_output_folder if not args.overwrite else False,
        args.overwrite, False, logger)
    output_width, output_height = set_output_dimension(
        args.output_width, args.output_height, args.dvs128, args.dvs240,
        args.dvs346, args.dvs640, args.dvs1024, logger)
    first = exr_to_dn(files[0], weights, args.white)
    if output_width is None:
        output_height, output_width = first.shape
    infofile = write_args_info(args, output_folder, other_args, command_line)
    fh = logging.FileHandler(infofile, mode='a')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)

    exposure_mode, exposure_val, area_dimension = v2e_check_dvs_exposure_args(args)
    dvs_vid = args.dvs_vid if not args.skip_video_output else None
    torch_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu').type

    emulator = EventEmulator(
        pos_thres=args.pos_thres, neg_thres=args.neg_thres,
        sigma_thres=args.sigma_thres, cutoff_hz=args.cutoff_hz,
        leak_rate_hz=args.leak_rate_hz, shot_noise_rate_hz=args.shot_noise_rate_hz,
        photoreceptor_noise=args.photoreceptor_noise,
        leak_jitter_fraction=args.leak_jitter_fraction,
        noise_rate_cov_decades=args.noise_rate_cov_decades,
        refractory_period_s=args.refractory_period, seed=args.dvs_emulator_seed,
        output_folder=output_folder, dvs_h5=args.dvs_h5, dvs_aedat2=args.dvs_aedat2,
        dvs_aedat4=args.dvs_aedat4, dvs_text=args.dvs_text,
        show_dvs_model_state=args.show_dvs_model_state,
        save_dvs_model_state=args.save_dvs_model_state,
        output_width=output_width, output_height=output_height, device=torch_device,
        cs_lambda_pixels=args.cs_lambda_pixels, cs_tau_p_ms=args.cs_tau_p_ms,
        hdr=False,  # see design memo: float DN goes in, v2e's own lin_log runs inside the emulator
        scidvs=args.scidvs, record_single_pixel_states=args.record_single_pixel_states,
        label_signal_noise=args.label_signal_noise)
    if args.dvs_params is not None:
        emulator.set_dvs_params(args.dvs_params)
    if not args.legacy_dn:
        v2ecore.emulator.rescale_intensity_frame = modified_functions.rescale_intensity_frame
        assert v2ecore.emulator.rescale_intensity_frame is modified_functions.rescale_intensity_frame
        logger.info('installed modified_functions.rescale_intensity_frame (inten01 clamped to <=1)')
    renderer = EventRenderer(
        output_path=output_folder, dvs_vid=dvs_vid, preview=not args.no_preview,
        full_scale_count=args.dvs_vid_full_scale, exposure_mode=exposure_mode,
        exposure_value=exposure_val, area_dimension=area_dimension,
        avi_frame_rate=args.avi_frame_rate)

    dt = 1.0 / (args.fps * args.input_slowmotion_factor)
    check_lowpass(args.cutoff_hz, 1 / dt, logger)
    c = args.crop if args.crop is not None else (0, 0, 0, 0)
    t_start = time.time()
    events = np.zeros((0, 4), dtype=np.float32)
    with tqdm(total=len(files), desc='dvs', unit='fr') as pbar, torch.no_grad():
        for i, path in enumerate(files):
            fr = exr_to_dn(path, weights, args.white)
            h, w = fr.shape
            fr = fr[c[2]:h - c[3], c[0]:w - c[1]]
            if fr.shape != (output_height, output_width):
                fr = cv2.resize(fr, (output_width, output_height), interpolation=cv2.INTER_AREA)
            if args.legacy_dn:
                fr = np.clip(np.rint(fr), 0, 255).astype(np.float32)
            new_events = emulator.generate_events(fr, i * dt)
            pbar.update(1)
            if new_events is not None and new_events.shape[0] > 0 and not args.skip_video_output:
                events = np.array(np.append(events, new_events, axis=0))
                if i % args.batch_size == 0:
                    renderer.render_events_to_frames(events, height=output_height, width=output_width)
                    events = np.zeros((0, 4), dtype=np.float32)
        if len(events) > 0 and not args.skip_video_output:
            renderer.render_events_to_frames(events, height=output_height, width=output_width)

    renderer.cleanup()
    emulator.cleanup()
    logger.info('generated total {} events ({} on, {} off) from {} frames in {:.1f}s'.format(
        eng(emulator.num_events_total), eng(emulator.num_events_on),
        eng(emulator.num_events_off), len(files), time.time() - t_start))


if __name__ == '__main__':
    main()
