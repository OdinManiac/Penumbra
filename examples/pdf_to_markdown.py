#!/usr/bin/env python
"""Example script for converting PDF to Markdown using Docling."""

import argparse
import sys
from pathlib import Path

from src.utils.pdf_md_converter import PDFToMarkdownConverter


def main():
    """Run the PDF to Markdown conversion example."""
    parser = argparse.ArgumentParser(
        description="Convert PDF to Markdown using Docling"
    )
    parser.add_argument("input_file", help="Path to the input PDF file or URL")
    parser.add_argument(
        "-o",
        "--output",
        help="Path to the output Markdown file (default: print to stdout)",
    )
    parser.add_argument(
        "--use-gpu", action="store_true", help="Use GPU acceleration if available"
    )
    parser.add_argument(
        "--enable-vlm",
        action="store_true",
        help="Enable Visual Language Model for image understanding",
    )
    parser.add_argument(
        "--force-ocr", action="store_true", help="Force OCR for all pages"
    )
    parser.add_argument(
        "--ocr-language", help="Language for OCR (e.g., 'eng', 'fra', 'deu')"
    )
    # Note: These options are kept for backward compatibility but don't affect the conversion
    # in Docling v2 as tables and figures are included automatically
    parser.add_argument(
        "--extract-tables",
        action="store_true",
        help="Extract tables from the PDF (informational only, tables are included automatically)",
    )
    parser.add_argument(
        "--extract-figures",
        action="store_true",
        help="Extract figures from the PDF (informational only, figures are included automatically)",
    )
    parser.add_argument(
        "--vlm-model", help="VLM model name to use for image understanding"
    )

    args = parser.parse_args()

    try:
        # Create pipeline options
        pipeline_options = PDFToMarkdownConverter.create_pipeline_options(
            use_gpu=args.use_gpu,
            enable_vlm=args.enable_vlm,
            vlm_model=args.vlm_model,
        )

        # Initialize converter
        converter = PDFToMarkdownConverter(pipeline_options=pipeline_options)

        # Prepare conversion options
        options = {}
        if args.force_ocr:
            options["force_ocr"] = True
        if args.ocr_language:
            options["ocr_language"] = args.ocr_language

        # Convert PDF to Markdown
        markdown = converter.convert_pdf(
            source=args.input_file,
            output_path=args.output,
            options=options,
        )

        # Print to stdout if no output file is specified
        if not args.output:
            print(markdown)

        # Print conversion information
        print(f"\nSource: {args.input_file}")
        print(f"GPU Acceleration: {'Enabled' if args.use_gpu else 'Disabled'}")
        print(f"VLM: {'Enabled' if args.enable_vlm else 'Disabled'}")
        if args.enable_vlm and args.vlm_model:
            print(f"VLM Model: {args.vlm_model}")
        print(f"OCR: {'Forced' if args.force_ocr else 'Auto'}")
        if args.ocr_language:
            print(f"OCR Language: {args.ocr_language}")
        print(f"Tables and Figures: Included automatically by Docling v2")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
