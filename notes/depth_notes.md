# RealSense Depth 데이터의 ZFP 압축 조사

> 작성 기준일: 2026-07-25  
> 범위: RealSense `Z16` depth 수집, 거리 마스킹, ZFP CPU/CUDA 압축, 30~60초 에피소드 저장, SpatialVLA 입력 검토  
> 근거: LLNL ZFP 및 RealSense 공식 자료, SpatialVLA 공개 논문·저장소, 차후 RVT-2 확장 아이디어

---

## 1. 결론

RealSense depth 데이터는 ZFP 기반 저장 backend로 전환하는 것을 전제로 설계할 만함

- ZFP는 공간적 상관성이 있는 2D·3D 수치 배열에 적합
- RealSense depth는 `Z16` 형식의 규칙적인 2D 수치 배열
- 여러 프레임을 `(T, H, W)` 3D 배열로 묶어 처리 가능
- 공식 CUDA 구현이 있지만 **fixed-rate 모드만 지원**
- 공식 Python 바인딩 `zfpy`는 **serial 실행만 지원**
- RealSense의 `uint16`은 ZFP high-level 입력 타입이 아니며, 공식 문서상 **32-bit signed integer로 promotion**해야 함
- 30~60초 에피소드를 하나의 단위로 관리하되, 내부 압축은 32~128프레임 chunk로 나누는 것이 안전함.
- ZFP를 쓰면 depth 산출물은 MP4가 아니라 ZFP bitstream 기반 binary chunk가 됨

권장 초기 파이프라인:

```text
RealSense Z16 uint16
→ ROI crop
→ 유효 거리 밖 값을 0으로 마스킹
→ 64프레임씩 chunk 구성
→ 공식 integer promotion
→ ZFP fixed-rate 8/10/12 bits-per-value 비교
→ chunk별 저장
```

결론

```text
RGB 영상: 기존처럼 mp4 저장
Depth 영상: mp4 대신 zfp chunk 저장
Dataset index/meta: LeRobotDataset feature와 timestamp를 유지하도록 확장
Replay/viewer/stat: zfp decode 경로 추가
```

현재 구현된 LeRobot depth 백포트는 이미 다음을 만족함

```text
LeRobotDataset feature/meta 통합
→ 12-bit 로그 양자화
→ HEVC gray12le lossless 영상 저장
→ PyAV decode 및 역양자화
→ replay/viewer/stat 경로 연결
→ 실물 RealSense 2대 검증
```

그러나 이 방식은 depth를 영상 codec 파이프라인에 맞춰 넣은 구조이므로 앞으로 depth를 학습 입력으로 계속 사용할 계획이라면, depth를 영상이 아니라 수치 배열로 보고 ZFP chunk backend를 추가하는 방향이 더 자연스러움

---

## 2. 공식 자료

| 구분 | 공식 자료 | 용도 |
|---|---|---|
| ZFP GitHub | https://github.com/LLNL/zfp | 소스, 빌드, 라이선스, CUDA 구현 |
| ZFP 공식 문서 | https://zfp.readthedocs.io/en/release1.0.1/ | API, 모드, 실행 정책 |
| Parallel Execution | https://zfp.readthedocs.io/en/release1.0.1/execution.html | OpenMP/CUDA 지원과 제약 |
| Compression Modes | https://zfp.readthedocs.io/en/release1.0.1/modes.html | rate/precision/accuracy/lossless |
| Python Bindings | https://zfp.readthedocs.io/en/release1.0.1/python.html | `zfpy` 지원 범위 |
| ZFP FAQ | https://zfp.readthedocs.io/en/release1.0.1/faq.html | 8/16-bit integer promotion |
| ZFP CLI | https://zfp.readthedocs.io/en/release1.0.1/zfpcmd.html | CLI 인자와 CUDA 실행 |
| ZFP releases | https://github.com/LLNL/zfp/releases | 공식 릴리스 |
| RealSense GitHub | https://github.com/realsenseai/librealsense | SDK와 예제 |
| RealSense alignment 예제 | https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py | Z16, depth scale, `np.where` |
| RealSense depth tuning | https://dev.realsenseai.com/docs/tuning-depth-cameras-for-best-performance/ | depth unit, 오차, 후처리 |
| SpatialVLA paper | https://arxiv.org/abs/2501.15830 | 3D-aware VLA, Ego3D Position Encoding, 추론 메모리 |
| SpatialVLA GitHub | https://github.com/SpatialVLA/SpatialVLA | 공개 checkpoint, Hugging Face 기반 실행 |
| RVT-2 paper | https://arxiv.org/abs/2406.08545 | 차후 Gemma prompt front-end 아이디어 |

