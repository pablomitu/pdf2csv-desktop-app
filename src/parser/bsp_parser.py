# parser/bsp_parser.py
"""
Unified parser for BSP (Bank of South Pacific) statements. Auto-detects
which of the two known BSP table layouts a given PDF uses (by looking
for either format's column-header line) and runs the matching clean +
convert pipeline. This replaces the previous balance-delta-reconciliation
approach for the DATE/VALUE DATE layout, and the separate
BSPNarrativeParser for the Posting Date/Narrative layout — both are now
handled by this single class, mirroring the standalone pdf_to_csv.py
reference script this was lifted from.

FORMAT 1 — 7 columns (Posting Date / Effective Date / Cheque Sr. No. /
           Narrative / Debit / Credit / Balance)
    Header:  "     Date        Date      Sr. No.  Narrative   Debit   Credit   Balance "
    Ends at: a line like "Account Transaction List ... Page : N"
    Output:
        Posting Date / Effective Date -> Date (DD/MM/YYYY)
        Cheque Sr. No.                -> Integer (or "" if none)
        Narrative                     -> Text
        Debit / Credit / Balance      -> Decimal (float)

FORMAT 2 — 6 columns (DATE / VALUE DATE / DESCRIPTION / DEBIT / CREDIT / BALANCE)
    Header:  "   DATE   VALUE DATE   DESCRIPTION   DEBIT   CREDIT   BALANCE "
    Ends at: a line starting with "Totals"
    Output:
        DATE / VALUE DATE           -> Text, left as extracted (DD-MMM-YYYY)
        DESCRIPTION                 -> Text
        DEBIT / CREDIT / BALANCE    -> Text (NVARCHAR-style; trailing "-"
                                       for negatives is preserved, not
                                       converted to a signed float)

Uses pdfminer.six for text extraction (rather than pdfplumber, used by
the other parsers), since both formats' debit/credit column splits rely
on character x-position data calibrated against pdfminer's layout output.
"""

import re
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer

from .base_parser import BaseParser


