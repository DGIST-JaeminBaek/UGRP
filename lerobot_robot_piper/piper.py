from typing import Any
import logging

from lerobot.cameras import make_cameras_from_configs
from lerobot.robots import Robot

from .config_piper import PiperConfig
from .piper_sdk_interface import PiperSDKInterface

logger = logging.getLogger(__name__)

# End-effector axis names (matches LoRA-SP's read_end_pose_msg field order)
EEF_NAMES = ["x", "y", "z", "rx", "ry", "rz"]


class Piper(Robot):
    config_class = PiperConfig
    name = "piper"
    _instances: dict[str, "Piper"] = {}

    def __init__(self, config: PiperConfig):
        super().__init__(config)
        self.config = config
        self._iface: PiperSDKInterface | None = None
        self.cameras = make_cameras_from_configs(config.cameras) if config.cameras else {}
        self._last_obs: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        return (
            self._iface is not None
            and getattr(self._iface, "piper", None) is not None
            and all(cam.is_connected for cam in self.cameras.values())
        )

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {k: (c.height, c.width, 3) for k, c in self.cameras.items()}

    @property
    def observation_features(self) -> dict:
        ft: dict = {f"{n}.pos": float for n in EEF_NAMES}
        if self.config.include_gripper:
            ft["gripper.pos"] = float
        ft.update(self._cameras_ft)
        return ft

    @property
    def action_features(self) -> dict:
        ft: dict = {f"{n}.pos": float for n in EEF_NAMES}
        if self.config.include_gripper:
            ft["gripper.pos"] = float
        return ft

    def connect(self, calibrate: bool = True) -> None:
        if self._iface is None:
            self._iface = PiperSDKInterface(
                port=self.config.can_interface,
                enable_timeout=self.config.enable_timeout,
                skip_enable=(self.config.control_mode == "teleop"),
            )
        for cam in self.cameras.values():
            cam.connect()
        self.configure()
        Piper._instances[self.config.can_interface] = self

    def disconnect(self) -> None:
        Piper._instances.pop(self.config.can_interface, None)
        if self._iface is not None:
            self._iface.disconnect()
            self._iface = None
        for cam in self.cameras.values():
            cam.disconnect()

    @property
    def is_calibrated(self) -> bool:  # type: ignore[override]
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected or self._iface is None:
            raise ConnectionError(f"{self} is not connected.")

        status = self._iface.get_end_pose_raw()
        obs: dict[str, Any] = {f"{n}.pos": float(status[n]) for n in EEF_NAMES}
        if self.config.include_gripper:
            obs["gripper.pos"] = float(status["gripper"])

        for cam_key, cam in self.cameras.items():
            obs[cam_key] = cam.async_read()
        self._last_obs = obs
        return obs

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected or self._iface is None:
            raise ConnectionError(f"{self} is not connected.")

        # In slave mode the Piper SDK handles master-slave sync via CAN.
        # Sending EndPoseCtrl here would conflict with that sync and cause unwanted movement.
        if self.config.control_mode == "teleop":
            return action

        eef_data = [int(action.get(f"{n}.pos", 0)) for n in EEF_NAMES]
        gripper_angle = int(action.get("gripper.pos", 0)) if self.config.include_gripper else None

        try:
            self._iface.ctrl_end_pose(eef_data, gripper_angle, self.config.gripper_effort)
        except Exception as e:
            logger.exception("Failed to send end-effector command: %s", e)
            raise

        return action