```bash
git clone https://github.com/LLNL/zfp.git
cd zfp
git checkout 1.0.1
```

---

## 3. ZFP가 depth에 맞는 이유

ZFP 공식 README는 다음을 지원한다고 설명한다.

- 다차원 floating-point 및 integer 배열
- serial, OpenMP, CUDA whole-array compression
- lossy 및 reversible lossless compression
- 공간적 상관성이 있는 2D, 3D, 4D 배열
- 고정 크기 블록 단위의 독립 압축

RealSense depth 한 프레임은:

```text
shape: (H, W)
dtype: uint16
```

여러 프레임을 묶으면:

```text
shape: (T, H, W)
```

가 되어 3D 배열로 처리할 수 있다.

다만 시간축에서 물체가 빠르게 움직이면 인접 프레임 상관성이 낮아질 수 있으므로 다음을 모두 비교해야 한다.

```text
A. 프레임별 2D 압축
B. 여러 프레임의 3D chunk 압축
```

---

## 4. RealSense 입력과 마스킹

공식 Python 예제의 depth stream:

```python
config.enable_stream(
    rs.stream.depth,
    640,
    480,
    rs.format.z16,
    30,
)
```

depth scale:

```python
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
```

거리 변환:

```text
distance_m = raw_depth * depth_scale
```

거리 기준 마스킹:

```python
import numpy as np

def mask_depth_range(
    depth: np.ndarray,
    depth_scale: float,
    min_distance_m: float,
    max_distance_m: float,
) -> np.ndarray:
    if depth.dtype != np.uint16:
        raise TypeError(f"expected uint16, got {depth.dtype}")

    min_raw = int(round(min_distance_m / depth_scale))
    max_raw = int(round(max_distance_m / depth_scale))

    out = depth.copy()
    out[(out < min_raw) | (out > max_raw)] = 0
    return out
```

RealSense 공식 alignment 예제도 depth scale로 clipping distance를 계산하고 `np.where()`로 배경 제거

마스킹은 배열의 원본 byte 수를 줄이지 않는다. 대신 넓은 영역을 0으로 통일하여 이후 압축률을 높일 수 있음.

고정된 작업대라면:

```text
ROI crop → 거리 마스킹 → 압축
```

순서가 좋음

함께 저장할 메타데이터:

```yaml
depth_scale: 0.001
depth_format: Z16
width: 848
height: 480
fps: 30
camera_serial: "..."
```

---

## 5. `uint16` 처리 시 핵심 제약

ZFP high-level API와 CLI가 직접 지원하는 scalar type:

```text
i32
i64
f32
f64
```

`uint16`은 직접 지원되는 high-level 입력 타입이 아님

ZFP 공식 FAQ는 8-bit 또는 16-bit integer 데이터를 **32-bit signed integer로 promotion**하라 되어있음. 또한 단순 cast 대신 `zfp_promote_*_to_int32` 계열 함수를 사용할 것을 권장

공식 promotion은:

- unsigned를 signed로 변환하고
- 낮은 정밀도 값을 31-bit integer의 상위 비트 쪽으로 이동하여
- leading zero 인코딩에 비트를 낭비하지 않도록 한다.

권장 경로:

```text
uint16 block
→ zfp_promote_*_to_int32
→ ZFP 압축
→ ZFP 복원
→ 대응 demotion
→ uint16 block
```

다음 단순 변환은 공식 promotion과 같지 않다.

```python
depth_i32 = depth_u16.astype(np.int32)
```

단순 cast를 쓸 경우 공식 promotion 대비 압축률과 복원 오차를 따로 검증해야 함.

---

## 6. 압축 모드

| 모드 | 제어 대상 | 특징 |
|---|---|---|
| Fixed-rate | bits/value | 압축 크기 예측 가능 |
| Fixed-precision | bit planes | 상대적 정밀도 중심 |
| Fixed-accuracy | absolute tolerance | 절대오차 중심 |
| Reversible | lossless | bit-for-bit 복원 |
| Expert | 여러 제약 | 고급 설정 |

