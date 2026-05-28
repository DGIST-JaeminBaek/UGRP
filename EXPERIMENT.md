# 실험 계획

코드를 실제 하드웨어에서 검증하기 위한 단계별 실험 계획.
**안전이 최우선 — 각 실험 전 해당 항목의 안전 주의사항을 반드시 읽을 것.**

---

## 위험 시나리오 사전 정리

실험 전에 발생할 수 있는 위험 상황과 원인을 먼저 숙지한다.

### 위험 A — EEF 데이터 zeros → arm이 로봇 베이스 내부로 이동 시도 (치명적)

**원인:** `ConnectPort()` 후 CAN 첫 프레임이 아직 안 와서 `get_end_pose_raw()`가 전부 0 반환.
이 상태로 추론을 시작하면 정책이 "현재 위치 = (0,0,0)"으로 인식하고,
`(0,0,0)`은 로봇 마운팅 베이스 내부 좌표 → `EndPoseCtrl(0,0,0,...)` 명령이 나갈 경우 자가 충돌.

**대응:** 추론 시작 전 반드시 `get_end_pose_raw()` 출력이 non-zero인지 육안 확인.
코드의 2초 대기 루프가 통과했더라도, 로그에 warning이 찍혔으면 arm에 명령 보내지 말 것.

---

### 위험 B — action 값 이상 (스케일 오류) → arm 급격한 이동

**원인:** postprocessor 역정규화 오류, 또는 학습 데이터셋과 추론 데이터셋의 stats 불일치.
정상 범위를 크게 벗어난 raw SDK 정수가 `EndPoseCtrl`로 전달되면 arm이 한 스텝에 수십 cm 이동할 수 있음.

**정상 범위 (참고값):**
| 축 | raw SDK 정수 범위 (대략) |
|---|---|
| X (전후) | 100,000 ~ 400,000 |
| Y (좌우) | -200,000 ~ 200,000 |
| Z (상하) | 50,000 ~ 350,000 |
| RX/RY/RZ | -180,000 ~ 180,000 |
| gripper | 0 ~ 70,000 |

**대응:** 추론 전 시뮬레이션 모드(`--use_devices=false`)에서 action 값을 로그로 확인.
범위를 크게 벗어나면 실제 arm에 연결하지 말 것.

---

### 위험 C — zero_configuration 진행 중 장애물 충돌

**원인:** arm이 현재 위치에서 전 관절 0도로 이동할 때 경유 경로가 넓은 호를 그림.
중간 경로에 사람 또는 장애물이 있으면 충돌.

**대응:** `zero_configuration()` 호출 전 arm 주변 **최소 50cm** 이내 사람·물체 없는지 확인.
arm이 어느 위치에 있든 worst-case sweep을 가정할 것.

---

### 위험 D — teleop 모드에서 `send_action`이 실수로 명령 전송

**원인:** `control_mode` 확인 로직 오류, 또는 잘못된 config 전달.
CAN 마스터-슬레이브 sync가 활성 상태에서 `EndPoseCtrl`이 동시에 들어오면 arm이 예측 불가한 방향으로 급격히 움직일 수 있음.

**대응:** 녹화 시작 전 3-1 실험으로 `send_action`이 실제로 no-op인지 검증 후 진행.

---

## 공통 안전 수칙

모든 레벨 1 이상 실험에 적용.

1. **E-stop 준비** — 터미널에서 Ctrl+C로 즉시 중단 가능한 상태로 유지. 키보드에서 손 떼지 말 것.
2. **작업 공간** — arm 주변 50cm 이내 사람·물체 없이 유지.
3. **순서** — 반드시 아래 레벨 순서대로 진행. 이전 레벨 통과 없이 다음 레벨 진행 금지.
4. **비상시** — Ctrl+C 후에도 arm이 멈추지 않으면 CAN 인터페이스 즉시 비활성화:
   ```bash
   sudo ip link set can0 down
   ```
5. **속도** — `ctrl_end_pose`는 `MotionCtrl_2(..., speed=20, ...)` 기준으로 동작 (최대 속도의 20%). 변경하지 말 것.

---

## 레벨 0 — 하드웨어 없이 (소프트웨어만)

### 0-1. 패키지 임포트

```bash
python -c "import lerobot_robot_piper; print('OK')"
```

