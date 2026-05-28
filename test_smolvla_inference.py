"""SmolVLA 로드 및 추론 드라이런 테스트"""
import torch
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")

# 1. Policy 로드
print("Loading SmolVLA...")
policy = SmolVLAPolicy.from_pretrained("lerobot/smolvla_base").to(device).eval()

preprocessor, postprocessor = make_pre_post_processors(
    policy_cfg=policy.config,
    pretrained_path="lerobot/smolvla_base",
)
print("Policy loaded!")

# 2. 더미 배치 — (B, C, H, W), [0, 1] float
batch = {
    "observation.state": torch.randn(1, 7).to(device),
    "task": ["pick and place"],
    "observation.images.camera1": torch.rand(1, 3, 480, 640).to(device),
    "observation.images.camera2": torch.rand(1, 3, 480, 640).to(device),
    "observation.images.camera3": torch.rand(1, 3, 480, 640).to(device),
}

# 3. 추론
print("Running inference...")
batch = preprocessor(batch)
with torch.inference_mode():
    action = policy.select_action(batch)
action = postprocessor(action)

print(f"Success! Action shape: {action.shape}")
print(f"Action sample: {action[0, :7]}")