### Fixed-rate

```text
rate = 압축 후 값 하나당 평균 비트 수
```

`uint16` 원본과 단순 비교하면:

```text
rate 12 → 이론상 약 1.33배
rate 10 → 약 1.60배
rate  8 → 약 2.00배
rate  6 → 약 2.67배
```

실제 파일에는 index와 metadata overhead가 들어갈 수 있다.

### Fixed-accuracy

floating-point 데이터에만 사용할 수 있다.

예:

```text
float32 depth in meters
tolerance = 0.002
```

는 약 2 mm 절대오차 기준을 목표로 한다.

### Reversible

무손실 모드이며 CUDA에서는 지원되지 않는다.

---

## 7. CUDA 공식 지원

공식 실행 정책:

```c
zfp_exec_serial
zfp_exec_omp
zfp_exec_cuda
```

C API:

```c
if (!zfp_stream_set_execution(stream, zfp_exec_cuda)) {
    /* CUDA policy unavailable */
}
```

CLI:

```bash
-x cuda
```

지원표:

| 항목 | CUDA |
|---|---:|
| Fixed-rate 압축 | O |
| Fixed-rate 복원 | O |
| Fixed-precision | X |
| Fixed-accuracy | X |
| Reversible | X |
| 1D/2D/3D | O |
| 4D | X |
| Host pointer | O |
| Device pointer | O |

Host pointer를 넘기면 내부적으로 GPU 메모리를 할당하고 H2D/D2H 복사를 수행한다. 입력과 출력이 모두 device pointer이면 복사를 생략한다.

따라서 RealSense처럼 CPU 메모리로 프레임이 들어오는 경우:

- 한 프레임씩 CUDA로 보내면 전송·할당 오버헤드가 커질 수 있다.
- 여러 프레임을 큰 3D chunk로 묶으면 GPU가 유리해질 가능성이 있다.
- 데이터가 이미 CUDA tensor에 있다면 GPU 이점이 커진다.

CUDA 제약:

- CUDA support 기본값은 OFF
- CMake 빌드 필요
- `ZFP_WITH_CUDA=ON`
- `ZFP_BIT_STREAM_WORD_SIZE=64`
- host field는 contiguous
- CUDA에서 ZFP header 미지원
- 4D 배열 미지원

### GPU 영상 인코딩과의 차이

Depth 저장을 빠르게 만들기 위해 GPU를 쓰려면

```text
depth를 수치 배열로 보고 ZFP fixed-rate로 압축
```

depth를 애초에 수치 배열로 처리. ZFP CUDA는 fixed-rate 압축/복원을 공식 지원하고, `(T, H, W)` chunk 단위로 묶으면 GPU 전송 오버헤드를 줄일 수 있음. 다만 fixed-rate만 가능하고, Python `zfpy`만으로는 CUDA를 사용할 수 없으며, `uint16` 입력은 공식 promotion 경로를 거쳐야 한다.

정리:

| 후보 | 기대 장점 | 주요 리스크 |
|---|---|---|
| CPU HEVC gray12le | 이미 LeRobot 통합·검증 완료, replay/viewer/stat 연결 완료 | CPU x265 인코딩이 느릴 수 있음, depth를 영상 codec 구조에 맞춰 저장함, 크기가 큼 |
| CUDA ZFP | depth 수치 배열에 자연스러움, fixed-rate 크기 예측, chunk random access | C++/CUDA wrapper 필요, fixed-rate 제한, LeRobot loader/viewer/stat 추가 구현 필요 |


우선순위:

```text
1. 같은 raw depth chunk로 CPU/OpenMP/CUDA ZFP benchmark
2. bit-exact 또는 허용오차, 압축률, encode/decode 시간, replay 호환성 비교
3. 결과가 충분하면 ZFP chunk backend를 기본 저장 방식으로 전환
4. 필요하다면 NVENC gray/p010/yuv444 계열은 별도 참고 실험으로만 비교
```

---

## 8. Python 제약

공식 `zfpy`:

```python
import zfpy

compressed = zfpy.compress_numpy(array, rate=10)
restored = zfpy.decompress_numpy(compressed)
```

공식 문서상 `zfpy`는 serial execution만 지원한다.

즉 다음은 `zfpy`만으로 불가능하다.

