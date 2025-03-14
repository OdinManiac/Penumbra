"""PDF to Markdown converter using Docling."""

from pathlib import Path
from typing import Dict, Optional, Union, Any

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PipelineOptions,
    PdfPipelineOptions,
    AcceleratorOptions,
    AcceleratorDevice,
)
from loguru import logger


class PDFToMarkdownConverter:
    """Convert PDF files to Markdown using Docling."""

    def __init__(self, pipeline_options: Optional[PipelineOptions] = None):
        """
        Initialize the PDF to Markdown converter.

        Args:
            pipeline_options: Optional Docling pipeline options for customization
        """
        # In Docling v2, pipeline_options need to be passed through format_options
        if pipeline_options:
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        else:
            self.converter = DocumentConverter()

        logger.info("Initialized PDF to Markdown converter with Docling")

    def convert_pdf(
        self,
        source: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Convert a PDF file to Markdown.

        Args:
            source: Path to the PDF file or URL
            output_path: Optional path to save the Markdown output
            options: Optional conversion options
                - force_ocr: Force OCR for all pages
                - ocr_language: Language for OCR (e.g., 'eng', 'fra', 'deu')
                - extract_tables: Whether to extract tables (note: this is handled automatically by Docling)
                - extract_figures: Whether to extract figures (note: this is handled automatically by Docling)

        Returns:
            The Markdown content as a string
        """
        logger.info(f"Converting PDF from {source} to Markdown")
        options = options or {}

        try:
            # Set up conversion options
            convert_kwargs = {}

            # Handle OCR options
            if options.get("force_ocr"):
                convert_kwargs["force_ocr"] = True

            if "ocr_language" in options:
                convert_kwargs["ocr_language"] = options["ocr_language"]

            # Convert the PDF using Docling
            result = self.converter.convert(source, **convert_kwargs)

            # Export to Markdown - in Docling v2, tables and figures are included automatically
            # and the export_to_markdown method doesn't accept include_tables or include_figures parameters
            markdown_content = result.document.export_to_markdown()

            # Save to file if output path is provided
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(markdown_content)
                logger.info(f"Markdown content saved to {output_path}")

            return markdown_content

        except Exception as e:
            logger.error(f"Error converting PDF to Markdown: {str(e)}")
            raise

    @staticmethod
    def create_pipeline_options(
        use_gpu: bool = False, enable_vlm: bool = False, vlm_model: Optional[str] = None
    ) -> PdfPipelineOptions:
        """
        Create pipeline options for Docling.

        Args:
            use_gpu: Whether to use GPU acceleration
            enable_vlm: Whether to enable Visual Language Model for image understanding
            vlm_model: Optional VLM model name

        Returns:
            PdfPipelineOptions object for Docling
        """
        # Use PdfPipelineOptions instead of generic PipelineOptions
        options = PdfPipelineOptions()

        # Configure accelerator options
        accelerator_options = AcceleratorOptions()

        # Configure GPU usage
        if use_gpu:
            accelerator_options.device = AcceleratorDevice.CUDA
            # Enable flash attention for better performance if available
            accelerator_options.cuda_use_flash_attention2 = True
        else:
            accelerator_options.device = AcceleratorDevice.CPU

        # Set accelerator options
        options.accelerator_options = accelerator_options

        # Configure VLM
        if enable_vlm:
            options.enable_vlm = True
            if vlm_model:
                options.vlm_model = vlm_model

        return options
