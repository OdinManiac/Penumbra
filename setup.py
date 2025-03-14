"""Setup script for Penumbra."""

from setuptools import find_packages, setup

setup(
    name="penumbra",
    version="0.1.0",
    description="Penumbra project",
    author="OdinManiac",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
        "pydantic>=2.6.0",
        "loguru>=0.7.2",
    ],
)
