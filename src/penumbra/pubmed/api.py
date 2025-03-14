"""FastAPI endpoints for PubMed parser service."""

import os
from datetime import date
from typing import List, Optional, Set, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from src.penumbra.pubmed.config import PubMedConfig
from src.penumbra.pubmed.models import (
    JournalTier,
    PaperFilter,
    PubMedPaper,
    SearchCriteria,
    StudyType,
)
from src.penumbra.pubmed.parser import PubMedParser


# Creating API router for PubMed operations
router = APIRouter(
    prefix="/pubmed",
    tags=["pubmed"],
    responses={404: {"description": "Not found"}},
)


class PubMedSearchRequest(BaseModel):
    """PubMed search request model."""

    query: str = Field(..., description="PubMed search query")
    max_results: int = Field(20, description="Maximum number of results to return")
    retrieve_citations: bool = Field(
        False, description="Retrieve citation counts for papers"
    )
    retrieve_full_text: bool = Field(
        False, description="Try to retrieve full text URLs"
    )
    download_pdf: bool = Field(False, description="Download PDFs for matching papers")
    convert_to_markdown: bool = Field(False, description="Convert PDFs to markdown")

    # Filter options
    min_publication_date: Optional[date] = Field(
        None, description="Minimum publication date"
    )
    max_publication_date: Optional[date] = Field(
        None, description="Maximum publication date"
    )
    journal_tiers: Optional[Set[JournalTier]] = Field(
        None, description="Filter by journal tiers"
    )
    study_types: Optional[Set[StudyType]] = Field(
        None, description="Filter by study types"
    )
    min_citations: Optional[int] = Field(None, description="Minimum citation count")
    required_keywords: Optional[Set[str]] = Field(None, description="Required keywords")
    required_mesh_terms: Optional[Set[str]] = Field(
        None, description="Required MeSH terms"
    )
    author_names: Optional[Set[str]] = Field(
        None, description="Filter by author last names"
    )

    def to_search_criteria(self) -> SearchCriteria:
        """Convert to SearchCriteria object."""
        filter_args = {}

        # Add filter parameters if present
        if self.min_publication_date:
            filter_args["min_publication_date"] = self.min_publication_date

        if self.max_publication_date:
            filter_args["max_publication_date"] = self.max_publication_date

        if self.journal_tiers:
            filter_args["journal_tiers"] = self.journal_tiers

        if self.study_types:
            filter_args["study_types"] = self.study_types

        if self.min_citations is not None:
            filter_args["min_citations"] = self.min_citations

        if self.required_keywords:
            filter_args["required_keywords"] = self.required_keywords

        if self.required_mesh_terms:
            filter_args["required_mesh_terms"] = self.required_mesh_terms

        if self.author_names:
            filter_args["author_names"] = self.author_names

        # Create filter if we have any filter arguments
        paper_filter = PaperFilter(**filter_args) if filter_args else None

        # Create search criteria
        return SearchCriteria(
            query=self.query,
            max_results=self.max_results,
            filter=paper_filter,
            retrieve_citations=self.retrieve_citations,
            retrieve_full_text=self.retrieve_full_text,
            download_pdf=self.download_pdf,
            convert_to_markdown=self.convert_to_markdown,
        )


class PubMedPaperResponse(BaseModel):
    """Response model for PubMed papers with simplified structure."""

    pmid: str
    title: str
    abstract: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    journal_name: Optional[str] = None
    journal_tier: Optional[str] = None
    publication_date: Optional[date] = None
    study_type: str
    keywords: List[str] = Field(default_factory=list)
    mesh_terms: List[str] = Field(default_factory=list)
    doi: Optional[str] = None
    citation_count: Optional[int] = None
    full_text_url: Optional[str] = None
    pdf_path: Optional[str] = None
    markdown_path: Optional[str] = None

    @classmethod
    def from_pubmed_paper(cls, paper: PubMedPaper) -> "PubMedPaperResponse":
        """Convert PubMedPaper to response model."""
        return cls(
            pmid=paper.pmid,
            title=paper.title,
            abstract=paper.abstract,
            authors=[
                f"{a.last_name}, {a.fore_name}" if a.fore_name else a.last_name
                for a in paper.authors
            ],
            journal_name=paper.journal.name if paper.journal else None,
            journal_tier=paper.journal.tier.value if paper.journal else None,
            publication_date=paper.publication_date,
            study_type=paper.study_type.value,
            keywords=paper.keywords,
            mesh_terms=paper.mesh_terms,
            doi=paper.doi,
            citation_count=paper.citations.count if paper.citations else None,
            full_text_url=paper.full_text_url,
            pdf_path=paper.pdf_path,
            markdown_path=paper.markdown_path,
        )


