# piper_lerobot

Piper-to-Piper 마스터-슬레이브 텔레오퍼레이션으로 [LeRobotDataset](https://github.com/huggingface/lerobot)을 녹화하고, 학습된 VLA 정책을 실시간으로 추론하는 파이프라인.

원본 [`AgRoboticsResearch/lerobot_robot_piper`](https://github.com/AgRoboticsResearch/lerobot_robot_piper)를 기반으로 [LoRA-SP](https://github.com/dhkim-furiosa/LoRA-SP)의 엔드이펙터 설계를 통합하여 발전시켰습니다.

> **LoRA-SP: Rank-Adaptive Fine-Tuning for Vision-Language-Action Models**
> Donghoon Kim, Minji Bae\*, Unghui Nam\*, Gyeonghun Kim\*, Suyun Lee\*, Kyuhong Shim†, Byonghyo Shim†
> Seoul National University (ISLab) · Sungkyunkwan University — ICRA 2026

---

## 파이프라인

```
[1] 녹화  →  [2] 학습  →  [3] 추론
  (완료)     (외부 도구)    (완료)
```

| 단계 | 상태 | 도구 |
|------|------|------|
| 녹화 | ✅ 완료 | `lerobot-record` + `piper_slave_only` |
| 학습 | — | `lerobot-train` (π0) |
| 추론 | ✅ 완료 | `piper-inference` |

자세한 현황 → [ROADMAP.md](ROADMAP.md)

---

## 이 레포가 원본과 다른 점

### 핵심 변경: 관절 공간 → 엔드이펙터 공간

원본은 관절 각도(joint space) 기반이었지만, 이 버전은 **엔드이펙터 좌표(end-effector space)** 로 전면 교체했습니다.

**이유:** π0는 end-effector 기반 액션을 예측하는 VLA 모델입니다 ([arXiv 2410.24164](https://arxiv.org/abs/2410.24164)). 관절 각도로 데이터셋을 녹화하면 정책의 출력 공간과 불일치가 발생합니다.

π0는 기본적으로 **절대 EEF 좌표 (absolute action)** 를 예측합니다 ([LeRobot π0 문서](https://huggingface.co/docs/lerobot/pi0)). LoRA-SP도 이 기본값을 그대로 따랐고, 이 프로젝트도 동일합니다. Piper에 absolute를 쓰는 추가적인 이유는 다음과 같습니다:
1. Piper SDK의 `EndPoseCtrl`이 절대 좌표를 받는 API이므로 변환 없이 그대로 전달 가능
2. relative 방식은 매 스텝마다 현재 위치를 읽어 더해야 해서 누적 오차 발생 가능

이 설계를 그대로 따라 **녹화 → 학습 → 추론 전 구간이 동일한 절대 EEF 좌표 단위**를 사용합니다.

```
녹화: get_end_pose_raw() → raw SDK 정수 저장
학습: π0가 EEF 좌표 분포 학습
추론: π0 출력 → 역정규화 → EndPoseCtrl() 로 그대로 전달
```

| 항목 | 원본 | 이 버전 | 변경 이유 |
|------|------|---------|----------|
| 액션 공간 | 관절 각도 (deg) | EEF 좌표 (raw SDK 정수) | π0 출력 공간과 일치 |
| 텔레오퍼레이터 | SO101 리더 arm | `PiperSlaveOnly` (CAN 패스스루) | Piper-to-Piper CAN sync 활용 |
| 추론 스크립트 | 없음 | `piper_real_time_inference.py` | LoRA-SP 추론 루프 포팅 |
| 제어 모드 | 없음 | `control_mode` (`teleop` / `user`) | 녹화/추론 간 send_action 동작 구분 |

코드 출처 및 설계 결정 상세 → [LINEAGE.md](LINEAGE.md)

전체 변경 이력 → [CHANGES.md](CHANGES.md)

---

## 설치

```bash
git clone https://github.com/DGIST-JaeminBaek/UGRP.git
cd UGRP
pip install -e .
```

> `editable_mode = compat` (`setup.cfg`)가 LeRobot 플러그인 탐색에 필요합니다.

---

## 사용법

### 플러그인 등록 인자 (`--discover_packages_path`)

`lerobot-record` / `lerobot-train` 실행 시 `--robot.type=piper`를 인식시키려면 아래 인자가 **항상** 필요합니다:

```
--robot.discover_packages_path=lerobot_robot_piper
--teleop.discover_packages_path=lerobot_robot_piper
```

> **왜 필요한가?**
> `pip install -e .`로 설치하면 lerobot이 entry point를 통해 자동으로 플러그인을 찾아야 하지만,
> lerobot 내부의 `register_third_party_devices()`가 draccus 인자 파싱 **이후**에 호출되는 구조라
> `--robot.type=piper`를 파싱하는 시점에는 piper가 아직 등록되지 않아 `invalid choice` 에러가 발생합니다.
> `--discover_packages_path`는 파싱 전에 패키지를 강제 로드하는 workaround입니다.

---

### 카메라 시리얼 번호 확인

RealSense 카메라를 USB에 연결한 상태에서:

```bash
python -c "
import pyrealsense2 as rs
ctx = rs.context()
for i, d in enumerate(ctx.devices):
    print(f'[{i}] {d.get_info(rs.camera_info.name)}  시리얼: {d.get_info(rs.camera_info.serial_number)}')
"
```

카메라가 여러 개일 경우 USB를 하나씩 뽑아 top/wrist를 구분합니다.

> **현재 실험실 세팅:**
> - top 카메라: `327122074262` (Intel RealSense D435IF)
> - wrist 카메라: `243322071626` (Intel RealSense D435IF)
>
> 아래 명령어 예시의 `123456789` / `987654321` 자리에 위 시리얼 번호를 넣으면 됩니다.

---

### 데이터 저장 위치

기본 저장 경로는 `~/.cache/huggingface/lerobot/<repo_id>/`입니다. 컴퓨터를 꺼도 유지되며, `rm -rf`하지 않는 한 삭제되지 않습니다.

원하는 경로에 저장하려면 `--dataset.root`를 지정합니다:

```bash
--dataset.root=/home/ugrp308/Group43/datasets/piper-demo
```

---

### 녹화

master arm을 손으로 움직이면 slave arm이 CAN으로 자동 추종. LeRobot이 slave arm 상태를 데이터셋으로 저장합니다.

이미지는 프레임별 배열이 아니라 **mp4 비디오**로 압축 저장되며, parquet 파일에는 EEF state/action 및 타임스탬프/프레임 인덱스만 저장됩니다. 학습 시 lerobot이 `frame_index`를 이용해 mp4에서 해당 프레임을 디코딩하여 배치를 구성합니다.

**RealSense 카메라:**
```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_serial=123456789 \
    --robot.wrist_serial=987654321 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-demo \
    --dataset.single_task="pick and place" \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=false \
    --robot.discover_packages_path=lerobot_robot_piper \
    --teleop.discover_packages_path=lerobot_robot_piper
```

**OpenCV 카메라:**
```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --robot.top_index=0 \
    --robot.wrist_index=4 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-demo \
    --dataset.single_task="pick and place" \
    --dataset.num_episodes=10 \
    --dataset.push_to_hub=false \
    --robot.discover_packages_path=lerobot_robot_piper \
    --teleop.discover_packages_path=lerobot_robot_piper
```

> `--dataset.num_episodes`: 녹화할 에피소드 수. 지정하지 않으면 ESC로 수동 종료할 때까지 계속 녹화합니다.
> 에피소드 중 `→` 키로 조기 종료, `←` 키로 재녹화, ESC로 전체 종료.

### 학습

```bash
lerobot-train \
    --policy.type=pi0 \
    --dataset.repo_id=local/piper-demo \
    --output_dir=outputs/piper-pi0
```

### 추론 (동기, sync)

추론과 로봇 제어를 한 프로세스에서 순차 실행. 추론 중 로봇이 대기합니다.

`--temporal_ensemble` 플래그를 추가하면 action chunk를 지수 가중 평균으로 집계해 더 부드러운 동작을 생성합니다 (LoRA-SP 방식). 기본값은 off입니다.

**RealSense 카메라:**
```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --can_interface=can0 \
    --task="pick and place" \
    --top_serial=123456789 \
    --wrist_serial=987654321
```

**OpenCV 카메라:**
```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --can_interface=can0 \
    --task="pick and place"
```

### 추론 (비동기, async)

추론 서버와 로봇 클라이언트를 분리해 추론 중에도 로봇이 계속 동작합니다.
외부 GPU 서버에 PolicyServer를 띄우고 로봇 PC에서 클라이언트를 실행하는 구조입니다.

> lerobot async 의존성 설치 필요:
> ```bash
> cd /path/to/lerobot && pip install -e ".[async]"
> ```

**GPU 서버:**
```bash
python -m lerobot.async_inference.policy_server --host=0.0.0.0 --port=8080
```

**로봇 PC:**
```bash
piper-async-client \
    --robot.type=piper \
    --robot.can_interface=can0 \
    --robot.top_serial=123456789 \
    --robot.wrist_serial=987654321 \
    --server_address=<GPU서버_IP>:8080 \
    --policy_type=pi0 \
    --pretrained_name_or_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --task="pick and place"
```

> 두 PC가 같은 네트워크에 있어야 하고, 방화벽에서 8080 포트가 열려 있어야 합니다.

---

## 액션 공간 규약

`get_end_pose_raw()`는 SDK raw 정수를 그대로 반환합니다. 변환 없이 데이터셋 저장 → 학습 → 추론까지 동일 단위를 사용합니다.

| 축 | 단위 |
|---|---|
| X, Y, Z | 0.001 mm |
| RX, RY, RZ | 0.001 도 |
| gripper | SDK raw 정수 |

---

## 문서

| 문서 | 내용 |
|------|------|
| [ROADMAP.md](ROADMAP.md) | 파이프라인 현황 및 미해결 과제 |
| [CHANGES.md](CHANGES.md) | 원본 대비 전체 변경 이력 |
| [LINEAGE.md](LINEAGE.md) | 코드 출처 및 설계 결정 |
| [EXPERIMENT.md](EXPERIMENT.md) | 하드웨어 검증 실험 계획 (안전 포함) |
| [SESSION_START.md](SESSION_START.md) | 실험실 세션 시작 프롬프트 |
