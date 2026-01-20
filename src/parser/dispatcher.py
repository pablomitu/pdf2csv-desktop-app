# parser/dispatcher.py
"""
Unified PDF Parser Dispatcher

Automatically selects the correct parser (BPNG or BSP) based on PDF content.
Provides a single interface for the GUI or CLI to parse any supported PDF.
"""

import pdfplumber
from typing import Callable, List
import pandas as pd

from parser.bpng_parser import BPNGParser
from parser.bsp_parser import BSPParser

class PDFParserDispatcher:
    """Dispatches PDF parsing to the correct parser based on content."""

    def __init__(self, tabula_jar_path: str):
        self.bpng_parser = BPNGParser()
        self.bsp_parser = BSPParser(tabula_jar_path)

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
                log_callback(f"Detected {parser_type} parser for {pdf_path}")

            if parser_type == "BPNG":
                def page_cb(page_number, total_pages):
                    if log_callback:
                        log_callback(f"Processing page {page_number}/{total_pages} of {pdf_path}")

                df = self.bpng_parser.parse_pdf(pdf_path, progress_callback=page_cb)
                all_frames.append(df)

            elif parser_type == "BSP":
                df = self.bsp_parser.parse_pdf(pdf_path, progress_callback=log_callback)
                all_frames.append(df)
            else:
                if log_callback:
                    log_callback(f"WARNING: Could not detect parser for {pdf_path}, skipping")

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
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                first_page_text = pdf.pages[0].extract_text() or ""
        except Exception:
            return "UNKNOWN"

        first_page_text_upper = first_page_text.upper()

        if "BANK OF PAPUA NEW GUINEA" in first_page_text_upper:
            return "BPNG"
        elif "BSP" in first_page_text_upper or "BANK OF SOUTH PACIFIC" in first_page_text_upper:
            return "BSP"
        else:
            return "UNKNOWN"