**확인:** 에러 없이 `OK` 출력.
**실패 원인 후보:** `pyrealsense2` 없을 때 import 오류 → `config_piper.py`에 RealSense import가 다시 생겼는지 확인.

---

### 0-2. 플러그인 탐색

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

**확인:** 두 줄 모두 OK 출력.
**실패 원인 후보:** `setup.cfg`의 `editable_mode = compat` 누락, `pip install -e .` 미실행.

---

### 0-3. Config 기본값

```bash
python -c "
from lerobot_robot_piper.config_piper import PiperConfig
cfg = PiperConfig()
assert cfg.control_mode == 'teleop', cfg.control_mode
assert cfg.include_gripper == True
assert list(cfg.cameras.keys()) == ['top', 'wrist']
print('config defaults OK')
"
```

---

### 0-4. 추론 시뮬레이션 (체크포인트 있을 때)

> 실제 arm 없이 action 값 사전 점검 — **레벨 4 전에 반드시 수행**

```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --use_devices=false \
    --max_steps=20 \
    --task="pick and place"
```

**확인 (위험 B 예방):**
- 로그의 action 값이 위험 시나리오 B의 정상 범위 이내인지 확인
- 전부 0이면 postprocessor/stats 문제 → 실제 arm 연결 전 원인 파악
- 범위를 크게 벗어나면 실제 arm 연결 금지

---

## 레벨 1 — CAN 연결 (카메라·arm 동작 없음)

> 준비: `sudo ip link set can0 up type can bitrate 1000000`

### 1-1. SDK 연결 및 EEF 데이터 확인

> ⚠️ arm이 연결된 상태. 이 실험에서는 명령을 보내지 않지만, 연결만으로도 CAN 상태가 바뀔 수 있음.

```bash
python -c "
from lerobot_robot_piper.piper_sdk_interface import PiperSDKInterface
import logging; logging.basicConfig(level=logging.INFO)
iface = PiperSDKInterface(port='can0', skip_enable=False)
data = iface.get_end_pose_raw()
print(data)
assert any(v != 0 for v in data.values()), '전부 0 — CAN 수신 문제'
print('EEF non-zero OK')
"
```

**확인 (위험 A 예방):**
- 모든 값이 0이면 `assert`로 실험 중단됨 — CAN 연결 상태 재확인
- 로그에 `EEF data still zero after 2.0s` warning 없어야 정상
- X, Y, Z 값이 위험 B 정상 범위 이내인지 눈으로 확인

---

### 1-2. teleop 모드 — EnablePiper 건너뜀 확인

```bash
python -c "
import logging; logging.basicConfig(level=logging.DEBUG)
from lerobot_robot_piper.piper_sdk_interface import PiperSDKInterface
iface = PiperSDKInterface(port='can0', skip_enable=True)
print('connected OK')
" 2>&1 | grep -E "(Skipping|timed out|ERROR)"
```

**확인:** `Skipping EnablePiper (slave mode)` 출력, timeout 없음.

---

### 1-3. zero_configuration

> ⚠️ **arm이 실제로 이동함.** 실행 전 반드시 공통 안전 수칙 확인.
> arm 현재 위치가 어디든 전 관절 0도까지 이동하는 경로를 예상하기 어려우므로
> **arm 주변을 완전히 비운 후** 실행.

```bash
python -c "
from lerobot_robot_piper.piper_sdk_interface import PiperSDKInterface
iface = PiperSDKInterface(port='can0')

# 실행 전 마지막 확인
input('arm 주변이 비어 있습니까? Enter로 계속, Ctrl+C로 중단: ')

iface.zero_configuration(wait=5.0)
print('zero OK')
"
```

**확인:** arm이 천천히 원점(모든 관절 0도)으로 이동, 5초 대기 후 멈춤.
**비상시:** 움직임이 예상과 다르면 즉시 Ctrl+C → `sudo ip link set can0 down`.

---

### 1-4. get_end_pose_raw 연속 읽기

arm을 손으로 살짝 밀었을 때 값이 변하는지 확인 (CAN 수신 정상 여부).

```bash
python -c "
import time
from lerobot_robot_piper.piper_sdk_interface import PiperSDKInterface
iface = PiperSDKInterface(port='can0')
for i in range(10):
    print(i, iface.get_end_pose_raw())
    time.sleep(0.2)
"
```

**확인:** arm을 움직이면 값이 따라 변함. 고정 시 값이 안정적(일정).

---

## 레벨 2 — 카메라 연결

