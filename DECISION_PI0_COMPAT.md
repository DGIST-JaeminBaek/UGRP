# pi0 체크포인트 호환성 — 의사결정

작성일: 2026-05-07

---

## 결론

`lerobot/pi0_base`를 사용한다.

- `lerobot/pi0`은 v0.1 시절 포맷 → lerobot 0.4.0과 호환 안 됨
- `lerobot/pi0_base`는 v0.4.x 호환 포맷으로 새로 publish된 체크포인트
- lerobot 0.4.0에서 로드 확인 완료
- OpenPI 환경 분리 불필요, lerobot 0.4.0 + Piper 플러그인 그대로 유지

## 다음 단계

`pi0_base`를 base weight로 Piper 데이터셋 fine-tuning:

```bash
lerobot-train \
  --policy.type=pi0 \
  --policy.pretrained_path=lerobot/pi0_base \
  --dataset.repo_id=local/piper-demo \
  --output_dir=outputs/piper-pi0-finetune \
  --policy.dtype=bfloat16 \
  --policy.gradient_checkpointing=true \
  --robot.discover_packages_path=lerobot_robot_piper
```
