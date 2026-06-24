# 실험 런북

이 문서는 앞으로 실제 하드웨어에서 실행할 실험 절차와 안전 체크리스트를 관리한다.
완료된 과거 실험 기록은 [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md)에 보존한다.

현재 기준선: 2026-06-12 UGRP 중간보고서, [CHANGES.md](CHANGES.md), [ROADMAP.md](ROADMAP.md).

---

## 현재 상태 요약

### 완료된 검증

- PiPER Master-Slave teleoperation 환경 구축 및 상태값 수신 정상화
- LeRobot record 구조를 PiPER CAN direct teleoperation에 맞게 재구성
- joint-space 기반 기록/제어를 end-effector absolute 좌표 기반으로 전환
- 카메라 없는 EEF-only 녹화 및 top/wrist RealSense 포함 녹화 확인
- `PiperSlaveOnly` teleoperator와 `send_action()` no-op 동작 확인
- SmolVLA 기반 녹화, fine-tuning, 실제 PiPER 50 step 추론 검증

### 아직 해야 할 핵심 실험

- 저장된 EEF state/action과 비전 데이터의 재현성 검증
- 데이터셋별 EEF/action 안전 범위 자동 산출
- 충분한 episode 수집 후 SmolVLA 작업 성공률 평가
- 연구실 GPU 서버와 로봇 PC를 분리한 async inference 검증
- async 환경에서 pi0 등 대형 VLA 모델 비교 실험

---

## 위험 시나리오

### 위험 A: EEF 데이터 all-zero

`ConnectPort()` 후 CAN 첫 프레임이 오기 전에 `get_end_pose_raw()`가 전부 0을 반환할 수 있다.
이 상태로 추론을 시작하면 정책이 현재 위치를 로봇 베이스 내부 좌표로 오인할 수 있다.

대응:

- 추론 전 `get_end_pose_raw()` 출력이 non-zero인지 확인한다.
- 로그에 `EEF data still zero after 2.0s` warning이 있으면 실제 arm에 명령을 보내지 않는다.

### 위험 B: action scale 오류

postprocessor 역정규화 오류, dataset stats mismatch, clamp 범위 오류가 있으면 arm이 한 step에 크게 움직일 수 있다.

참고 정상 범위:

| 축 | raw SDK 정수 범위 |
|----|-------------------|
| X | 100000 ~ 400000 |
| Y | -200000 ~ 200000 |
| Z | 50000 ~ 350000 |
| RX/RY/RZ | -180000 ~ 180000 |
| gripper | 0 ~ 70000 |

대응:

- 실제 arm 연결 전 `--use_devices=false` 시뮬레이션에서 action 값을 확인한다.
- 새 데이터셋을 사용할 때 `smolvla_inference.py`의 `ACTION_MIN` / `ACTION_MAX`를 재계산한다.
- 범위를 크게 벗어나면 실제 arm에 연결하지 않는다.

### 위험 C: zero_configuration 충돌

`zero_configuration()`은 현재 위치에서 전 관절 0도 위치로 이동한다. 중간 경로가 넓은 호를 그릴 수 있다.

대응:

- 실행 전 arm 주변 50 cm 안에 사람이나 물체가 없는지 확인한다.
- 예상과 다른 움직임이 보이면 즉시 `Ctrl+C`를 누른다.
- 멈추지 않으면 `sudo ip link set can0 down`을 실행한다.

### 위험 D: teleop 중 send_action 명령 전송

teleop 녹화 중 `send_action()`이 실제 `EndPoseCtrl()`을 보내면 CAN Master-Slave sync와 충돌할 수 있다.

대응:

- 녹화 전 `control_mode=teleop`에서 `send_action()`이 no-op인지 확인한다.
- `send_action returned: True`, `obs == action: True`를 확인한 뒤 녹화한다.

---

## 공통 안전 수칙

모든 실제 arm 실험에 적용한다.

1. 터미널에서 즉시 `Ctrl+C`를 누를 수 있게 한다.
2. arm 주변 50 cm 이내를 비운다.
3. 새 코드, 새 모델, 새 데이터셋은 항상 시뮬레이션 또는 작은 `max_steps`부터 시작한다.
4. 비상 시 CAN을 내린다.

```bash
sudo ip link set can0 down
```

5. 실제 추론은 `max_steps=5`에서 시작하고, 안정적일 때만 늘린다.

---

## 개발 PC 확인

하드웨어가 없는 개발 PC에서 코드 import와 플러그인 등록만 확인한다.

```bash
python -c "import lerobot_robot_piper; print('OK')"
```

