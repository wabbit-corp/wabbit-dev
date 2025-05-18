from setuptools import setup, find_packages
from pathlib import Path

# Read the requirements from requirements.txt
reqs_path = Path(__file__).parent / "requirements.txt"
requirements = [
    line.strip()
    for line in reqs_path.read_text().splitlines()
    if line.strip() and not line.startswith("#")
]

setup(
    name="wabbit-dev",
    version="0.1.0",
    description="Development utilities for the Wabbit project",
    author="Sir Wabbit",
    packages=find_packages(),
    install_requires=requirements,
)