```text
zfpy → zfp_exec_cuda
```

Python에서 CUDA ZFP를 쓰려면:

1. pybind11 C++ wrapper
2. PyTorch C++/CUDA extension
3. Cython에서 libzfp C API 확장
4. 별도 C++ 압축 worker

권장 구조:

```text
Python RealSense recorder
→ queue/shared memory
→ C++ CUDA ZFP worker
→ compressed chunk
```

---

## 9. 빌드

### CPU/OpenMP

```bash
git clone https://github.com/LLNL/zfp.git
cd zfp
git checkout 1.0.1

cmake -S . -B build   -DCMAKE_BUILD_TYPE=Release   -DZFP_WITH_OPENMP=ON   -DBUILD_EXAMPLES=ON

cmake --build build -j
ctest --test-dir build
```

### CUDA

```bash
git clone https://github.com/LLNL/zfp.git
cd zfp
git checkout 1.0.1

cmake -S . -B build   -DCMAKE_BUILD_TYPE=Release   -DZFP_WITH_CUDA=ON   -DZFP_BIT_STREAM_WORD_SIZE=64   -DBUILD_EXAMPLES=ON

cmake --build build -j
ctest --test-dir build
```

GNU Make 빌드는 CUDA를 지원하지 않으므로 CUDA 사용 시 CMake를 사용한다.

---

## 10. CLI 예제

ZFP CLI 입력 타입:

```text
-t i32
-t i64
-t f32
-t f64
```

3D C 배열:

```bash
-3 <nx> <ny> <nz>
```

NumPy chunk가 `(T, H, W)`이고 C-contiguous라면 CLI는:

```bash
-3 W H T
```

예: 64프레임, 480×848:

```bash
zfp   -i depth_i32.raw   -z depth.zfp   -t i32   -3 848 480 64   -r 10   -x cuda
```

복원:

```bash
zfp   -z depth.zfp   -o restored_i32.raw   -t i32   -3 848 480 64   -r 10   -x cuda
```

CUDA에서는 header를 지원하지 않으므로 다음 정보를 별도로 저장한다.

```yaml
dtype: i32
shape: [64, 480, 848]
zfp_dimensions: [848, 480, 64]
rate: 10
execution: cuda
```

---

## 11. 30~60초 에피소드 구조

`848×480×30 FPS×uint16`의 대략적인 원본 크기:

```text
1초  ≈ 24.4 MB
30초 ≈ 733 MB
60초 ≈ 1.47 GB
```

권장 chunk:

```text
32 frames  ≈ 1.07초
64 frames  ≈ 2.13초
128 frames ≈ 4.27초
```

시작점은 64 frames가 적당하다.

장점:

- 프레임별 GPU 호출보다 오버헤드가 작음
- 전체 에피소드를 한 번에 int32로 만들 필요 없음
- 일부 손상 시 한 chunk만 영향
- 부분 읽기와 샘플링이 쉬움

권장 파일 구조:

```text
episode_000123/
├── metadata.json
├── depth_index.json
├── depth_0000.zfp
├── depth_0001.zfp
├── ...
├── rgb.mp4
├── actions.parquet
└── timestamps.npy
```

즉 ZFP backend에서 depth는 다음과 같이 저장된다.

```text
기존 HEVC backend:
videos/observation.images.top_depth/chunk-000/file-000.mp4

ZFP backend:
depth/observation.images.top_depth/chunk-000/depth_000000.zfp
depth/observation.images.top_depth/chunk-000/depth_000001.zfp
depth/observation.images.top_depth/index.json
```

`.zfp`는 영상 컨테이너가 아니라 ZFP compressed bitstream이다. 일반 동영상 플레이어로 열 수 없고, LeRobot loader/viewer가 `index.json`과 metadata를 읽어 해당 chunk를 복원해야 한다. 따라서 ZFP를 도입하면 depth feature는 `dtype=video`처럼 다루기보다 `dtype=depth_zfp` 또는 `info.storage_backend=zfp_chunk` 같은 별도 메타데이터로 구분하는 편이 맞다.

권장 feature metadata:

```json
{
  "dtype": "depth_zfp",
  "shape": [480, 848, 1],
  "names": ["depth"],
  "info": {
    "is_depth_map": true,
    "storage_backend": "zfp_chunk",
    "source_dtype": "uint16",
    "zfp_dtype": "int32_promoted",
    "compression_mode": "fixed-rate",
    "rate_bits_per_value": 10,
    "chunk_frames": 64,
    "depth_scale": 0.001
  }
}
```

