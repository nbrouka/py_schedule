"""
DOCX to PDF converter using LibreOffice.
"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def convert_docx_to_pdf(docx_path):
    """
    Convert DOCX file to PDF using LibreOffice.

    Args:
        docx_path: Path to the DOCX file

    Returns:
        str: Path to the generated PDF file, or None if conversion failed
    """
    pdf_path = os.path.splitext(docx_path)[0] + '.pdf'

    # Skip if PDF already exists
    if os.path.exists(pdf_path):
        return pdf_path

    try:
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir',
             os.path.dirname(docx_path) or '.', docx_path],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0 and os.path.exists(pdf_path):
            logger.info(f"  Converted to PDF: {pdf_path}")
            return pdf_path
        else:
            logger.error(f"  Conversion failed: {result.stderr}")
            return None
    except FileNotFoundError:
        logger.error("  LibreOffice not found - cannot convert DOCX to PDF")
        return None
    except Exception as e:
        logger.error(f"  Conversion error: {e}")
        return None
