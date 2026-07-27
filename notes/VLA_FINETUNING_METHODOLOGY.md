# VLA Model Fine-Tuning Methodology for Piper Robot

## 1. Overview

이 문서는 `piper` 로봇의 '도형 지우기' 과업 수행을 위해, 언어 조건부 VLA(Vision-Language-Action) 모델을 파인튜닝하는 방법론을 정의합니다. 모든 실험은 `lerobot` 프레임워크를 기반으로 하며, 수집된 로봇 시연 데이터셋을 활용합니다.

본 방법론의 목표는 **두 개의 후보 모델(`smolvla`, `Octo`)**과 **두 가지 최신 파인튜닝 기법(`LoRA`, `DoRA`)**을 조합하여, 우리 과업에 가장 최적화된 조합을 실험적으로 찾아내는 것입니다.

---

## 2. Core Fine-Tuning Pipeline

모든 실험은 아래의 4단계 파이프라인을 공통으로 따릅니다.

### Step 1: Data Collection
- **스크립트**: `scripts/5__record.sh`
- **프로세스**: `piper_leader`를 이용한 원격 조종으로, `piper_follower`가 화이트보드의 다양한 도형을 지우는 전문가 시연을 녹화합니다.
- **결과물**: `(관측, 행동)` 시계열 데이터가 포함된 원본 `lerobot` 데이터셋.

### Step 2: Data Preprocessing (Language-Conditioning)
- **목표**: 원본 데이터셋에 VLA 모델 훈련을 위한 텍스트 명령을 주입합니다.
- **스크립트**: `scripts/tools/add_language_command.py` (신규 생성 필요)
- **프로세스**:
    1. 각 에피소드의 첫 프레임을 GUI로 시각화합니다.
    2. 해당 에피소드에서 수행된 과업을 설명하는 자연어 명령을 터미널을 통해 입력받습니다. (예: "erase the circle on the left")
    3. `smolvla` 또는 `Octo`가 사용하는 VLM과 동일한 토크나이저(Tokenizer)를 사용하여, 입력된 텍스트를 `input_ids`와 `attention_mask`로 변환합니다.
    4. 변환된 토큰 정보를 `observation.language_tokens`와 `observation.language_attention_mask`라는 새로운 컬럼으로 데이터셋에 추가하고, 새 경로에 저장합니다.
- **결과물**: VLA 모델 훈련에 즉시 사용할 수 있는, 언어 주석이 포함된 최종 데이터셋.

### Step 3: Model Fine-Tuning
- **목표**: 2단계에서 가공된 데이터셋을 사용하여, 사전 훈련된 VLA 모델을 특정 파인튜닝 기법으로 학습시킵니다.
- **스크립트**: `scripts/7__train.sh` (또는 목적에 맞게 복사/수정된 버전)
- **프로세스**: `POLICY_TYPE`과 파인튜닝 옵션을 변경하여 각 실험을 실행합니다. (상세 내용은 `4. Experimental Matrix` 참조)

### Step 4: Inference & Evaluation
- **목표**: 파인튜닝된 모델의 실제 성능을 평가합니다.
- **스크립트**: `scripts/legacy_tools/piper_validate.py` 또는 `scripts/legacy_tools/piper_tui.py`
- **프로세스**: `--task` 인자로 텍스트 명령을 전달하여, 훈련된 모델이 실제 로봇 또는 시뮬레이션 환경에서 명령을 올바르게 수행하는지 확인합니다.

---

## 3. Candidate Models & FT Methodologies

본 프로젝트는 파이프라인의 수정 없이, `lerobot` 프레임워크와의 호환성을 최우선으로 고려하여 후보 모델과 파인튜닝 기법을 선정했습니다.

### 3.1. Candidate Models

#### 선정 기준
- **`lerobot` 네이티브 호환성:** 별도의 아키텍처 수정이나 복잡한 통합 과정 없이, `POLICY_TYPE` 변경만으로 즉시 사용할 수 있어야 함.
- **VLA 아키텍처:** 언어 명령(`language_command`)을 입력받아 로봇 행동을 출력할 수 있는 Vision-Language-Action 모델이어야 함.
- **사전 훈련 모델 존재:** 처음부터 학습하는 것이 아닌, 파인튜닝을 통해 효율적으로 성능을 달성할 수 있는 고품질의 사전 훈련 가중치가 공개되어 있어야 함.

