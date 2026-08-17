# 비동기 추론 실험 설계: Sync / Sync discard / Async discard

## 1. 목적

최근 ACT 계열 후속 연구들은 단순히 “동기 vs 비동기”만 비교하는 대신, 세 가지 엄격한 환경으로 나누어 실험을 진행한다.

1. Sync
2. Sync discard
3. Async discard

이 분류는 지연이 실험 결과에 미치는 영향을 분리해서 볼 수 있게 해 주므로, 우리 프로젝트에서도 매우 적절하다.

목표는 다음과 같다.

- 모델의 순수 행동 생성 능력과 실시간 제어 적응성을 분리한다.
- 지연 때문에 실패한 것인지, 비동기 알고리즘 자체가 문제인지 판별한다.
- SmolVLA와 π0를 같은 조건에서 공정하게 비교한다.
- 실제 로봇 환경에서 가장 중요한 실시간 성능을 정량화한다.

---

## 2. 세 실험 환경의 정의

### 2.1 Sync

정의:

- 추론이 끝난 뒤 다음 chunk를 바로 실행한다.
- 로봇은 이전 chunk가 끝날 때까지 기다린다.
- 새 chunk가 도착할 때까지 제어가 멈춘다.

의미:

- 가장 단순한 동기 baseline
- 실시간 지연을 숨기지 않는 방식
- “사실상 inference pause를 허용하는 제어”

장점:

- 구현이 단순하다.
- 동기 baseline이므로 비교가 쉽다.

한계:

- 실제 로봇에서 pause가 생기므로, 학습 데이터와 다른 환경이 된다.
- 긴 지연에서는 task 성공률이 크게 떨어질 수 있다.

---

### 2.2 Sync discard

정의:

- 동기 방식이지만, 추론 지연을 반영해서 이미 지나간 timestep을 버린다.
- 즉, 추론 완료 시점에 이미 늦은 action은 discard 하고, 남은 부분만 실행한다.

의미:

- 동기 baseline을 “지연을 반영한 형태”로 바꾸어 비교하는 구조
- 지연 자체가 실험 성능을 왜곡하는 정도를 정량화할 수 있다.

장점:

- 동기와 비동기 사이의 차이를 더 잘 분리할 수 있다.
- 지연이 전체 문제인지 아니면 비동기 merge가 문제인지 판단할 수 있다.

한계:

- 실제 로봇에서는 여전히 pause가 존재한다.
- 여전히 chunk 경계에서 action continuity가 좋지 않을 수 있다.

---

### 2.3 Async discard

정의:

- 로봇은 이전 chunk를 계속 실행하면서, 새 chunk가 도착하면 기존 queue와 합친다.
- 이미 지나간 부분은 버리고, 남은 overlap 구간은 merge 또는 aggregate한다.
- 추론 지연은 실제로 반영되며, 동시에 행동 continuity를 유지한다.

의미:

- 가장 현실적인 실시간 로봇 제어 방식
- 현재 우리 프로젝트가 이미 구현하고 있는 형태와 가장 가깝다.

장점:

- inference pause를 줄인다.
- 로봇이 “생각하는 동안 움직이는” 구조를 유지한다.
- 실제 실시간 환경에 맞는 평가가 가능하다.

한계:

- action merge 정책이 잘못되면 chunk 경계 불연속이 생긴다.
- 지연이 길수록 보정이 중요해진다.

---

## 3. 왜 이 3모드 비교가 더 엄격한가

단순한 동기 vs 비동기 비교는 다음 문제를 가린다.

- 동기 방식이 실패한 이유가 모델 자체 때문인지
- 지연 때문인지
- 비동기 merge가 잘못되었는지

이 3모드 비교는 지연을 별도로 통제한다.

그래서 실제로는 다음을 분리해볼 수 있다.

1. 모델 자체의 행동 품질
2. 지연이 미치는 영향
3. 비동기 merge가 실제로 얼마나 좋은지

이것이 ACT 후속 연구에서 통제된 비교 방식을 채택하는 이유다.

---

## 4. 우리 프로젝트에서의 실험 구조

우리 프로젝트는 이미 다음 요소를 갖추고 있다.

- chunk queue 기반 제어 루프
- threshold-triggered 재추론
- `latency_align=True`
- `aggregate_fn=weighted_average`
- EMA / rate limit smoothing
- 안전 clamp (`send_action()` 내부)

