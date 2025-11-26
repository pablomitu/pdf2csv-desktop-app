"""
PDF parsing and CSV/Excel export utilities for the PDF-to-CSV converter app.

This module extracts banking transaction tables from PDF statements,
cleans monetary values, restructures transaction descriptions, and
saves the combined output to CSV or Excel format.
"""

import os
import re
from datetime import datetime
from typing import List, Tuple

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
    Convert a date to DD/MM/YYYY if it matches known formats.
    Otherwise return the original string.
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

def process_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Extract transaction data from a single PDF file.

    Returns a DataFrame with columns:
    Date, Transaction Details, Debit, Credit, Balance, Line Count, Page Number
    """
    records = []
    headers_found = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = text.split("\n")
            line_count = len(lines)

            for line in lines:
                line = line.strip()

                # Skip metadata or boilerplate lines
                if is_ignored_line(line):
                    continue

                # Detect header row
                if not headers_found and is_header_line(line):
                    headers_found = True
                    continue

                # Handle continuation of long transaction descriptions
                if is_date_on_own_line(line):
                    if records:
                        records[-1][1] += " " + line
                    continue

                # Full transaction line containing date + details + numbers
                if (match := re.match(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(.*)$", line)):
                    record = parse_transaction_line(
                        match, line_count, page_number, records
                    )
                    if record:
                        records.append(record)
                    continue

                # Monetary detail lines that follow previous transaction
                if is_monetary_line(line):
                    merge_monetary_line(records, line)
                    continue

                # Otherwise, append to previous transaction description
                if records:
                    records[-1][1] += " " + line

    return pd.DataFrame(
        records,
        columns=[
            "Date", "Transaction Details",
            "Debit", "Credit", "Balance",
            "Line Count", "Page Number"
        ]
    )


def is_ignored_line(line: str) -> bool:
    """Return True if a line should be ignored."""
    return (
        "BANK OF PAPUA NEW GUINEA" in line
        or "Bank Statement for Account" in line
        or "END OF REPORT" in line
        or re.search(r"Page\s*\d+\s*of\s*\d+", line, re.IGNORECASE)
    )


def is_header_line(line: str) -> bool:
    """Check if a line represents a transaction header row."""
    keywords = ["DATE", "TRANSACTION DETAILS", "DEBIT", "CREDIT", "BALANCE"]
    return all(word in line for word in keywords)


def is_date_on_own_line(line: str) -> bool:
    """Determine if a line containing only a date should be merged."""
    return bool(re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", line))


def is_monetary_line(line: str) -> bool:
    """Check if a line contains only monetary values."""
    return bool(re.match(r"^[\d,\.]+\s*$", line))


def parse_transaction_line(
    match: re.Match, line_count: int, page_number: int, records: List[list]
) -> List:
    """Parse a line containing a full transaction entry."""
    date_str, rest = match.groups()
    date_formatted = format_date(date_str.strip())
    rest = rest.strip()

    # Opening balance
    if "OPENING BALANCE" in rest:
        balance = find_monetary_values(rest)
        closing_balance = balance[-1] if balance else "0.00"
        return [
            date_formatted, "OPENING BALANCE",
            "0.00", "0.00", closing_balance,
            line_count, page_number
        ]

    money_positions = list(re.finditer(MONEY_PATTERN, rest))
    if not money_positions:
        if records:
            records[-1][1] += " " + rest
        return None

    debit, credit, balance, detail = extract_money_fields(rest, money_positions)
    return [
        date_formatted, detail.strip(),
        debit, credit, balance,
        line_count, page_number
    ]


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

    # Only balance present
    balance = matches[0].group()
    detail = rest.split(balance, 1)[0].strip()
    return "0.00", "0.00", balance, detail


def reconstruct_detail(rest: str, spans: List[Tuple[int, int]]) -> str:
    """Remove monetary value segments from the rest of the text to keep only description."""
    detail = ""
    last_pos = 0

    for match in spans:
        start, end = match.start(), match.end()
        detail += rest[last_pos:start]
        last_pos = end

    return detail + rest[last_pos:]


def merge_monetary_line(records: List[list], line: str) -> None:
    """Merge a monetary-only line into the last transaction record."""
    if not records:
        return

    amounts = find_monetary_values(line)
    if not amounts:
        records[-1][1] += " " + line
        return

    last = records[-1]

    # Two numbers = credit, balance
    if last[2] == "0.00" and last[3] == "0.00" and len(amounts) == 2:
        last[3], last[4] = amounts
        return

    # Three numbers = debit, credit, balance
    if len(amounts) == 3:
        last[2], last[3], last[4] = amounts
        return

    # Fallback: treat as description continuation
    last[1] += " " + line


# -------------------------------------------------------------------------
# Cleanup Functions
# -------------------------------------------------------------------------

def clean_transaction_details(text: str) -> str:
    """
    Remove stray header-like words from transaction descriptions.
    """
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
    """
    Correct misparsed monetary columns for cases where balances and credits
    collapse into one field.
    """
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

def convert_pdfs_and_write(pdf_paths: List[str], out_path: str) -> Tuple[bool, str]:
    """
    Convert multiple PDFs to a combined DataFrame and write the results
    to either Excel or CSV.

    Returns:
        (success: bool, message: str)
    """
    parsed_frames = []

    for path in pdf_paths:
        df = process_pdf(path)
        df = clean_monetary_values(df)
        df["Transaction Details"] = df["Transaction Details"].apply(clean_transaction_details)
        parsed_frames.append(df)

    if not parsed_frames:
        return False, "No PDF data extracted."

    combined = pd.concat(parsed_frames, ignore_index=True)
    combined = combined.drop(columns=["Line Count", "Page Number"])

    ext = os.path.splitext(out_path)[1].lower()

    if ext in (".xlsx", ".xls"):
        with pd.ExcelWriter(out_path) as writer:
            combined.to_excel(writer, sheet_name="AllData", index=False)
    else:
        combined.to_csv(out_path, index=False)

    return True, f"Saved to {out_path}"
