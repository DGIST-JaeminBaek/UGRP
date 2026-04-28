"""
Piper Slave-Only Dummy Teleoperator

Piper-to-Piper 마스터-슬레이브 녹화용.
Piper SDK가 CAN에서 자동 동기화하므로,
LeRobot은 단순히 데이터만 수집하면 됨.

이 Dummy Teleop은 lerobot-record의 teleop 요구사항만 충족.
"""

from typing import Any
from lerobot.teleoperators.teleoperator import Teleoperator
from dataclasses import dataclass
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("piper_slave_only")
@dataclass
class PiperSlaveOnlyConfig(TeleoperatorConfig):
    """Slave-only dummy teleop config (Piper SDK가 master-slave 처리)"""
    pass


class PiperSlaveOnly(Teleoperator):
    """
    Slave 모드에서는 Piper SDK가 CAN을 통해 자동으로 master-slave 동기화.
    LeRobot은 데이터 수집만 하면 되므로, 이 Teleop은 아무 작업도 안 함.

    Usage:
        lerobot-record \\
            --robot.type=piper \\
            --robot.control_mode=teleop \\
            --teleop.type=piper_slave_only \\
            --dataset.repo_id=local/piper-demo
    """

    config_class = PiperSlaveOnlyConfig
    name = "piper_slave_only"

    def __init__(self, config: PiperSlaveOnlyConfig):
        super().__init__(config)
        self.config = config

    @property
    def action_features(self) -> dict[str, type]:
        # 빈 dict - action을 생성하지 않음
        return {}

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return True  # 항상 연결된 상태 (실제 연결 불필요)

    def connect(self, calibrate: bool = True) -> None:
        # 아무것도 안 함
        pass

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def get_action(self) -> dict[str, Any]:
        from .piper import Piper
        for robot in Piper._instances.values():
            # Reuse the observation the record loop already captured this frame.
            # Avoids a second round-trip to the SDK (duplicate EEF read per frame).
            obs = robot._last_obs
            if obs is None:
                try:
                    obs = robot.get_observation()
                except Exception:
                    break
            return {k: v for k, v in obs.items() if k in robot.action_features}
        return {}

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    def disconnect(self) -> None:
        pass
