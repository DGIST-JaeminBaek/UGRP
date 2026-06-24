# 로드맵

목표: PiPER 기반 demonstration 수집, LeRobotDataset 저장, VLA fine-tuning, 실제 로봇 추론까지 이어지는 데이터 효율적 작업 적응 파이프라인을 안정화한다.

현재 기준선은 2026-06-12 UGRP 중간보고서와 [CHANGES.md](CHANGES.md)의 "현재 상태" 섹션이다.

---

## 한 줄 현황

SmolVLA로 녹화 → fine-tuning → 실제 PiPER 50 step 추론까지 검증했다. 다음 핵심은 데이터 재현성 검증, episode 확충, 비동기 추론 서버 분리, SmolVLA/pi0 비교 실험이다.

---

## 완료

### 1. PiPER 제어 환경

- [x] Ubuntu 24.04 SDK/ROS2 호환성 문제 확인 후 Ubuntu 22.04 실험 환경으로 전환
- [x] PiPER 제어 PC와 CAN 통신 모듈 연동
- [x] Master-Slave 모드 설정 문제 분석 및 수정
- [x] master arm 입력이 slave arm에 정상 반영되는지 확인
- [x] joint/gripper 상태값 실시간 수신 확인

### 2. LeRobot 녹화 파이프라인

- [x] LeRobot 기본 record 구조와 PiPER CAN direct teleoperation 구조 차이 분석
- [x] `Piper` robot plugin 등록
- [x] `PiperSlaveOnly` teleoperator 추가
- [x] teleop 녹화 중 `send_action()` no-op 처리로 CAN Master-Slave sync 충돌 방지
- [x] joint-space 기반 state/action을 end-effector absolute 좌표 기반으로 전환
- [x] `get_end_pose_raw()` 기반 EEF state/action 저장
- [x] 카메라 없는 EEF-only episode parquet 저장 확인
- [x] top-view/wrist-view RealSense 포함 녹화 확인
- [x] `--robot.use_cameras=false`로 카메라 없는 기록 지원
- [x] `--robot.discover_packages_path=lerobot_robot_piper` workaround 정리

### 3. 추론/제어 코드

- [x] V1 SDK와 V2 SDK 이중 CAN 연결 제거
- [x] `Piper` V2 SDK 단일 연결로 관측/제어 통합
- [x] `create_batch()`가 `robot.get_observation()` 한 번으로 EEF와 카메라를 모두 읽도록 수정
- [x] `PiperSDKInterface.zero_configuration()` 추가
- [x] Ctrl+C를 메인 스레드에서 처리하도록 추론 루프 정리
- [x] `piper-inference` CLI 추가
- [x] `smolvla-inference` CLI 추가
- [x] `piper-async-client` CLI 추가

### 4. SmolVLA 파이프라인 검증

- [x] `lerobot/pi0` 체크포인트와 LeRobot 0.4.0 호환성 문제 확인
- [x] `lerobot/pi0_base`는 로드 가능하나 Piper 실험 카메라 구성과 맞지 않아 우선 검증 모델에서 제외
- [x] `lerobot/smolvla_base`를 우선 검증 모델로 선택
- [x] `pick the pan` 작업 top-view 카메라 1대, 5 episode, 2170 frame 수집
- [x] expert layer만 fine-tuning, VLM backbone frozen
- [x] 5000 step, batch size 8, 약 12분 학습
- [x] loss 0.242에서 0.010으로 감소 확인
- [x] 녹화 데이터 기반 EEF action clamp 적용
- [x] 실제 PiPER에서 50 step 추론 오류 없이 실행 확인

---

## 현재 미해결 문제

### 데이터 신뢰성

- [ ] 저장된 EEF state가 실제 물리 궤적을 일관되게 반영하는지 검증 필요
- [ ] 비전 frame과 EEF/action timestamp 동기화 검증 필요
- [ ] 녹화된 episode를 replay 또는 분석해서 궤적 재현성을 확인해야 함
- [ ] top/wrist 다중 카메라 조건에서 frame 누락, warmup, timeout 재현성 확인 필요

### 모델/학습

