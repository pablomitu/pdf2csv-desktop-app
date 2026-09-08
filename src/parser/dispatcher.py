# parser/dispatcher.py
"""
Unified PDF Parser Dispatcher

Automatically selects the correct parser (BPNG or BSP) based on PDF content.
Provides a single interface for the GUI or CLI to parse any supported PDF.

Note: BSPParser internally auto-detects which of the two known BSP table
layouts a given statement uses, so the dispatcher only needs to
distinguish BPNG vs. BSP at this level.
"""

import pdfplumber
from typing import Callable, List
import pandas as pd

from parser.bpng_parser import BPNGParser
from parser.bsp_parser import BSPParser


class PDFParserDispatcher:
    """Dispatches PDF parsing to the correct parser based on content."""

    def __init__(self):
        """Initialize parsers - no Tabula JAR needed!"""
        self.bpng_parser = BPNGParser()
        self.bsp_parser = BSPParser()

    def parse_pdfs(
        self,
        pdf_paths: List[str],
        log_callback: Callable[[str], None] = None
    ) -> pd.DataFrame:
        """
        Parse multiple PDFs, selecting BPNG or BSP parser per file.

        Args:
            pdf_paths: List of PDF file paths
            log_callback: Optional function(str) for live log updates

        Returns:
            pandas.DataFrame containing all parsed transactions
        """
        all_frames = []

        for pdf_path in pdf_paths:
            parser_type = self._detect_pdf_type(pdf_path)
            if log_callback:
                log_callback(f"📄 Detected {parser_type} format for {pdf_path}")

            if parser_type == "BPNG":
                def page_cb(page_number, total_pages):
                    if log_callback:
                        log_callback(f"  Processing page {page_number}/{total_pages}")

                df = self.bpng_parser.parse_pdf(pdf_path, progress_callback=page_cb)
                all_frames.append(df)

            elif parser_type == "BSP":
                df = self.bsp_parser.parse_pdf(pdf_path, progress_callback=log_callback)
                all_frames.append(df)

            else:
                if log_callback:
                    log_callback(f"⚠️  WARNING: Could not detect parser for {pdf_path}, skipping")

        if all_frames:
            combined = pd.concat(all_frames, ignore_index=True)
            return combined
        else:
            return pd.DataFrame()  # empty DataFrame

    # ===================== Internal helpers =====================

    def _detect_pdf_type(self, pdf_path: str) -> str:
        """
        Detect if the PDF is BPNG or BSP based on text heuristics.
        Returns: "BPNG", "BSP", or "UNKNOWN"

        Checks the first few pages (not just page 1), since a BSP
        table header doesn't always appear on the cover page.
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_to_check = pdf.pages[:3]
                text = "\n".join((p.extract_text() or "") for p in pages_to_check)
        except Exception:
            return "UNKNOWN"

        text_upper = text.upper()

        if "BANK OF PAPUA NEW GUINEA" in text_upper:
            return "BPNG"

        if "BSP" in text_upper or "BANK OF SOUTH PACIFIC" in text_upper:
            return "BSP"

        return "UNKNOWN"