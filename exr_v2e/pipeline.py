#!/usr/bin/env python
"""Drive the v2e event model from scene-linear EXR frames, and optionally write the matching 8-bit RGB frames.

Run with the repository root on PYTHONPATH and a working directory outside the v2e source tree:

    PYTHONPATH=<repo> python -m exr_v2e.pipeline --exr_dir FRAMES --fps 480 --white median \\
        --dvs346 --dvs_params noisy --dvs_h5 events.h5 --rgb_dir rgb --rgb_fps 60 -o OUT

Every EXR frame i enters the emulator at t = i / fps as float luminance DN = Y * 255 / white (not clipped, not
rounded); v2e's own lin_log, filter, noise and event generation do the rest. Only rescale_intensity_frame is replaced
(modified_functions.py). Not supported: --dvs_text, SuperSloMo upsampling, --start_time and --stop_time.
"""
import argparse
import json
import logging
import os
import sys
import time

import cv2
import numpy as np
import torch
from engineering_notation import EngNumber as eng
from tqdm import tqdm

import v2ecore
import v2ecore.emulator
from v2ecore.emulator import EventEmulator
from v2ecore.renderer import EventRenderer
from v2ecore.v2e_args import v2e_args, write_args_info, SmartFormatter, v2e_check_dvs_exposure_args
from v2ecore.v2e_utils import set_output_folder, set_output_dimension, v2e_quit, check_lowpass

from exr_v2e import modified_functions, rgb_camera
from exr_v2e.exr_io import REC709, list_exr_frames, luminance, read_exr_rgb, validate_frames

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger("exr_v2e")


def get_args(argv=None):
    parser = argparse.ArgumentParser(description="Simulated DVS events from scene-linear EXR frames.",
                                     allow_abbrev=True, formatter_class=SmartFormatter)
    parser = v2e_args(parser)
    parser.set_defaults(output_folder=None)
    group = parser.add_argument_group("EXR input")
    group.add_argument("--exr_dir", type=str, required=True, help="folder of EXR frames (ZIP, half float)")
    group.add_argument("--fps", type=float, required=True, help="frame rate of the EXR frames in Hz")
    group.add_argument("--white", type=str, default="1.0",
                       help="scene-linear luminance that maps to DN 255 and to 8-bit 255: a number, or 'median' "
                            "(clip median luminance maps to 18%% mid-gray)")
    group.add_argument("--ev", type=float, default=0.0, help="exposure offset in stops: white = white / 2**EV")
    group.add_argument("--weights", type=str, default=",".join(str(w) for w in REC709),
                       help="R,G,B luminance weights")
    group.add_argument("--n_frames", type=int, default=None, help="use only the first N EXR frames")
    group.add_argument("--rgb_dir", type=str, default=None, help="write 8-bit sRGB PNG frames into this folder")
    group.add_argument("--rgb_fps", type=float, default=None, help="frame rate of the RGB frames (default: --fps)")
    group.add_argument("--rgb_shutter", type=float, default=0.5,
                       help="fraction of the RGB frame interval during which the shutter is open (0.5 = 180 deg)")
    args, other = parser.parse_known_args(argv)
    return args, other, " ".join(sys.argv if argv is None else argv)


def exr_to_dn(path, weights, white):
    """Float DN of one EXR frame: scene-linear luminance scaled so that white maps to 255."""
    return (luminance(read_exr_rgb(path, validate=False), weights) * (255.0 / white)).astype(np.float32)


def crop_frame(frame, crop):
    """Remove (left, right, top, bottom) pixels from a frame."""
    left, right, top, bottom = crop
    height, width = frame.shape
    return frame[top:height - bottom, left:width - right]