즉, 현재 구현은 “Async discard”에 매우 가까운 구조다.

현재 구현을 기준으로 3모드 실험을 구성하면 다음과 같다.

| 모드 | 구현 아이디어 |
|---|---|
| Sync | 추론 완료를 기다린 뒤 다음 chunk 전송, queue flush |
| Sync discard | 동기 추론 후 지연된 앞부분 drop, 남은 부분만 실행 |
| Async discard | threshold 기반 queue 재추론 + latency align + aggregation 유지 |

이 구조는 프로젝트에서 바로 실험 가능한 상태다.

---

## 5. 비교 지표

다음 지표를 함께 기록해야 비교가 정당하다.

- 실제 control fps
- 평균 inference latency
- queue 길이 변화
- pending_steps / horizon 비율
- `[LAG]` 로그
- `[RATE]` 적용 횟수
- `[CLAMP]` 발생 횟수
- TV, RMS jerk
- task 성공률
- 완료 시간
- 실패 패턴

중요한 점은 latency만 보고 끝내면 안 된다는 것이다. 실제로는 다음을 함께 봐야 한다.

- 지연이 증가해도 action continuity가 유지되는가?
- 비동기 merge가 지연을 숨기면서 성공률을 올렸는가?
- 동기 baseline이 지연 때문에 생긴 문제를 비동기 방식이 실제로 해결했는가?

---

## 6. 추천 실험 매트릭스

### 6.1 모델별 비교

| 케이스 | 모델 | 환경 | trigger | aggregate | latency align | 목적 |
|---|---|---|---|---|---|---|
| A1 | SmolVLA | Sync | fixed | latest_only | off | 단순 baseline |
| A2 | SmolVLA | Sync discard | fixed | latest_only | off | 지연 반영 동기 baseline |
| A3 | SmolVLA | Async discard | threshold | weighted_average | on | 현재 현실적 방식 |
| B1 | π0 | Sync | fixed | latest_only | off | 단순 baseline |
| B2 | π0 | Sync discard | fixed | latest_only | off | 지연 반영 동기 baseline |
| B3 | π0 | Async discard | threshold | weighted_average | on | 현실적 비동기 방식 |

### 6.2 추가 ablation

| 케이스 | 환경 | 목적 |
|---|---|---|
| C1 | Async discard + latency_align off | 지연 보정 효과 확인 |
| C2 | Async discard + latest_only | 최신 예측 우선성 확인 |
| C3 | Async discard + weighted_average | 현재 기본형과의 비교 |

---

## 7. 실험 조건 권장값

우리 프로젝트의 현재 구조와 가장 잘 맞는 공통 기본값은 다음과 같다.

- `trigger_mode=threshold`
- `chunk_threshold=0.3`
- `latency_align=True`
- `aggregate_fn=weighted_average`
- `ema_alpha=0.2`
- `rate_limit=5.0`

동기 baseline에서는 이를 해제하거나, 같은 값으로 고정된 고정 간격으로 맞춘다.

이렇게 해야 다음이 보장된다.

- SmolVLA와 π0를 공정하게 비교 가능
- 시스템 지연을 분리해서 볼 수 있음
- 실물 로봇에서 현재 구현과 비교할 수 있음

---

## 8. 비교의 해석 방식

실험 결과를 해석할 때는 단순 평균만 보지 말고 아래 흐름으로 봐야 한다.

1. Sync baseline이 얼마나 나쁜가
2. Sync discard가 얼마나 개선되나
3. Async discard가 추가로 얼마나 개선되나
4. 왜 개선됐는지: 지연 보정, queue 유지, aggregation, smoothing 중 무엇이 효과적이었나

핵심은 “비동기 자체가 좋았다”가 아니라,

> 지연을 구조적으로 처리한 비동기 방식이 더 나은가?

를 판단하는 것이다.

---

## 9. 결론

이 3모드 비교는 단순한 동기/비동기 비교보다 훨씬 엄격하고, 실제 로봇 실시간 제어에 더 적합하다.

우리 프로젝트는 이미 비동기 제어 루프를 갖고 있으므로, 실험 설계만 추가하면 바로 실행 가능한 상태다.

즉,

- Sync: 단순 baseline
- Sync discard: 지연을 반영한 동기 baseline
- Async discard: 실시간을 보장하는 실제 비동기 방식

이 3개를 함께 보면, 지연과 비동기 알고리즘의 효과를 분리해서 볼 수 있다.

