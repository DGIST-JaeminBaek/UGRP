# smolVLA 파인튜닝 전략 제안 (고성능 환경: 2x RTX 5090)

## 1. 개요

본 보고서는 **고성능 컴퓨팅 자원(CPU: 7800X3D, RAM: 32GB, GPU: 2x RTX 5090)** 환경에서 Vision-Language-Action (VLA) 모델, 특히 `smolVLA`의 파인튜닝 전략을 제안한다. 기존의 자원 제약적 접근에서 벗어나, 보유한 하드웨어를 최대한 활용하여 **최고 성능을 달성하고 훈련 시간을 단축**하는 데 목표를 둔다.

---

## 2. 컴퓨팅 자원 분석 및 시사점

- **GPU**: **NVIDIA RTX 5090 2대**는 현재 사용 가능한 최상위 등급의 GPU로, 방대한 VRAM과 압도적인 연산 능력을 제공한다.
- **시사점**:
    - **메모리 제약 극복**: `smolVLA`와 같은 경량 모델의 전체 파라미터 파인튜닝(Full Fine-tuning)은 물론, 향후 더 큰 VLA 모델을 훈련하기에도 충분한 환경이다.
    - **훈련 속도 극대화**: 2개의 GPU를 활용한 병렬 처리(Data Parallelism)를 통해 훈련 시간을 획기적으로 단축할 수 있다. 큰 배치 사이즈(Batch Size)를 사용하여 학습을 안정적이고 빠르게 진행할 수 있다.
    - **전략의 변화**: 더 이상 '가능하게' 하는 것이 아니라, '어떻게 최고 성능을 뽑아낼 것인가'에 초점을 맞출 수 있다.

---

## 3. 핵심 접근법: 아키텍처 수준의 논의

'아키텍처(Architecture)'는 AI 모델의 '내부 설계도'이자 '뇌 구조'를 의미합니다. 따라서 '아키텍처 수준의 논의'는 모델을 단순히 '데이터를 넣으면 결과가 나오는 마법의 상자(블랙박스)'로 취급하지 않고, "모델의 내부 구조가 어떻게 이루어져 있으니, 우리 하드웨어 상황에 맞춰 어느 부위만 타겟팅해서 수술(학습)할 것인가?"를 분석하는 핵심적인 엔지니어링 과정입니다.

`smolVLA`를 예시로 두 접근법을 명확히 비교할 수 있습니다.

> **1. 단순한 논의 (블랙박스 관점)**
> - **접근법**: "파이퍼 로봇으로 화이트보드 지우는 데이터를 모아서 SmolVLA에 넣고 학습률 0.001로 파인튜닝하자."
> - **한계**: 이처럼 모델 전체를 통째로 튜닝하려 할 경우, 32GB 시스템 RAM의 한계로 인해 OOM(Out Of Memory) 에러가 발생하여 프로젝트가 중단될 수 있습니다.

> **2. 아키텍처 수준의 논의 (해부학적 관점)**
> - **접근법**: "SmolVLA의 뇌 구조(아키텍처)를 뜯어보니 크게 두 부위로 나뉜다. 눈과 언어를 담당하는 **VLM(Vision-Language Model)**이 있고, 여기서 나온 정보를 바탕으로 로봇의 손을 움직이는 **DiT(Diffusion Transformer)**가 있다."
> - **전략 도출**: "화이트보드나 지우개의 형태는 VLM이 이미 잘 알고 있으니 VLM 부위는 가중치를 동결(Freeze)하자. 대신, 화이트보드에 지우개를 문지르는 마찰력과 같은 새로운 물리 법칙은 모델이 처음 겪는 것이므로, 행동을 생성하는 DiT 부위에만 DoRA 등을 적용하여 집중적으로 학습시키자."

따라서 본 보고서의 4단계 로드맵은 바로 이 아키텍처 수준의 논의에 기반한 정밀한 '수술 계획'입니다. "모델의 어느 장기를 얼리고, 어느 장기를 열어서 파라미터를 업데이트할지"에 대한 구조적인 튜닝 전략을 제시합니다.

---

---

## 4. 파인튜닝 핵심 이론: PEFT와 주요 논문들

