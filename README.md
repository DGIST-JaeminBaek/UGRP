# piper_lerobot

Piper-to-Piper 마스터-슬레이브 텔레오퍼레이션으로 [LeRobotDataset](https://github.com/huggingface/lerobot)을 녹화하고, 학습된 VLA 정책을 실시간으로 추론하는 파이프라인.

원본 [`AgRoboticsResearch/lerobot_robot_piper`](https://github.com/AgRoboticsResearch/lerobot_robot_piper)를 기반으로  LoRA-SP의 엔드이펙터 설계를 통합하여 발전시켰습니다.

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

원본은 관절 각도(joint space) 기반이었지만, 이 버전은 **엔드이펙터 좌표(end-effector space)** 로 전면 교체했습니다.

| 항목 | 원본 | 이 버전 |
|------|------|---------|
| 액션 공간 | 관절 각도 (deg) | EEF 좌표 (raw SDK 정수) |
| 텔레오퍼레이터 | SO101 리더 arm | `PiperSlaveOnly` (CAN 패스스루) |
| 추론 스크립트 | 없음 | `piper_real_time_inference.py` |
| 제어 모드 | 없음 | `control_mode` (`teleop` / `user`) |

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

### 녹화

master arm을 손으로 움직이면 slave arm이 CAN으로 자동 추종. LeRobot이 slave arm 상태를 데이터셋으로 저장합니다.

```bash
lerobot-record \
    --robot.type=piper \
    --robot.control_mode=teleop \
    --robot.can_interface=can0 \
    --teleop.type=piper_slave_only \
    --dataset.repo_id=local/piper-demo \
    --dataset.single_task="pick and place" \
    --dataset.push_to_hub=false
```

### 학습

```bash
lerobot-train \
    --policy.type=pi0 \
    --dataset.repo_id=local/piper-demo \
    --output_dir=outputs/piper-pi0
```

### 추론

**OpenCV 카메라:**
```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --can_interface=can0 \
    --task="pick and place"
```

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
