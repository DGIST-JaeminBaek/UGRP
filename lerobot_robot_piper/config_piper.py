from dataclasses import dataclass, field
from typing import Optional

from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.robots import RobotConfig


@RobotConfig.register_subclass("piper")
@dataclass
class PiperConfig(RobotConfig):
    can_interface: str = "can0"
    # "teleop": CAN hardware handles master-slave sync, send_action is no-op
    # "user": script directly controls the arm via EndPoseCtrl
    control_mode: str = "teleop"
    # Include gripper in observation and action (7th dimension)
    include_gripper: bool = True
    # Gripper effort sent to SDK (LoRA-SP uses 100)
    gripper_effort: int = 100
    enable_timeout: float = 5.0

    # OpenCV camera indices (used when RealSense serials are not provided)
    top_index: int = 0
    wrist_index: int = 4

    # RealSense serial numbers — if provided, overrides OpenCV index cameras.
    # Both must be specified together.
    top_serial: Optional[str] = None
    wrist_serial: Optional[str] = None

    # Set False to disable all cameras (EEF-only recording/inference)
    use_cameras: bool = True

    # Built automatically in __post_init__ — do not set manually.
    cameras: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        if not self.use_cameras:
            self.cameras = {}
            return
        if self.top_serial or self.wrist_serial:
            if not self.top_serial or not self.wrist_serial:
                raise ValueError("top_serial 과 wrist_serial 을 둘 다 지정해야 합니다.")
            from lerobot.cameras.realsense import RealSenseCameraConfig
            self.cameras = {
                "top": RealSenseCameraConfig(
                    serial_number_or_name=self.top_serial, fps=30, width=640, height=480, warmup_s=5
                ),
                "wrist": RealSenseCameraConfig(
                    serial_number_or_name=self.wrist_serial, fps=30, width=640, height=480, warmup_s=5
                ),
            }
        else:
            self.cameras = {
                "top": OpenCVCameraConfig(
                    index_or_path=self.top_index, width=640, height=480, fps=30, fourcc="MJPG"
                ),
                "wrist": OpenCVCameraConfig(
                    index_or_path=self.wrist_index, width=640, height=480, fps=30, fourcc="MJPG"
                ),
            }
