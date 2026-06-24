# 실험 로그

완료된 실험 기록과 시행착오를 보존하는 문서다. 앞으로 실행할 절차는 [EXPERIMENT.md](EXPERIMENT.md)에 둔다.

---

## 2026-05-28: wrist 카메라 설치 후 녹화 파이프라인 재검증

### 환경

- conda 환경: `piper`
- top 카메라: RealSense D435IF 시리얼 `327122074262`
- wrist 카메라: RealSense D435IF 시리얼 `243322071626`
- PiPER master-slave, `can0`

### 수행 내용

RealSense 시리얼 확인:

- 카메라 2대 정상 인식
- top: `327122074262`
- wrist: `243322071626`

Piper + 카메라 동시 연결:

- EEF non-zero 확인: `{'x.pos': 58050.0, 'y.pos': 2853.0, 'z.pos': 220777.0, ...}`
- top/wrist shape 모두 `(480, 640, 3)` 정상

`PiperSlaveOnly` no-op 검증:

- `send_action returned: True`
- `obs == action: True`
- 위험 D 없음 확인

실제 녹화:

- 3 episode
- top + wrist 카메라 동시 녹화
- 저장 경로: `/home/ugrp308/Group43/datasets/piper-test`
- episode당 약 370 frame
- 오른쪽 화살표 키로 조기 종료, 약 12초
- SVT-AV1 코덱으로 mp4 정상 인코딩 완료

### 발견 사항

데이터셋 저장 경로:

- 기본값 `~/.cache/huggingface/lerobot/` 대신 `--dataset.root`로 `/home/ugrp308/Group43/datasets/` 지정
- README, EXPERIMENT.md 명령어를 실제 시리얼 번호 및 경로로 업데이트

카메라 미리보기:

- `preview_camera.py`로 top/wrist 좌우 병렬 표시
- matplotlib TkAgg backend 사용
- top은 작업 공간 전체, wrist는 gripper 시점의 파지 대상 close-up 확인

PiPER SDK V2 원점 복귀:

- `ReqMasterArmMoveToHome(mode)` 확인 (`piper_interface_v2.py:3659`)
- `mode=0`: master-slave 모드 복원
- `mode=1`: master arm 원점 복귀
- `mode=2`: master + slave 둘 다 원점 복귀

---

## 2026-05-07: SmolVLA 파이프라인 전체 검증

### 환경

- conda 환경: `piper`
- LeRobot 0.4.0
- SmolVLA: `lerobot/smolvla_base`, 450M
- top 카메라 단독: RealSense D435IF, 시리얼 `327122074262`
- PiPER single arm, `can0`

### 수행 내용

녹화:

- 작업: `pick the pan`
- top 카메라 1대
- 5 episode, 2170 frame
- dataset repo id: `local/piper-smolvla`

Fine-tuning:

- 명령: `lerobot-train --policy.type=smolvla --policy.pretrained_path=lerobot/smolvla_base`
- expert layer만 학습: 100M / 450M
- VLM frozen
- 5000 steps
- batch size 8
- 약 12분 소요
- loss: 0.242 -> 0.010

추론:

- `smolvla-inference`로 실제 로봇 연결
- 녹화 데이터 EEF 범위 기반 action clamp 적용
- 50 steps 정상 동작 확인
- 에러 없음
- 결과: 로봇이 움직이나 팬 근처까지 안정적으로 도달하지는 못함
- 판단: 5 episode로는 데이터 부족

### 발견 사항

정책 전환:

- `lerobot/pi0`은 v0.1 포맷이라 LeRobot 0.4.0과 호환 안 됨
- `lerobot/pi0_base`는 호환되지만 ALOHA 기준 카메라 3개를 요구해 Piper 단일 카메라 구성과 mismatch
- `lerobot/smolvla_base`로 전환
- SmolVLA는 카메라 key 이름에 무관하게 dataset metadata 기반으로 자동 설정

카메라 warmup:

- `warmup_s=0`이면 추론 스크립트에서 `async_read` timeout 발생
- connect 후 `time.sleep(8.0)` 추가로 해결
- 재연결 시 간헐적 timeout은 재시도로 해결 가능

학습 방식:

- `train_expert_only=True`가 기본값
- VLM은 frozen, expert만 학습
- 소량 데이터에서는 이 방식이 적절
- 데이터가 충분해지면 LoRA로 VLM 일부 학습을 고려

---

## 2026-04-29: PiPER 단독 arm 테스트

### 환경

- conda 환경: `piper`
- LeRobot 0.4.0
- `piper_sdk` OK
- torch 2.7.1+cu126
- 카메라 없음
- master arm 없음
- slave arm 단독 테스트

### 발견 사항

CAN 첫 프레임:

- CAN 첫 프레임 도착 전 `get_status_deg()` 첫 호출이 전부 0 반환
- 0.5초 대기 후 정상값 수신
- 위험 A 재확인

`zero_configuration()`:

- `skip_enable=False`로 `EnablePiper()` 호출 시 servo on
- arm이 `CAN_CTRL` 모드였으나 SDK `JointCtrl` 명령도 CAN으로 전달되어 정상 동작
- master arm 없이 단독 테스트할 때는 `skip_enable=True` 권장
- `DisablePiper()` -> `DisableArm(7)` 호출로 servo 해제 확인

LeRobot plugin 등록:

- `--robot.type=piper` 단독 사용 시 `invalid choice` 오류 발생
- `--robot.discover_packages_path=lerobot_robot_piper` 필요
- teleoperator도 동일하게 discover path 필요
- `register_third_party_devices()`는 `main()` 안에서 호출되어 draccus parsing 후 실행되므로 효과 없음
- `parser.wrap()`의 `load_plugin()` 메커니즘으로 parsing 전에 로드해야 함

녹화:

- `use_cameras=false` 옵션으로 카메라 없이 EEF만 녹화 가능하도록 추가
- episode 데이터가 단일 parquet 파일에 저장됨
- `episode_index` 컬럼으로 episode 구분
- 오른쪽 화살표 키로 episode 조기 종료
- 왼쪽 화살표 키로 재녹화
- ESC로 전체 종료
- 키 안내 메시지는 LeRobot 기본 동작에서도 출력되지 않음

---

## 완료 체크리스트 기록

| 항목 | 상태 |
|------|------|
| 패키지 import | 완료 |
| robot/teleop plugin import | 완료 |
| config 기본값 확인 | 완료 |
| SDK 연결 및 EEF non-zero 확인 | 완료 |
| teleop EnablePiper skip 확인 | 완료 |
| `zero_configuration()` 확인 | 완료 |
| EEF 연속 읽기 확인 | 완료 |
| OpenCV 카메라 인덱스 확인 | 완료 |
| Piper + 카메라 + EEF 관측 확인 | 완료 |
| RealSense 시리얼 확인 | 완료 |
| `send_action()` no-op 및 cache 검증 | 완료 |
| 실제 녹화 | 완료 |
| 추론 시뮬레이션 | 완료 |
| 실제 SmolVLA arm 추론 | 완료 |
| async 의존성 설치 | 미완료 |
| PolicyServer 기동 | 미완료 |
| 비동기 추론 시뮬레이션 | 미완료 |
| 실제 arm 비동기 추론 | 미완료 |
