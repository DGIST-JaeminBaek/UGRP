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

LoRA-SP는 π0를 Piper arm에 fine-tuning할 때 **절대 EEF 좌표 (absolute)** 를 액션 공간으로 채택했습니다. π0 원논문의 delta(변화량) 방식과 달리 절대 좌표를 쓴 이유는 두 가지입니다:
1. Piper SDK의 `EndPoseCtrl`이 절대 좌표를 받는 API이므로 변환 없이 그대로 전달 가능
2. delta 방식은 매 스텝마다 현재 위치를 읽어 더해야 해서 누적 오차 발생 가능

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

### 녹화

master arm을 손으로 움직이면 slave arm이 CAN으로 자동 추종. LeRobot이 slave arm 상태를 데이터셋으로 저장합니다.

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
    --dataset.push_to_hub=false
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