class PubMedSearchResponse(BaseModel):
    """Response model for PubMed search."""

    query: str
    total_results: int
    filtered_results: int
    papers: List[PubMedPaperResponse]


def get_pubmed_parser() -> PubMedParser:
    """
    Dependency to get the PubMed parser.

    Returns:
        PubMedParser instance
    """
    try:
        # Check for required environment variable
        if not os.environ.get("PUBMED_EMAIL"):
            raise ValueError("PUBMED_EMAIL environment variable is required")

        # Create the parser
        config = PubMedConfig.from_env()
        return PubMedParser(config)
    except Exception as e:
        logger.error(f"Error creating PubMed parser: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=PubMedSearchResponse)
async def search_pubmed(
    request: PubMedSearchRequest, parser: PubMedParser = Depends(get_pubmed_parser)
) -> PubMedSearchResponse:
    """
    Search PubMed with the given criteria.

    Args:
        request: Search request parameters
        parser: PubMed parser instance

    Returns:
        Search results
    """
    try:
        # Convert request to search criteria
        criteria = request.to_search_criteria()

        # Search PubMed
        papers = await parser.search(criteria)

        # Convert to response model
        response_papers = [PubMedPaperResponse.from_pubmed_paper(p) for p in papers]

        return PubMedSearchResponse(
            query=request.query,
            total_results=len(
                papers
            ),  # This should ideally be the total before filtering
            filtered_results=len(papers),
            papers=response_papers,
        )

    except Exception as e:
        logger.error(f"Error searching PubMed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/{pmid}", response_model=PubMedPaperResponse)
async def get_paper_by_pmid(
    pmid: str,
    download_pdf: bool = False,
    convert_to_markdown: bool = False,
    parser: PubMedParser = Depends(get_pubmed_parser),
) -> PubMedPaperResponse:
    """
    Get a paper by its PubMed ID.

    Args:
        pmid: PubMed ID
        download_pdf: Whether to download the PDF
        convert_to_markdown: Whether to convert the PDF to markdown
        parser: PubMed parser instance

    Returns:
        Paper details
    """
    try:
        # Get the paper
        paper = await parser.get_paper_by_pmid(pmid)

        if not paper:
            raise HTTPException(
                status_code=404, detail=f"Paper with PMID {pmid} not found"
            )

        # Get additional info if requested
        if download_pdf or convert_to_markdown:
            if not paper.full_text_url:
                await parser._fetch_full_text_url(paper)

            if download_pdf and paper.full_text_url:
                await parser._download_pdf(paper)

            if convert_to_markdown and paper.pdf_path:
                await parser._convert_to_markdown(paper)

        # Convert to response model
        return PubMedPaperResponse.from_pubmed_paper(paper)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper by PMID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/doi/{doi}", response_model=PubMedPaperResponse)
async def get_paper_by_doi(
    doi: str,
    download_pdf: bool = False,
    convert_to_markdown: bool = False,
    parser: PubMedParser = Depends(get_pubmed_parser),
) -> PubMedPaperResponse:
    """
    Get a paper by its DOI.

    Args:
        doi: DOI
        download_pdf: Whether to download the PDF
        convert_to_markdown: Whether to convert the PDF to markdown
        parser: PubMed parser instance

    Returns:
        Paper details
    """
    try:
        # Get the paper
        paper = await parser.get_paper_by_doi(doi)

        if not paper:
            raise HTTPException(
                status_code=404, detail=f"Paper with DOI {doi} not found"
            )

        # Get additional info if requested
        if download_pdf or convert_to_markdown:
            if not paper.full_text_url:
                await parser._fetch_full_text_url(paper)

            if download_pdf and paper.full_text_url:
                await parser._download_pdf(paper)

            if convert_to_markdown and paper.pdf_path:
                await parser._convert_to_markdown(paper)

        # Convert to response model
        return PubMedPaperResponse.from_pubmed_paper(paper)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper by DOI: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
