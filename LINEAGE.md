# 코드 출처

이 패키지가 각 업스트림 소스에서 무엇을 가져왔고 어떻게 발전시켰는지 정리한 문서.

## 소스

| 소스 | 위치 | 역할 |
|------|------|------|
| `lerobot_robot_piper` (agilexrobotics) | `c:/UGRP/repos/lerobot_robot_piper` | 원본 LeRobot 플러그인 — 패키지 뼈대 제공 |
| `LoRA-SP` (KAIST) | `c:/UGRP/repos/LoRA-SP` | 연구 코드베이스 — 엔드이펙터 설계 및 추론 패턴 제공 |

---

## 원본 `lerobot_robot_piper`에서 가져온 것

### 그대로 유지

| 파일 | 유지한 내용 |
|------|------------|
| `piper_sdk_interface.py` | `PiperSDKInterface.__init__` 구조: `C_PiperInterface_V2`, `ConnectPort`, `EnablePiper` 타임아웃 루프, `GetAllMotorAngleLimitMaxSpd`로 관절 범위 읽기 |
| `piper_sdk_interface.py` | `get_status_deg()`, `set_joint_positions_deg()`, `set_joint_positions()` — 추론 파이프라인에서는 더 이상 사용하지 않으나 하위 호환성을 위해 보존 |
| `piper_sdk_interface.py` | `disconnect()` |
| `piper.py` | 클래스 뼈대: `config_class`, `name`, `__init__`, `is_connected`, `_cameras_ft`, `connect`, `disconnect`, `is_calibrated`, `calibrate`, `configure` |
| `config_piper.py` | `@RobotConfig.register_subclass("piper")` 데코레이터 패턴, `can_interface`, `enable_timeout`, `OpenCVCameraConfig` 기반 `cameras` 필드 |
| `setup.py` | 패키지 구조, `find_packages`, `install_requires` |

### 크게 수정한 것

**`config_piper.py`**
- 제거: `bitrate`, `joint_names`, `joint_signs`, `joint_aliases`, `use_degrees`
- 추가: `control_mode` — `send_action`이 no-op(`"teleop"`)인지 직접 제어(`"user"`)인지 결정
- 추가: `gripper_effort` — LoRA-SP의 `GRIPPER_EFFORT = 100`과 일치하는 그리퍼 힘 상수

**`piper.py`**
- 관절 위치 액션 공간을 엔드이펙터 좌표로 전면 교체 (아래 LoRA-SP 항목 참고)
- 제거: `_motors_ft`, `_apply_signs`, `_get_hw_limits`, `_get_oriented_limits`, 퍼센트/도 단위 변환 로직 전부
- 추가: `EEF_NAMES`, `_instances` 클래스 레지스트리, slave 모드 no-op

**`piper_sdk_interface.py`**
- 제거: init 시 `EmergencyStop` 블록 (활성 슬레이브 팔 방해)
- 제거: init 시 `MotionCtrl_2` 강제 호출 (제어 모드 리셋)
- 추가: `get_end_pose_raw()`, `ctrl_end_pose()`, `zero_configuration()` (LoRA-SP 패턴 포팅 — 아래 참고)

---

## LoRA-SP (`common/robot_devices/robot_utils.py`)에서 가져온 것

LoRA-SP는 엔드이펙터 좌표를 로봇 상태/액션 표현으로 사용한다. 이 패키지에 채택한 핵심 설계 결정이다.

### 직접 포팅 (V2 SDK로 변환)

| LoRA-SP 원본 | 우리 구현 | 위치 | 비고 |
|-------------|-----------|------|------|
| `read_end_pose_msg(piper)` | `PiperSDKInterface.get_end_pose_raw()` | `piper_sdk_interface.py:115` | 동일한 SDK 호출, 텐서 대신 dict 반환, 그리퍼 포함 |
| `ctrl_end_pose(piper, end_pose_data, gripper_data)` | `PiperSDKInterface.ctrl_end_pose()` | `piper_sdk_interface.py:184` | 동일한 `MotionCtrl_2 → EndPoseCtrl → GripperCtrl` 순서 |
| `set_zero_configuration(piper)` | `PiperSDKInterface.zero_configuration()` | `piper_sdk_interface.py:202` | 동일한 4개 명령 + `time.sleep(5)`, V2 SDK로 포팅 |
| `read_end_pose_msg`, `read_joint_msg` 함수 시그니처 | `robot_utils.py` (패키지 내 복사본) | `lerobot_robot_piper/robot_utils.py` | 거의 그대로 복사, V1 SDK 사용, 호환성을 위해 유지 |

