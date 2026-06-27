"""
Safe replay of recorded Piper end-effector trajectories from a LeRobot dataset.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata

from .config_piper import PiperConfig
from .piper import EEF_NAMES, Piper

logger = logging.getLogger(__name__)

ACTION_KEYS = [f"{name}.pos" for name in EEF_NAMES] + ["gripper.pos"]

# Conservative absolute raw-SDK workspace guard rails for replay validation.
DEFAULT_ACTION_MIN = np.array([-100000.0, -300000.0, 0.0, -360000.0, -360000.0, -360000.0, 0.0])
DEFAULT_ACTION_MAX = np.array([500000.0, 300000.0, 600000.0, 360000.0, 360000.0, 360000.0, 80000.0])

# Per-step absolute jump guard rails. Actions are absolute poses, so large jumps usually indicate
# a corrupted trajectory, wrong dataset, or an unsafe initial condition.
DEFAULT_STEP_DELTA_MAX = np.array([120000.0, 120000.0, 120000.0, 90000.0, 90000.0, 90000.0, 50000.0])

# First commanded pose vs current live EEF tolerance before sending the first action.
DEFAULT_INITIAL_GAP_MAX = np.array([80000.0, 80000.0, 80000.0, 60000.0, 60000.0, 60000.0, 30000.0])


@dataclass
class ReplayData:
    fps: int
    action_names: list[str]
    state_names: list[str]
    actions: np.ndarray
    states: np.ndarray | None
    episode_index: int
    frame_indices: list[int]


def _parse_bool(value: str) -> bool:
    return value.lower() in ("1", "true", "yes", "y", "on")


def _vector_to_dict(vector: np.ndarray) -> dict[str, float]:
    return {key: float(vector[i]) for i, key in enumerate(ACTION_KEYS)}


def _obs_to_vector(obs: dict[str, Any]) -> np.ndarray:
    return np.asarray([float(obs[key]) for key in ACTION_KEYS], dtype=np.float64)


def _diff_summary(target: np.ndarray, actual: np.ndarray) -> str:
    diff = np.abs(actual - target)
    return (
        f"xyz_max={diff[:3].max():.0f} "
        f"rpy_max={diff[3:6].max():.0f} "
        f"gripper={diff[6]:.0f}"
    )


def _preview_indices(mask: np.ndarray, limit: int = 10) -> str:
    indices = np.flatnonzero(mask).tolist()
    if not indices:
        return "[]"
    head = indices[:limit]
    suffix = " ..." if len(indices) > limit else ""
    return f"{head}{suffix}"


def _load_episode_data(repo_id: str, root: str | None, episode: int) -> ReplayData:
    meta = LeRobotDatasetMetadata(repo_id, root=root)
    data_path = meta.get_data_file_path(episode)
    df = pd.read_parquet(data_path)
    df = df[df["episode_index"] == episode].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"Episode {episode} not found in {data_path}")

    if "action" not in df.columns:
        raise ValueError("Dataset parquet does not contain an `action` column.")

    action_names = list(meta.features["action"]["names"])
    expected_action_names = ACTION_KEYS
    if action_names != expected_action_names:
        raise ValueError(
            f"Unexpected action names for Piper replay.\n"
            f"expected={expected_action_names}\n"
            f"found={action_names}"
        )

    state_names: list[str] = []
    if "observation.state" in meta.features:
        state_names = list(meta.features["observation.state"]["names"])

    actions = np.stack([np.asarray(row, dtype=np.float64) for row in df["action"].to_list()])
    states = None
    if "observation.state" in df.columns:
        states = np.stack([np.asarray(row, dtype=np.float64) for row in df["observation.state"].to_list()])

    frame_indices = (
        df["frame_index"].astype(int).tolist()
        if "frame_index" in df.columns
        else list(range(len(df)))
    )

    return ReplayData(
        fps=int(meta.fps),
        action_names=action_names,
        state_names=state_names,
        actions=actions,
        states=states,
        episode_index=episode,
        frame_indices=frame_indices,
    )


def _validate_recorded_episode(data: ReplayData, allow_invalid: bool) -> None:
    zero_mask = np.all(data.actions == 0, axis=1)
    abs_low_mask = np.any(data.actions < DEFAULT_ACTION_MIN, axis=1)
    abs_high_mask = np.any(data.actions > DEFAULT_ACTION_MAX, axis=1)
    if len(data.actions) > 1:
        step_delta = np.abs(np.diff(data.actions, axis=0))
        jump_mask = np.any(step_delta > DEFAULT_STEP_DELTA_MAX, axis=1)
    else:
        jump_mask = np.zeros(0, dtype=bool)

    if data.states is not None:
        state_zero_mask = np.all(data.states == 0, axis=1)
        obs_action_mismatch = np.any(np.abs(data.states - data.actions) > 1e-6, axis=1)
    else:
        state_zero_mask = np.zeros(len(data.actions), dtype=bool)
        obs_action_mismatch = np.zeros(len(data.actions), dtype=bool)

    logger.info(
        "Recorded episode checks | frames=%d action_zero=%d state_zero=%d abs_low=%d abs_high=%d large_jumps=%d obs_action_mismatch=%d",
        len(data.actions),
        int(zero_mask.sum()),
        int(state_zero_mask.sum()),
        int(abs_low_mask.sum()),
        int(abs_high_mask.sum()),
        int(jump_mask.sum()),
        int(obs_action_mismatch.sum()),
    )

    if zero_mask.any():
        logger.warning("All-zero actions at local frame indices %s", _preview_indices(zero_mask))
    if state_zero_mask.any():
        logger.warning("All-zero recorded states at local frame indices %s", _preview_indices(state_zero_mask))
    if abs_low_mask.any():
        logger.warning("Under-range actions at local frame indices %s", _preview_indices(abs_low_mask))
    if abs_high_mask.any():
        logger.warning("Over-range actions at local frame indices %s", _preview_indices(abs_high_mask))
    if jump_mask.any():
        logger.warning("Large inter-frame action jumps before frames %s", _preview_indices(jump_mask))
    if obs_action_mismatch.any():
        logger.warning(
            "Recorded observation.state differs from recorded action at local frame indices %s",
            _preview_indices(obs_action_mismatch),
        )

    invalid = (
        zero_mask.any()
        or state_zero_mask.any()
        or abs_low_mask.any()
        or abs_high_mask.any()
        or jump_mask.any()
    )
    if invalid and not allow_invalid:
        raise ValueError(
            "Recorded episode failed safety validation. "
            "Inspect warnings above or rerun with --allow_invalid_actions=true if you intentionally want to bypass it."
        )


def _connect_robot(args: argparse.Namespace) -> Piper:
    robot = Piper(
        PiperConfig(
            can_interface=args.can_interface,
            control_mode="user",
            use_cameras=False,
        )
    )
    robot.connect(calibrate=False)
    if robot.config.control_mode != "user":
        raise RuntimeError("Replay requires Piper control_mode=user.")
    return robot


def _log_live_gap(prefix: str, target: np.ndarray, observed: np.ndarray) -> None:
    logger.info("%s | %s", prefix, _diff_summary(target, observed))


def replay(args: argparse.Namespace) -> None:
    data = _load_episode_data(args.dataset_repo_id, args.dataset_root, args.episode)
    _validate_recorded_episode(data, allow_invalid=args.allow_invalid_actions)

    start = max(0, args.start_frame)
    if start >= len(data.actions):
        raise ValueError(f"start_frame={start} is outside episode length {len(data.actions)}")

    end = len(data.actions)
    if args.max_steps is not None:
        end = min(end, start + args.max_steps)

    actions = data.actions[start:end]
    frame_indices = data.frame_indices[start:end]
    if len(actions) == 0:
        raise ValueError(
            "Selected replay range is empty. "
            "Check start_frame/max_steps and make sure they select at least one frame."
        )
    replay_fps = args.replay_fps or data.fps
    period_s = 1.0 / replay_fps

    logger.info(
        "Replay plan | episode=%d start_frame=%d steps=%d replay_fps=%d use_devices=%s",
        data.episode_index,
        start,
        len(actions),
        replay_fps,
        args.use_devices,
    )

    robot: Piper | None = None
    step = 0
    try:
        if args.use_devices:
            robot = _connect_robot(args)
            current_obs = robot.get_observation()
            current_vec = _obs_to_vector(current_obs)
            first_action = actions[0]
            gap = np.abs(current_vec - first_action)
            _log_live_gap("Initial live EEF vs first recorded action", first_action, current_vec)
            if np.any(gap > DEFAULT_INITIAL_GAP_MAX) and not args.allow_large_initial_gap:
                raise ValueError(
                    "Current live EEF is too far from the first replay action. "
                    "Reposition the arm near the recorded start pose or rerun with --allow_large_initial_gap=true."
                )

        for local_idx, action in enumerate(actions):
            t0 = time.perf_counter()
            frame_idx = frame_indices[local_idx]

            if robot is not None:
                before_obs = robot.get_observation()
                before_vec = _obs_to_vector(before_obs)
                _log_live_gap(
                    f"Step {step:04d} frame={frame_idx} before-send gap",
                    action,
                    before_vec,
                )

                robot.send_action(_vector_to_dict(action))

                if args.observe_after_send_delay_s > 0:
                    time.sleep(args.observe_after_send_delay_s)

                after_obs = robot.get_observation()
                after_vec = _obs_to_vector(after_obs)
                _log_live_gap(
                    f"Step {step:04d} frame={frame_idx} after-send gap",
                    action,
                    after_vec,
                )
            else:
                if data.states is not None:
                    recorded_state = data.states[start + local_idx]
                    logger.info(
                        "Dry-run step %04d frame=%d | recorded obs-action gap: %s",
                        step,
                        frame_idx,
                        _diff_summary(action, recorded_state),
                    )
                logger.info(
                    "Dry-run step %04d frame=%d | action=%s",
                    step,
                    frame_idx,
                    np.array2string(action, precision=1, separator=", "),
                )

            elapsed = time.perf_counter() - t0
            sleep_s = max(0.0, period_s - elapsed)
            if sleep_s > 0:
                time.sleep(sleep_s)
            step += 1

    finally:
        if robot is not None:
            robot.disconnect()
        logger.info("Replay finished after %d steps", step)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe replay of a Piper LeRobotDataset episode",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset_repo_id", type=str, required=True, help="LeRobot dataset repo ID")
    parser.add_argument("--dataset_root", type=str, default=None, help="Local dataset root path")
    parser.add_argument("--episode", type=int, required=True, help="Episode index to replay")
    parser.add_argument("--use_devices", type=_parse_bool, default=False, help="False = dry-run only")
    parser.add_argument("--can_interface", type=str, default="can0")
    parser.add_argument("--start_frame", type=int, default=0, help="Episode-local frame offset")
    parser.add_argument("--max_steps", type=int, default=None, help="Maximum number of replayed frames")
    parser.add_argument("--replay_fps", type=int, default=None, help="Override recorded dataset fps")
    parser.add_argument(
        "--observe_after_send_delay_s",
        type=float,
        default=0.05,
        help="Delay before reading live EEF after each send_action",
    )
    parser.add_argument(
        "--allow_invalid_actions",
        type=_parse_bool,
        default=False,
        help="Bypass dataset safety validation failures",
    )
    parser.add_argument(
        "--allow_large_initial_gap",
        type=_parse_bool,
        default=False,
        help="Allow replay even if current live EEF is far from the first action",
    )
    return parser.parse_args()


def cli_main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    replay(parse_args())


if __name__ == "__main__":
    cli_main()
