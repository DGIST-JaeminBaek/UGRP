"""
Real-time VLA inference and Piper robot control.

1. Loads a LeRobot policy checkpoint
2. Streams end-effector + camera observations from Piper
3. Runs inference at ~5Hz
4. Sends end-effector control commands back to Piper
"""

import argparse
import logging
import time
from pprint import pformat
from typing import Any

import torch

from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
from lerobot.policies.factory import make_policy, make_pre_post_processors

from .config_piper import PiperConfig
from .piper import EEF_NAMES, Piper

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TARGET_FPS = 5
SLEEP_TIME = 1.0 / TARGET_FPS


def create_batch(robot: Piper, task: str) -> dict[str, Any]:
    """로봇 상태와 카메라에서 정책 입력 배치를 생성."""
    obs = robot.get_observation()

    state_keys = [f"{n}.pos" for n in EEF_NAMES]
    if robot.config.include_gripper:
        state_keys.append("gripper.pos")
    state = torch.tensor([obs[k] for k in state_keys], dtype=torch.float32).unsqueeze(0)

    batch: dict[str, Any] = {"observation.state": state, "task": [task]}
    for cam_key in robot.cameras:
        batch[f"observation.images.{cam_key}"] = torch.from_numpy(obs[cam_key]).unsqueeze(0)
    return batch


def main(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() and args.device == "cuda" else "cpu")
    logger.info("Using device: %s", device)
    logger.info(pformat(vars(args)))

    # ── 1. Load policy ───────────────────────────────────────────────────────
    logger.info("Loading policy from %s", args.pretrained_path)
    policy_cfg = PreTrainedConfig.from_pretrained(args.pretrained_path)
    policy_cfg.pretrained_path = args.pretrained_path
    policy_cfg.device = str(device)

    ds_meta = LeRobotDatasetMetadata(args.dataset_repo_id, root=args.dataset_root)
    policy = make_policy(cfg=policy_cfg, ds_meta=ds_meta)
    policy.eval()

    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy_cfg,
        pretrained_path=args.pretrained_path,
        dataset_stats=ds_meta.stats,
    )
    logger.info("Policy loaded")

    # ── 2. Connect robot ─────────────────────────────────────────────────────
    robot: Piper | None = None
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
        logger.info("Robot connected — moving to zero configuration (5s)...")
        robot._iface.zero_configuration()
    else:
        logger.warning("Simulation mode (--use_devices false)")

    # ── 3. Inference loop ────────────────────────────────────────────────────
    logger.info("Starting inference loop (%dHz, max %d steps)...", TARGET_FPS, args.max_steps)
    step = 0
    total_inference_time = 0.0

    try:
        while step < args.max_steps:
            t0 = time.perf_counter()

            if robot is not None:
                batch = create_batch(robot, task=args.task)
            else:
                batch = {
                    "observation.state": torch.randn(1, 7),
                    "observation.images.top": torch.randint(
                        0, 256, (1, 480, 640, 3), dtype=torch.uint8
                    ),
                    "observation.images.wrist": torch.randint(
                        0, 256, (1, 480, 640, 3), dtype=torch.uint8
                    ),
                    "task": [args.task],
                }

            t1 = time.perf_counter()
            batch = preprocessor(batch)
            t2 = time.perf_counter()

            with torch.no_grad():
                action = policy.select_action(batch).squeeze()

            t3 = time.perf_counter()
            action = postprocessor(action.unsqueeze(0)).squeeze()

            if robot is not None:
                action_dict = {f"{n}.pos": action[i].item() for i, n in enumerate(EEF_NAMES)}
                if robot.config.include_gripper:
                    action_dict["gripper.pos"] = action[6].item()
                try:
                    robot.send_action(action_dict)
                except Exception as e:
                    logger.error("Failed to send action: %s", e)
                    robot._iface.zero_configuration()
                    break

            t4 = time.perf_counter()
            infer_time = t3 - t2
            total_inference_time += infer_time
            logger.info(
                "Step %4d | obs=%.3fs gpu=%.3fs infer=%.3fs total=%.3fs",
                step, t1 - t0, t2 - t1, infer_time, t4 - t0,
            )

            sleep_time = max(0.0, SLEEP_TIME - (t4 - t0))
            if sleep_time > 0:
                time.sleep(sleep_time)
            step += 1

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
    finally:
        if robot is not None:
            logger.info("Stopping robot safely...")
            robot._iface.zero_configuration()
            robot.disconnect()

        avg = total_inference_time / max(step, 1)
        logger.info("Done: %d steps, avg inference %.3fs", step, avg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time VLA inference on Piper robot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pretrained_path", type=str, required=True,
                        help="학습된 LeRobot 정책 체크포인트 경로")
    parser.add_argument("--dataset_repo_id", type=str, default="local/piper-demo",
                        help="LeRobot 데이터셋 repo ID (정규화 통계용)")
    parser.add_argument("--dataset_root", type=str, default=None,
                        help="데이터셋 로컬 경로 (기본값: HuggingFace 캐시)")
    parser.add_argument("--use_devices", type=lambda x: x.lower() in ("true", "1", "yes"),
                        default=True, help="실제 하드웨어 연결 여부 (false = 시뮬레이션)")
    parser.add_argument("--can_interface", type=str, default="can0")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--max_steps", type=int, default=1000)
    parser.add_argument("--task", type=str, default="pick and place")
    # RealSense 시리얼 번호 — 둘 다 지정하면 RealSense 사용, 미지정 시 OpenCV 인덱스 사용
    parser.add_argument("--top_serial", type=str, default=None,
                        help="top 카메라 RealSense 시리얼 번호")
    parser.add_argument("--wrist_serial", type=str, default=None,
                        help="wrist 카메라 RealSense 시리얼 번호")
    # OpenCV 인덱스 — RealSense 미사용 시 적용
    parser.add_argument("--top_index", type=int, default=0,
                        help="top 카메라 OpenCV 인덱스 (기본값: 0)")
    parser.add_argument("--wrist_index", type=int, default=4,
                        help="wrist 카메라 OpenCV 인덱스 (기본값: 4)")
    return parser.parse_args()


def cli_main():
    main(parse_args())


if __name__ == "__main__":
    cli_main()