### 채택한 설계 방식

| LoRA-SP 개념 | 우리 구현 |
|-------------|----------|
| EEF 상태: `[X, Y, Z, RX, RY, RZ, gripper]` raw SDK 정수 | `EEF_NAMES`, `get_end_pose_raw()`, `observation_features` / `action_features` |
| `GRIPPER_EFFORT = 100` 상수 | `PiperConfig.gripper_effort = 100` |
| `create_batch(piper, cam, ...)` → 정책 입력 관찰 dict | `piper_real_time_inference.py`의 `create_batch(robot, task)` |
| 추론 루프: 관찰 → 전처리 → GPU → 후처리 → `ctrl_end_pose` | `piper_real_time_inference.py` 추론 루프 |
| 추론 전후 `set_zero_configuration`으로 안전 초기화 | 시작 시 및 `finally` 블록에서 `robot._iface.zero_configuration()` 호출 |

### LoRA-SP에 있지만 이 패키지에 포함하지 않은 것

| LoRA-SP 기능 | 미포함 이유 |
|-------------|------------|
| 시간적 앙상블 (슬라이딩 버퍼) | 기본 추론은 없어도 동작, 향후 개선 사항으로 남김 |
| LoRA-MSP / LoRA-MoE 어댑터 래핑 (`wrap_policy`) | LoRA-SP 전용, 표준 LeRobot 정책 API와 무관 |
| RealSense 커스텀 스레딩 클래스 (`cam_utils.py`) | LeRobot 내장 `RealSenseCameraConfig` 사용 — 시리얼 번호 기반, 별도 스레딩 코드 불필요 |
| 멀티태스크 키보드 리스너 (`init_keyboard_listener`) | `except KeyboardInterrupt` 단순 처리로 대체 |
| 궤적 시각화 (`plot_trajectory`, `pretty_plot`) | 디버깅 도구, 범위 밖 |

---

## 이 프로젝트에서 새로 추가한 것 (양쪽 업스트림 모두에 없음)

| 파일 | 추가 내용 | 목적 |
|------|----------|------|
| `piper_slave_only.py` | `PiperSlaveOnly` + `PiperSlaveOnlyConfig` | CAN 하드웨어가 마스터-슬레이브 sync를 담당할 때 LeRobot `record` 루프를 위한 더미 텔레오퍼레이터 — 두 업스트림 모두에 없음 |
| `piper.py` | `_instances` 클래스 레지스트리 | `PiperSlaveOnly.get_action()`이 직접 참조 없이 활성 `Piper` 인스턴스의 실시간 상태를 읽을 수 있도록 |
| `setup.cfg` | `editable_mode = compat` | editable 설치에서 `pkgutil.iter_modules()` 플러그인 탐색에 필요 |
| `setup.py` | `piper-inference` 엔트리 포인트 | 추론 스크립트를 위한 CLI 단축 명령 |

---

## 데이터 단위 규약 (학습/추론 일관성의 핵심)

`get_end_pose_raw()`와 LoRA-SP의 `read_end_pose_msg()` 모두 `GetArmEndPoseMsgs()`에서 raw SDK 정수를 그대로 반환한다:

- 위치축 (X, Y, Z): 단위 = **0.001 mm** (예: 150 mm → 값 150000)
- 회전축 (RX, RY, RZ): 단위 = **0.001 도**
- 그리퍼: `grippers_angle` raw SDK 정수

데이터셋이 이 raw 정수를 저장하고, 정책이 이 범위를 학습하며, postprocessor가 역정규화 후 동일 범위로 복원한다. `EndPoseCtrl`이 그대로 받으므로 **어디에도 `* 1000` 변환은 필요 없다.**
