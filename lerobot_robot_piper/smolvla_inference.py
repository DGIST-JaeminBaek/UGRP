"""
SmolVLA real-time inference on Piper robot.
"""

import argparse
import logging
import time

import numpy as np
import torch

from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

from .config_piper import PiperConfig
from .piper import EEF_NAMES, Piper

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

TARGET_FPS = 5
SLEEP_TIME = 1.0 / TARGET_FPS

# 녹화 데이터 기반 EEF action 안전 범위
ACTION_MIN = np.array([  5467., -44012., 133176., -173958.,   -3845., -171853.,   -3100.])
ACTION_MAX = np.array([329779.,  89639., 522348.,  -63833.,   77631.,  -65456.,  48500.])


def create_batch(robot: Piper, task: str) -> dict:
    obs = robot.get_observation()

    state_keys = [f"{n}.pos" for n in EEF_NAMES]
    if robot.config.include_gripper:
        state_keys.append("gripper.pos")
    state = torch.tensor([obs[k] for k in state_keys], dtype=torch.float32).unsqueeze(0)

    batch: dict = {"observation.state": state, "task": [task]}
    for cam_key in robot.cameras:
        img = torch.from_numpy(obs[cam_key]).float() / 255.0  # (H, W, C) [0,1]
        img = img.permute(2, 0, 1).unsqueeze(0)               # (1, C, H, W)
        batch[f"observation.images.{cam_key}"] = img
    return batch


def main(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() and args.device == "cuda" else "cpu")
    logger.info("Using device: %s", device)

    # 1. Load policy
    logger.info("Loading SmolVLA from %s", args.pretrained_path)
    policy = SmolVLAPolicy.from_pretrained(args.pretrained_path).to(device).eval()

    try:
        preprocessor, postprocessor = make_pre_post_processors(
            policy_cfg=policy.config,
            pretrained_path=args.pretrained_path,
        )
    except Exception as e:
        logger.warning("make_pre_post_processors failed (%s), using identity", e)
        preprocessor = lambda x: x
        postprocessor = lambda x: x
    logger.info("Policy loaded")

    # 2. Connect robot
    robot = None
    if args.use_devices:
        logger.info("Connecting to Piper on %s", args.can_interface)
        robot_config = PiperConfig(
            can_interface=args.can_interface,
            control_mode="user",
            top_serial=args.top_serial,
            wrist_serial=args.wrist_serial,
            top_index=args.top_index,
            wrist_index=args.wrist_index,
        )
        robot = Piper(robot_config)
        robot.connect(calibrate=False)
        logger.info("Robot connected — warming up cameras (8s)...")
        time.sleep(8.0)
        logger.info("Moving to zero (5s)...")
        robot._iface.zero_configuration()
    else:
        logger.warning("Simulation mode")

    # 3. Inference loop
    logger.info("Starting inference loop (%dHz, max %d steps)...", TARGET_FPS, args.max_steps)
    step = 0

    try:
        while step < args.max_steps:
            t0 = time.perf_counter()

            if robot is not None:
                batch = create_batch(robot, task=args.task)
            else:
                batch = {
                    "observation.state": torch.randn(1, 7),
                    "task": [args.task],
                    "observation.images.top": torch.rand(1, 3, 480, 640),
                }

            batch = preprocessor(batch)

            with torch.inference_mode():
                action = policy.select_action(batch)

            action = postprocessor(action).squeeze().cpu().numpy()

            # 안전 clamp — 학습 데이터 범위 내로 제한
            action = np.clip(action, ACTION_MIN, ACTION_MAX)

            if robot is not None:
                action_dict = {f"{n}.pos": float(action[i]) for i, n in enumerate(EEF_NAMES)}
                if robot.config.include_gripper:
                    action_dict["gripper.pos"] = float(action[6])
                try:
                    robot.send_action(action_dict)
                except Exception as e:
                    logger.error("Failed to send action: %s", e)
                    robot._iface.zero_configuration()
                    break

            elapsed = time.perf_counter() - t0
            logger.info("Step %4d | total=%.3fs action=%s", step, elapsed, action[:3].round(1))

            sleep_time = max(0.0, SLEEP_TIME - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
            step += 1

    except KeyboardInterrupt:
        logger.warning("Interrupted")
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
    finally:
        if robot is not None:
            logger.info("Stopping robot safely...")
            robot._iface.zero_configuration()
            robot.disconnect()
        logger.info("Done: %d steps", step)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--pretrained_path", type=str, required=True)
    parser.add_argument("--use_devices", type=lambda x: x.lower() in ("true", "1", "yes"), default=True)
    parser.add_argument("--can_interface", type=str, default="can0")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--max_steps", type=int, default=100)
    parser.add_argument("--task", type=str, default="pick the pan")
    parser.add_argument("--top_serial", type=str, default=None)
    parser.add_argument("--wrist_serial", type=str, default=None)
    parser.add_argument("--top_index", type=int, default=0)
    parser.add_argument("--wrist_index", type=int, default=4)
    return parser.parse_args()


def cli_main():
    main(parse_args())


if __name__ == "__main__":
    cli_main()
