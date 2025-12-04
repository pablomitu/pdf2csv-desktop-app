"""
PDF parsing and CSV/Excel export utilities for the PDF-to-CSV converter app.

Includes live logging via an optional `log_callback`.
"""

import os
import re
from datetime import datetime
from typing import List, Tuple, Callable

import pandas as pd
import pdfplumber

# -------------------------------------------------------------------------
# Constants & Patterns
# -------------------------------------------------------------------------

MONEY_PATTERN = r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b"
HEADER_KEYWORDS = ["DATE", "TRANSACTION", "DETAILS", "DEBIT", "CREDIT", "BALANCE"]


# -------------------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------------------

def find_monetary_values(text: str) -> List[str]:
    """Return all monetary values found in the text."""
    return re.findall(MONEY_PATTERN, text)


def format_date(date_str: str) -> str:
    """
    Convert a date string to DD/MM/YYYY if it matches known formats.

    Otherwise, return the original string.
    """
    date_formats = ("%d/%m/%y", "%d-%m-%Y")

    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return date_str


# -------------------------------------------------------------------------
# Core PDF Parsing Logic
# -------------------------------------------------------------------------

def process_pdf(
    pdf_path: str,
    progress_callback: Callable[[int, int], None] = None
) -> pd.DataFrame:
    """
    Extract transaction data from a single PDF file.

    Args:
        pdf_path: Path to the PDF file.
        progress_callback: Optional function(page_number, total_pages) to
                           report progress per page.

    Returns:
        DataFrame containing the extracted transaction data.
    """
    records = []
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

    return pd.DataFrame(
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


def is_ignored_line(line: str) -> bool:
    """Return True if a line should be ignored (metadata, boilerplate)."""
    return (
        "BANK OF PAPUA NEW GUINEA" in line
        or "Bank Statement for Account" in line
        or "END OF REPORT" in line
        or re.search(r"Page\s*\d+\s*of\s*\d+", line, re.IGNORECASE)
    )


def is_header_line(line: str) -> bool:
    """Return True if a line represents a transaction header row."""
    keywords = ["DATE", "TRANSACTION DETAILS", "DEBIT", "CREDIT", "BALANCE"]
    return all(word in line for word in keywords)


def is_date_on_own_line(line: str) -> bool:
    """Return True if the line contains only a date and should be merged."""
    return bool(re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", line))


def is_monetary_line(line: str) -> bool:
    """Return True if the line contains only monetary values."""
    return bool(re.match(r"^[\d,\.]+\s*$", line))


def parse_transaction_line(
    match: re.Match, line_count: int, page_number: int, records: List[list]
) -> List:
    """Parse a line containing a full transaction entry."""
    date_str, rest = match.groups()
    date_formatted = format_date(date_str.strip())
    rest = rest.strip()

    if "OPENING BALANCE" in rest:
        balance = find_monetary_values(rest)
        closing_balance = balance[-1] if balance else "0.00"
        return [
            date_formatted,
            "OPENING BALANCE",
            "0.00",
            "0.00",
            closing_balance,
            line_count,
            page_number,
        ]

    money_positions = list(re.finditer(MONEY_PATTERN, rest))
    if not money_positions:
        if records:
            records[-1][1] += " " + rest
        return None

    debit, credit, balance, detail = extract_money_fields(rest, money_positions)
    return [date_formatted, detail.strip(), debit, credit, balance, line_count, page_number]


def extract_money_fields(rest: str, matches: List[re.Match]) -> Tuple[str, str, str, str]:
    """Extract debit, credit, and balance amounts from a text line."""
    if len(matches) >= 3:
        debit = matches[-3].group()
        credit = matches[-2].group()
        balance = matches[-1].group()
        detail = reconstruct_detail(rest, matches[-3:])
        return debit, credit, balance, detail

    if len(matches) == 2:
        credit = matches[0].group()
        balance = matches[1].group()
        detail = rest.split(credit, 1)[0].strip()
        return "0.00", credit, balance, detail

    balance = matches[0].group()
    detail = rest.split(balance, 1)[0].strip()
    return "0.00", "0.00", balance, detail


def reconstruct_detail(rest: str, spans: List[re.Match]) -> str:
    """Remove monetary segments from the text to leave only the description."""
    detail = ""
    last_pos = 0

    for match in spans:
        start, end = match.start(), match.end()
        detail += rest[last_pos:start]
        last_pos = end

    return detail + rest[last_pos:]


def merge_monetary_line(records: List[list], line: str) -> None:
    """
    Merge a monetary-only line into the last transaction record.
    Handles two or three number lines (credit/balance or debit/credit/balance).
    """
    if not records:
        return

    amounts = find_monetary_values(line)
    if not amounts:
        records[-1][1] += " " + line
        return

    last = records[-1]

    if last[2] == "0.00" and last[3] == "0.00" and len(amounts) == 2:
        last[3], last[4] = amounts
        return

    if len(amounts) == 3:
        last[2], last[3], last[4] = amounts
        return

    last[1] += " " + line


# -------------------------------------------------------------------------
# Cleanup Functions
# -------------------------------------------------------------------------

def clean_transaction_details(text: str) -> str:
    """Remove stray header-like words from transaction descriptions."""
    words = text.split()
    indices = []
    pos = 0

    for keyword in HEADER_KEYWORDS:
        for i in range(pos, len(words)):
            if words[i].upper() == keyword:
                indices.append(i)
                pos = i + 1
                break

    if len(indices) != len(HEADER_KEYWORDS):
        return text.strip()

    first, last = indices[0], indices[-1]
    cleaned = " ".join(words[:first] + words[last + 1:])
    return cleaned.strip()


def clean_monetary_values(df: pd.DataFrame) -> pd.DataFrame:
    """Correct misparsed monetary columns where balances and credits collapse."""
    for index, row in df.iterrows():
        values = re.findall(MONEY_PATTERN, row["Balance"])
        if len(values) == 2:
            df.at[index, "Credit"] = values[0]
            df.at[index, "Balance"] = values[1]

            if values[0] == "0.00" and row["Credit"] not in ("0.00", ""):
                df.at[index, "Debit"] = row["Credit"]
                df.at[index, "Credit"] = "0.00"

    return df


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

def convert_pdfs_and_write(
    pdf_paths: List[str],
    out_path: str,
    log_callback: Callable[[str], None] = None,
) -> Tuple[bool, str]:
    """
    Convert multiple PDFs to a combined DataFrame and write the results
    to Excel or CSV.

    Args:
        pdf_paths: List of PDF file paths.
        out_path: Output file path (.xlsx, .xls, or .csv).
        log_callback: Optional function(str) to receive live log messages.

    Returns:
        Tuple of (success: bool, message: str)
    """
    parsed_frames = []

    for path in pdf_paths:
        if log_callback:
            log_callback(f"Extracting from {os.path.basename(path)}")

        def page_cb(page_number: int, total_pages: int):
            if log_callback:
                log_callback(f"Extracting page {page_number} of {total_pages}")

        df = process_pdf(path, progress_callback=page_cb)
        df = clean_monetary_values(df)
        df["Transaction Details"] = df["Transaction Details"].apply(
            clean_transaction_details
        )
        parsed_frames.append(df)

    if not parsed_frames:
        return False, "No PDF data extracted."

    combined = pd.concat(parsed_frames, ignore_index=True)
    combined = combined.drop(columns=["Line Count", "Page Number"])

    if log_callback:
        log_callback(
            f"Converting to {'Excel' if out_path.endswith(('.xlsx','.xls')) else 'CSV'}"
        )

    try:
        ext = os.path.splitext(out_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            combined.to_excel(out_path, index=False)
        else:
            combined.to_csv(out_path, index=False)
    except Exception as e:
        return False, f"Failed to write output file: {e}"

    return True, f"Saved to {out_path}"
