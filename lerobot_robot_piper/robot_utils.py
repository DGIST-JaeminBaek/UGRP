"""
Low-level Piper SDK control utilities for real-time inference.

This module provides safe, well-tested Piper robot control functions
adapted from LoRA-SP's eval_real_time.py patterns.
"""

import time
import torch
from piper_sdk import C_PiperInterface

# Constants
GRIPPER_EFFORT = 100  # Default gripper effort
GRIPPER_MAX_ANGLE = 60000  # Maximum gripper angle in units


def init_robot(can_interface: str = "can0") -> C_PiperInterface:
    """
    Initialize and connect to Piper robot via CAN interface.

    Args:
        can_interface: CAN interface name (e.g., "can0", "can1")

    Returns:
        Connected PiperInterface instance

    Raises:
        RuntimeError: If connection fails or robot is not responsive
    """
    piper = C_PiperInterface(can_interface)
    piper.ConnectPort()
    piper.EnableArm(7)

    # Set initial motion control mode
    piper.MotionCtrl_2(0x01, 0x01, 20, 0x00)

    return piper


def read_end_pose_msg(piper: C_PiperInterface) -> torch.Tensor:
    """
    Read current end-effector pose and gripper state.

    Returns tensor of shape (1, 7):
    [x, y, z, rx, ry, rz, gripper_angle]

    Args:
        piper: PiperInterface instance

    Returns:
        Tensor with end-effector pose + gripper state (batch format)
    """
    end_pose = piper.GetArmEndPoseMsgs().end_pose
    gripper_state = piper.GetArmGripperMsgs().gripper_state

    end_pose_data = torch.tensor(
        [
            end_pose.X_axis,
            end_pose.Y_axis,
            end_pose.Z_axis,
            end_pose.RX_axis,
            end_pose.RY_axis,
            end_pose.RZ_axis,
            gripper_state.grippers_angle,
        ],
        dtype=torch.float32,
    )

    return end_pose_data.unsqueeze(0)  # Add batch dimension


def read_joint_msg(piper: C_PiperInterface) -> torch.Tensor:
    """
    Read current joint positions and gripper state.

    Returns tensor of shape (1, 7):
    [joint_1, joint_2, joint_3, joint_4, joint_5, joint_6, gripper_angle]

    Args:
        piper: PiperInterface instance

    Returns:
        Tensor with joint positions + gripper state (batch format)
    """
    joint_state = piper.GetArmJointMsgs().joint_state
    gripper_state = piper.GetArmGripperMsgs().gripper_state

    joint_data = torch.tensor(
        [
            joint_state.joint_1,
            joint_state.joint_2,
            joint_state.joint_3,
            joint_state.joint_4,
            joint_state.joint_5,
            joint_state.joint_6,
            gripper_state.grippers_angle,
        ],
        dtype=torch.float32,
    )

    return joint_data.unsqueeze(0)  # Add batch dimension


def set_zero_configuration(piper: C_PiperInterface) -> None:
    """
    Safely initialize robot to zero configuration.

    This function:
    1. Enables joint control mode
    2. Zeros all joints
    3. Closes gripper
    4. Re-enables motion control
    5. Waits 5 seconds for mechanical deceleration

    CRITICAL: The 5-second sleep is intentional to ensure safe mechanical halt.

    Args:
        piper: PiperInterface instance
    """
    # Enable joint control mode
    piper.MotionCtrl_2(0x01, 0x01, 20, 0x00)

    # Zero all joints
    piper.JointCtrl(0, 0, 0, 0, 0, 0)

    # Close gripper
    piper.GripperCtrl(0, 0, 0x01, 0)

    # Re-enable motion control
    piper.MotionCtrl_2(0x01, 0x01, 20, 0x00)

    # CRITICAL: Wait for mechanical deceleration
    time.sleep(5)


def ctrl_end_pose(
    piper: C_PiperInterface,
    end_pose_data: list | torch.Tensor,
    gripper_data: list | torch.Tensor,
) -> None:
    """
    Control robot end-effector to target pose with gripper command.

    Args:
        piper: PiperInterface instance
        end_pose_data: [x, y, z, rx, ry, rz] (6 DOF)
        gripper_data: [gripper_angle, gripper_effort] (2 values)

    Raises:
        ValueError: If data shapes are incorrect
    """
    if isinstance(end_pose_data, torch.Tensor):
        end_pose_data = end_pose_data.cpu().tolist()
    if isinstance(gripper_data, torch.Tensor):
        gripper_data = gripper_data.cpu().tolist()

    # Validate input shapes
    if len(end_pose_data) != 6:
        raise ValueError(f"Expected 6 DOF, got {len(end_pose_data)}")
    if len(gripper_data) != 2:
        raise ValueError(f"Expected 2 gripper values, got {len(gripper_data)}")

    gripper_angle, gripper_effort = gripper_data

    # Switch to end-pose control mode
    piper.MotionCtrl_2(0x01, 0x00, 20, 0x00)

    # Send end-effector pose command
    piper.EndPoseCtrl(*end_pose_data)

    # Send gripper command (use absolute value of angle)
    piper.GripperCtrl(int(abs(gripper_angle)), int(gripper_effort), 0x01, 0)
