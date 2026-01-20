# parser/bpng_parser.py
"""
BPNG PDF Parser for PDF-to-CSV converter app.

Wraps the existing parser_logic functions into a class-based structure
for modular integration with GUI and multi-bank architecture.
"""

import re
from typing import Callable, List
import pandas as pd
import pdfplumber
from decimal import Decimal

# Import your existing helper functions here
# You can copy them directly from parser_logic.py
from .parser_logic import (
    find_monetary_values,
    format_date,
    clean_transaction_details,
    clean_monetary_values,
    parse_transaction_line,
    merge_monetary_line,
    is_ignored_line,
    is_header_line,
    is_date_on_own_line,
    is_monetary_line,
)

class BPNGParser:
    """Parser class for Bank of Papua New Guinea PDFs."""

    def can_parse(self, pdf_text: str) -> bool:
        """
        Determine if this parser can handle the PDF.

        Args:
            pdf_text: text extracted from the PDF (first page recommended)
        Returns:
            True if BPNG PDF, False otherwise
        """
        return "BANK OF PAPUA NEW GUINEA" in pdf_text.upper()

    def parse_pdf(
        self, pdf_path: str, progress_callback: Callable[[int, int], None] = None
    ) -> pd.DataFrame:
        """
        Parse a BPNG PDF and return a DataFrame of transactions.

        Args:
            pdf_path: path to PDF file
            progress_callback: optional function(page_number, total_pages) for progress

        Returns:
            pandas.DataFrame with columns:
            ["Date", "Transaction Details", "Debit", "Credit", "Balance"]
        """
        records: List[list] = []
        headers_found = False

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                lines = text.split("\n")
                line_count = len(lines)

                for line in lines:
                    line = line.strip()

                    if is_ignored_line(line):
                        continue

                    if not headers_found and is_header_line(line):
                        headers_found = True
                        continue

                    if is_date_on_own_line(line):
                        if records:
                            records[-1][1] += " " + line
                        continue

                    match = re.match(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(.*)$", line)
                    if match:
                        record = parse_transaction_line(match, line_count, page_number, records)
                        if record:
                            records.append(record)
                        continue

                    if is_monetary_line(line):
                        merge_monetary_line(records, line)
                        continue

                    if records:
                        records[-1][1] += " " + line

                if progress_callback:
                    progress_callback(page_number, total_pages)

        df = pd.DataFrame(
            records,
            columns=[
                "Date",
                "Transaction Details",
                "Debit",
                "Credit",
                "Balance",
                "Line Count",
                "Page Number",
            ],
        )

        df = clean_monetary_values(df)
        df["Transaction Details"] = df["Transaction Details"].apply(clean_transaction_details)
        
        # Drop the extra columns before returning
        df = df.drop(columns=["Line Count", "Page Number"])

        return df