### 2-1. OpenCV 카메라 인덱스 확인

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

**확인:** `top` / `wrist` 카메라가 실제로 어느 인덱스에 있는지 파악.
확인된 인덱스를 CLI 인자로 전달:
```bash
--robot.top_index=<top 인덱스> --robot.wrist_index=<wrist 인덱스>
```

---

### 2-2. Piper + 카메라 동시 연결 및 관측값 확인

```bash
python -c "
from lerobot_robot_piper.config_piper import PiperConfig
from lerobot_robot_piper.piper import Piper
cfg = PiperConfig(can_interface='can0', control_mode='teleop')
robot = Piper(cfg)
robot.connect()
obs = robot.get_observation()
print('EEF:', {k: v for k, v in obs.items() if 'pos' in k})
print('top shape:', obs['top'].shape)
print('wrist shape:', obs['wrist'].shape)
assert any(v != 0 for k, v in obs.items() if 'pos' in k), 'EEF 전부 0'
robot.disconnect()
print('OK')
"
```

**확인:**
- EEF 값이 non-zero (위험 A 조건 사전 점검)
- 카메라 shape `(480, 640, 3)`
- `robot._last_obs`가 채워졌는지:

```bash
python -c "
...
obs = robot.get_observation()
assert robot._last_obs is obs, '_last_obs 캐시 실패'
"
```

### 2-3. RealSense 시리얼 번호 확인

카메라를 USB로 연결한 상태에서 아래 스크립트 실행:

```python
import pyrealsense2 as rs

ctx = rs.context()
devices = list(ctx.devices)

if not devices:
    print("RealSense 장치 없음 — USB 연결 확인")
else:
    for i, d in enumerate(devices):
        name   = d.get_info(rs.camera_info.name)
        serial = d.get_info(rs.camera_info.serial_number)
        print(f"[{i}] {name}  시리얼: {serial}")
```

**출력 예시:**
```
[0] Intel RealSense D435  시리얼: 123456789
[1] Intel RealSense D435  시리얼: 987654321
```

**확인:** 카메라가 두 개 잡히면 어느 쪽이 top/wrist인지 USB를 하나씩 뽑아서 구분.
확인된 시리얼 번호를 CLI 인자로 전달:
```bash
--robot.top_serial=123456789 --robot.wrist_serial=987654321
```

---

## 레벨 3 — 녹화

### 3-1. PiperSlaveOnly no-op 및 캐시 동작 검증 (위험 D 예방)

> arm에 명령을 보내지 않는지 검증. **녹화 전 반드시 수행.**

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

# send_action no-op 확인
returned = robot.send_action(action)
print('send_action returned (should equal input):', returned == action)

# 캐시 일치 확인
eef_keys = [k for k in obs if 'pos' in k]
match = all(obs[k] == action[k] for k in eef_keys)
print('obs == action:', match)  # True 이어야 함

robot.disconnect()
"
```

**확인:**
- `send_action returned: True` — 명령이 arm으로 나가지 않음
- `obs == action: True` — 캐시 재사용 정상

---

### 3-2. 실제 녹화

> ⚠️ master arm을 손으로 움직이면 slave arm이 따라옴. **slave arm 주변 공간 확보.**
> 녹화 시작 시 arm이 갑자기 움직이지 않아야 함 (skip_enable 효과).

```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-test \
    --dataset.root=/home/ugrp308/Group43/datasets/piper-test \
    --dataset.single_task="test task" \
    --dataset.push_to_hub=false
```

**확인 항목:**
- 녹화 시작 시 slave arm이 갑자기 움직이지 않음
- master arm 움직임이 slave arm에 실시간으로 반영됨
- 에피소드 저장 후 parquet 파일 생성

**데이터 검증:**
```bash
python -c "
import pandas as pd, pathlib
p = sorted(pathlib.Path('/home/ugrp308/Group43/datasets/piper-test').glob('data/**/*.parquet'))[0]
df = pd.read_parquet(p)
print(df.columns.tolist())
state = df['observation.state'].iloc[0]
print('state sample:', state)
assert any(v != 0 for v in state), '녹화된 EEF 전부 0 — 데이터 불량'
"
```

---

## 레벨 4 — 추론

> 사전 조건: 레벨 0-4 시뮬레이션 통과 + 학습 완료된 체크포인트 존재

### 4-1. 추론 시뮬레이션 재확인 (실제 arm 연결 직전)

```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-test \
    --use_devices=false \
    --max_steps=20 \
    --task="test task"