#### 후보 1: `smolvla`
- **선정 이유:** **우리 코드베이스의 기본 정책(`POLICY_TYPE=smolvla`)으로 이미 설정되어 있는 모델**입니다. Hugging Face가 `lerobot` 프레임워크를 위해 직접 포팅한 버전으로, 호환성이 100% 보장되는 가장 확실한 출발점입니다.
- **장점:**
    - **완벽한 통합:** 프레임워크와 완벽하게 통합되어 있어, 어떠한 코드 수정도 없이 안정적으로 파이프라인을 실행할 수 있습니다.
    - **효율성 중심 설계:** Stanford SmallVLA의 철학을 계승하여, 실제 로봇 환경에서의 빠른 추론 속도와 낮은 리소스 사용을 목표로 설계되었습니다.
    - **명확한 기준점:** 현재 시스템의 성능을 측정하고 다른 모델과 비교하기 위한 가장 이상적인 베이스라인 역할을 합니다.

#### 후보 2: `Octo`
- **선정 이유:** `lerobot` 생태계의 **사실상 표준(de-facto standard)이자 가장 대표적인 범용(Generalist) VLA 모델**입니다. `smolvla`와 동일하게 `POLICY_TYPE` 변경만으로 즉시 적용 가능하여, 공정한 성능 비교가 가능한 최고의 대안입니다.
- **장점:**
    - **압도적인 일반화 성능:** 수십 종류의 로봇과 수백 개의 과업으로 구성된 대규모 데이터셋(RT-X)으로 사전 훈련되어, 물리 세계에 대한 깊은 '상식'을 내재하고 있습니다. 이는 우리의 특정 과업을 더 빠르고 견고하게 학습할 잠재력이 높음을 의미합니다.
    - **유연한 확장성:** `octo-small`, `octo-base` 등 다양한 크기의 모델이 제공되어, 필요에 따라 모델의 성능과 리소스 사용량 사이의 트레이드오프를 조절할 수 있습니다.
    - **활발한 커뮤니티:** 가장 널리 사용되는 모델인 만큼, 관련 문서, 예제, 커뮤니티의 지원을 받기 용이합니다.

### 3.2. Fine-Tuning (FT) Methodologies

#### 선정 기준
- **파라미터 효율성 (Parameter-Efficiency):** 사전 훈련된 모델의 수억 개에 달하는 모든 파라미터를 업데이트하는 대신, 극소수의 파라미터만 학습하여 GPU 메모리 사용량을 줄이고 훈련 속도를 높여야 합니다.
- **성능 극대화:** 원본 모델이 가진 유용한 지식을 보존하면서(치명적 망각 방지), 우리의 데이터에 대한 성능을 최대로 끌어올릴 수 있어야 합니다.
- **적용 용이성:** Hugging Face `PEFT` 라이브러리를 통해 지원되어, 복잡한 코드 수정 없이 훈련 스크립트의 옵션 변경만으로 쉽게 적용할 수 있어야 합니다.

#### 방법론 1: `LoRA` (Low-Rank Adaptation)
- **선정 이유:** 파라미터 효율적 파인튜닝(PEFT) 분야에서 **가장 널리 알려지고 검증된 표준적인 방법론**입니다. 모든 최신 기법들의 성능을 비교하기 위한 필수적인 베이스라인 역할을 합니다.
- **장점:**
    - **검증된 안정성:** 수많은 연구와 실제 사례를 통해 그 효과와 안정성이 입증되었습니다.
    - **빠른 훈련:** 원본 가중치를 고정한 채, 모델의 각 레이어에 추가된 작은 '어댑터'만 훈련하므로 매우 빠릅니다.

#### 방법론 2: `DoRA` (Weight-Decomposed Low-Rank Adaptation)
- **선정 이유:** **LoRA의 단점을 개선하여 더 높은 성능을 달성하는, 2026년 현재 가장 진보된 SOTA(State-of-the-Art) 방법론**입니다. `PEFT` 라이브러리에 통합되어 있어 LoRA와 동일한 방식으로 쉽게 적용할 수 있으므로, 비교 실험을 하지 않을 이유가 없습니다.
- **장점:**
    - **우수한 성능:** LoRA가 학습 방향과 크기를 함께 업데이트하는 것과 달리, DoRA는 가중치를 '방향'과 '크기'로 분해하여 '방향'을 더 정교하게 학습합니다. 이로 인해 동일한 조건에서 LoRA보다 더 높은 최종 성능을 달성하는 것으로 알려져 있습니다.
    - **안정적인 학습 과정:** 학습 과정이 더 안정적이며, 하이퍼파라미터 변화에 덜 민감하여 튜닝이 용이합니다.
    - **손쉬운 업그레이드:** `peft_method` 옵션을 'lora'에서 'dora'로 바꾸는 것만으로 LoRA의 모든 장점을 계승하면서 더 높은 성능을 기대할 수 있습니다.