```bash
python -c "
from lerobot_robot_piper.config_piper import PiperConfig
from lerobot_robot_piper.piper_slave_only import PiperSlaveOnly, PiperSlaveOnlyConfig
cfg = PiperConfig()
print('robot plugin OK:', cfg.control_mode)
t = PiperSlaveOnly(PiperSlaveOnlyConfig())
print('teleop plugin OK')
"
```

```bash
python -c "
from lerobot_robot_piper.config_piper import PiperConfig
cfg = PiperConfig()
assert cfg.control_mode == 'teleop', cfg.control_mode
assert cfg.include_gripper is True
print('config defaults OK:', list(cfg.cameras.keys()))
"
```

---

## 실험 PC 기본 점검

실제 PiPER 실험 전 매번 확인한다.

### CAN 활성화

```bash
sudo ip link set can0 up type can bitrate 1000000
ip link show can0
```

### SDK 연결 및 EEF non-zero 확인

```bash
python -c "
from lerobot_robot_piper.piper_sdk_interface import PiperSDKInterface
import logging; logging.basicConfig(level=logging.INFO)
iface = PiperSDKInterface(port='can0', skip_enable=False)
data = iface.get_end_pose_raw()
print(data)
assert any(v != 0 for v in data.values()), 'EEF all-zero: CAN 수신 문제'
print('EEF non-zero OK')
"
```

### teleop no-op 재확인

녹화 전, 특히 코드 수정 후 반드시 확인한다.

```bash
python -c "
from lerobot_robot_piper.config_piper import PiperConfig
from lerobot_robot_piper.piper import Piper
from lerobot_robot_piper.piper_slave_only import PiperSlaveOnly, PiperSlaveOnlyConfig

robot = Piper(PiperConfig(can_interface='can0', control_mode='teleop'))
robot.connect()
teleop = PiperSlaveOnly(PiperSlaveOnlyConfig())
obs = robot.get_observation()
action = teleop.get_action()
returned = robot.send_action(action)
print('send_action returned:', returned == action)
eef_keys = [k for k in obs if 'pos' in k]
print('obs == action:', all(obs[k] == action[k] for k in eef_keys))
robot.disconnect()
"
```

통과 기준:

- `send_action returned: True`
- `obs == action: True`

---

## 카메라 점검

### RealSense 시리얼 확인

```bash
python -c "
import pyrealsense2 as rs
ctx = rs.context()
for i, d in enumerate(ctx.devices):
    name = d.get_info(rs.camera_info.name)
    serial = d.get_info(rs.camera_info.serial_number)
    print(f'[{i}] {name} serial={serial}')
"
```

현재 실험실 기록:

| 위치 | 시리얼 |
|------|--------|
| top | `327122074262` |
| wrist | `243322071626` |

### OpenCV 인덱스 확인

```bash
python -c "
import cv2
for idx in range(8):
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        ret, frame = cap.read()
        print(f'index {idx}: OK shape={frame.shape if ret else \"read failed\"}')
        cap.release()
"
```

---

## 현재 우선 실험 1: 데이터셋 재현성 검증

목표: 저장된 EEF state/action과 비전 frame이 실제 물리 궤적을 일관되게 반영하는지 확인한다.

### 1-1. parquet 기본 검사

```bash
python -c "
import pathlib
import pandas as pd

root = pathlib.Path('/home/ugrp308/Group43/datasets/piper-test')
paths = sorted(root.glob('data/**/*.parquet'))
assert paths, f'parquet 없음: {root}'
for p in paths:
    df = pd.read_parquet(p)
    print('\\n', p)
    print('rows:', len(df))
    print('columns:', df.columns.tolist())
    if 'observation.state' in df:
        states = list(df['observation.state'])
        zero = sum(not any(v != 0 for v in s) for s in states)
        print('all-zero states:', zero)
        assert zero == 0, 'all-zero state 있음'
"
```

확인:

- parquet 파일이 존재한다.
- `observation.state`가 all-zero가 아니다.
- episode별 row 수가 비정상적으로 작지 않다.

### 1-2. EEF/action 범위 산출

아직 스크립트화 필요. 목표는 데이터셋에서 `ACTION_MIN` / `ACTION_MAX` 후보를 자동 계산하는 것이다.

필요한 출력:

- state min/max
- action min/max
- gripper min/max
- 비정상 outlier frame index

### 1-3. 비전 frame 정합성 확인

확인할 것:

- parquet row 수와 video frame index 대응
- top/wrist frame 누락 여부
- warmup 이후 첫 frame timeout 여부
- episode별 mp4 파일 생성 여부

---

## 현재 우선 실험 2: SmolVLA episode 확충

