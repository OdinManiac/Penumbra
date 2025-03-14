#!/usr/bin/env python
"""Example script to demonstrate PubMed parser usage."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.penumbra.pubmed.config import PubMedConfig
from src.penumbra.pubmed.models import (
    JournalTier,
    PaperFilter,
    SearchCriteria,
    StudyType,
)
from src.penumbra.pubmed.parser import PubMedParser


async def search_depression_treatments():
    """Search for high-quality papers on depression treatments."""
    # Check for email environment variable
    if not os.environ.get("PUBMED_EMAIL"):
        print("Please set the PUBMED_EMAIL environment variable.")
        print("Example: export PUBMED_EMAIL=your.email@example.com")
        return

    # Initialize the parser
    config = PubMedConfig.from_env()
    parser = PubMedParser(config)

    # Create a filter for high-quality papers
    paper_filter = PaperFilter(
        # Only recent papers (last 5 years)
        min_publication_date=(datetime.now() - timedelta(days=5 * 365)).date(),
        # Only high-quality journals
        journal_tiers={JournalTier.TIER_1, JournalTier.TIER_2},
        # Only meta-analyses and systematic reviews
        study_types={StudyType.META_ANALYSIS, StudyType.SYSTEMATIC_REVIEW},
        # At least 10 citations
        min_citations=10,
        # Required keywords
        required_keywords={"depression", "treatment", "efficacy"},
    )

    # Create search criteria
    criteria = SearchCriteria(
        query="depression treatment efficacy",
        max_results=10,  # Limit to 10 results for this example
        filter=paper_filter,
        retrieve_citations=True,
        retrieve_full_text=True,
        download_pdf=True,
        convert_to_markdown=True,
    )

    # Search PubMed
    print(f"Searching PubMed for: {criteria.query}")
    print("This may take a few minutes...")

    papers = await parser.search(criteria)

    # Display results
    print(f"\nFound {len(papers)} matching papers:")

    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}] {paper.title}")
        print(f"    Authors: {', '.join(a.last_name for a in paper.authors[:3])}")
        if len(paper.authors) > 3:
            print(f"    ... and {len(paper.authors) - 3} more authors")

        if paper.journal:
            print(
                f"    Journal: {paper.journal.name} (Tier: {paper.journal.tier.value})"
            )

        if paper.publication_date:
            print(f"    Published: {paper.publication_date.isoformat()}")

        print(f"    Study Type: {paper.study_type.value}")

        if paper.citations:
            print(f"    Citations: {paper.citations.count}")

        if paper.pdf_path:
            print(f"    PDF saved to: {paper.pdf_path}")

        if paper.markdown_path:
            print(f"    Markdown saved to: {paper.markdown_path}")


async def search_by_doi():
    """Demonstrate fetching a paper by DOI."""
    # Check for email environment variable
    if not os.environ.get("PUBMED_EMAIL"):
        print("Please set the PUBMED_EMAIL environment variable.")
        print("Example: export PUBMED_EMAIL=your.email@example.com")
        return

    # Initialize the parser
    config = PubMedConfig.from_env()
    parser = PubMedParser(config)

    # Nature paper DOI
    doi = "10.1038/s41380-021-01113-1"  # Depression treatment paper

    print(f"Fetching paper with DOI: {doi}")
    paper = await parser.get_paper_by_doi(doi)

    if not paper:
        print(f"Paper with DOI {doi} not found")
        return

    # Get full text and PDF
    if not paper.full_text_url:
        await parser._fetch_full_text_url(paper)

    if paper.full_text_url:
        await parser._download_pdf(paper)

    if paper.pdf_path:
        await parser._convert_to_markdown(paper)

    # Display paper details
    print(f"\nTitle: {paper.title}")
    print(f"Authors: {', '.join(a.last_name for a in paper.authors)}")

    if paper.journal:
        print(f"Journal: {paper.journal.name}")

    if paper.publication_date:
        print(f"Published: {paper.publication_date.isoformat()}")

    print(f"Abstract: {paper.abstract[:200]}...")

    if paper.pdf_path:
        print(f"PDF saved to: {paper.pdf_path}")

    if paper.markdown_path:
        print(f"Markdown saved to: {paper.markdown_path}")


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    print("Penumbra PubMed Parser Example")
    print("============================")

    # Choose which example to run
    print("1. Search for depression treatment papers")
    print("2. Fetch specific paper by DOI")

    choice = input("Enter your choice (1 or 2): ")

    if choice == "1":
        asyncio.run(search_depression_treatments())
    elif choice == "2":
        asyncio.run(search_by_doi())
    else:
        print("Invalid choice. Please enter 1 or 2.")
