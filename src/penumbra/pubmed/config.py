"""Configuration options for PubMed parser."""

import os
from pathlib import Path
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field, model_validator


class PubMedConfig(BaseModel):
    """Configuration for PubMed parser."""

    # API access
    email: str = Field(..., description="Email for NCBI E-utilities API")
    api_key: Optional[str] = Field(
        None, description="NCBI API key for higher rate limits"
    )
    tool_name: str = Field("PenumbraPubMedParser", description="Tool name for NCBI API")

    # Rate limiting
    requests_per_second: float = Field(
        3.0, description="Max requests per second without API key"
    )

    # Storage paths
    pdf_dir: Path = Field(
        Path("papers/pdf"), description="Directory to store PDF files"
    )
    markdown_dir: Path = Field(
        Path("papers/markdown"), description="Directory to store markdown files"
    )

    # Journal tiers mapping
    journal_tier_mapping: Dict[str, str] = Field(
        default_factory=dict, description="Journal name to tier mapping"
    )

    # Parser options
    download_timeout: int = Field(
        60, description="Timeout for downloading PDFs in seconds"
    )
    max_retry_attempts: int = Field(
        3, description="Maximum retry attempts for failed requests"
    )

    @model_validator(mode="after")
    def ensure_directories_exist(self) -> "PubMedConfig":
        """Ensure all storage directories exist."""
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def from_env(cls) -> "PubMedConfig":
        """
        Create configuration from environment variables.

        Environment variables:
        - PUBMED_EMAIL: Email for NCBI E-utilities API
        - PUBMED_API_KEY: NCBI API key (optional)
        - PUBMED_TOOL_NAME: Tool name for NCBI API
        - PUBMED_PDF_DIR: Directory to store PDF files
        - PUBMED_MARKDOWN_DIR: Directory to store markdown files
        """
        return cls(
            email=os.environ.get("PUBMED_EMAIL", ""),
            api_key=os.environ.get("PUBMED_API_KEY"),
            tool_name=os.environ.get("PUBMED_TOOL_NAME", "PenumbraPubMedParser"),
            pdf_dir=Path(os.environ.get("PUBMED_PDF_DIR", "papers/pdf")),
            markdown_dir=Path(os.environ.get("PUBMED_MARKDOWN_DIR", "papers/markdown")),
        )