class BSPParser(BaseParser):
    """Unified parser for both known BSP statement layouts."""

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------
    FORMAT1_START_RE = re.compile(
        r"Date\s+Date\s+Sr\.?\s*No\.?\s+Narrative\s+Debit\s+Credit\s+Balance",
        re.IGNORECASE,
    )
    FORMAT2_START_RE = re.compile(
        r"DATE\s+VALUE\s+DATE\s+DESCRIPTION\s+DEBIT\s+CREDIT\s+BALANCE",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # Format 1 patterns / columns
    # ------------------------------------------------------------------
    F1_END_MARKER_RE = re.compile(
        r"Account\s+Transactions?\s+List.*Page\s*:\s*\d+",
        re.IGNORECASE,
    )
    F1_PAGE_BREAK_RE = re.compile(r"^\s*-+\s*Page\s+\d+\s*-+\s*$", re.IGNORECASE)

    F1_COLUMNS = [
        "Posting Date",
        "Effective Date",
        "Cheque Sr. No.",
        "Narrative",
        "Debit",
        "Credit",
        "Balance",
    ]
    F1_DATE_RE = re.compile(r"\d{1,2}/\d{2}/\d{4}")
    F1_AMOUNT_RE = re.compile(r"\d[\d,]*\.\d{2}|\.\d{2}")
    F1_COLUMN_SPLIT = 95  # Debit/Credit boundary, calibrated from sample data

    # ------------------------------------------------------------------
    # Format 2 patterns / columns
    # ------------------------------------------------------------------
    F2_END_MARKER_RE = re.compile(r"^\s*Totals\b", re.IGNORECASE)
    F2_ABOUT_BLANK_RE = re.compile(r"^\s*about:blank\s*$", re.IGNORECASE)
    F2_PAGE_BREAK_RE = re.compile(r"^\s*-+\s*Page\s+\d+\s*-+\s*$", re.IGNORECASE)
    F2_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
    F2_TIMESTAMP_RE = re.compile(
        r"^\s*\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(AM|PM)\s*$",
        re.IGNORECASE,
    )
    F2_EQUALS_SEPARATOR_RE = re.compile(r"^[\s=]+$")
    F2_DASH_SEPARATOR_RE = re.compile(r"^[\s\-]+$")

    F2_COLUMNS = ["DATE", "VALUE DATE", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"]
    F2_DATE_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")
    F2_AMOUNT_RE = re.compile(r"\d[\d,]*\.\d{2}-?")
    F2_R_FLAG_RE = re.compile(r"^\s*R\s+")
    F2_COLUMN_SPLIT = 75  # Debit/Credit boundary, calibrated from sample data

    # ------------------------------------------------------------------
    # BaseParser interface
    # ------------------------------------------------------------------
    def can_parse(self, pdf_text: str) -> bool:
        """Return True if either known BSP table header appears."""
        return bool(
            self.FORMAT1_START_RE.search(pdf_text)
            or self.FORMAT2_START_RE.search(pdf_text)
        )

    def parse_pdf(
        self,
        pdf_path: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> pd.DataFrame:
        """
        Parse a BSP PDF, auto-detecting which of the two known layouts
        it uses, and return the corresponding DataFrame.
        """
        if progress_callback:
            progress_callback("Extracting text")
        raw_text = self._extract_raw_text(pdf_path)

        fmt = self._detect_format(raw_text)
        if fmt is None:
            if progress_callback:
                progress_callback(
                    "Could not detect BSP statement format (no known "
                    "table header found)"
                )
            return pd.DataFrame()

        if progress_callback:
            progress_callback(f"Detected BSP Format {fmt}")
            progress_callback("Finding transaction tables")

        if fmt == 1:
            kept_lines, _ = self._f1_clean_lines(raw_text)
            if progress_callback:
                progress_callback("Converting to transaction rows")
            rows = self._f1_build_rows(kept_lines)
            return pd.DataFrame(rows, columns=self.F1_COLUMNS)

        kept_lines, _ = self._f2_clean_lines(raw_text)
        if progress_callback:
            progress_callback("Converting to transaction rows")
        rows = self._f2_build_rows(kept_lines)
        return pd.DataFrame(rows, columns=self.F2_COLUMNS)

    # ------------------------------------------------------------------
    # Stage 1: EXTRACT (shared)
    # ------------------------------------------------------------------
    def _extract_raw_text(self, pdf_path: str) -> str:
        chunks = []
        for page_num, page_layout in enumerate(extract_pages(pdf_path), start=1):
            page_text_parts = [
                element.get_text()
                for element in page_layout
                if isinstance(element, LTTextContainer)
            ]
            page_text = "".join(page_text_parts).strip("\n")
            chunks.append(f"--- Page {page_num} ---\n{page_text}")
        return "\n".join(chunks)

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------
    def _detect_format(self, raw_text: str) -> Optional[int]:
        """
        Scan the extracted text line by line and return 1 or 2 depending
        on which format's column-header line is found first. Returns
        None if neither is found.
        """
        for line in raw_text.splitlines():
            if self.FORMAT1_START_RE.search(line):
                return 1
            if self.FORMAT2_START_RE.search(line):
                return 2
        return None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _collapse_spaces(text: str) -> str:
        """Collapse runs of whitespace into single spaces for a clean field."""
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # FORMAT 1 — clean + convert
    # ==================================================================
    def _f1_clean_lines(self, raw_text: str):
        kept_lines: List[str] = []
        inside_table = False
        table_count = 0

        for raw_line in raw_text.splitlines():
            line = raw_line.rstrip("\n")

            if not inside_table:
                if self.FORMAT1_START_RE.search(line):
                    inside_table = True
                    table_count += 1
                continue

            if self.F1_END_MARKER_RE.search(line):
                inside_table = False
                continue

            if self.F1_PAGE_BREAK_RE.match(line):
                continue

            if not line.strip():
                continue

            kept_lines.append(line)

        return kept_lines, table_count

    @staticmethod
    def _f1_normalize_date(raw: str) -> str:
        """Convert D/MM/YYYY or DD/MM/YYYY to zero-padded DD/MM/YYYY."""
        dt = datetime.strptime(raw, "%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")

    @staticmethod
    def _f1_normalize_amount(raw: str) -> float:
        """Convert '1,690.49' or '.25' into a float."""
        return float(raw.replace(",", ""))

    def _f1_extract_cheque_no(self, text: str):
        """
        If the text starts with a standalone SHORT number (digits only,
        at most 4 digits) followed by real narrative text, treat that
        number as the Cheque Sr. No. and return the remaining text as
        the Narrative.
        """
        tokens = text.split(None, 1)
        has_trailing_text = len(tokens) > 1 and tokens[1].strip()

        if tokens and tokens[0].isdigit() and len(tokens[0]) <= 4 and has_trailing_text:
            cheque_no = int(tokens[0])
            narrative = tokens[1].strip()
            return cheque_no, self._collapse_spaces(narrative)

        return "", self._collapse_spaces(text)

    def _f1_parse_line(self, line: str):
        """
        Parse a single line into a Format-1 row dict, or return None
        if it has no date (a narrative-continuation line).
        """
        dates = list(self.F1_DATE_RE.finditer(line[:45]))
        if not dates:
            return None

        posting_date = self._f1_normalize_date(dates[0].group())
        effective_date = self._f1_normalize_date(dates[1].group()) if len(dates) > 1 else ""

        remainder = line[dates[-1].end():]
        amounts = list(self.F1_AMOUNT_RE.finditer(remainder))

        if not amounts:
            narrative_text = remainder.strip()
            cheque_no, narrative = self._f1_extract_cheque_no(narrative_text)
            return {
                "Posting Date": posting_date,
                "Effective Date": effective_date,
                "Cheque Sr. No.": cheque_no,
                "Narrative": narrative,
                "Debit": "",
                "Credit": "",
                "Balance": "",
            }

        balance = self._f1_normalize_amount(amounts[-1].group())
        debit = ""
        credit = ""

        if len(amounts) >= 2:
            amt_match = amounts[-2]
            amt_value = self._f1_normalize_amount(amt_match.group())
            absolute_pos = dates[-1].end() + amt_match.start()
            if absolute_pos < self.F1_COLUMN_SPLIT:
                debit = amt_value
            else:
                credit = amt_value
            narrative_text = remainder[:amt_match.start()].strip()
        else:
            narrative_text = remainder[:amounts[0].start()].strip()

        cheque_no, narrative = self._f1_extract_cheque_no(narrative_text)

        return {
            "Posting Date": posting_date,
            "Effective Date": effective_date,
            "Cheque Sr. No.": cheque_no,
            "Narrative": narrative,
            "Debit": debit,
            "Credit": credit,
            "Balance": balance,
        }

    def _f1_build_rows(self, lines: List[str]) -> List[dict]:
        rows: List[dict] = []

        for line in lines:
            if not line.strip():
                continue

            row = self._f1_parse_line(line)

            if row is None:
                if rows:
                    extra = self._collapse_spaces(line)
                    if extra:
                        rows[-1]["Narrative"] = self._collapse_spaces(
                            f"{rows[-1]['Narrative']} {extra}"
                        )
                continue

            rows.append(row)

        return rows

    # ==================================================================
    # FORMAT 2 — clean + convert
    # ==================================================================
    def _f2_is_page_break_junk(self, line: str) -> bool:
        return bool(
            self.F2_ABOUT_BLANK_RE.match(line)
            or self.F2_PAGE_BREAK_RE.match(line)
            or self.F2_PAGE_NUMBER_RE.match(line)
            or self.F2_TIMESTAMP_RE.match(line)
            or self.F2_EQUALS_SEPARATOR_RE.match(line)
            or self.F2_DASH_SEPARATOR_RE.match(line)
        )

    def _f2_clean_lines(self, raw_text: str):
        """
        Page-break noise (about:blank, page numbers, timestamps, and
        "----"/"====" divider lines) is skipped WITHOUT ending the
        table, since it appears mid-table at every page break.
        """
        kept_lines: List[str] = []
        inside_table = False
        table_count = 0

        for raw_line in raw_text.splitlines():
            line = raw_line.rstrip("\n")

            if not inside_table:
                if self.FORMAT2_START_RE.search(line):
                    inside_table = True
                    table_count += 1
                continue

            if self.F2_END_MARKER_RE.match(line):
                inside_table = False
                continue

            if self._f2_is_page_break_junk(line):
                continue

            if not line.strip():
                continue

            kept_lines.append(line)

        return kept_lines, table_count

    def _f2_parse_line(self, line: str):
        """
        Parse a single line into a Format-2 row dict, or return None
        if it doesn't have both a DATE and a VALUE DATE (a
        description-continuation line).
        """
        dates = list(self.F2_DATE_RE.finditer(line[:45]))
        if len(dates) < 2:
            return None

        date_val = dates[0].group()
        value_date = dates[1].group()

        remainder = line[dates[-1].end():]

        r_match = self.F2_R_FLAG_RE.match(remainder)
        r_flag_end = r_match.end() if r_match else 0

        amounts = list(self.F2_AMOUNT_RE.finditer(remainder))

        if not amounts:
            description = self._collapse_spaces(remainder[r_flag_end:])
            return {
                "DATE": date_val,
                "VALUE DATE": value_date,
                "DESCRIPTION": description,
                "DEBIT": "",
                "CREDIT": "",
                "BALANCE": "",
            }

        balance = amounts[-1].group()
        debit = ""
        credit = ""

        if len(amounts) >= 2:
            amt_match = amounts[-2]
            amt_value = amt_match.group()
            absolute_pos = dates[-1].end() + amt_match.start()
            if absolute_pos < self.F2_COLUMN_SPLIT:
                debit = amt_value
            else:
                credit = amt_value
            description_text = remainder[r_flag_end:amt_match.start()]
        else:
            description_text = remainder[r_flag_end:amounts[0].start()]

        description = self._collapse_spaces(description_text)

        return {
            "DATE": date_val,
            "VALUE DATE": value_date,
            "DESCRIPTION": description,
            "DEBIT": debit,
            "CREDIT": credit,
            "BALANCE": balance,
        }

    def _f2_build_rows(self, lines: List[str]) -> List[dict]:
        rows: List[dict] = []

        for raw_line in lines:
            line = raw_line.rstrip("\n") if raw_line.endswith("\n") else raw_line

            if not line.strip():
                continue

            row = self._f2_parse_line(line)

            if row is None:
                if rows:
                    extra = self._collapse_spaces(line)
                    if extra:
                        rows[-1]["DESCRIPTION"] = self._collapse_spaces(
                            f"{rows[-1]['DESCRIPTION']} {extra}"
                        )
                continue

            rows.append(row)

        return rows