```

**확인 (위험 B 최종 점검):**
로그에서 action 값 직접 확인:

```python
# piper_real_time_inference.py 추론 루프 안에 임시 추가
logger.info("action raw: %s", action.tolist())
```

값이 정상 범위이면 4-2 진행. 아니면 추론 스크립트 수정 후 재확인.

---

### 4-2. 실제 arm 추론

> ⚠️ arm이 정책의 명령을 따라 자율 이동. **가장 위험한 단계.**
>
> **체크리스트 (실행 전 모두 확인):**
> - [ ] 4-1에서 action 값 정상 범위 확인 완료
> - [ ] 1-1에서 EEF non-zero 확인 완료
> - [ ] arm 주변 50cm 이내 사람·물체 없음
> - [ ] 한 손은 키보드(Ctrl+C) 위에 대기
> - [ ] `max_steps=5`로 시작 (정상이면 점차 늘림)

```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-test \
    --can_interface=can0 \
    --max_steps=5 \
    --task="test task"
```

**확인 항목:**
- 시작 시 `zero_configuration()` 후 arm이 원점으로 천천히 이동 (5초)
- 추론 중 arm 동작이 학습한 태스크와 대략 일치
- 5 스텝 완료 후 자동으로 `zero_configuration()` 재실행 → 원점 복귀
- 이상 없으면 `--max_steps=50`으로 재실행

**비상 시나리오:**
- arm이 갑자기 큰 폭으로 움직임 → 즉시 Ctrl+C, 원인: 위험 B
- Ctrl+C 후에도 안 멈춤 → `sudo ip link set can0 down`
- zero_configuration이 안 끝남 → 10초 기다린 후 CAN 비활성화

---

## 레벨 5 — 비동기 추론 (외부 GPU 서버 분리)

> 사전 조건: 레벨 4-2 통과 + 외부 GPU 서버와 네트워크 연결 확인

### 5-1. async 의존성 설치

```bash
cd /home/ugrp308/Group43/lerobot && pip install -e ".[async]"
```

---

### 5-2. PolicyServer 기동 (GPU 서버)

```bash
python -m lerobot.async_inference.policy_server --host=0.0.0.0 --port=8080
```

**확인:** 서버가 8080 포트에서 대기 중인지 로그로 확인.
방화벽에서 8080 포트 열려 있어야 함.

---

### 5-3. 비동기 추론 시뮬레이션 (로봇 PC, 하드웨어 없이)

> 실제 arm 연결 전 네트워크 연결 및 action 값 사전 점검

```bash
piper-async-client \
    --robot.type=piper \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --server_address=<GPU서버_IP>:8080 \
    --policy_type=pi0 \
    --pretrained_name_or_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --task="test task" \
    --actions_per_chunk=50 \
    --chunk_size_threshold=0.5 \
    --debug_visualize_queue_size=True
```

**확인:**
- 서버와 연결되는지 확인
- action 값이 위험 B 정상 범위 이내인지 확인
- `debug_visualize_queue_size`로 버퍼 상태 모니터링

---

### 5-4. 파라미터 튜닝 가이드

네트워크 지연이 있어도 로봇이 끊기지 않으려면 버퍼가 소진되기 전에 다음 chunk가 도착해야 함.

| 파라미터 | 설명 | 권장 시작값 |
|---|---|---|
| `actions_per_chunk` | 한 번에 받을 action 스텝 수. 크게 잡을수록 지연에 강하지만 반응성 감소 | 50 |
| `chunk_size_threshold` | 버퍼가 몇 % 남았을 때 다음 chunk 요청. 작으면 버퍼 소진 위험 | 0.5 |

**튜닝 순서:**
1. `--debug_visualize_queue_size=True`로 버퍼 크기 실시간 모니터링
2. 버퍼가 자주 0에 가까워지면 `actions_per_chunk` 증가 또는 `chunk_size_threshold` 증가
3. 버퍼가 항상 가득 차 있으면 `actions_per_chunk` 감소로 반응성 개선

---

### 5-5. 실제 arm 비동기 추론

> ⚠️ 레벨 4-2와 동일한 안전 수칙 적용. 5-3 시뮬레이션 통과 후 진행.

```bash
piper-async-client \
    --robot.type=piper \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --server_address=<GPU서버_IP>:8080 \
    --policy_type=pi0 \
    --pretrained_name_or_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --task="test task" \
    --actions_per_chunk=50 \
    --chunk_size_threshold=0.5
