"""
PDF Generator Service
Converts HTML to PDF using WeasyPrint.
"""
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from typing import Optional
import os


def generate_pdf_from_html(
    html_content: str,
    output_path: str,
    base_url: Optional[str] = None
) -> str:
    """
    Generate PDF from HTML content using WeasyPrint.

    Args:
        html_content: HTML string to convert
        output_path: Path to save PDF file
        base_url: Base URL for resolving relative paths (optional)

    Returns:
        Path to generated PDF file
    """
    # Configure fonts
    font_config = FontConfiguration()

    # Create HTML object
    html = HTML(string=html_content, base_url=base_url)

    # Generate PDF
    html.write_pdf(
        output_path,
        font_config=font_config,
        optimize_images=True,
        jpeg_quality=85
    )

    return output_path


def generate_pdf_from_file(
    html_path: str,
    output_path: str
) -> str:
    """
    Generate PDF from HTML file using WeasyPrint.

    Args:
        html_path: Path to HTML file
        output_path: Path to save PDF file

    Returns:
        Path to generated PDF file
    """
    # Configure fonts
    font_config = FontConfiguration()

    # Create HTML object from file
    html = HTML(filename=html_path)

    # Generate PDF
    html.write_pdf(
        output_path,
        font_config=font_config,
        optimize_images=True,
        jpeg_quality=85
    )

    return output_path


def get_pdf_size_mb(pdf_path: str) -> float:
    """
    Get PDF file size in megabytes.

    Args:
        pdf_path: Path to PDF file

    Returns:
        File size in MB
    """
    if not os.path.exists(pdf_path):
        return 0.0

    size_bytes = os.path.getsize(pdf_path)
    size_mb = size_bytes / (1024 * 1024)

    return round(size_mb, 2)
