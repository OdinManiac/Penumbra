"""Pydantic models for PubMed data structures and filtering."""

from datetime import date
from enum import Enum
from typing import List, Optional, Dict, Any, Set

from pydantic import BaseModel, Field, field_validator, model_validator


class JournalTier(str, Enum):
    """Journal tier based on impact factor and reputation."""

    TIER_1 = "tier_1"  # Top journals (e.g., Nature, Science)
    TIER_2 = "tier_2"  # High-impact specialized journals
    TIER_3 = "tier_3"  # Mid-tier journals
    TIER_4 = "tier_4"  # Other indexed journals
    UNKNOWN = "unknown"


class StudyType(str, Enum):
    """Type of scientific study."""

    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    RANDOMIZED_CONTROLLED_TRIAL = "randomized_controlled_trial"
    COHORT_STUDY = "cohort_study"
    CASE_CONTROL = "case_control"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    EXPERT_OPINION = "expert_opinion"
    OTHER = "other"
    UNKNOWN = "unknown"


class Author(BaseModel):
    """Author information."""

    last_name: str
    fore_name: Optional[str] = None
    initials: Optional[str] = None
    affiliations: List[str] = Field(default_factory=list)


class Journal(BaseModel):
    """Scientific journal information."""

    name: str
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    impact_factor: Optional[float] = None
    tier: JournalTier = JournalTier.UNKNOWN


class Citation(BaseModel):
    """Citation metrics for a paper."""

    count: int = 0
    normalized_count: Optional[float] = None  # Citations normalized by time
    h_index: Optional[int] = None  # H-index of the paper
    i10_index: Optional[int] = None  # i10-index of the paper


class PubMedPaper(BaseModel):
    """Scientific paper from PubMed with extended metadata."""

    pmid: str
    title: str
    abstract: Optional[str] = None
    authors: List[Author] = Field(default_factory=list)
    journal: Optional[Journal] = None
    publication_date: Optional[date] = None
    study_type: StudyType = StudyType.UNKNOWN
    keywords: List[str] = Field(default_factory=list)
    mesh_terms: List[str] = Field(default_factory=list)
    doi: Optional[str] = None
    citations: Optional[Citation] = None
    full_text_url: Optional[str] = None
    pdf_path: Optional[str] = None
    markdown_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def filename_base(self) -> str:
        """Generate a base filename for storing the paper."""
        if self.pmid:
            return f"pmid_{self.pmid}"
        elif self.doi:
            # Replace slashes with underscores in DOI
            return f"doi_{self.doi.replace('/', '_')}"
        else:
            # Fallback to title-based filename
            return f"paper_{self.title[:50].replace(' ', '_').lower()}"


class PaperFilter(BaseModel):
    """Filtering criteria for PubMed papers."""

    min_publication_date: Optional[date] = None
    max_publication_date: Optional[date] = None
    journal_tiers: Set[JournalTier] = Field(default_factory=set)
    study_types: Set[StudyType] = Field(default_factory=set)
    min_citations: Optional[int] = None
    required_keywords: Set[str] = Field(default_factory=set)
    required_mesh_terms: Set[str] = Field(default_factory=set)
    author_names: Set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_filter_combination(self) -> "PaperFilter":
        """Validate that the filter combination makes sense."""
        # If journal tiers is empty, allow all tiers
        if not self.journal_tiers:
            self.journal_tiers = set(JournalTier)

        # If study types is empty, allow all types
        if not self.study_types:
            self.study_types = set(StudyType)

        return self

    def matches(self, paper: PubMedPaper) -> bool:
        """
        Check if a paper matches the filter criteria.

        Args:
            paper: The paper to check against the filter

        Returns:
            True if the paper matches all criteria, False otherwise
        """
        # Check publication date range
        if (
            self.min_publication_date
            and paper.publication_date
            and paper.publication_date < self.min_publication_date
        ):
            return False

        if (
            self.max_publication_date
            and paper.publication_date
            and paper.publication_date > self.max_publication_date
        ):
            return False

        # Check journal tier
        if paper.journal and paper.journal.tier not in self.journal_tiers:
            return False

        # Check study type
        if paper.study_type not in self.study_types:
            return False

        # Check citations
        if (
            self.min_citations is not None
            and paper.citations
            and paper.citations.count < self.min_citations
        ):
            return False

        # Check required keywords (all must be present)
        if self.required_keywords and not all(
            kw.lower() in [k.lower() for k in paper.keywords]
            for kw in self.required_keywords
        ):
            return False

        # Check required MeSH terms (all must be present)
        if self.required_mesh_terms and not all(
            term.lower() in [t.lower() for t in paper.mesh_terms]
            for term in self.required_mesh_terms
        ):
            return False

        # Check authors
        if self.author_names:
            paper_authors = {a.last_name.lower() for a in paper.authors if a.last_name}
            author_matches = any(
                author.lower() in paper_authors for author in self.author_names
            )
            if not author_matches:
                return False

        return True


class SearchCriteria(BaseModel):
    """Search criteria for PubMed queries."""

    query: str
    max_results: int = 100
    filter: Optional[PaperFilter] = None
    retrieve_citations: bool = True
    retrieve_full_text: bool = False
    download_pdf: bool = False
    convert_to_markdown: bool = False
