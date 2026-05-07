import lerobot_robot_piper  # noqa: F401 — registers piper plugin before draccus parsing
import lerobot.async_inference.constants as _c
_c.SUPPORTED_ROBOTS.append("piper")
from lerobot.async_inference.robot_client import async_client

if __name__ == "__main__":
    async_client()