이것은 우리 프로젝트의 비교 실험을 더 설득력 있게 만드는 가장 적절한 구조다.

---

## 부록: 출처 및 개념 기원

이 3모드 실험 설계는 하나의 단일 논문에서 명시적으로 정의된 "표준"이라기보다, 다음 연구 흐름들을 종합한 것이다.

### ACT (Action Chunking with Transformers)

- **핵심 기여**: action을 chunk 단위로 예측하는 구조를 도입
- **문제 제기**: chunk 경계에서 동작이 끊기거나 겹치면 문제가 발생
- **이 설계와의 관계**: Sync/Sync discard/Async discard는 모두 ACT 구조에서 chunk를 이어 붙이는 방식을 비교하는 프레임

**참고**: 
- Zhao et al., "ACT: Action Chunking with Transformers" (2023)
- chunk 기반 policy 설계의 기원이자, 실시간 제어에서의 지연 문제를 명확히 함

### 실시간 제어 (Real-time Control) / 지연 대응 연구

- **일반 원칙**: 동기식 지연을 정량화하고 별도로 통제해야 함
- **표준 패턴**: 동기 baseline + 지연-반영 동기 baseline + 비동기 방식의 3단계 비교
- **이 설계와의 관계**: "Sync discard"는 지연을 반영한 동기 baseline으로, 순수 모델 성능과 시스템 지연을 분리하는 핵심 개념

**참고**:
- 이는 실시간 로봇 제어, 고주파 거래 시스템, 자율주행 등에서 널리 쓰는 비교 방법론
- 특정 논문보다는 실시간 제어 분야의 일반 관례

### PI RTC (Proportional Integral Real-Time Control) / Overlap-Aware Merging

- **핵심 기여**: 비동기 환경에서 chunk가 겹칠 때, 단순히 latest만 쓰지 말고 weighted average나 temporal ensemble로 smooth하게 merge
- **지연 처리**: 추론 지연(`latency_align`)을 반영해 이미 지나간 action은 버리고, 남은 부분만 실행
- **이 설계와의 관계**: "Async discard" 모드의 구현 패턴이며, queue 기반 제어와 EMA/rate limit 등의 smoothing이 여기서 온 아이디어

**참고**:
- 우리 프로젝트의 [docs/policy/smoothing.md](../policy/smoothing.md)에서 실측한 SmolVLA / π0 inference latency와 queue 거동
- PI RTC 스타일 구현은 고지연 환경에서 매우 효과적

### SmolVLA / π0 비교 실험의 맥락

- **SmolVLA**: 상대적으로 낮은 지연 (3~5 step)
- **π0**: 더 높은 지연 (5~6 step) + 더 강한 지연 대응 필요성

이 두 모델을 같은 조건에서 비교하려면, 시스템 지연을 별도로 통제해야 한다. 그래서 3모드 비교가 특히 중요하다.

**참고**:
- [docs/training/pi0_finetuning.md](../training/pi0_finetuning.md): π0 도입 과정에서 지연의 중요성 발견
- [docs/policy/async_inference_report.md](../policy/async_inference_report.md): SmolVLA vs π0의 async inference 패턴 분석

---

### 정리: 이 설계는 어디서 왔는가

| 요소 | 출처 | 우리 설계에서의 역할 |
|---|---|---|
| Chunk-based action prediction | ACT (2023) | 기본 구조 |
| 동기식 baseline + latency-aware 비교 | 실시간 제어 일반론 | Sync / Sync discard 설계 |
| Overlap-aware merge + latency alignment | PI RTC 패턴 | Async discard 구현 |
| Queue 기반 threshold trigger + EMA smoothing | 프로젝트 실측 최적화 | 현재 코드에 구현된 설정값 |

### 결론

이 3모드 실험 설계는 "한 논문의 표준"이 아니라, **ACT와 실시간 제어 연구들이 정립한 일반 원칙을 우리 프로젝트에 맞게 재구성한 것**이다.

특히 다음 조합이 효과적이다:

- ACT의 chunk 개념
- 실시간 제어의 지연 통제 패턴
- PI RTC의 overlap-aware merge
- 우리 프로젝트의 measured latency와 queue dynamics

따라서 이 설계는 학술적으로도 타당하고, 우리 프로젝트의 구현 현실과도 가장 잘 맞는 구조다. (개인적인 생각입니다)