- [ ] demonstration 5 episode만으로는 작업 성공률 평가가 불가능
- [ ] SmolVLA 성능 평가용 충분한 episode 수집 필요
- [ ] 작업 성공률, 실패 유형, 추론 안정성 기준 정의 필요
- [ ] `smolvla_inference.py`의 `ACTION_MIN` / `ACTION_MAX`가 하드코딩되어 있어 새 데이터셋마다 재계산 필요

### 대형 VLA 적용

- [ ] RTX 4070 Ti 단일 로컬 환경에서 pi0급 모델의 실시간 추론/제어 병목 해결 필요
- [ ] pi0 적용 전 action safety/clamp 정책을 더 명확히 해야 함
- [ ] policy server와 robot PC를 분리하는 async inference 검증 필요
- [ ] 네트워크 지연이 action chunk 처리와 제어 안정성에 미치는 영향 확인 필요

---

## 다음 작업 순서

### Phase 1. 데이터 검증

1. 저장된 LeRobotDataset에서 EEF state/action 범위와 all-zero frame 여부를 자동 검사한다.
2. 카메라 frame 수, timestamp, parquet index, video frame index 정합성을 점검한다.
3. 녹화 episode의 EEF 궤적을 plot하거나 replay해서 실제 teleop 움직임과 맞는지 확인한다.
4. 데이터셋별 EEF/action min/max를 계산하는 스크립트를 만든다.
5. `smolvla_inference.py`의 하드코딩된 clamp를 데이터셋 stats 기반으로 바꿀지 결정한다.

### Phase 2. SmolVLA 실험 확장

1. 평가 작업을 하나 확정한다.
2. top-view/wrist-view 사용 여부를 결정한다.
3. 충분한 demonstration episode를 수집한다.
4. SmolVLA fine-tuning 조건을 고정한다.
5. 실제 PiPER에서 반복 trial을 수행해 성공률과 실패 유형을 기록한다.

### Phase 3. 비동기 추론

1. 연구실 GPU 서버에 LeRobot async policy server 환경을 구성한다.
2. 로봇 PC에서 `piper-async-client`가 서버와 연결되는지 하드웨어 없이 확인한다.
3. action chunk 크기, queue threshold, 네트워크 지연을 모니터링한다.
4. 시뮬레이션 모드에서 action 범위와 지연 안정성을 먼저 확인한다.
5. 실제 PiPER에서 작은 `max_steps`로 검증한다.

### Phase 4. pi0/대형 모델 비교

1. pi0 모델과 Piper 데이터셋 feature/camera 구성 mismatch를 다시 점검한다.
2. async server 환경에서 pi0 로드와 추론 latency를 측정한다.
3. SmolVLA와 동일 작업/데이터 조건에서 학습 시간, 추론 안정성, 작업 성공률을 비교한다.
4. 데이터 효율적 fine-tuning 방법을 비교한다.

---

## 보류 또는 낮은 우선순위

- pi0 동기 로컬 추론: 코드 경로는 유지하지만, 로컬 RTX 4070 Ti 단일 환경에서 주 경로로 보지 않는다.
- `piper-inference`: 일반 LeRobot policy용 entrypoint로 보존한다. 현재 검증된 주 경로는 `smolvla-inference`다.
- LoRA-SP 스타일 temporal ensemble: `piper-inference`에 구현되어 있으나, 현재 SmolVLA 검증의 필수 요소는 아니다.
- `DECISION_PI0_COMPAT.md`: 과거 pi0 호환성 검토 메모로 보존하되, 문서 정리 단계에서 archive 여부를 결정한다.

---

## 실험 성공 기준 초안

| 항목 | 기준 |
|------|------|
| 데이터 유효성 | EEF all-zero frame 없음, state/action 범위가 실제 작업 공간 안에 있음 |
| 동기화 | parquet index와 video frame index가 누락 없이 대응 |
| 추론 안전성 | action clamp 후 값이 작업 데이터 범위 또는 사전 정의 안전 범위 안에 있음 |
| 제어 안정성 | 작은 `max_steps`에서 급격한 이동 없이 정지/복귀 가능 |
| 작업 성능 | 동일 초기 조건에서 반복 trial 성공률로 평가 |
| 모델 비교 | 학습 시간, VRAM 사용량, 추론 latency, 성공률을 함께 기록 |