RGB는 계속 MP4로 두는 것이 좋다. RGB는 영상 codec에 맞는 데이터이고, 기존 LeRobot video path와 viewer가 그대로 동작하기 때문이다. 바뀌는 대상은 depth stream뿐이다.

`metadata.json` 예:

```json
{
  "depth_format": "Z16",
  "source_dtype": "uint16",
  "zfp_dtype": "int32_promoted",
  "shape": [1800, 480, 848],
  "fps": 30,
  "depth_scale": 0.001,
  "chunk_frames": 64,
  "compression_mode": "fixed-rate",
  "rate_bits_per_value": 10,
  "execution_policy": "cuda",
  "zfp_version": "1.0.1",
  "mask_min_m": 0.15,
  "mask_max_m": 1.5
}
```

---

## 12. ZFP backend와 VLA 입력 연결

ZFP는 모델이 직접 먹는 입력 포맷이 아니라 저장 backend다. VLA가 `.zfp` 파일을
그대로 읽는 것이 아니라, dataset loader가 압축을 풀어 depth tensor나 spatial
feature로 넘겨주는 구조가 필요하다.

학습·추론 경로는 다음처럼 잡는 것이 자연스럽다.

```text
teleop recording
→ RGB mp4 저장
→ depth zfp chunk 저장
→ LeRobotDataset index/meta 저장
→ 학습 시 zfp decode
→ uint16/float32 depth tensor
→ 모델별 입력 변환
```

모델별 입력 변환:

```text
SpatialVLA:
RGB image + language
→ 기본 구조는 RGB에서 depth를 추정해 Ego3D Position Encoding 구성
→ 실제 RealSense depth를 쓰려면 추정 depth 경로를 measured depth로 대체하는 수정 필요
```

이때 ZFP backend에서 중요한 것은 저장 경로와 모델 입력 경로를 분리해서 보는
것이다. 저장은 `.zfp` chunk로 하되, 모델에는 복원된 depth tensor나 spatial
encoding이 들어간다.

```text
저장 포맷:
depth/observation.images.<camera>_depth/chunk-000/depth_000000.zfp

데이터셋 feature:
info.storage_backend = "zfp_chunk"

모델 입력:
decode_zfp_depth(...) -> depth tensor
depth tensor + intrinsics -> point cloud 또는 spatial encoding
```

### SpatialVLA 위치

SpatialVLA는 `PaLiGemma2` 기반의 spatial-enhanced VLA다. 논문에서는
1.1M real robot demonstrations로 pretrain하고, 224x224 RGB image와 language
instruction을 입력받아 action chunk를 예측한다고 설명한다. 또한 RTX 4090
한 장에서 약 8.5GB GPU memory, 약 20Hz inference를 보고한다.

우리 하드웨어가 시스템 RAM 32GB, RTX 5090 2장인 점을 고려하면, SpatialVLA는
메인 VLA 후보로 두기에 가장 현실적이다. 추론 메모리 요구가 낮은 편이고,
일반 RGB VLA보다 3D spatial reasoning을 직접 고려하기 때문이다. 다만
SpatialVLA의 기본 구조가 RealSense `Z16` depth를 직접 입력으로 받는 것은
아니다. 실제 depth 저장 backend의 효과를 확인하려면 다음 중 하나가 필요하다.

```text
A. ZoeDepth 추정 결과 대신 RealSense depth를 Ego3D Position Encoding에 사용
B. RealSense depth를 별도 depth feature adapter로 주입
```

### 차후 아이디어: Gemma + RVT-2

SpatialVLA를 우선 검토하고, 별도 장기 아이디어로 Gemma와 RVT-2 조합을 남긴다.
이 경우 Gemma는 저수준 action을 직접 예측하는 모델이 아니다. 사용자의 긴
자연어 명령을 RVT-2가 처리하기 쉬운 짧은 task instruction 또는 subtask prompt로
정리해주는 front-end에 가깝다.

```text
사용자 자연어
→ Gemma prompt 정규화
→ RVT-2용 짧은 task instruction
→ RVT-2 RGB-D / point cloud manipulation policy
```

