# piper_lerobot

PiPER 로봇 팔에서 Master-Slave teleoperation 데이터를 LeRobotDataset으로 기록하고, 수집한 demonstration으로 VLA 정책을 fine-tuning한 뒤 실제 PiPER 동작까지 연결하는 실험용 LeRobot 플러그인입니다.

현재 연구 기준선은 2026-06-12 UGRP 중간보고서입니다. 이 레포의 현재 주 경로는 **SmolVLA 기반 녹화 → fine-tuning → 실제 로봇 추론 검증**이며, `pi0`는 대형 모델 적용을 위한 향후 비동기 추론/server 분리 과제로 남아 있습니다.

원본 [`AgRoboticsResearch/lerobot_robot_piper`](https://github.com/AgRoboticsResearch/lerobot_robot_piper)를 기반으로, PiPER의 CAN 기반 Master-Slave teleoperation 구조와 LoRA-SP 계열 end-effector 제어 설계를 반영했습니다.

---

## 현재 상태

| 영역 | 상태 | 메모 |
|------|------|------|
| PiPER 제어 환경 | 완료 | Ubuntu 22.04, CAN, Master-Slave 모드, joint/gripper 상태 수신 확인 |
| LeRobot 녹화 | 완료 | PiPER CAN direct teleoperation에 맞게 record 구조 재구성 |
| 액션/상태 공간 | 완료 | joint-space 대신 absolute end-effector raw SDK 정수 사용 |
| 카메라 녹화 | 완료 | top-view/wrist-view RealSense 기록 확인 |
| SmolVLA 학습/추론 | 검증 완료 | 5 episode, 5000 step fine-tuning, 실제 PiPER 50 step 추론 성공 |
| 데이터 재현성 검증 | 진행 예정 | 저장된 EEF/비전 데이터가 실제 궤적을 일관되게 반영하는지 확인 필요 |
| pi0 적용 | 보류 | 로컬 VRAM/안전/카메라 구성 문제로 async server 기반 검증 예정 |
| 비동기 추론 | 구현 일부 완료 | `piper-async-client` entrypoint 있음, 서버 분리 실험은 미검증 |

자세한 변경 이력은 [CHANGES.md](CHANGES.md), 설계 출처와 포팅 관계는 [LINEAGE.md](LINEAGE.md)를 봅니다.

---

## 핵심 설계

### PiPER teleoperation 구조

LeRobot의 일반적인 record 구조는 PC가 teleoperator 입력을 읽고 robot에 제어 명령을 보내는 흐름을 전제로 합니다. 하지만 현재 PiPER 실험 환경은 master arm 입력이 PC를 거치지 않고 CAN을 통해 slave arm으로 직접 전달됩니다.

그래서 이 레포에서는 녹화 중 slave arm에 별도 제어 명령을 보내지 않습니다. 대신 `PiperSlaveOnly` teleoperator가 LeRobot record loop에 맞는 action을 제공하고, 실제 추종은 PiPER의 CAN Master-Slave sync가 담당합니다.

### End-effector action space

원본 구현은 joint-space 기반이었지만, 이 레포는 전 구간을 end-effector absolute 좌표로 맞췄습니다.

```
녹화: get_end_pose_raw() -> raw SDK 정수 저장
학습: LeRobotDataset의 observation.state/action으로 EEF 분포 학습
추론: 정책 출력 -> postprocess/clamp -> EndPoseCtrl()
```

| 축 | 단위 |
|----|------|
| X, Y, Z | 0.001 mm |
| RX, RY, RZ | 0.001 deg |
| gripper | SDK raw 정수 |

`control_mode=teleop`에서는 `send_action()`이 no-op으로 동작해 CAN Master-Slave sync와 충돌하지 않게 하고, `control_mode=user`에서는 추론 스크립트가 직접 `EndPoseCtrl()`로 arm을 제어합니다.

---

## 설치

### 개발 PC

코드 개발만 하는 PC에서는 하드웨어 의존성까지 모두 검증할 필요는 없습니다. 다만 LeRobot 0.4.0 기준으로 개발하는 것을 권장합니다.

```bash
conda create -n UGRP python=3.10
conda activate UGRP

cd ~
git clone https://github.com/huggingface/lerobot.git
cd lerobot
git checkout v0.4.0
pip install -e .

cd ~
git clone https://github.com/DGIST-JaeminBaek/UGRP.git
cd UGRP
pip install -e .
```

설치 확인:

```bash
python -c "import lerobot; print(lerobot.__file__)"
python -c "import lerobot_robot_piper; print('piper plugin OK')"
python -c "from piper_sdk import C_PiperInterface_V2; print('piper_sdk OK')"
```

### 실험 PC

실제 로봇 실험 PC에는 위 Python 환경 외에 다음이 필요합니다.

- PiPER arm, CAN adapter, `can0` SocketCAN 설정
- `piper_sdk`, `python-can`
- RealSense 사용 시 `pyrealsense2` 및 장치 권한 설정
- 학습/추론용 CUDA/PyTorch 환경
- 비동기 추론을 쓸 경우 LeRobot async extra

CAN 활성화 예:

```bash
sudo ip link set can0 up type can bitrate 1000000
ip link show can0
```

---

## LeRobot 플러그인 인자

`lerobot-record` / `lerobot-train`에서 `--robot.type=piper` 또는 `--teleop.type=piper_slave_only`를 인식시키려면 아래 인자를 함께 넣습니다.

```bash
--robot.discover_packages_path=lerobot_robot_piper
--teleop.discover_packages_path=lerobot_robot_piper
```

`pip install -e .` 상태에서도 LeRobot의 third-party device 등록이 draccus 인자 파싱 이후에 호출되어 `piper` 타입이 늦게 등록될 수 있습니다. 위 인자는 파싱 전에 패키지를 강제로 로드하는 workaround입니다.

---

## 카메라

RealSense 시리얼 확인:

```bash
python -c "
import pyrealsense2 as rs
ctx = rs.context()
for i, d in enumerate(ctx.devices):
    print(f'[{i}] {d.get_info(rs.camera_info.name)}  serial: {d.get_info(rs.camera_info.serial_number)}')
"
```

현재 실험실 기록:

| 위치 | 장치 | 시리얼 |
|------|------|--------|
| top | Intel RealSense D435IF | `327122074262` |
| wrist | Intel RealSense D435IF | `243322071626` |

OpenCV 카메라를 쓸 때는 `--robot.top_index`, `--robot.wrist_index`를 사용합니다. 카메라 없이 EEF만 기록하려면 `--robot.use_cameras=false`를 사용합니다.

---

## 녹화

Master arm을 손으로 움직이면 slave arm이 CAN으로 직접 추종합니다. LeRobot은 slave arm의 EEF state/action과 카메라 프레임을 LeRobotDataset 형식으로 기록합니다.

RealSense 2대 녹화 예:

```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-demo \
    --dataset.root=/home/ugrp308/Group43/datasets/piper-demo \
    --dataset.single_task="pick and place" \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=false \
    --robot.discover_packages_path=lerobot_robot_piper \
    --teleop.discover_packages_path=lerobot_robot_piper
```

OpenCV 카메라 녹화 예:

```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_index=0 \
    --robot.wrist_index=4 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-demo \
    --dataset.root=/home/ugrp308/Group43/datasets/piper-demo \
    --dataset.single_task="pick and place" \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=false \
    --robot.discover_packages_path=lerobot_robot_piper \
    --teleop.discover_packages_path=lerobot_robot_piper
```

데이터는 기본적으로 `~/.cache/huggingface/lerobot/<repo_id>/`에 저장됩니다. 실험 PC에서는 `--dataset.root`로 명시 경로를 지정하는 것을 권장합니다.

---

## 학습

현재 전체 파이프라인 검증은 SmolVLA로 진행했습니다.

```bash
lerobot-train \
    --policy.type=smolvla \
    --policy.pretrained_path=lerobot/smolvla_base \
    --dataset.repo_id=local/piper-smolvla \
    --output_dir=outputs/piper-smolvla \
    --robot.discover_packages_path=lerobot_robot_piper
```

중간보고서 기준 검증 기록:

- 작업: `pick the pan`
- 데이터: top-view 카메라 1대, 5 episode, 2170 frame
- 학습: expert layer만 fine-tuning, VLM backbone frozen
- 조건: 5000 step, batch size 8, 약 12분
- loss: 0.242 -> 0.010

pi0는 별도 대형 모델 실험 대상으로 남겨둡니다. 로컬 RTX 4070 Ti 환경에서는 안정적인 실시간 추론과 로봇 제어를 동시에 처리하기 어려워, policy server 분리 구조에서 재검증할 계획입니다.

---

## 추론

### SmolVLA 동기 추론

현재 실제 PiPER에서 검증된 주 경로입니다. `smolvla-inference`는 녹화 데이터 기반 EEF action clamp를 적용합니다.

새 작업이나 새 데이터셋으로 학습한 모델을 사용할 때는 `lerobot_robot_piper/smolvla_inference.py`의 `ACTION_MIN` / `ACTION_MAX`를 해당 녹화 데이터 범위에 맞게 다시 계산해야 합니다.

시뮬레이션:

```bash
smolvla-inference \
    --pretrained_path=outputs/piper-smolvla/checkpoints/last/pretrained_model \
    --use_devices=false \
    --max_steps=20 \
    --task="pick the pan"
```

실제 로봇:

```bash
smolvla-inference \
    --pretrained_path=outputs/piper-smolvla/checkpoints/last/pretrained_model \
    --can_interface=can0 \
    --top_serial=327122074262 \
    --max_steps=50 \
    --task="pick the pan"
```

### 일반 LeRobot 정책 동기 추론

`piper-inference`는 LeRobot policy checkpoint와 dataset stats를 사용해 EEF action을 생성하는 동기 추론 entrypoint입니다. pi0 계열 검토와 LoRA-SP 방식 temporal ensemble 포팅을 위해 남겨둔 경로입니다.

```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --dataset_root=/home/ugrp308/Group43/datasets/piper-demo \
    --can_interface=can0 \
    --task="pick and place" \
    --top_serial=327122074262 \
    --wrist_serial=243322071626 \
    --max_steps=5
```

`--temporal_ensemble`을 추가하면 action chunk를 지수 가중 평균으로 집계합니다.

### 비동기 추론

대형 VLA 모델 적용을 위해 정책 추론 서버와 로봇 제어 PC를 분리하는 구조입니다. 코드 경로는 준비되어 있지만, 중간보고서 기준 실제 서버-로봇 통합 검증은 향후 과제입니다.

LeRobot async 의존성:

```bash
cd /path/to/lerobot
pip install -e ".[async]"
```

GPU 서버:

```bash
python -m lerobot.async_inference.policy_server --host=0.0.0.0 --port=8080
```

로봇 PC:

```bash
piper-async-client \
    --robot.type=piper \
    --robot.can_interface=can0 \
    --robot.top_serial=327122074262 \
    --robot.wrist_serial=243322071626 \
    --server_address=<GPU_SERVER_IP>:8080 \
    --policy_type=pi0 \
    --pretrained_name_or_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --task="pick and place"
```

---

## 안전

실제 arm 추론 전에는 [EXPERIMENT.md](EXPERIMENT.md)의 안전 수칙을 먼저 확인합니다. 특히 다음 조건은 실제 arm에 명령을 보내기 전에 반드시 검증합니다.

- `get_end_pose_raw()`가 all-zero가 아닌지 확인
- action raw 값이 정상 범위 안에 있는지 시뮬레이션에서 확인
- `teleop` 모드에서 `send_action()`이 no-op인지 확인
- `zero_configuration()` 실행 전 arm 주변 50 cm 이상 확보
- 비상 시 `Ctrl+C`, 필요하면 `sudo ip link set can0 down`

---

## 문서

| 문서 | 내용 |
|------|------|
| [CHANGES.md](CHANGES.md) | 현재 상태 기준선과 세부 변경 이력 |
| [ROADMAP.md](ROADMAP.md) | 파이프라인 현황 및 향후 계획 |
| [EXPERIMENT.md](EXPERIMENT.md) | 하드웨어 검증 절차와 안전 수칙 |
| [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) | 완료된 실험 기록과 시행착오 |
| [LINEAGE.md](LINEAGE.md) | 코드 출처, 포팅 관계, 설계 결정 |
| [DECISION_PI0_COMPAT.md](DECISION_PI0_COMPAT.md) | pi0 호환성 검토 메모 |
