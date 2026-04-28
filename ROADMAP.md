# 로드맵

목표: Piper-to-Piper 마스터-슬레이브 텔레오퍼레이션 + LeRobotDataset 녹화 + VLA 추론 파이프라인 구축

---

## 파이프라인 개요

```
[1] 녹화  →  [2] 학습  →  [3] 추론
  (완료)     (외부 도구)    (완료)
```

---

## 현황

### [1] 녹화 — 완료

Piper-to-Piper 마스터-슬레이브 텔레오퍼레이션을 LeRobotDataset으로 녹화.

- [x] `Piper` 로봇이 `lerobot_robot_piper` 플러그인으로 등록 (`editable_mode=compat`으로 `pkgutil` 탐색)
- [x] `PiperSlaveOnly` 텔레오퍼레이터 등록 (`piper_slave_only`) — CAN 하드웨어 sync를 위한 패스스루
- [x] 액션 공간: 엔드이펙터 좌표 (raw SDK 정수, 0.001 mm / 0.001 도 단위) — LoRA-SP와 동일
- [x] `send_action()` — slave 모드에서 no-op으로 CAN 마스터-슬레이브 sync와 충돌 방지
- [x] `__init__` — 연결 시 `EmergencyStop` 및 `MotionCtrl_2` 강제 호출 제거
- [x] 카메라 두 개 지원: `top` / `wrist` — OpenCV(인덱스) 또는 RealSense(시리얼 번호) 선택 가능

**사용법:**
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

---

### [2] 학습 — 외부 도구 (이 패키지 범위 밖)

녹화된 데이터셋으로 표준 LeRobot 학습 진행. 별도 수정 불필요.

π0를 기본으로 사용. LoRA-SP fine-tuning은 학습 후 별도 적용.

```bash
lerobot-train \
    --policy.type=pi0 \
    --dataset.repo_id=local/piper-demo \
    --output_dir=outputs/piper-pi0
```

---

### [3] 추론 — 완료

학습된 VLA 정책을 실제 로봇에서 ~5Hz로 실행.

- [x] `PreTrainedConfig.from_pretrained`으로 정책 로드 (올바른 LeRobot 0.4.x API)
- [x] V2 SDK 단일 연결 — 이중 CAN 연결 문제 해결
- [x] `create_batch`가 `robot.get_observation()` 하나만 사용 — V1 SDK 중복 읽기 제거
- [x] `robot.send_action()`으로 제어 — 학습 데이터 포맷과 일관성 유지
- [x] `PiperSDKInterface.zero_configuration()` — V2 SDK 기반 안전한 시작/종료
- [x] Ctrl+C를 메인 스레드에서 처리 — 신뢰할 수 있는 비상 정지
- [x] `piper-inference` CLI 엔트리 포인트

**사용법 (OpenCV):**
```bash
piper-inference \
    --pretrained_path=outputs/piper-pi0/checkpoints/last/pretrained_model \
    --dataset_repo_id=local/piper-demo \
    --can_interface=can0 \
    --task="pick and place"
```

**사용법 (RealSense):**
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

## 미해결 사항 / 향후 과제

- [ ] 시간적 앙상블(temporal ensemble) 미구현 — LoRA-SP는 슬라이딩 윈도우 버퍼로 더 부드러운 액션 생성
- [ ] 추론 스크립트의 카메라 키 이름(`top`, `wrist`)이 하드코딩됨 — 데이터셋 메타데이터 기반으로 개선 필요
- [ ] `robot_utils.py`가 V1 SDK(`C_PiperInterface`)를 여전히 사용 — 호환성을 위해 유지하나 메인 파이프라인에서는 미사용
- [ ] LeRobot의 `async_inference` 서버/클라이언트 미연동
