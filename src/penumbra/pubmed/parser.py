"""Asynchronous PubMed parser for retrieving and processing scientific papers."""

import asyncio
from datetime import datetime
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, AsyncGenerator, Union
from urllib.parse import urlparse, parse_qs

import aiofiles
import aiohttp
import httpx
from Bio import Entrez
from bs4 import BeautifulSoup
from loguru import logger
from semanticscholar import SemanticScholar
from scholarly import scholarly

from src.penumbra.pubmed.models import (
    Author,
    Citation,
    Journal,
    JournalTier,
    PaperFilter,
    PubMedPaper,
    SearchCriteria,
    StudyType,
)
from src.penumbra.pubmed.config import PubMedConfig
from src.utils.pdf_md_converter import PDFToMarkdownConverter


class PubMedParser:
    """Asynchronous PubMed parser for scientific literature."""

    def __init__(self, config: Optional[PubMedConfig] = None):
        """
        Initialize the PubMed parser.

        Args:
            config: Optional parser configuration
        """
        self.config = config or PubMedConfig.from_env()

        # Set up NCBI Entrez
        Entrez.email = self.config.email
        Entrez.api_key = self.config.api_key
        Entrez.tool = self.config.tool_name

        # Initialize PDF to Markdown converter
        self.pdf_converter = PDFToMarkdownConverter()

        # Initialize semantic scholar client
        self.s2_client = SemanticScholar()

        # Initialize journal tier mapping
        self._init_journal_tier_mapping()

        logger.info(f"Initialized PubMed parser with email: {self.config.email}")

    def _init_journal_tier_mapping(self) -> None:
        """Initialize the journal tier mapping with default values."""
        # Default tier mapping for well-known journals
        default_mappings = {
            "Nature": JournalTier.TIER_1,
            "Science": JournalTier.TIER_1,
            "Cell": JournalTier.TIER_1,
            "The New England Journal of Medicine": JournalTier.TIER_1,
            "The Lancet": JournalTier.TIER_1,
            "JAMA": JournalTier.TIER_1,
            "BMJ": JournalTier.TIER_1,
            "Proceedings of the National Academy of Sciences": JournalTier.TIER_2,
            "PLOS ONE": JournalTier.TIER_3,
        }

        # Convert string values from config to enum
        tier_mapping = {}
        for journal, tier_str in self.config.journal_tier_mapping.items():
            try:
                tier_mapping[journal] = JournalTier(tier_str)
            except ValueError:
                logger.warning(f"Invalid journal tier: {tier_str} for {journal}")
                tier_mapping[journal] = JournalTier.UNKNOWN

        # Merge with defaults
        self.journal_tier_mapping = {**default_mappings, **tier_mapping}

    async def search(self, criteria: SearchCriteria) -> List[PubMedPaper]:
        """
        Search PubMed for papers matching the criteria.

        Args:
            criteria: Search criteria including query and filters

        Returns:
            List of matched papers
        """
        logger.info(
            f"Searching PubMed with query: {criteria.query}, max results: {criteria.max_results}"
        )

        # Search PubMed and get PMIDs
        pmids = await self._search_pubmed(criteria.query, criteria.max_results)

        if not pmids:
            logger.warning(f"No results found for query: {criteria.query}")
            return []

        logger.info(f"Found {len(pmids)} results, fetching details")

        # Fetch paper details
        papers = []
        async for paper in self._fetch_papers(pmids):
            # Apply filter if provided
            if criteria.filter and not criteria.filter.matches(paper):
                continue

            # Get citations if requested
            if criteria.retrieve_citations and (paper.pmid or paper.doi):
                await self._fetch_citations(paper)

            # Get full text if requested
            if criteria.retrieve_full_text and (paper.pmid or paper.doi):
                await self._fetch_full_text_url(paper)

            # Download PDF if requested
            if criteria.download_pdf and paper.full_text_url:
                await self._download_pdf(paper)

            # Convert to markdown if requested
            if criteria.convert_to_markdown and paper.pdf_path:
                await self._convert_to_markdown(paper)

            papers.append(paper)

        logger.info(f"Finished processing {len(papers)} papers after filtering")
        return papers

    async def _search_pubmed(self, query: str, max_results: int) -> List[str]:
        """
        Search PubMed and return list of PMIDs.

        Args:
            query: PubMed search query
            max_results: Maximum number of results to return

        Returns:
            List of PMIDs
        """
        loop = asyncio.get_event_loop()

        try:
            # Perform the search to get the count and PMIDs
            search_results = await loop.run_in_executor(
                None,
                lambda: Entrez.read(
                    Entrez.esearch(
                        db="pubmed", term=query, retmax=max_results, sort="relevance"
                    )
                ),
            )

            pmids = search_results.get("IdList", [])
            logger.debug(f"Search returned {len(pmids)} PMIDs")

            return pmids

        except Exception as e:
            logger.error(f"Error searching PubMed: {str(e)}")
            return []

    async def _fetch_papers(
        self, pmids: List[str]
    ) -> AsyncGenerator[PubMedPaper, None]:
        """
        Fetch detailed information for multiple PubMed papers.

        Args:
            pmids: List of PubMed IDs

        Yields:
            PubMedPaper objects with detailed information
        """
        loop = asyncio.get_event_loop()

        # Process in batches to avoid overwhelming the NCBI servers
        batch_size = 100
        for i in range(0, len(pmids), batch_size):
            batch_pmids = pmids[i : i + batch_size]

            try:
                # Fetch detailed information for the batch
                fetch_results = await loop.run_in_executor(
                    None,
                    lambda: Entrez.read(
                        Entrez.efetch(
                            db="pubmed", id=",".join(batch_pmids), retmode="xml"
                        )
                    ),
                )

                # Process each article in the batch
                for article in fetch_results["PubmedArticle"]:
                    try:
                        paper = await self._parse_pubmed_article(article)
                        yield paper
                    except Exception as e:
                        logger.error(f"Error parsing article: {str(e)}")
                        continue

                # Rate limiting
                await asyncio.sleep(1.0 / self.config.requests_per_second)

            except Exception as e:
                logger.error(f"Error fetching batch of papers: {str(e)}")
                continue

    async def _parse_pubmed_article(self, article: Dict[str, Any]) -> PubMedPaper:
        """
        Parse a PubMed article XML into a structured PubMedPaper.

        Args:
            article: PubMed article data from E-utilities

        Returns:
            Structured PubMedPaper object
        """
        # Extract the PubMed ID
        pmid = article["MedlineCitation"]["PMID"]

        # Extract article metadata
        medline_article = article["MedlineCitation"]["Article"]

        # Get title
        title = medline_article.get("ArticleTitle", "")

        # Get abstract
        abstract = ""
        if (
            "Abstract" in medline_article
            and "AbstractText" in medline_article["Abstract"]
        ):
            abstract_parts = medline_article["Abstract"]["AbstractText"]

            if isinstance(abstract_parts, list):
                # Handle structured abstracts with labeled sections
                for part in abstract_parts:
                    if isinstance(part, str):
                        abstract += part + " "
                    elif isinstance(part, dict) and "#text" in part:
                        label = part.get("Label", "")
                        text = part["#text"]
                        if label:
                            abstract += f"{label}: {text} "
                        else:
                            abstract += text + " "
            else:
                # Handle simple abstracts
                abstract = str(abstract_parts)

        # Get authors
        authors = []
        if (
            "AuthorList" in medline_article
            and "Author" in medline_article["AuthorList"]
        ):
            author_list = medline_article["AuthorList"]["Author"]

            # Ensure author_list is a list (it's a dict if there's only one author)
            if not isinstance(author_list, list):
                author_list = [author_list]

            for author_data in author_list:
                if isinstance(author_data, dict):
                    last_name = author_data.get("LastName", "")
                    fore_name = author_data.get("ForeName", "")
                    initials = author_data.get("Initials", "")

                    # Get affiliations
                    affiliations = []
                    if "AffiliationInfo" in author_data:
                        affiliation_info = author_data["AffiliationInfo"]
                        if isinstance(affiliation_info, list):
                            affiliations = [
                                aff.get("Affiliation", "")
                                for aff in affiliation_info
                                if isinstance(aff, dict)
                            ]
                        elif isinstance(affiliation_info, dict):
                            affiliations = [affiliation_info.get("Affiliation", "")]

                    if last_name:  # Only add if we have at least a last name
                        authors.append(
                            Author(
                                last_name=last_name,
                                fore_name=fore_name,
                                initials=initials,
                                affiliations=affiliations,
                            )
                        )

        # Get journal information
        journal = None
        if "Journal" in medline_article:
            journal_data = medline_article["Journal"]

            journal_name = journal_data.get("Title", "")
            issn = journal_data.get("ISSN", "")

            # Get volume and issue
            volume = journal_data.get("JournalIssue", {}).get("Volume", "")
            issue = journal_data.get("JournalIssue", {}).get("Issue", "")

            # Determine journal tier based on name
            tier = JournalTier.UNKNOWN
            if journal_name in self.journal_tier_mapping:
                tier = self.journal_tier_mapping[journal_name]

            journal = Journal(
                name=journal_name, issn=issn, volume=volume, issue=issue, tier=tier
            )

        # Get publication date
        publication_date = None
        if (
            "Journal" in medline_article
            and "JournalIssue" in medline_article["Journal"]
        ):
            pub_date_data = medline_article["Journal"]["JournalIssue"].get(
                "PubDate", {}
            )

            year = pub_date_data.get("Year", "")
            month = pub_date_data.get("Month", "1")
            day = pub_date_data.get("Day", "1")

            # Month might be a name, try to convert
            if not month.isdigit():
                try:
                    month = str(datetime.strptime(month, "%b").month)
                except ValueError:
                    try:
                        month = str(datetime.strptime(month, "%B").month)
                    except ValueError:
                        month = "1"  # Default to January

            if year:
                try:
                    publication_date = datetime(int(year), int(month), int(day)).date()
                except (ValueError, TypeError):
                    # Invalid date components, try just the year
                    try:
                        publication_date = datetime(int(year), 1, 1).date()
                    except (ValueError, TypeError):
                        pass

        # Get MeSH terms
        mesh_terms = []
        if "MeshHeadingList" in article["MedlineCitation"]:
            mesh_headings = article["MedlineCitation"]["MeshHeadingList"]
            for heading in mesh_headings:
                if "DescriptorName" in heading:
                    term = heading["DescriptorName"]
                    if isinstance(term, dict) and "#text" in term:
                        mesh_terms.append(term["#text"])
                    elif isinstance(term, str):
                        mesh_terms.append(term)

        # Get keywords
        keywords = []
        if "KeywordList" in article["MedlineCitation"]:
            keyword_lists = article["MedlineCitation"]["KeywordList"]
            for keyword_list in keyword_lists:
                if "Keyword" in keyword_list:
                    for keyword in keyword_list["Keyword"]:
                        if isinstance(keyword, dict) and "#text" in keyword:
                            keywords.append(keyword["#text"])
                        elif isinstance(keyword, str):
                            keywords.append(keyword)

        # Get DOI
        doi = None
        if "ArticleIdList" in article["PubmedData"]:
            for article_id in article["PubmedData"]["ArticleIdList"]:
                if isinstance(article_id, dict) and "#text" in article_id:
                    if article_id.get("IdType") == "doi":
                        doi = article_id["#text"]
                        break

        # Determine study type based on publication type
        study_type = StudyType.UNKNOWN
        if "PublicationTypeList" in medline_article:
            pub_types = medline_article["PublicationTypeList"]
            for pub_type in pub_types:
                if isinstance(pub_type, dict) and "#text" in pub_type:
                    pub_type_text = pub_type["#text"].lower()

                    if "meta-analysis" in pub_type_text:
                        study_type = StudyType.META_ANALYSIS
                        break
                    elif "systematic review" in pub_type_text:
                        study_type = StudyType.SYSTEMATIC_REVIEW
                        break
                    elif "randomized controlled trial" in pub_type_text:
                        study_type = StudyType.RANDOMIZED_CONTROLLED_TRIAL
                        break
                    elif "cohort" in pub_type_text:
                        study_type = StudyType.COHORT_STUDY
                        break
                    elif "case control" in pub_type_text:
                        study_type = StudyType.CASE_CONTROL
                        break
                    elif "case series" in pub_type_text:
                        study_type = StudyType.CASE_SERIES
                        break
                    elif "case report" in pub_type_text:
                        study_type = StudyType.CASE_REPORT
                        break
                    elif "expert" in pub_type_text and "opinion" in pub_type_text:
                        study_type = StudyType.EXPERT_OPINION
                        break

        # If study type is still unknown, try to infer from title or abstract
        if study_type == StudyType.UNKNOWN:
            full_text = f"{title} {abstract}".lower()

            if "meta-analysis" in full_text or "meta analysis" in full_text:
                study_type = StudyType.META_ANALYSIS
            elif "systematic review" in full_text:
                study_type = StudyType.SYSTEMATIC_REVIEW
            elif "randomized" in full_text and "trial" in full_text:
                study_type = StudyType.RANDOMIZED_CONTROLLED_TRIAL
            elif "cohort" in full_text:
                study_type = StudyType.COHORT_STUDY
            elif "case control" in full_text:
                study_type = StudyType.CASE_CONTROL
            elif "case series" in full_text:
                study_type = StudyType.CASE_SERIES
            elif "case report" in full_text:
                study_type = StudyType.CASE_REPORT

        return PubMedPaper(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            publication_date=publication_date,
            study_type=study_type,
            keywords=keywords,
            mesh_terms=mesh_terms,
            doi=doi,
            citations=Citation(count=0),  # Initialize with empty citation
        )

    async def _fetch_citations(self, paper: PubMedPaper) -> None:
        """
        Fetch citation information for a paper.

        Args:
            paper: Paper to fetch citations for
        """
        if not paper.doi and not paper.pmid:
            logger.warning("Cannot fetch citations without DOI or PMID")
            return

        try:
            # Try Semantic Scholar first as it has better citation data
            if paper.doi:
                paper_data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.s2_client.get_paper(f"DOI:{paper.doi}")
                )

                if paper_data and "citationCount" in paper_data:
                    paper.citations = Citation(
                        count=paper_data.get("citationCount", 0),
                        h_index=None,  # Not directly available from S2 API
                        i10_index=None,  # Not directly available from S2 API
                    )
                    logger.debug(
                        f"Updated citation count from Semantic Scholar: {paper.citations.count}"
                    )
                    return

            # Fallback to Google Scholar
            if paper.title:
                search_query = scholarly.search_pubs(paper.title)

                # Get first result
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: next(search_query, None)
                )

                if result and "num_citations" in result:
                    paper.citations = Citation(
                        count=result.get("num_citations", 0),
                        h_index=None,  # Not available in basic search
                        i10_index=None,  # Not available in basic search
                    )
                    logger.debug(
                        f"Updated citation count from Google Scholar: {paper.citations.count}"
                    )
                    return

            logger.warning(
                f"Could not find citation information for paper: {paper.title}"
            )

        except Exception as e:
            logger.error(f"Error fetching citations: {str(e)}")

    async def _fetch_full_text_url(self, paper: PubMedPaper) -> None:
        """
        Fetch the full text URL for a paper.

        Args:
            paper: Paper to fetch full text URL for
        """
        if not paper.pmid and not paper.doi:
            logger.warning("Cannot fetch full text without PMID or DOI")
            return

        try:
            # Try PubMed Central first
            if paper.pmid:
                url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/pmid/{paper.pmid}"

                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            text = await response.text()
                            soup = BeautifulSoup(text, "html.parser")

                            # Look for PDF link
                            pdf_link = soup.find("a", {"class": "int-view"})
                            if pdf_link and "href" in pdf_link.attrs:
                                pdf_url = pdf_link["href"]
                                if not pdf_url.startswith("http"):
                                    pdf_url = f"https://www.ncbi.nlm.nih.gov{pdf_url}"

                                paper.full_text_url = pdf_url
                                logger.debug(f"Found full text URL from PMC: {pdf_url}")
                                return

            # Try DOI resolver if we have a DOI
            if paper.doi:
                doi_url = f"https://doi.org/{paper.doi}"

                async with aiohttp.ClientSession() as session:
                    # Follow redirects to publisher site
                    async with session.get(doi_url, allow_redirects=True) as response:
                        if response.status == 200:
                            final_url = str(response.url)

                            # Extract PDF URL from well-known publishers
                            if "nature.com" in final_url:
                                pdf_url = final_url.replace(
                                    "/articles/", "/articles/pdf/"
                                )
                                paper.full_text_url = pdf_url
                                return

                            # For other publishers, try to find PDF link on the page
                            text = await response.text()
                            soup = BeautifulSoup(text, "html.parser")

                            # Common patterns for PDF links
                            pdf_links = soup.find_all(
                                "a", href=re.compile(r"\.(pdf|full)")
                            )
                            for link in pdf_links:
                                if (
                                    "pdf" in link.text.lower()
                                    or "full text" in link.text.lower()
                                ):
                                    pdf_url = link["href"]
                                    if not pdf_url.startswith("http"):
                                        # Handle relative URLs
                                        base_url = urlparse(final_url)
                                        pdf_url = f"{base_url.scheme}://{base_url.netloc}{pdf_url}"

                                    paper.full_text_url = pdf_url
                                    logger.debug(
                                        f"Found full text URL from publisher: {pdf_url}"
                                    )
                                    return

            logger.warning(f"Could not find full text URL for paper: {paper.title}")

        except Exception as e:
            logger.error(f"Error fetching full text URL: {str(e)}")

    async def _download_pdf(self, paper: PubMedPaper) -> None:
        """
        Download the PDF for a paper.

        Args:
            paper: Paper to download PDF for
        """
        if not paper.full_text_url:
            logger.warning("Cannot download PDF without full text URL")
            return

        filename = f"{paper.filename_base}.pdf"
        pdf_path = self.config.pdf_dir / filename

        # Skip if already downloaded
        if pdf_path.exists():
            logger.info(f"PDF already exists: {pdf_path}")
            paper.pdf_path = str(pdf_path)
            return

        try:
            logger.info(f"Downloading PDF from {paper.full_text_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    paper.full_text_url, timeout=self.config.download_timeout
                ) as response:
                    if response.status == 200:
                        # Ensure PDF directory exists
                        self.config.pdf_dir.mkdir(parents=True, exist_ok=True)

                        # Save PDF content
                        pdf_content = await response.read()
                        async with aiofiles.open(pdf_path, "wb") as f:
                            await f.write(pdf_content)

                        paper.pdf_path = str(pdf_path)
                        logger.info(f"PDF downloaded to {pdf_path}")
                    else:
                        logger.warning(
                            f"Failed to download PDF, status: {response.status}"
                        )

        except Exception as e:
            logger.error(f"Error downloading PDF: {str(e)}")

    async def _convert_to_markdown(self, paper: PubMedPaper) -> None:
        """
        Convert a paper's PDF to Markdown.

        Args:
            paper: Paper to convert to Markdown
        """
        if not paper.pdf_path:
            logger.warning("Cannot convert to Markdown without PDF path")
            return

        filename = f"{paper.filename_base}.md"
        markdown_path = self.config.markdown_dir / filename

        # Skip if already converted
        if markdown_path.exists():
            logger.info(f"Markdown already exists: {markdown_path}")
            paper.markdown_path = str(markdown_path)
            return

        try:
            logger.info(f"Converting PDF to Markdown: {paper.pdf_path}")

            # Ensure markdown directory exists
            self.config.markdown_dir.mkdir(parents=True, exist_ok=True)

            # Convert PDF to Markdown using Docling
            # Run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()

            markdown_content = await loop.run_in_executor(
                None,
                lambda: self.pdf_converter.convert_pdf(
                    source=paper.pdf_path, output_path=markdown_path
                ),
            )

            paper.markdown_path = str(markdown_path)
            logger.info(f"PDF converted to Markdown: {markdown_path}")

        except Exception as e:
            logger.error(f"Error converting PDF to Markdown: {str(e)}")

    async def get_paper_by_pmid(self, pmid: str) -> Optional[PubMedPaper]:
        """
        Get a paper by its PubMed ID.

        Args:
            pmid: PubMed ID

        Returns:
            PubMedPaper if found, None otherwise
        """
        papers = []
        async for paper in self._fetch_papers([pmid]):
            papers.append(paper)

        return papers[0] if papers else None

    async def get_paper_by_doi(self, doi: str) -> Optional[PubMedPaper]:
        """
        Get a paper by its DOI.

        Args:
            doi: DOI

        Returns:
            PubMedPaper if found, None otherwise
        """
        # Search PubMed by DOI
        query = f"{doi}[DOI]"
        pmids = await self._search_pubmed(query, 1)

        if not pmids:
            logger.warning(f"No paper found with DOI: {doi}")
            return None

        # Get the paper details
        papers = []
        async for paper in self._fetch_papers(pmids):
            papers.append(paper)

        return papers[0] if papers else None