---

## 4. Experimental Matrix & Execution Plan

아래 4가지 조합의 실험을 통해 최적의 방법론을 도출합니다.

**공통 환경 변수 설정:**
```bash
# 2단계에서 생성한, 가공된 데이터셋 경로
export DATASET_PATH="records/local/processed_data_lang_v1"
# 모든 훈련 결과가 저장될 기본 폴더
export OUTPUT_DIR_BASE="training_outputs"
```

### 4.1. smolVLA + LoRA (Baseline)

`lerobot`과 `smolvla`의 기본 조합에 표준적인 LoRA를 적용합니다.

```bash
lerobot-train \
    --policy.type="smolvla" \
    --dataset.repo_id="${DATASET_PATH}" \
    --output_dir="${OUTPUT_DIR_BASE}/smolvla_lora" \
    --training.use_peft=true \
    --training.peft_method="lora" \
    --training.lora.rank=8 \
    --training.lora.alpha=16 \
    --training.learning_rate=1e-5 \
    --training.num_epochs=10 \
    --device="cuda" \
    --num_processes=2
```

### 4.2. smolVLA + DoRA (Recommended for `smolvla`)

`smolvla`에 최신 DoRA 기법을 적용하여 성능을 극대화합니다.

```bash
lerobot-train \
    --policy.type="smolvla" \
    --dataset.repo_id="${DATASET_PATH}" \
    --output_dir="${OUTPUT_DIR_BASE}/smolvla_dora" \
    --training.use_peft=true \
    --training.peft_method="dora" \
    --training.lora.rank=16 \
    --training.lora.alpha=32 \
    --training.learning_rate=1e-5 \
    --training.num_epochs=10 \
    --device="cuda" \
    --num_processes=2
```

### 4.3. Octo + LoRA (Alternative Baseline)

범용 모델 `Octo`에 표준 LoRA를 적용하여 `smolvla`와의 성능을 비교합니다.

```bash
lerobot-train \
    --policy.type="octo" \
    --from_pretrained="google/octo-small-1.5" \
    --dataset.repo_id="${DATASET_PATH}" \
    --output_dir="${OUTPUT_DIR_BASE}/octo_lora" \
    --training.use_peft=true \
    --training.peft_method="lora" \
    --training.lora.rank=8 \
    --training.lora.alpha=16 \
    --training.learning_rate=1e-5 \
    --training.num_epochs=10 \
    --device="cuda" \
    --num_processes=2
```

### 4.4. Octo + DoRA (Recommended for `Octo`)

범용 모델 `Octo`에 최신 DoRA 기법을 적용하여 잠재력을 최대로 끌어냅니다.

```bash
lerobot-train \
    --policy.type="octo" \
    --from_pretrained="google/octo-small-1.5" \
    --dataset.repo_id="${DATASET_PATH}" \
    --output_dir="${OUTPUT_DIR_BASE}/octo_dora" \
    --training.use_peft=true \
    --training.peft_method="dora" \
    --training.lora.rank=16 \
    --training.lora.alpha=32 \
    --training.learning_rate=1e-5 \
    --training.num_epochs=10 \
    --device="cuda" \
    --num_processes=2
```

---

## 5. Evaluation Criteria

각 실험 결과는 다음 기준에 따라 평가하여 최종 모델을 선정합니다.

- **정량적 평가:**
  - **과업 성공률 (Success Rate):** 주어진 텍스트 명령을 10회 반복 수행 시, 성공적으로 완료하는 비율. (예시)
  - **과업 완료 시간 (Task Completion Time):** 명령 시작부터 완료까지 걸리는 평균 시간.
- **정성적 평가:**
  - **움직임의 자연스러움 (Smoothness):** 로봇의 움직임이 덜컥거리거나 불안정하지 않고 부드러운가.
  - **명령 이해 능력 (Instruction Following):** "가장 작은 원" 또는 "오른쪽 위에 있는 사각형"과 같이 복잡하고 미묘한 뉘앙스의 명령을 얼마나 잘 이해하고 수행하는가.
  - **강건성 (Robustness):** 조명 변화나 약간의 위치 변화에도 작업을 안정적으로 수행하는가.

---