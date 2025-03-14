# Penumbra

A modern Python project for evidence-based health insights, using FastAPI and Pydantic.

## Features

- **Asynchronous PubMed Parser**: Search, filter, and download scientific papers based on quality criteria
- **PDF to Markdown Conversion**: Automatically convert scientific papers to markdown format
- **FastAPI Endpoints**: RESTful API for accessing scientific literature
- **Quality Filtering**: Filter papers by journal tier, study type, citation count, and more

## Installation

```bash
# Clone the repository
git clone https://github.com/OdinManiac/Penumbra.git
cd Penumbra

# Install with pip in development mode
pip install -e .
```

## Development

```bash
# Install dependencies with Poetry
poetry install

# Run tests
pytest
```

## Usage

### Running the API server

```bash
# Set required environment variables
export PUBMED_EMAIL=your.email@example.com  # Required for PubMed API access
export PUBMED_API_KEY=your_api_key  # Optional, for higher rate limits

# Run the API server
python -m src.penumbra.main
```

### Using the PubMed Parser CLI

```bash
# Search for papers on a topic
python -m src.penumbra.pubmed.cli "depression treatment" --max-results 10 --retrieve-citations --download-pdf --convert-to-markdown

# Using filters
python -m src.penumbra.pubmed.cli "depression treatment" --study-types meta_analysis systematic_review --journal-tiers tier_1 tier_2 --min-citations 10
```

### Using the PubMed Parser in code

```python
import asyncio
from src.penumbra.pubmed.config import PubMedConfig
from src.penumbra.pubmed.models import SearchCriteria, PaperFilter, JournalTier, StudyType
from src.penumbra.pubmed.parser import PubMedParser

async def search_pubmed():
    # Initialize the parser
    config = PubMedConfig(email="your.email@example.com")
    parser = PubMedParser(config)
    
    # Create search criteria
    criteria = SearchCriteria(
        query="depression treatment",
        max_results=10,
        filter=PaperFilter(
            journal_tiers={JournalTier.TIER_1, JournalTier.TIER_2},
            study_types={StudyType.META_ANALYSIS, StudyType.SYSTEMATIC_REVIEW},
        ),
        retrieve_citations=True,
        download_pdf=True,
        convert_to_markdown=True
    )
    
    # Search PubMed
    papers = await parser.search(criteria)
    
    # Print results
    for paper in papers:
        print(f"Title: {paper.title}")
        print(f"PDF: {paper.pdf_path}")
        print(f"Markdown: {paper.markdown_path}")

if __name__ == "__main__":
    asyncio.run(search_pubmed())
```

### Example Scripts

Check the `examples/` directory for usage examples:

```bash
# Run the PubMed search example
python examples/pubmed_search.py
```

## API Endpoints

Once the API server is running, you can access the following endpoints:

- **API Documentation**: http://localhost:8000/docs
- **Search PubMed**: POST /pubmed/search
- **Get Paper by PMID**: GET /pubmed/paper/{pmid}
- **Get Paper by DOI**: GET /pubmed/paper/doi/{doi}

## Directory Structure

- `src/penumbra/` - Core application code
- `src/penumbra/pubmed/` - PubMed parser modules
- `papers/pdf/` - Downloaded PDF papers
- `papers/markdown/` - Markdown conversions of papers
- `tests/` - Test suite
- `examples/` - Example usage scripts 