본 보고서에서 제안하는 파인튜닝 전략들은 **PEFT(Parameter-Efficient Fine-Tuning)** 라는 최신 경량화 튜닝 기법에 깊이 뿌리내리고 있습니다. PEFT는 사전 학습된 거대 모델의 전체 파라미터를 모두 미세조정하는 'Full Fine-tuning' 방식의 막대한 컴퓨팅 자원 소모와 시간 문제를 해결하기 위해 등장했습니다. 핵심 아이디어는 **모델의 원본 가중치는 대부분 동결(freeze)시킨 채, 극소수의 추가 파라미터만을 학습**하여 원본 모델의 성능을 특정 태스크에 맞게 효율적으로 '적응(Adaptation)'시키는 것입니다.

아래는 우리 로드맵의 기반이 되는 가장 중요하고 검증된 PEFT 관련 논문 2편에 대한 요약입니다.

### 1. LoRA: Low-Rank Adaptation of Large Language Models

-   **저자**: Edward J. Hu, et al. (Microsoft)
-   **링크**: [https://arxiv.org/abs/2106.09685](https://arxiv.org/abs/2106.09685)
-   **한 줄 요약**: "거대 모델의 가중치를 직접 수정하는 대신, 그 '변화량'만을 저차원(Low-Rank) 행렬로 근사하여 학습함으로써 파라미터 효율을 극대화하자."

#### 핵심 아이디어
파인튜닝 시 모델 가중치의 변화량(ΔW)은 매우 낮은 '내재적 차원(intrinsic dimension)'을 갖는다는 가설, 즉 변화의 본질은 몇 개의 핵심 축으로만 설명될 수 있다는 아이디어에서 출발합니다. 따라서 거대한 변화량 행렬 `ΔW`를 두 개의 훨씬 작은 '저차원(Low-Rank)' 행렬 `B`와 `A`의 곱 (`ΔW = B * A`)으로 분해하여 근사할 수 있다고 보았습니다.

#### 방법론
1.  **가중치 동결**: 사전 학습된 원본 모델의 가중치 `W`는 훈련 내내 완전히 동결합니다.
2.  **LoRA 행렬 주입**: Transformer의 각 레이어에 학습 가능한 두 개의 작은 행렬 `A`와 `B`를 추가합니다.
3.  **변화량 학습**: 훈련 시에는 오직 `A`와 `B` 행렬만 업데이트합니다.
4.  **연산**: 최종적으로 `h = Wx + (B * A)x` 와 같이 원본 가중치를 통과한 결과에 LoRA를 통과한 결과가 더해집니다.

#### 주요 결과 및 의의
-   **압도적인 파라미터 효율**: 전체 파라미터의 0.01% 수준만으로 Full Fine-tuning과 거의 동등한 성능을 달성했습니다.
-   **빠른 태스크 전환**: 원본 모델은 공유하고, 태스크별로 수십 MB 크기의 LoRA 가중치만 교체하면 되므로 저장 공간과 배포 효율성이 극대화됩니다.
-   PEFT 시대의 서막을 연 논문으로, 거대 모델의 활용성을 대중에게 크게 넓혔습니다. `[전략 3]`의 기반이 됩니다.

---

### 2. DoRA: Weight-Decomposed Low-Rank Adaptation

-   **저자**: Shih-Yang Liu, et al. (NVIDIA, University of California)
-   **링크**: [https://arxiv.org/abs/2402.09353](https://arxiv.org/abs/2402.09353)
-   **한 줄 요약**: "LoRA가 가중치의 '크기(Magnitude)'와 '방향(Direction)'을 함께 학습하는 문제를 해결하기 위해, 이 둘을 명시적으로 분해하여 따로 학습시키자."

#### 핵심 아이디어
LoRA가 `W' = W + ΔW` 방식으로 가중치의 '크기'와 '방향'을 뒤섞어버리는 문제를 지적합니다. DoRA는 가중치 `W`를 **크기 `m`**과 **방향 `V`**의 곱 (`W = m * V`)으로 분해하고, 이 둘을 독립적으로 파인튜닝하여 더 정교한 적응을 꾀합니다.

#### 방법론
1.  **가중치 분해**: 사전 학습된 가중치 `W`를 스칼라 값인 크기 `m`과 단위 벡터인 방향 `V`로 분해합니다.
2.  **독립적 학습**: 크기 변화량(`Δm`)과 방향 변화량(`ΔV`)을 별도로 학습합니다. 이때 방향 변화량 `ΔV`를 학습하기 위해 **LoRA를 사용**합니다.
3.  **재결합**: 최종 가중치는 `W' = (m + Δm) * (V + B * A)` 로 계산됩니다. LoRA가 '방향' 조정에만 집중하도록 역할을 분리한 것입니다.

#### 주요 결과 및 의의
-   **성능 향상**: LoRA와 동일한 학습 파라미터 수로 더 높은 성능을 보였으며, 특히 학습 파라미터가 매우 적은 상황에서 성능 격차가 더 크게 나타났습니다.
-   **안정적인 훈련**: 학습 과정이 더 안정적이며 빠르게 수렴하는 경향을 보입니다.
-   LoRA의 자연스러운 진화형으로 평가받으며, `[전략 2]`의 기반이 됩니다.

---

---

---

## 5. 왜 이 전략들을 선택했는가? (전략적 당위성)

SVD 기반 가중치 교체와 같은 혁신적인 연구 방법론도 존재하지만, 본 보고서가 **DiT 전면 학습, LoRA, DoRA**를 핵심 전략으로 채택한 데에는 명확한 이유가 있습니다. 이는 현재 우리의 목표 달성을 위한 가장 **현실적이고, 빠르며, 신뢰도 높은** 접근법이기 때문입니다.

#### 1. 검증된 신뢰성과 낮은 리스크

-   **LoRA와 DoRA는** 학계와 산업계에서 수없이 검증된, **사실상의 업계 표준(Industry Standard) PEFT 기법**입니다. 이는 우리가 '미지의 기술을 탐험'하는 리스크를 감수하는 대신, '보장된 성능의 청사진'을 기반으로 안정적인 개발을 진행할 수 있음을 의미합니다.
-   반면, SVD 기반 방법론은 'Task'와 'Domain' 성분을 분리하는 핵심적인 클러스터링 과정에 대한 명확한 해답이 없는 연구 단계의 기술입니다. 성공 시 잠재력은 크지만, 실패 확률 또한 높은 '고위험 고수익(High-risk, High-return)' 접근법입니다.

#### 2. 즉각적인 구현과 빠른 실험 반복

-   우리가 선택한 전략들은 **Hugging Face의 `peft`와 `accelerate` 라이브러리를 통해 즉시 구현 가능**합니다. 이는 우리가 '파인튜닝 도구를 만드는 시간'을 낭비하는 대신, **'파인튜닝 실험 자체'**에 온전히 집중할 수 있게 해줍니다.
-   비유하자면, "엔진을 튜닝하기 위해 직접 스패너와 렌치를 만드는 것"이 아니라, "최고급 공구 세트를 가지고 바로 튜닝 작업을 시작"하는 것과 같습니다. 이를 통해 우리는 더 많은 가설을 더 빠르게 검증하고, 프로젝트의 진척 속도를 극대화할 수 있습니다.

#### 3. 유연하고 실용적인 문제 해결 능력

-   제시된 4가지 전략은 각기 다른 문제 상황을 해결하기 위한 **'상황별 전술 카드'**와 같습니다.
    -   **데이터가 충분할 때:** `전략 1` (DiT 전면 학습)로 최고의 성능을 노립니다.
    -   **데이터가 부족하거나 과적합이 발생할 때:** `전략 2/3` (DoRA/LoRA)로 경량화 튜닝을 시도합니다.
    -   **모델의 시각 인지 자체에 문제가 있을 때:** `전략 4` (VLM LoRA)로 '눈'을 교정합니다.
-   이러한 유연성은 프로젝트 진행 중 마주할 수 있는 다양한 기술적 난관에 효과적으로 대응할 수 있는 강력한 무기입니다.

결론적으로, 우리가 채택한 전략들은 **성능, 구현 속도, 리스크 관리**라는 세 가지 핵심 요소를 가장 균형 있게 만족시키는 최적의 선택입니다. 먼저 이 검증된 방법들로 강력한 베이스라인을 구축한 뒤, 더 나아가 혁신적인 연구 방법론을 탐색하는 것이 가장 이상적인 순서입니다.

---

## 6. 기본 코드 분석 및 아키텍처 튜닝 구현 방법론

'아키텍처 수준의 튜닝'을 실제로 구현하기 위해, 먼저 프로젝트에 포함된 기본 학습 코드를 분석하고 이를 어떻게 활용할지 구체적인 실행 계획을 수립합니다.

### 1. 기본 학습 실행 코드 분석 (`7__train.sh`)

프로젝트의 `scripts/7__train.sh` 파일은 `lerobot-train`이라는 명령어를 다양한 인자와 함께 실행하는 '런처(Launcher)' 역할을 합니다. 이는 `lerobot` 라이브러리가 제공하는 기본 학습 기능의 진입점이 `lerobot-train`임을 의미합니다.

### 2. 핵심 코드의 위치: 외부 라이브러리 `lerobot`

`pyproject.toml` 파일을 통해 우리 프로젝트가 `lerobot>=0.3.0` 라이브러리에 의존하고 있음을 확인했습니다. 이는 `lerobot-train` 명령어가 우리 프로젝트 내부 코드가 아닌, 설치된 외부 라이브러리에 포함된 기능이라는 것을 의미합니다. 따라서 라이브러리 코드를 직접 수정하는 대신, 라이브러리가 제공하는 기능(API)을 활용하는 새로운 스크립트를 작성하는 것이 올바른 접근 방식입니다.

### 3. 올바른 구현 접근법: 새로운 학습 스크립트 작성

`lerobot` 라이브러리가 제공하는 `make_policy` (모델 로딩), `LeRobotDataset` (데이터 로딩) 등의 구성요소를 활용하여, 우리의 필요에 맞게 파라미터를 '수술'하는 새로운 파이썬 학습 스크립트를 작성합니다. 아래는 이 접근법에 따라 `[전략 1: VLM 동결 + DiT 전면 학습]`을 구현하는 예시 코드입니다.

#### `scripts/train_dit_full.py` 구현 예시

```python
import torch
from accelerate import Accelerator
from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
from lerobot.common.policies.factory import make_policy

def main():
    # 1. Multi-GPU 및 혼합 정밀도 지원을 위한 Accelerator 초기화
    accelerator = Accelerator()

    # 2. lerobot 라이브러리를 사용해 데이터셋 로드
    dataset = LeRobotDataset("local/piper_write_light")
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=32)

    # 3. lerobot 라이브러리를 사용해 smolVLA 모델 로드
    policy = make_policy("smolvla")

    # 4. 아키텍처 '수술': VLM(backbone)을 동결
    print("Freezing VLM (backbone)...")
    for name, param in policy.named_parameters():
        if 'backbone' in name:
            param.requires_grad = False

    # 5. 학습할 파라미터(DiT)만 필터링하여 옵티마이저에 전달
    trainable_params = filter(lambda p: p.requires_grad, policy.parameters())
    optimizer = torch.optim.AdamW(trainable_params, lr=1e-4)

    # 6. Accelerate를 통해 훈련 환경 준비
    policy, optimizer, dataloader = accelerator.prepare(
        policy, optimizer, dataloader
    )

    # 7. 기본 훈련 루프
    policy.train()
    num_epochs = 10 # 예시
    for epoch in range(num_epochs):
        for batch in dataloader:
            # policy.forward()는 loss를 반환하도록 설계되어 있음
            loss = policy(batch)
            accelerator.backward(loss)
            optimizer.step()
            optimizer.zero_grad()
            if accelerator.is_main_process:
                print(f"Epoch {epoch}, Loss: {loss.item()}")

    # 8. 모델 저장 (Multi-GPU 환경 고려)
    accelerator.wait_for_everyone()
    unwrapped_policy = accelerator.unwrap_model(policy)
    # ... 저장 로직 ...

if __name__ == "__main__":
    main()
```

이 예시 코드는 `lerobot-train`이라는 블랙박스를 사용하는 대신, 내부 아키텍처를 직접 제어하면서 파인튜닝을 수행하는 방법에 대한 구체적인 청사진입니다. `[전략 2, 3, 4]` 역시 이 코드의 4번 '수술' 부분만 바꾸면 동일한 원리로 구현할 수 있습니다.

---

## 7. smolVLA 파인튜닝 전략 (4가지 옵션)

제시해주신 상세한 로드맵을 기반으로, 각 상황에 맞는 최적의 파인튜닝 '방법'을 선택할 수 있도록 4가지 전략적 옵션을 제시합니다. 각 방법은 독립적이며, 데이터의 양, 과적합 여부, 에러 발생 등 특정 조건에 따라 선택적으로 사용해야 합니다.



### 전략 1 (정석): VLM 동결 + DiT 전면 학습

- **전략**: 충분한 데이터(100 에피소드 이상)가 확보되었을 때 가장 먼저 시도해야 할 메인 전략입니다.
- **구조**: 시각/언어 백본(VLM)은 완전히 얼리고, 궤적을 만드는 DiT 디코더 레이어 전체를 학습(Full Fine-Tuning)시킵니다.
- **자원**: VLM의 기울기를 계산하지 않아 시스템 RAM 32GB 내에서 방어가 가능합니다. 남는 VRAM(2x RTX 5090)을 활용해 배치 사이즈를 최대한 키울 수 있습니다.
- **특징**: 파이퍼 로봇 팔의 모터 한계와 화이트보드의 마찰력이라는 새로운 물리 법칙을 모델의 뇌(DiT)에 가장 깊고 완벽하게 새겨 넣습니다.


---

### 전략 2 (스마트 경량화): VLM 동결 + DiT DoRA

- **전략**: 데이터가 적거나(20~50 에피소드), 전면 학습 시 과적합(로봇이 한 가지 궤적만 반복하는 현상)이 발생할 때 선택하는 1순위 타협안입니다.
- **구조**: VLM은 얼리고, DiT 레이어에 DoRA(크기/방향 분리형 LoRA)를 부착합니다.
- **자원**: 32GB RAM 환경에서 가장 쾌적하고 안전합니다 (10GB 안팎 소모).
- **특징**: 메모리는 기존 LoRA만큼 적게 먹으면서, 가중치의 크기(누르는 힘)와 방향(움직이는 궤적)을 분리 학습하여 물리 제어 환경에 압도적으로 잘 적응합니다.

### 전략 3 (비상 탈출구): VLM 동결 + DiT 일반 LoRA

- **전략**: 전략 2의 DoRA 세팅으로 학습을 돌렸는데 알 수 없는 프레임워크 에러나 Loss 발산이 터질 때 사용하는 백업 플랜입니다.
- **구조**: VLM은 얼리고, DiT 레이어에 일반 LoRA를 부착합니다 (`use_dora=False`).
- **자원**: DoRA와 100% 동일하여 RAM 병목이 없습니다.
- **특징**: 성능은 DoRA보다 살짝 떨어질 수 있지만, Hugging Face `peft` 라이브러리에서 가장 오래되고 완벽하게 검증된 코드이므로 라이브러리 버전 충돌이나 의존성 에러를 즉각적으로 우회할 수 있습니다.

#### 아키텍처 및 구현 방안 (전략 1)

`lerobot_sync_player.py` 코드 분석을 통해 확인된 `lerobot`의 데이터셋 구조를 활용하여 다음과 같이 구체적인 구현을 진행합니다.

1.  **학습 스크립트 생성 (`scripts/train_dit_full.py`)**: 이 스크립트는 `lerobot` 라이브러리를 활용하여 데이터 로딩 및 모델 훈련을 수행합니다.

2.  **데이터 로딩**: `lerobot_sync_player.py`가 `LeRobotDatasetMetadata`를 사용하는 것과 같이, `lerobot`이 제공하는 공식 데이터셋 클래스 (e.g., `LeRobotDataset`)를 사용합니다. 이는 복잡한 `.parquet` 및 비디오 파일 처리를 자동화합니다.
    ```python
    # 예시 코드
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
    dataset = LeRobotDataset(dataset_repo_id="local/my_robot_data")
    ```

3.  **모델 로딩 및 '수술' (VLM 동결)**: `smolVLA` 모델을 로드한 후, DiT 부분만 학습하도록 파라미터를 설정합니다.
    ```python
    from lerobot.common.policies.factory import make_policy

    # 모델 로드
    policy = make_policy(cfg)

    # VLM 동결: 'decoder'가 이름에 포함되지 않은 모든 파라미터의 그래디언트 계산을 비활성화
    for name, param in policy.named_parameters():
        if 'decoder' not in name: 
            param.requires_grad = False
    ```

4.  **옵티마이저 설정**: 학습할 파라미터(DiT 가중치)만 옵티마이저에 전달합니다.
    ```python
    import torch.optim as optim

    # requires_grad=True인 파라미터만 필터링하여 옵티마이저에 전달
    optimizer = optim.AdamW(filter(lambda p: p.requires_grad, policy.parameters()), lr=1e-4)
    ```

5.  **실행 스크립트 (`7a__train_dit_full.sh`)**: Hugging Face `accelerate`를 사용하여 Multi-GPU로 훈련을 실행합니다.
    ```bash
    accelerate launch --multi_gpu --num_machines=1 --num_processes=2 scripts/train_dit_full.py \
        --dataset_repo_id="local/my_robot_data" \
        --batch_size=128 \
        --mixed_precision="bf16"
    ```



---
#### 아키텍처 및 구현 방안 (전략 2 & 3 공통)

1.  **의존성 설치**: `peft` 라이브러리가 필수적이므로, 아래 명령어로 직접 설치합니다.
    ```bash
    pip install peft transformers bitsandbytes accelerate
    ```

2.  **PEFT를 이용한 '정밀 수술'**: 모델 로드 및 VLM 동결 후, 학습 대상인 DiT 모듈에 DoRA/LoRA를 적용합니다.
    ```python
    from peft import get_peft_model, LoraConfig

    # DiT의 Linear 레이어만 타겟팅하는 LoRA/DoRA 설정
    peft_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.1,
        target_modules=['attention.to_q', 'attention.to_k', 'attention.to_v'],
        use_dora=True, # 전략 2의 경우 True, 전략 3의 경우 False
    )

    # DiT 디코더(policy.decoder)에만 PEFT 모델 적용
    policy.decoder = get_peft_model(policy.decoder, peft_config)
    policy.print_trainable_parameters()
    ```

3.  **학습 및 실행**: `train_dit_peft.py`와 같은 스크립트로 구현하고 `accelerate`로 실행합니다.

---
### 전략 4 (시각 교정): VLM 일반 LoRA + DiT 전면 학습

- **전략**: 모델이 로봇 팔의 생김새나 연구실의 화이트보드를 전혀 인식하지 못해 헛손질을 할 때, 모델의 '눈'을 교정하는 마지막 수단입니다.
- **구조**: DiT는 전면 학습으로 켜고, 얼려두었던 VLM 쪽에 일반 LoRA(또는 DoRA)를 추가로 부착합니다.
- **자원 (위험)**: VLM과 DiT 양쪽의 옵티마이저 상태를 유지해야 하므로 32GB RAM이 폭파될 위험이 가장 높습니다.
- **필수 조치**: 이 방식을 쓸 때는 반드시 Dataloader의 `num_workers=0`으로 설정하고, 리눅스 스왑(Swap) 메모리를 64GB 이상 넉넉히 잡아두어야 프로세스 다운을 막을 수 있습니다.

#### 아키텍처 및 구현 방안 (전략 4)

1.  **VLM에 LoRA 부착**: DiT는 그대로 두고, VLM 모듈에만 `peft`를 적용합니다.
    ```python
    # VLM의 Linear 레이어만 타겟팅하는 LoRA 설정
    peft_config_vlm = LoraConfig(..., target_modules=[...]) # VLM 내부 레이어 이름 지정
    policy.backbone = get_peft_model(policy.backbone, peft_config_vlm)
    ```


2.  **파라미터 그룹화 및 옵티마이저 설정**: DiT의 모든 파라미터와, VLM에 부착된 LoRA 파라미터를 **각각 다른 학습률(Learning Rate)로** 학습시키는 것이 핵심입니다.
    ```python
    # VLM의 LoRA 파라미터만 필터링
    vlm_lora_params = [p for n, p in policy.backbone.named_parameters() if p.requires_grad]

    # DiT 파라미터는 LoRA가 적용되지 않았으므로 모두 학습 대상
    dit_params = policy.decoder.parameters()

    optimizer = optim.AdamW([
        {'params': dit_params, 'lr': 1e-4}, # DiT는 더 높은 학습률로 적극적으로 학습
        {'params': vlm_lora_params, 'lr': 1e-6} # VLM은 미세조정이므로 매우 낮은 학습률로 안정적으로 학습
    ])
    ```

3.  **자원 관리 설정**: `Dataloader` 생성 시 `num_workers=0`으로 명시적으로 설정하여 추가적인 프로세스 생성을 막고, RAM 사용량을 최소화해야 합니다. 또한, 시스템에 충분한 스왑 공간이 설정되어 있는지 반드시 확인해야 합니다.

4.  **학습/실행 스크립트**: `train_vlm_lora_dit_full.py` 와 같은 별도의 스크립트를 작성하여 위 로직을 구현합니다. Multi-GPU 환경이 필수적이지만, RAM 병목 현상으로 인해 배치 사이즈를 이전 단계들보다 훨씬 작게 시작해야 할 수 있습니다.

---

💡 **최종 요약**

데이터가 충분하다면 **전략 1(DiT 전면 학습)**으로 직진하시고, 가볍게 테스트하거나 데이터가 적을 때는 **전략 2(DoRA)**를 기본값으로 쓰되 에러가 날 때만 **전략 3(일반 LoRA)**으로 스위칭하시면 됩니다. **전략 4**는 로봇의 행동이 아니라 '인식' 자체에 근본적인 문제가 있다고 판단될 때 시도하는 최후의 수단입니다.