def main(argv=None):
    args, other_args, command_line = get_args(argv)
    files = list_exr_frames(args.exr_dir)[:args.n_frames]
    if len(files) < 2:
        logger.error(f"need at least 2 EXR frames in {args.exr_dir}")
        v2e_quit(1)
    validate_frames(files)
    weights = [float(w) for w in args.weights.split(",")]
    white = rgb_camera.resolve_white(files, args.white, args.ev, weights)
    meta = dict(exr_dir=os.path.abspath(args.exr_dir), n_frames=len(files), fps=args.fps, weights=weights,
                white_rule=args.white, ev=args.ev, white_used=white)

    if args.rgb_dir:
        info = rgb_camera.extract_rgb_frames(args.exr_dir, args.rgb_dir, args.fps, args.rgb_fps, white, 0.0,
                                             args.rgb_shutter, weights, args.n_frames)
        meta.update(rgb_fps=info["rgb_fps"], n_rgb_frames=info["n_frames"], rgb_shutter=args.rgb_shutter)
        with open(os.path.join(args.rgb_dir, "exr_v2e_meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
        logger.info(f"wrote {info['n_frames']} RGB frames to {args.rgb_dir} (white = {white:.6g})")
    if args.output_folder is None:
        logger.error("-o/--output_folder is required")
        v2e_quit(1)
    v2e_root = os.path.realpath(os.path.dirname(os.path.dirname(v2ecore.__file__)))
    if os.path.commonpath([os.path.realpath(args.output_folder), v2e_root]) == v2e_root:
        logger.error(f"output folder {args.output_folder} is inside the v2e source tree {v2e_root}")
        v2e_quit(1)
    if args.dvs_text:
        logger.error("--dvs_text is not supported; use --dvs_h5, --dvs_aedat2 or --dvs_aedat4")
        v2e_quit(1)
    if args.hdr or args.synthetic_input or args.input:
        logger.error("--hdr, --synthetic_input and --input are not used with EXR input")
        v2e_quit(1)
    for name in ("start_time", "stop_time", "timestamp_resolution", "input_frame_rate", "ddd_output",
                 "output_in_place"):
        if getattr(args, name):
            logger.warning(f"--{name} is ignored")

    output_folder = set_output_folder(args.output_folder, args.exr_dir,
                                      args.unique_output_folder if not args.overwrite else False,
                                      args.overwrite, False, logger)
    output_width, output_height = set_output_dimension(args.output_width, args.output_height, args.dvs128, args.dvs240,
                                                       args.dvs346, args.dvs640, args.dvs1024, logger)
    crop = args.crop if args.crop is not None else (0, 0, 0, 0)
    if output_width is None:
        output_height, output_width = crop_frame(exr_to_dn(files[0], weights, white), crop).shape
    with open(os.path.join(output_folder, "exr_v2e_meta.json"), "w") as f:
        json.dump(dict(meta, crop=list(crop), output_size=[output_width, output_height]), f, indent=1)
    infofile = write_args_info(args, output_folder, other_args, command_line)
    handler = logging.FileHandler(infofile, mode="a")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

    exposure_mode, exposure_value, area_dimension = v2e_check_dvs_exposure_args(args)
    dvs_vid = args.dvs_vid if not args.skip_video_output else None
    torch_device = torch.device("cuda" if torch.cuda.is_available() else "cpu").type

    emulator = EventEmulator(
        pos_thres=args.pos_thres, neg_thres=args.neg_thres, sigma_thres=args.sigma_thres, cutoff_hz=args.cutoff_hz,
        leak_rate_hz=args.leak_rate_hz, shot_noise_rate_hz=args.shot_noise_rate_hz,
        photoreceptor_noise=args.photoreceptor_noise, leak_jitter_fraction=args.leak_jitter_fraction,
        noise_rate_cov_decades=args.noise_rate_cov_decades, refractory_period_s=args.refractory_period,
        seed=args.dvs_emulator_seed, output_folder=output_folder, dvs_h5=args.dvs_h5, dvs_aedat2=args.dvs_aedat2,
        dvs_aedat4=args.dvs_aedat4, dvs_text=args.dvs_text, show_dvs_model_state=args.show_dvs_model_state,
        save_dvs_model_state=args.save_dvs_model_state, output_width=output_width, output_height=output_height,
        device=torch_device, cs_lambda_pixels=args.cs_lambda_pixels, cs_tau_p_ms=args.cs_tau_p_ms,
        hdr=False,  # float DN goes in; the emulator applies lin_log itself
        scidvs=args.scidvs, record_single_pixel_states=args.record_single_pixel_states,
        label_signal_noise=args.label_signal_noise)
    if args.dvs_params is not None:
        emulator.set_dvs_params(args.dvs_params)
    v2ecore.emulator.rescale_intensity_frame = modified_functions.rescale_intensity_frame
    renderer = EventRenderer(
        output_path=output_folder, dvs_vid=dvs_vid, preview=not args.no_preview,
        full_scale_count=args.dvs_vid_full_scale, exposure_mode=exposure_mode, exposure_value=exposure_value,
        area_dimension=area_dimension, avi_frame_rate=args.avi_frame_rate)

    dt = 1.0 / (args.fps * args.input_slowmotion_factor)
    check_lowpass(args.cutoff_hz, 1 / dt, logger)
    start = time.time()
    events = np.zeros((0, 4), dtype=np.float32)
    with tqdm(total=len(files), desc="dvs", unit="fr") as progress, torch.no_grad():
        for i, path in enumerate(files):
            frame = crop_frame(exr_to_dn(path, weights, white), crop)
            if frame.shape != (output_height, output_width):
                frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
            new_events = emulator.generate_events(frame, i * dt)
            progress.update(1)
            if new_events is not None and new_events.shape[0] > 0 and not args.skip_video_output:
                events = np.append(events, new_events, axis=0)
                if i % args.batch_size == 0:
                    renderer.render_events_to_frames(events, height=output_height, width=output_width)
                    events = np.zeros((0, 4), dtype=np.float32)
        if len(events) > 0 and not args.skip_video_output:
            renderer.render_events_to_frames(events, height=output_height, width=output_width)

    renderer.cleanup()
    emulator.cleanup()
    logger.info("generated {} events ({} on, {} off) from {} frames in {:.1f}s".format(
        eng(emulator.num_events_total), eng(emulator.num_events_on), eng(emulator.num_events_off),
        len(files), time.time() - start))


if __name__ == "__main__":
    main()
