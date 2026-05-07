from pathlib import Path

from setuptools import find_packages, setup


here = Path(__file__).parent
readme_path = here / "README.md"
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")
else:
    long_description = ""

setup(
    name="lerobot_robot_piper",
    version="0.1.0",
    description="LeRobot Piper robot integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Piper Contributors",
    packages=find_packages(),
    install_requires=[
        "lerobot>=0.4.0",
        "python-can",
        "piper_sdk",
    ],
    entry_points={
        "console_scripts": [
            "piper-inference=lerobot_robot_piper.piper_real_time_inference:cli_main",
            "piper-async-client=lerobot_robot_piper.piper_async_client:async_client",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)