목표: 5 episode 검증 수준에서 벗어나 작업 성공률을 평가할 수 있을 만큼 demonstration을 늘린다.

### 녹화 명령

```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-smolvla \
    --dataset.root=/home/ugrp308/Group43/datasets/piper-smolvla \
    --dataset.single_task="pick the pan" \
    --dataset.num_episodes=20 \
    --dataset.push_to_hub=false \
    --robot.discover_packages_path=lerobot_robot_piper \
    --teleop.discover_packages_path=lerobot_robot_piper
```

확인:

- 녹화 시작 시 slave arm이 갑자기 움직이지 않는다.
- master arm 움직임이 slave arm에 실시간 반영된다.
- top/wrist view가 의도한 작업 공간을 담는다.
- episode 저장 후 parquet와 mp4가 생성된다.

### SmolVLA 학습

```bash
lerobot-train \
    --policy.type=smolvla \
    --policy.pretrained_path=lerobot/smolvla_base \
    --dataset.repo_id=local/piper-smolvla \
    --output_dir=outputs/piper-smolvla \
    --robot.discover_packages_path=lerobot_robot_piper
```

---

## 현재 우선 실험 3: SmolVLA 실제 추론

실제 arm 연결 전 action 범위와 clamp를 확인한다.

### 시뮬레이션

```bash
smolvla-inference \
    --pretrained_path=outputs/piper-smolvla/checkpoints/last/pretrained_model \
    --use_devices=false \
    --max_steps=20 \
    --task="pick the pan"
```

확인:

- action 값이 데이터셋 기반 안전 범위 안에 있다.
- 새 데이터셋이면 `ACTION_MIN` / `ACTION_MAX`가 재계산되어 있다.

### 실제 arm

```bash
smolvla-inference \
    --pretrained_path=outputs/piper-smolvla/checkpoints/last/pretrained_model \
    --can_interface=can0 \
    --top_serial=327122074262 \
    --wrist_serial=243322071626 \
    --max_steps=5 \
    --task="pick the pan"
```

실행 전 체크:

- [ ] EEF non-zero 확인 완료
- [ ] action 범위 확인 완료
- [ ] arm 주변 50 cm 확보
- [ ] 키보드에서 즉시 `Ctrl+C` 가능
- [ ] `max_steps=5`로 시작

---

## 현재 우선 실험 4: 비동기 추론

목표: 연구실 GPU 서버에서 policy server를 띄우고, 로봇 PC에서 client를 실행해 대형 VLA 모델 적용 가능성을 확인한다.

### async 의존성

```bash
cd /home/ugrp308/Group43/lerobot
pip install -e ".[async]"
```

### GPU 서버

```bash
python -m lerobot.async_inference.policy_server --host=0.0.0.0 --port=8080
```

확인:

- 서버가 8080 포트에서 대기한다.
- 로봇 PC와 같은 네트워크에서 접근 가능하다.
- 방화벽에서 8080 포트가 막혀 있지 않다.

### 로봇 PC 시뮬레이션/연결 확인

```bash
piper-async-client \
    --robot.type=piper \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --server_address=<GPU_SERVER_IP>:8080 \
    --policy_type=pi0 \
    --pretrained_name_or_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --task="pick and place" \
    --actions_per_chunk=50 \
    --chunk_size_threshold=0.5 \
    --debug_visualize_queue_size=True
```

확인:

- 서버와 연결된다.
- action 값이 안전 범위 안에 있다.
- queue가 자주 0에 가까워지지 않는다.
- 실제 arm 실험 전 작은 `max_steps` 또는 안전한 제한 조건을 추가한다.

---

## 완료/미완료 체크리스트

| 영역 | 항목 | 상태 |
|------|------|------|
| 환경 | PiPER Master-Slave teleop 정상화 | 완료 |
| 환경 | joint/gripper 상태값 수신 | 완료 |
| 녹화 | EEF-only LeRobotDataset 저장 | 완료 |
| 녹화 | top/wrist RealSense 포함 저장 | 완료 |
| 안전 | teleop `send_action()` no-op 검증 | 완료 |
| 학습 | SmolVLA 5 episode fine-tuning | 완료 |
| 추론 | SmolVLA 실제 PiPER 50 step 실행 | 완료 |
| 데이터 | EEF/비전 재현성 자동 검증 | 미완료 |
| 데이터 | 데이터셋별 action min/max 자동 산출 | 미완료 |
| 평가 | 충분한 episode 기반 성공률 평가 | 미완료 |
| async | policy server/robot client 분리 검증 | 미완료 |
| 대형 모델 | pi0 async 추론 및 비교 | 미완료 |
