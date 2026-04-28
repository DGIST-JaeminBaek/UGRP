from dataclasses import dataclass, field

from lerobot.cameras import CameraConfig
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
    # Camera configs — OpenCV (index 기반) 또는 RealSense (시리얼 번호 기반) 중 선택
    # RealSense 예시:
    #   "top": RealSenseCameraConfig(serial_number_or_name="123456789", fps=30, width=640, height=480)
    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "top": OpenCVCameraConfig(
                index_or_path=0, width=640, height=480, fps=30, fourcc="MJPG"
            ),
            "wrist": OpenCVCameraConfig(
                index_or_path=4, width=640, height=480, fps=30, fourcc="MJPG"
            ),
        }
    )
    enable_timeout: float = 5.0
