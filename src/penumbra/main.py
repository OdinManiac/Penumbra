"""Main module for Penumbra application."""

import uvicorn
from fastapi import FastAPI
from loguru import logger

from src.penumbra import __version__

app = FastAPI(
    title="Penumbra",
    description="Penumbra API",
    version=__version__,
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to Penumbra API", "version": __version__}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    logger.info(f"Starting Penumbra API v{__version__}")
    uvicorn.run("src.penumbra.main:app", host="0.0.0.0", port=8000, reload=True)
