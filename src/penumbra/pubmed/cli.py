"""Command-line interface for PubMed parser."""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from src.penumbra.pubmed.config import PubMedConfig
from src.penumbra.pubmed.models import (
    JournalTier,
    PaperFilter,
    SearchCriteria,
    StudyType,
)
from src.penumbra.pubmed.parser import PubMedParser


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="PubMed paper parser")

    # Required email for NCBI API
    parser.add_argument(
        "--email",
        type=str,
        required=not bool(os.environ.get("PUBMED_EMAIL")),
        help="Email for NCBI E-utilities API (required, can be set via PUBMED_EMAIL env var)",
    )

    # Search query
    parser.add_argument(
        "query", type=str, help="PubMed search query (e.g., 'depression treatment')"
    )

    # Optional arguments
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum number of results to return (default: 20)",
    )

    parser.add_argument(
        "--study-types",
        type=str,
        nargs="+",
        choices=[t.value for t in StudyType],
        help="Filter by study types",
    )

    parser.add_argument(
        "--journal-tiers",
        type=str,
        nargs="+",
        choices=[t.value for t in JournalTier],
        help="Filter by journal tiers",
    )

    parser.add_argument("--min-citations", type=int, help="Minimum number of citations")

    parser.add_argument(
        "--min-date", type=str, help="Minimum publication date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--max-date", type=str, help="Maximum publication date (YYYY-MM-DD)"
    )

    parser.add_argument("--keywords", type=str, nargs="+", help="Required keywords")

    parser.add_argument("--mesh-terms", type=str, nargs="+", help="Required MeSH terms")

    parser.add_argument(
        "--authors", type=str, nargs="+", help="Filter by author last names"
    )

    parser.add_argument(
        "--download-pdf", action="store_true", help="Download PDFs for matching papers"
    )

    parser.add_argument(
        "--convert-to-markdown", action="store_true", help="Convert PDFs to markdown"
    )

    parser.add_argument(
        "--retrieve-citations",
        action="store_true",
        help="Retrieve citation counts for papers",
    )

    parser.add_argument(
        "--retrieve-full-text",
        action="store_true",
        help="Try to retrieve full text URLs for papers",
    )

    parser.add_argument(
        "--pdf-dir", type=str, help="Directory to store PDF files (default: papers/pdf)"
    )

    parser.add_argument(
        "--markdown-dir",
        type=str,
        help="Directory to store markdown files (default: papers/markdown)",
    )

    parser.add_argument(
        "--api-key", type=str, help="NCBI API key for higher rate limits"
    )

    parser.add_argument("--output-json", type=str, help="Save results to JSON file")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    return parser.parse_args()


def create_filter_from_args(args: argparse.Namespace) -> Optional[PaperFilter]:
    """Create a paper filter from command line arguments."""
    filter_args = {}

    # Parse journal tiers
    if args.journal_tiers:
        filter_args["journal_tiers"] = {
            JournalTier(tier) for tier in args.journal_tiers
        }

    # Parse study types
    if args.study_types:
        filter_args["study_types"] = {StudyType(stype) for stype in args.study_types}

    # Parse date ranges
    if args.min_date:
        try:
            filter_args["min_publication_date"] = datetime.strptime(
                args.min_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            logger.error(
                f"Invalid min date format: {args.min_date}, expected YYYY-MM-DD"
            )
            sys.exit(1)

    if args.max_date:
        try:
            filter_args["max_publication_date"] = datetime.strptime(
                args.max_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            logger.error(
                f"Invalid max date format: {args.max_date}, expected YYYY-MM-DD"
            )
            sys.exit(1)

    # Parse other filters
    if args.min_citations is not None:
        filter_args["min_citations"] = args.min_citations

    if args.keywords:
        filter_args["required_keywords"] = set(args.keywords)

    if args.mesh_terms:
        filter_args["required_mesh_terms"] = set(args.mesh_terms)

    if args.authors:
        filter_args["author_names"] = set(args.authors)

    # Only create a filter if we have at least one filter criterion
    if filter_args:
        return PaperFilter(**filter_args)

    return None


def create_config_from_args(args: argparse.Namespace) -> PubMedConfig:
    """Create configuration from command line arguments."""
    config_args = {}

    # Email is required for NCBI API
    if args.email:
        config_args["email"] = args.email
    elif "PUBMED_EMAIL" in os.environ:
        config_args["email"] = os.environ["PUBMED_EMAIL"]
    else:
        logger.error(
            "Email is required for PubMed API. Provide --email or set PUBMED_EMAIL env var."
        )
        sys.exit(1)

    # Optional API key
    if args.api_key:
        config_args["api_key"] = args.api_key
    elif "PUBMED_API_KEY" in os.environ:
        config_args["api_key"] = os.environ["PUBMED_API_KEY"]

    # Storage directories
    if args.pdf_dir:
        config_args["pdf_dir"] = Path(args.pdf_dir)

    if args.markdown_dir:
        config_args["markdown_dir"] = Path(args.markdown_dir)

    return PubMedConfig(**config_args)


async def main() -> None:
    """Run the PubMed parser from command line arguments."""
    args = parse_args()

    # Configure logging
    log_level = "DEBUG" if args.debug else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)

    # Create configuration
    config = create_config_from_args(args)

    # Create paper filter
    paper_filter = create_filter_from_args(args)

    # Create search criteria
    criteria = SearchCriteria(
        query=args.query,
        max_results=args.max_results,
        filter=paper_filter,
        retrieve_citations=args.retrieve_citations,
        retrieve_full_text=args.retrieve_full_text or args.download_pdf,
        download_pdf=args.download_pdf,
        convert_to_markdown=args.convert_to_markdown,
    )

    # Initialize parser
    parser = PubMedParser(config)

    # Search PubMed
    logger.info(f"Searching PubMed for: {criteria.query}")
    papers = await parser.search(criteria)

    # Display results
    logger.info(f"Found {len(papers)} matching papers")

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

        if paper.doi:
            print(f"    DOI: {paper.doi}")

        if paper.pmid:
            print(f"    PMID: {paper.pmid}")

        if paper.pdf_path:
            print(f"    PDF: {paper.pdf_path}")

        if paper.markdown_path:
            print(f"    Markdown: {paper.markdown_path}")

    # Save results to JSON if requested
    if args.output_json:
        result_data = []
        for paper in papers:
            paper_dict = paper.model_dump()
            # Convert dates to strings for JSON serialization
            if paper_dict.get("publication_date"):
                paper_dict["publication_date"] = paper_dict[
                    "publication_date"
                ].isoformat()
            result_data.append(paper_dict)

        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)

        logger.info(f"Saved results to {args.output_json}")


if __name__ == "__main__":
    asyncio.run(main())
