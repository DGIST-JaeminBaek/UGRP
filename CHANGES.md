# 변경 이력

원본 `lerobot_robot_piper` (agilexrobotics)에서 현재 버전까지의 모든 변경 사항.

---

## [현재] — 2026-04-28

### `piper_real_time_inference.py` — 전면 재작성

**버그: `make_policy(cfg=None)` — 잘못된 API 사용**
- 기존: `make_policy(cfg=None, ds_meta=ds_meta)` 후 인스턴스에서 `policy.from_pretrained(path)` 호출 → 항상 크래시
- 수정: `PreTrainedConfig.from_pretrained(path)`로 체크포인트에서 config 로드, `pretrained_path` 설정 후 `make_policy(cfg=policy_cfg, ds_meta=ds_meta)` 호출
- 메타데이터용으로 `LeRobotDataset` 전체 로드 대신 `LeRobotDatasetMetadata(repo_id)` 직접 사용으로 변경

**버그: 이중 CAN 연결**
- 기존: 같은 CAN 인터페이스에 `init_robot(can0)` (V1 SDK, `C_PiperInterface`)와 `robot.connect()` (V2 SDK, `C_PiperInterface_V2`)를 동시에 연결
- 수정: 추론 스크립트에서 V1 SDK 완전 제거. `Piper` (V2 SDK) 하나만 사용

**버그: `create_batch`에서 중복 데이터 소스**
- 기존: V1 SDK(`read_end_pose_msg(piper_sdk)`)에서 EEF 상태, V2 SDK(`robot.get_observation()`)에서 카메라를 따로 읽음
- 수정: `create_batch(robot, task)` — `robot.get_observation()` 한 번 호출로 상태와 카메라 모두 처리

**버그: `PiperConfig` cameras에 plain dict 전달**
- 기존: `PiperConfig(cameras={"top": {"index_or_path": 0, ...}})` — plain dict는 타입 검증 실패
- 수정: `OpenCVCameraConfig(index_or_path=0, ...)` 객체로 올바르게 전달

**버그: 데몬 스레드 `keyboard_interrupt_handler` 무의미**
- 기존: 데몬 스레드에서 `KeyboardInterrupt`를 잡으려 했으나, Python은 메인 스레드에서만 이 예외를 발생시킴 — 스레드는 아무 역할도 못함
- 수정: 스레드 완전 제거. 메인 루프의 `except KeyboardInterrupt`로 Ctrl+C 처리

**버그: V1 SDK의 `ctrl_end_pose` / `set_zero_configuration` 사용**
- 기존: 추론 루프에서 `ctrl_end_pose(piper_sdk, ...)`, `set_zero_configuration(piper_sdk)` — V1 SDK 의존
- 수정: `robot.send_action(action_dict)` (V2 SDK)으로 제어, 영점 이동은 새로 추가한 `robot._iface.zero_configuration()` 사용

---

### `piper_sdk_interface.py` — `zero_configuration()` 추가

- `zero_configuration(wait=5.0)` 메서드 추가: 관절 제어 모드 전환 → 전체 관절 0도 → 그리퍼 닫기 → 감속 대기
- LoRA-SP의 `set_zero_configuration()`과 동일한 로직을 V2 SDK(`C_PiperInterface_V2`)로 포팅

---

## [이전 세션]

### 패키지 구조 재편

- `robot_utils.py`, `piper_real_time_inference.py`를 리포 루트에서 `lerobot_robot_piper/` 패키지 내부로 이동
- 상대 임포트 수정 (`from .piper import Piper` 등)
- `setup.cfg`에 `editable_mode = compat` 추가 — `pkgutil.iter_modules()` 플러그인 탐색을 위해 필요

### `config_piper.py` — EEF 파이프라인에 맞게 단순화

- 제거: `joint_names`, `joint_signs`, `joint_aliases`, `use_degrees`, `bitrate`
- 추가: `control_mode` ("teleop" | "user") — `send_action`을 no-op으로 할지 여부 제어
- 추가: `gripper_effort` (int, 기본값 100) — LoRA-SP의 `GRIPPER_EFFORT = 100`과 동일
- 카메라 기본값 변경: 두 개 카메라 (`top` 인덱스 0, `wrist` 인덱스 4)

### `piper.py` — 액션 공간을 엔드이펙터 좌표로 전환

- 관절 위치 파이프라인 제거 (`get_status_deg`, `set_joint_positions_deg`, 부호/별칭/범위 변환 로직 전부)
- `EEF_NAMES = ["x", "y", "z", "rx", "ry", "rz"]` 추가
- `observation_features` / `action_features`를 EEF 키(`x.pos`, `y.pos`, ..., `gripper.pos`)로 변경
- `get_observation()`이 `get_end_pose_raw()` 호출 — raw SDK 정수(0.001 mm / 0.001 도 단위) 반환
- `send_action()`: slave 모드일 때 no-op early return — CAN 마스터-슬레이브 sync와 충돌 방지
- `_instances` 클래스 레지스트리 추가 — `PiperSlaveOnly.get_action()`이 활성 로봇 인스턴스에 접근할 수 있도록

### `piper_sdk_interface.py` — 안전성 개선 및 EEF 메서드 추가

- 제거: init 시 `MotionCtrl_2(0x01, 0x01, 100, 0x00)` 강제 호출 (슬레이브 녹화 중 제어 모드 리셋 문제)
- 제거: init 시 `EmergencyStop(0x02)` 블록 (활성 CAN 슬레이브 sync 중단 문제)
- 추가: `get_end_pose_raw()` — EEF 포즈를 raw SDK 정수로 읽음, LoRA-SP의 `read_end_pose_msg` 필드 순서와 일치
- 추가: `ctrl_end_pose()` — 엔드포즈 제어 모드 설정 후 EEF 명령 전송, LoRA-SP의 `ctrl_end_pose`와 동일 구조

### `piper_slave_only.py` — 신규 추가

- Piper-to-Piper 마스터-슬레이브 녹화용 더미 텔레오퍼레이터
- `@TeleoperatorConfig.register_subclass("piper_slave_only")` — LeRobot CLI 플러그인 탐색 등록
- `get_action()`: `_instances` 레지스트리를 통해 활성 `Piper` 인스턴스에서 현재 EEF 상태 읽기
- CAN sync는 하드웨어가 전담, 이 텔레오퍼레이터는 LeRobot record 루프를 위한 패스스루

### `__init__.py` — 익스포트 업데이트

- `PiperSlaveOnly`, `PiperSlaveOnlyConfig`, `robot_utils` 함수들 추가

### `setup.py` — CLI 엔트리 포인트 추가

- `piper-inference = lerobot_robot_piper.piper_real_time_inference:main`