```

**비상시:** Ctrl+C → `sudo ip link set can0 down`

---

## 실험 노트 (2026-05-28) — wrist 카메라 설치 후 녹화 파이프라인 재검증

### 환경
- conda 환경: `piper`
- top 카메라: RealSense D435IF 시리얼 `327122074262`
- wrist 카메라: RealSense D435IF 시리얼 `243322071626` (신규 설치)
- Piper master-slave, can0

### 수행 내용

**2-3 (RealSense 시리얼 확인):**
- 카메라 2대 정상 인식, 시리얼 기존 기록과 일치
- top: `327122074262`, wrist: `243322071626`

**2-2 (Piper + 카메라 동시 연결):**
- EEF non-zero 확인: `{'x.pos': 58050.0, 'y.pos': 2853.0, 'z.pos': 220777.0, ...}`
- top/wrist shape 모두 `(480, 640, 3)` 정상

**3-1 (send_action no-op 검증):**
- `send_action returned: True`, `obs == action: True` — 위험 D 없음 확인

**3-2 (실제 녹화):**
- 3 에피소드, top + wrist 카메라 동시 녹화
- 저장 경로: `/home/ugrp308/Group43/datasets/piper-test`
- 에피소드당 약 370프레임 (→ 키로 조기 종료, 약 12초)
- SVT-AV1 코덱으로 mp4 정상 인코딩 완료

### 발견 사항

**데이터셋 저장 경로:**
- 기본값(`~/.cache/huggingface/lerobot/`) 대신 `--dataset.root` 로 `/home/ugrp308/Group43/datasets/` 지정
- README, EXPERIMENT.md 명령어 모두 실제 시리얼 번호 및 경로로 업데이트 완료

**카메라 미리보기:**
- `preview_camera.py` — top/wrist 좌우 병렬 표시, matplotlib TkAgg 백엔드 사용
- 뷰 확인: top은 작업 공간 전체, wrist는 그리퍼 시점에서 파지 대상 클로즈업

**piper_sdk V2 원점 복귀:**
- `ReqMasterArmMoveToHome(mode)` 확인 (`piper_interface_v2.py:3659`)
  - mode=0: master-slave 모드 복원
  - mode=1: master arm 원점 복귀
  - mode=2: master + slave 둘 다 원점 복귀

---

## 실험 노트 (2026-05-07) — SmolVLA 파이프라인 전체 검증

### 환경
- conda 환경: `piper`
- lerobot 0.4.0, SmolVLA (`lerobot/smolvla_base`, 450M)
- top 카메라 단독 (RealSense D435IF, 시리얼: 327122074262)
- Piper single arm, can0

### 수행 내용

**녹화:**
- `pick the pan` 태스크, top 카메라 1대, 5 에피소드 (2170 프레임)
- `local/piper-smolvla` 데이터셋으로 저장

**Fine-tuning:**
- `lerobot-train --policy.type=smolvla --policy.pretrained_path=lerobot/smolvla_base`
- expert 레이어만 학습 (100M / 450M), VLM frozen
- 5000 steps, batch_size=8, 약 12분 소요
- loss: 0.242 → 0.010 수렴

**추론:**
- `smolvla-inference` 스크립트로 실제 로봇 연결
- action clamp (녹화 데이터 EEF 범위 기반) 안전장치 적용
- 50 steps 정상 동작 확인 (에러 없음)
- 결과: 로봇이 움직이나 팬 근처까지는 못 감 → 데이터 부족 (5 에피소드)

### 발견 사항

**정책 전환 (pi0 → smolvla):**
- `lerobot/pi0`은 v0.1 포맷 → lerobot 0.4.0과 호환 안 됨
- `lerobot/pi0_base`는 호환되나 ALOHA 기준 카메라 3개 필요 → Piper 단일 카메라와 mismatch
- `lerobot/smolvla_base`로 전환 — 카메라 키 이름에 무관하게 ds_meta 기반으로 자동 설정

**카메라 warmup:**
- warmup_s=0으로 설정 시 추론 스크립트에서 async_read timeout 발생
- connect 후 `time.sleep(8.0)` 추가로 해결
- 재연결 시 간헐적 timeout — 재시도로 해결 가능

**학습 방식:**
- `train_expert_only=True` (기본값) — VLM frozen, expert만 학습
- 소량 데이터(5 에피소드)에서는 이 방식이 적절
- 데이터 충분히 늘어나면 LoRA로 VLM도 일부 학습 고려

---

## 실험 노트 (2026-04-29)

### 환경
- conda 환경: `piper`
- lerobot 0.4.0, piper_sdk OK, torch 2.7.1+cu126
- 카메라 없음, 마스터 암 없음, 슬레이브 암 단독 테스트

### 발견 사항

**1-1:** CAN 첫 프레임 도착 전 `get_status_deg()` 첫 호출이 전부 0 반환 — 위험 A 재확인.
0.5초 대기 후 정상값 수신됨.

**1-3 (zero_configuration):**
- `skip_enable=False`로 `EnablePiper()` 호출 시 서보 on (관절에 힘 들어감).
- arm이 `CAN_CTRL` 모드였으나 SDK `JointCtrl` 명령도 CAN으로 전달되어 정상 동작.
- 마스터 암 없이 단독 테스트 시 `skip_enable=True` 권장 (불필요한 서보 on 방지).
- `DisablePiper()` → `DisableArm(7)` 호출로 서보 해제 확인.

**lerobot-record 플러그인 등록:**
- `--robot.type=piper` 단독 사용 시 `invalid choice` 오류.
- `--robot.discover_packages_path=lerobot_robot_piper` 추가 필요 (teleop도 동일).
- `register_third_party_devices()`는 `main()` 안에서 호출되어 draccus 파싱 후 실행되므로 효과 없음.
- `parser.wrap()`의 `load_plugin()` 메커니즘을 통해 파싱 전 로드해야 함.

**3-2 (녹화):**
- `use_cameras=false` 옵션으로 카메라 없이 EEF만 녹화 가능 (오늘 추가).
- 에피소드 데이터가 단일 parquet 파일에 저장됨 (`episode_index` 컬럼으로 구분).
- → 키로 에피소드 조기 종료, ← 키로 재녹화, ESC로 전체 종료.
- 키 안내 메시지는 LeRobot 기본 동작에서도 출력 안 됨.

---

## 체크리스트 요약

| 레벨 | 항목 | 하드웨어 | 안전 위험도 | 완료 |
|------|------|:---:|:---:|:---:|
| 0-1 | 패키지 임포트 | ✗ | 없음 | [x] |
| 0-2 | 플러그인 탐색 | ✗ | 없음 | [x] |
| 0-3 | Config 기본값 | ✗ | 없음 | [x] |
| 0-4 | 추론 시뮬레이션 (action 값 점검) | ✗ | 없음 | [ ] |
| 1-1 | SDK 연결 + EEF non-zero 확인 | CAN | 낮음 | [x] |
| 1-2 | teleop EnablePiper 건너뜀 | CAN | 낮음 | [x] |
| 1-3 | zero_configuration | CAN + arm | **높음** | [x] |
| 1-4 | EEF 연속 읽기 | CAN + arm | 낮음 | [x] |
| 2-1 | 카메라 인덱스 확인 | 카메라 | 없음 | [x] |
| 2-2 | Piper + 카메라 + EEF 검증 | CAN + arm + 카메라 | 낮음 | [x] |
| 2-3 | RealSense 시리얼 번호 확인 | 카메라 | 없음 | [x] |
| 3-1 | send_action no-op + 캐시 검증 | CAN + arm | 낮음 | [x] |
| 3-2 | 실제 녹화 (카메라 포함) | CAN + arm + 카메라 | **중간** | [x] |
| 4-1 | 추론 시뮬레이션 재확인 | ✗ | 없음 | [x] |
| 4-2 | 실제 추론 (5 스텝→50 스텝) | 풀 셋업 + 체크포인트 | **높음** | [x] |
| 5-1 | async 의존성 설치 | ✗ | 없음 | [ ] |
| 5-2 | PolicyServer 기동 (GPU 서버) | GPU 서버 | 없음 | [ ] |
| 5-3 | 비동기 추론 시뮬레이션 | 네트워크 | 없음 | [ ] |
| 5-4 | 파라미터 튜닝 | 네트워크 | 없음 | [ ] |
| 5-5 | 실제 arm 비동기 추론 | 풀 셋업 + GPU 서버 | **높음** | [ ] |
