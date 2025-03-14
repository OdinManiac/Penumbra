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
        "biopython>=1.83.0",
        "httpx>=0.26.0",
        "aiofiles>=23.2.1",
        "aiohttp>=3.9.1",
        "beautifulsoup4>=4.12.3",
        "scholarly>=1.7.11",
        "semanticscholar>=0.5.0",
        "docling>=2.0.0",
        "sentence-transformers>=2.2.2",
        "qdrant-client>=1.7.0",
        "pydantic-ai>=0.0.37",
        "python-dotenv>=1.0.0",
    ],
)
