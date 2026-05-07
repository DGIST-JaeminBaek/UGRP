# pi0 체크포인트 호환성 — 의사결정 문서

작성일: 2026-05-07

---

## 문제의 본질

세 조각의 시간대가 어긋나 있다:

| 조각 | 시점 |
|------|------|
| `lerobot/pi0` 체크포인트 | 2025년 초, LeRobot v0.1~v0.2 시절 publish |
| 우리 LeRobot v0.4.0 + Piper 플러그인 | 2025년 중후반, plugin system 안정화 시점 |
| LeRobot main (v0.5.x) | 2026년 봄, OpenPI 전면 통합 + Python 3.12 강제 |

`lerobot/pi0` 체크포인트는 v0.1 시절 포맷으로 저장됐고, v0.4.0과 사이에 1년 가까운 진화가 끼어 있다.
**체크포인트와 라이브러리는 한 쌍이어야 하는데, 그 짝이 깨진 상태.**

---

## 겪은 에러들의 진짜 정체

모두 "v0.1 체크포인트를 v0.4.0으로 끌어오는 비용"에서 비롯됨:

1. **PI0Config 필드 불일치** — v0.1과 v0.4.0 사이에 PI0Config 스키마가 변경됨
   - `resize_imgs_with_padding`, `adapt_to_pi_aloha`, `proj_width` 등 10개 필드
   - 임시 해결: `config.json`에서 해당 필드 제거 (`.bak` 백업 있음)

2. **`policy_preprocessor.json` 없음** — v0.4.x에서 normalization을 모델 외부 processor로 분리
   - migration 스크립트(`migrate_policy_normalization.py`)로 해결 가능하나 추가 검증 필요

3. **앞으로 나올 가능성이 있는 문제들**
   - modeling_pi0.py가 옛 필드를 새 방식으로 처리 못 할 가능성
   - 가중치 구조 불일치 (missing/unexpected key)
   - silent 정규화 실패

각각이 독립된 호환성 단층. 하나 해결하면 다음 게 나오는 구조.

---

## 선택지

### (A) 호환성 패치를 끝까지 밀고 가기

Migration 실행 → PI0Config 패치 → modeling 코드 backport → 가중치 호환 검증.

- **장점**: 기존 환경(lerobot 0.4.0 + Piper 플러그인) 유지
- **단점**: 각 단계마다 silent failure 위험. 학습은 되지만 inference가 미묘하게 망가질 수 있음. 끝이 안 보임

### (B) Pretrained 포기, v0.4.0에서 from-scratch에 가깝게 학습

`lerobot/pi0` 체크포인트 없이 v0.4.0의 PI0를 처음부터 학습.
PaliGemma backbone은 자동 로드되지만 action expert는 처음부터.

- **장점**: 호환성 문제 전부 사라짐. 가장 단순
- **단점**: pi0의 10k+ 시간 robot 데이터 prior를 잃음. Piper 데이터셋이 충분히 크지 않으면 성능이 안 나올 수 있음
- **기준**: 에피소드 200개 이상이면 진지한 선택지, 50개 미만이면 prior가 중요해서 불리

### (C) OpenPI로 갈아타기

체크포인트와 코드의 짝이 깨지지 않은 환경. `pi0_base`/`pi05_base` 체크포인트와 OpenPI 코드가 함께 maintain됨.

- **장점**: 호환성 문제 전부 사라짐. LeRobotDataset 그대로 사용 가능. Piper 플러그인은 데이터 수집/teleop용으로 유지
- **단점**: 학습/inference 환경 분리 필요. 초기 세팅 비용
- **구조**: 데이터 수집은 lerobot 0.4.0 + Piper, 학습/inference는 OpenPI

LoRA-SP도 이 방식 (OpenPI 기반 자체 구현, lerobot은 변환 스크립트에서만 사용).

---

## 핵심 판단 기준

**"`lerobot/pi0`의 prior가 우리에게 그만큼 가치 있는가?"**

- **가치 있다** → (A) 또는 (C)
- **그렇게 결정적이지 않다** → (B)

현재 상태:
- (A)는 점점 비싸지고 있음
- (C)는 처음 보였던 것보다 비용이 작음
- (B)는 아직 진지하게 검토 안 됨

---

## 현재 상태

- `config.json` 수정본: 모르는 필드 제거, 원본은 `.bak`으로 백업
- `policy_preprocessor.json` migration: 미실행 (철회)
- 결정 보류 중