이 방향은 SpatialVLA 구동과 ZFP depth backend 검증이 끝난 뒤 검토한다.

결론:

```text
ZFP backend는 VLA 입력 형식이 아니라 depth 저장/복원 계층이다.
따라서 "ZFP를 읽는 모델"을 찾기보다
"복원된 depth tensor 또는 spatial encoding을 어떻게 VLA에 넣을지"를 봐야 한다.
현재 하드웨어 기준으로는 SpatialVLA를 메인 후보로 둔다.
차후 확장 아이디어로만 Gemma + RVT-2 prompt front-end를 검토한다.
```

---

## 13. SpatialVLA의 표현 방식과 depth 활용 구조

SpatialVLA는 일반적인 RGB 기반 VLA에 3D 공간 정보를 더 강하게 반영하려는
모델이다. 입력은 RGB image와 language instruction이고, 출력은 로봇이 실행할
action chunk다. 즉 사용자의 자연어 명령과 카메라 관측을 함께 보고 다음 행동을
예측하는 VLA 구조를 따른다.

다만 SpatialVLA가 RealSense의 `Z16` depth map을 그대로 입력으로 받는 구조는
아님. 기본 구조에서는 RGB image로부터 depth를 추정하고, 이 depth 정보를
사용해 이미지 픽셀을 3D 공간상의 위치 표현으로 확장함. 이때 사용하는 핵심
표현이 `Ego3D Position Encoding`

흐름을 단순화하면 다음과 같다.

```text
RGB image
→ depth estimation
→ camera intrinsics를 이용한 3D 위치 계산
→ Ego3D Position Encoding
→ vision-language-action model 입력
→ action chunk 예측
```

여기서 depth는 최종 출력이 아니라, 이미지 feature에 3D 공간 감각을 넣기 위한
중간 표현으로 쓰인다. 일반 RGB VLA는 물체와 그리퍼 사이의 거리, 접근 방향,
작업 공간 안의 상대 위치를 2D feature만으로 추론해야 한다. SpatialVLA는 이
부분에 depth 기반 3D 위치 정보를 넣어 공간 관계를 더 직접적으로 반영한다.

본 프로젝트에서 수집하는 RealSense depth를 SpatialVLA와 연결하려면 한 가지
수정이 필요하다. SpatialVLA의 기본 경로는 RGB에서 추정한 depth를 사용하므로,
우리가 저장한 실제 `Z16` depth를 쓰려면 depth estimation 결과를 measured
depth로 대체하거나, 별도 depth adapter를 추가해야 한다.

가능한 연결 방식은 다음과 같다.

```text
A. 기본 SpatialVLA
RGB image
→ model 내부 depth estimation
→ Ego3D Position Encoding

B. RealSense depth 활용 SpatialVLA
RGB image + RealSense depth
→ measured depth 기반 Ego3D Position Encoding
→ SpatialVLA 입력
```

ZFP backend는 이 과정에서 모델 구조가 아니라 저장 계층에 해당한다. Teleop
중에는 RealSense depth를 `.zfp` chunk로 저장하고, 학습 시점에는 이를 다시
depth tensor로 복원한 뒤 SpatialVLA의 spatial encoding 경로에 연결하는 식이다.

```text
teleop recording
→ RealSense Z16 depth
→ ZFP chunk 저장
→ 학습 시 ZFP decode
→ measured depth tensor
→ SpatialVLA spatial encoding 입력
```

따라서 SpatialVLA를 사용할 경우, ZFP의 역할은 "모델이 직접 읽는 포맷"이
아니라 "실제 depth 정보를 보존해 두었다가 학습 시 spatial representation으로
변환할 수 있게 하는 저장 backend"로 보는 것이 맞다.

정리:

- SpatialVLA는 RGB image와 language instruction을 입력으로 받는 VLA다.
- 일반 RGB VLA와 달리 3D spatial representation을 내부적으로 사용한다.
- 기본 구조는 RGB에서 추정한 depth를 사용한다.
- 본 프로젝트의 RealSense depth를 직접 활용하려면 measured depth를 spatial
  encoding 경로에 연결해야 한다.
- ZFP는 이 measured depth를 효율적으로 저장하기 위한 backend다.
- 목표 구조는 `ZFP depth 저장 → decode → measured depth tensor → SpatialVLA
  spatial encoding`이다.