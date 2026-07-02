# Piper SDK interface for LeRobot integration

import time
import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    from piper_sdk import C_PiperInterface_V2
except Exception:
    C_PiperInterface_V2 = None
    log.debug("piper_sdk not available at import time; use `pip install piper_sdk` if you need hardware access")


class PiperSDKInterface:
    def __init__(self, port: str = "can0", enable_timeout: float = 5.0, skip_enable: bool = False):
        if C_PiperInterface_V2 is None:
            raise ImportError("piper_sdk is not installed. Install with `pip install piper_sdk`.")
        try:
            self.piper = C_PiperInterface_V2(port)
        except Exception as e:
            log.error("Failed to initialize Piper SDK: %s. Did you activate the CAN interface?", e)
            self.piper = None
            raise RuntimeError("Failed to initialize Piper SDK") from e

        try:
            self.piper.ConnectPort()
        except Exception as e:
            log.error("ConnectPort failed: %s", e)
            raise

        # Wait for valid EEF data before proceeding — SDK returns all-zeros until the
        # first CAN frame arrives. 2s is enough for a healthy CAN bus; log a warning if
        # we time out (arm may physically be at origin, or CAN is slow).
        _data_timeout = 2.0
        _start = time.time()
        while time.time() - _start < _data_timeout:
            try:
                ep = self.piper.GetArmEndPoseMsgs().end_pose
                if ep.X_axis != 0 or ep.Y_axis != 0 or ep.Z_axis != 0:
                    break
            except Exception:
                pass
            time.sleep(0.05)
        else:
            log.warning("EEF data still zero after %.1fs — arm may be at physical origin or CAN is slow", _data_timeout)

        # Log arm status for debugging only — do not send any commands here.
        # In slave mode the arm is actively following the master via CAN;
        # sending EmergencyStop/resume would interrupt that sync.
        try:
            status = self.piper.GetArmStatus().arm_status
            log.debug("Initial arm motion_status=%s ctrl_mode=%s", getattr(status, "motion_status", None), getattr(status, "ctrl_mode", None))
        except Exception as e:
            log.debug("Unable to read arm status: %s", e)

        # In slave mode (recording) the arm is already enabled by the CAN master;
        # calling EnablePiper() again is harmless but can cause a long wait or fail
        # if the arm is in teaching mode. Skip it when the caller says so.
        if not skip_enable:
            start = time.time()
            while True:
                try:
                    ok = self.piper.EnablePiper()
                except Exception:
                    ok = False
                if ok:
                    break
                if time.time() - start > enable_timeout:
                    raise TimeoutError(f"EnablePiper timed out after {enable_timeout} seconds")
                time.sleep(0.01)
        else:
            log.debug("Skipping EnablePiper (slave mode)")

        # Do NOT force MotionCtrl_2 here.
        # In slave mode (recording), the CAN master-slave sync is already active and
        # calling MotionCtrl_2 would reset the control mode and cause unwanted movement.
        # Callers should set the mode explicitly when needed (e.g. before inference).

        # Cache joint angle limits and keep a conservative placeholder range for the
        # gripper helper path below. Replay/inference uses raw SDK gripper units directly.
        try:
            angel_status = self.piper.GetAllMotorAngleLimitMaxSpd()
            # SDK motor list appears 1-indexed -> extract 1..6
            # Angle limits are in deci-degrees (0.1 deg). Convert to degrees for consistency.
            self.min_pos = [pos.min_angle_limit / 10.0 for pos in angel_status.all_motor_angle_limit_max_spd.motor[1:7]] + [0.0]
            self.max_pos = [pos.max_angle_limit / 10.0 for pos in angel_status.all_motor_angle_limit_max_spd.motor[1:7]] + [10.0]
        except Exception as e:
            log.warning("Could not read joint limits: %s", e)
            # sensible defaults to avoid crashes; keep lists length >=7
            self.min_pos = [-180.0] * 6 + [0.0]
            self.max_pos = [180.0] * 6 + [10.0]

    def set_joint_positions(self, positions):
        """
        positions: list of 7 floats.
        The first 6 values are joint percentages in [-100, 100].
        The 7th value is a gripper percentage in [0, 100] used only by this helper path.
        Replay/inference paths do not use this helper; they pass signed raw SDK gripper
        stroke values directly to `GripperCtrl`.
        """
        if not isinstance(positions, (list, tuple)) or len(positions) < 7:
            raise ValueError("positions must be a sequence of length >=7")

        # clamp and map percent [-100,100] -> angle between min_pos and max_pos
        scaled_angles = []
        for i in range(6):
            p = positions[i]
            try:
                p = float(p)
            except Exception:
                p = 0.0
            p = max(-100.0, min(100.0, p))
            minv = self.min_pos[i]
            maxv = self.max_pos[i]
            angle = minv + (p + 100.0) / 200.0 * (maxv - minv)
            scaled_angles.append(int(round(angle * 1000.0)))  # SDK expects int thousandths

        # gripper percent 0..100 -> mm
        g = positions[6]
        try:
            g = float(g)
        except Exception:
            g = 0.0
        g = max(0.0, min(100.0, g))
        g_mm = self.min_pos[6] + (self.max_pos[6] - self.min_pos[6]) * (g / 100.0)
        g_int = int(round(g_mm * 10000.0))

        # send to SDK
        try:
            self.piper.JointCtrl(*scaled_angles)
            self.piper.GripperCtrl(g_int, 1000, 0x01, 0)
        except Exception as e:
            log.exception("Failed to send joint/gripper via JointCtrl/GripperCtrl: %s", e)
            raise

    # --- LeRobot-friendly helpers (degrees/mm) ---
    def get_status_deg(self) -> dict[str, float]:
        """Return joints in degrees and gripper in mm."""
        js = self.piper.GetArmJointMsgs().joint_state
        g = self.piper.GetArmGripperMsgs()
        out = {
            "joint_1.pos": js.joint_1 / 1000.0,
            "joint_2.pos": js.joint_2 / 1000.0,
            "joint_3.pos": js.joint_3 / 1000.0,
            "joint_4.pos": js.joint_4 / 1000.0,
            "joint_5.pos": js.joint_5 / 1000.0,
            "joint_6.pos": js.joint_6 / 1000.0,
        }
        # Convert gripper back from SDK unit to mm (SDK used *10000 when sending)
        try:
            out["gripper.pos"] = g.gripper_state.grippers_angle / 10000.0
        except Exception:
            pass
        return out

    def set_joint_positions_deg(self, joints_deg: list[float], gripper_mm: float | None = None) -> None:
        """Send joints in degrees and optional gripper in mm."""
        j_ints = [int(round(d * 1000.0)) for d in joints_deg]
        try:
            self.piper.JointCtrl(*j_ints)
            if gripper_mm is not None:
                self.piper.GripperCtrl(int(round(gripper_mm * 10000.0)), 1000, 0x01, 0)
        except Exception as e:
            log.exception("set_joint_positions_deg failed: %s", e)
            raise

    def get_status(self) -> dict[str, Any]:
        joint_status = self.piper.GetArmJointMsgs()
        gripper = self.piper.GetArmGripperMsgs()

        joint_state = joint_status.joint_state
        obs_dict = {
            "joint_0.pos": joint_state.joint_1,
            "joint_1.pos": joint_state.joint_2,
            "joint_2.pos": joint_state.joint_3,
            "joint_3.pos": joint_state.joint_4,
            "joint_4.pos": joint_state.joint_5,
            "joint_5.pos": joint_state.joint_6,
        }
        obs_dict.update(
            {
                "joint_6.pos": gripper.gripper_state.grippers_angle,
            }
        )

        return obs_dict

    def get_end_pose_raw(self) -> dict[str, int]:
        """Return end-effector pose + gripper as raw SDK integers.

        Units: position = 0.001 mm, rotation = 0.001 degree, gripper = SDK raw.
        Matches LoRA-SP's read_end_pose_msg() field order: x, y, z, rx, ry, rz, gripper.
        """
        end_pose = self.piper.GetArmEndPoseMsgs().end_pose
        gripper = self.piper.GetArmGripperMsgs().gripper_state
        return {
            "x": end_pose.X_axis,
            "y": end_pose.Y_axis,
            "z": end_pose.Z_axis,
            "rx": end_pose.RX_axis,
            "ry": end_pose.RY_axis,
            "rz": end_pose.RZ_axis,
            "gripper": gripper.grippers_angle,
        }

    def ctrl_end_pose(
        self,
        eef_data: list[int],
        gripper_angle: int | None = None,
        gripper_effort: int = 100,
    ) -> None:
        """Send end-effector pose command with optional gripper.

        Mirrors LoRA-SP's ctrl_end_pose():
          MotionCtrl_2(0x01, 0x00, ...) → end-pose mode
          EndPoseCtrl(*eef_data)
          GripperCtrl(angle, effort, 0x01, 0)
        """
        self.piper.MotionCtrl_2(0x01, 0x00, 20, 0x00)
        self.piper.EndPoseCtrl(*[int(v) for v in eef_data])
        if gripper_angle is not None:
            self.piper.GripperCtrl(int(gripper_angle), gripper_effort, 0x01, 0)

    def zero_configuration(self, wait: float = 5.0) -> None:
        """Move all joints to zero and close gripper. Blocks for `wait` seconds."""
        self.piper.MotionCtrl_2(0x01, 0x01, 20, 0x00)
        self.piper.JointCtrl(0, 0, 0, 0, 0, 0)
        self.piper.GripperCtrl(0, 0, 0x01, 0)
        self.piper.MotionCtrl_2(0x01, 0x01, 20, 0x00)
        time.sleep(wait)

    def disconnect(self):
        try:
            self.piper.JointCtrl(0, 0, 0, 0, 25000, 0)
        except Exception:
            log.debug("Disconnect: JointCtrl cleanup failed or piper already disconnected")
