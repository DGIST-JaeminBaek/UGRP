# 실험 세션 시작 프롬프트

아래 텍스트를 복사해서 새 Claude Code 세션 첫 메시지로 붙여넣기.
`[프로젝트 경로]` 부분만 실제 경로로 바꿀 것.

---

## 붙여넣기용 프롬프트

```
아래 파일들을 순서대로 읽고 프로젝트 전체 맥락을 파악한 다음, 내가 실험을 진행하는 것을 도와줘.

프로젝트 경로: [프로젝트 경로]/piper_lerobot

읽어야 할 파일 (순서대로):
1. EXPERIMENT.md        — 오늘 할 실험 계획 및 안전 주의사항
2. ROADMAP.md           — 전체 파이프라인 현황
3. lerobot_robot_piper/config_piper.py
4. lerobot_robot_piper/piper.py
5. lerobot_robot_piper/piper_sdk_interface.py
6. lerobot_robot_piper/piper_slave_only.py
7. lerobot_robot_piper/piper_real_time_inference.py

파일을 다 읽고 나면 "준비 완료" 라고 말하고 EXPERIMENT.md의 체크리스트를 보여줘.
이후 내가 "레벨 X 시작" 또는 "X번 실험 시작" 이라고 하면 해당 실험의 명령어와 확인 항목을 안내해줘.

실험 중 오류가 나면:
- 오류 메시지를 그대로 붙여넣으면 원인을 분석해줘
- 안전 관련 판단이 필요하면 EXPERIMENT.md의 위험 시나리오 A~D를 참고해서 먼저 언급해줘
```

---

## 경로 확인 방법 (실험실 도착 후)

```bash
# 프로젝트가 어디 있는지 모를 때
find ~ -name "piper_lerobot" -type d 2>/dev/null

# 패키지가 설치돼 있는지
pip show lerobot-robot-piper
```

---

## 실험실 도착 직후 체크 (Claude 없이)

1. CAN 인터페이스 활성화:
   ```bash
   sudo ip link set can0 up type can bitrate 1000000
   ip link show can0   # state UP 이어야 함
   ```

2. 패키지 editable 설치 확인:
   ```bash
   pip show lerobot-robot-piper | grep Location
   # Location이 piper_lerobot 디렉터리 안이어야 함
   # 아니면: cd piper_lerobot && pip install -e .
   ```

3. GPU 확인 (추론용):
   ```bash
   python -c "import torch; print(torch.cuda.is_available())"
   ```
