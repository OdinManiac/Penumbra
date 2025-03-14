"""Main module for Penumbra application."""

import os

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.penumbra import __version__
from src.penumbra.pubmed.api import router as pubmed_router

# Configure the logger
logger.configure(
    handlers=[
        dict(
            sink=os.environ.get("LOG_FILE", "logs/penumbra.log"),
            rotation="10 MB",
            level="INFO",
        ),
        dict(sink=lambda msg: print(msg), level="INFO"),
    ]
)

app = FastAPI(
    title="Penumbra",
    description="Penumbra API for scientific evidence-based health insights",
    version=__version__,
)

# Include PubMed router
app.include_router(pubmed_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Penumbra API",
        "version": __version__,
        "documentation": "/docs",
        "pubmed_endpoints": {
            "search": "/pubmed/search",
            "paper_by_pmid": "/pubmed/paper/{pmid}",
            "paper_by_doi": "/pubmed/paper/doi/{doi}",
        },
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    logger.info(f"Starting Penumbra API v{__version__}")
    uvicorn.run("src.penumbra.main:app", host="0.0.0.0", port=8000, reload=True)
