"""
pdf_to_csv.py

Unified PDF -> CSV parser that handles BOTH known BSP bank statement
formats in a single script. It extracts text from the PDF, auto-detects
which format the statement is in (by looking for either format's
column-header line), then runs the matching clean + convert pipeline.

FORMAT 1 — 7 columns
    Header:  "     Date        Date      Sr. No.  Narrative   Debit   Credit   Balance "
    Ends at: a line like "Account Transaction List ... Page : N"
    Output columns / types:
        Posting Date     -> Date    (DD/MM/YYYY)
        Effective Date   -> Date    (DD/MM/YYYY)
        Cheque Sr. No.   -> Integer
        Narrative        -> Text
        Debit            -> Decimal
        Credit           -> Decimal
        Balance          -> Decimal

FORMAT 2 — 6 columns
    Header:  "   DATE   VALUE DATE   DESCRIPTION   DEBIT   CREDIT   BALANCE "
    Ends at: a line starting with "Totals"
    (page-break noise like "about:blank", page numbers, timestamps,
    and "----"/"====" divider lines are skipped WITHOUT ending the
    table, since they appear mid-table at every page break)
    Output columns / types:
        DATE          -> Date (DD-MMM-YYYY)
        VALUE DATE    -> Date (DD-MMM-YYYY)
        DESCRIPTION   -> Text
        DEBIT         -> Text (NVARCHAR — trailing "-" preserved)
        CREDIT        -> Text (same reason as DEBIT)
        BALANCE       -> Text (same reason as DEBIT)

Usage:
    python pdf_to_csv.py input.pdf [output.csv]
    python pdf_to_csv.py input.pdf output.csv --keep-intermediate
    python pdf_to_csv.py input.pdf output.csv --format 1   # force a format
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer

# =======================================================================
# Stage 1: EXTRACT — pull text out of the PDF, page by page (shared)
# =======================================================================

def extract_raw_text(pdf_path: str) -> str:
    """
    Extract text from every page of the PDF and join it into a single
    string, with "--- Page N ---" markers between pages.
    """
    chunks = []

    for page_num, page_layout in enumerate(extract_pages(pdf_path), start=1):
        page_text_parts = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                page_text_parts.append(element.get_text())

        page_text = "".join(page_text_parts).strip("\n")
        chunks.append(f"--- Page {page_num} ---\n{page_text}")

    return "\n".join(chunks)


# =======================================================================
# FORMAT DETECTION
# =======================================================================

FORMAT1_START_RE = re.compile(
    r"Date\s+Date\s+Sr\.?\s*No\.?\s+Narrative\s+Debit\s+Credit\s+Balance",
    re.IGNORECASE,
)

FORMAT2_START_RE = re.compile(
    r"DATE\s+VALUE\s+DATE\s+DESCRIPTION\s+DEBIT\s+CREDIT\s+BALANCE",
    re.IGNORECASE,
)


def detect_format(raw_text: str):
    """
    Scan the extracted text line by line and return 1 or 2 depending on
    which format's column-header line is found first. Returns None if
    neither is found.
    """
    for line in raw_text.splitlines():
        if FORMAT1_START_RE.search(line):
            return 1
        if FORMAT2_START_RE.search(line):
            return 2
    return None


# =======================================================================
# FORMAT 1 — clean + convert
# =======================================================================

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


def f1_clean_lines(raw_text: str):
    kept_lines = []
    inside_table = False
    table_count = 0

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\n")

        if not inside_table:
            if FORMAT1_START_RE.search(line):
                inside_table = True
                table_count += 1
            continue

        if F1_END_MARKER_RE.search(line):
            inside_table = False
            continue

        if F1_PAGE_BREAK_RE.match(line):
            continue

        if not line.strip():
            continue

        kept_lines.append(line)

    return kept_lines, table_count


def f1_normalize_date(raw: str) -> str:
    dt = datetime.strptime(raw, "%d/%m/%Y")
    return dt.strftime("%d/%m/%Y")


def f1_normalize_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def f1_collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def f1_extract_cheque_no(text: str):
    tokens = text.split(None, 1)
    has_trailing_text = len(tokens) > 1 and tokens[1].strip()

    if tokens and tokens[0].isdigit() and len(tokens[0]) <= 4 and has_trailing_text:
        cheque_no = int(tokens[0])
        narrative = tokens[1].strip()
        return cheque_no, f1_collapse_spaces(narrative)

    return "", f1_collapse_spaces(text)


def f1_parse_line(line: str):
    dates = list(F1_DATE_RE.finditer(line[:45]))
    if not dates:
        return None

    posting_date = f1_normalize_date(dates[0].group())
    effective_date = f1_normalize_date(dates[1].group()) if len(dates) > 1 else ""

    remainder = line[dates[-1].end():]
    amounts = list(F1_AMOUNT_RE.finditer(remainder))

    if not amounts:
        narrative_text = remainder.strip()
        cheque_no, narrative = f1_extract_cheque_no(narrative_text)
        return {
            "Posting Date": posting_date,
            "Effective Date": effective_date,
            "Cheque Sr. No.": cheque_no,
            "Narrative": narrative,
            "Debit": "",
            "Credit": "",
            "Balance": "",
        }

    balance = f1_normalize_amount(amounts[-1].group())
    debit = ""
    credit = ""

    if len(amounts) >= 2:
        amt_match = amounts[-2]
        amt_value = f1_normalize_amount(amt_match.group())
        absolute_pos = dates[-1].end() + amt_match.start()
        if absolute_pos < F1_COLUMN_SPLIT:
            debit = amt_value
        else:
            credit = amt_value
        narrative_text = remainder[:amt_match.start()].strip()
    else:
        narrative_text = remainder[:amounts[0].start()].strip()

    cheque_no, narrative = f1_extract_cheque_no(narrative_text)

    return {
        "Posting Date": posting_date,
        "Effective Date": effective_date,
        "Cheque Sr. No.": cheque_no,
        "Narrative": narrative,
        "Debit": debit,
        "Credit": credit,
        "Balance": balance,
    }


def f1_build_rows(lines):
    rows = []
    for line in lines:
        if not line.strip():
            continue

        row = f1_parse_line(line)

        if row is None:
            if rows:
                extra = f1_collapse_spaces(line)
                if extra:
                    rows[-1]["Narrative"] = f1_collapse_spaces(
                        f"{rows[-1]['Narrative']} {extra}"
                    )
            continue

        rows.append(row)

    return rows


# =======================================================================
# FORMAT 2 — clean + convert
# =======================================================================

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


def f2_is_page_break_junk(line: str) -> bool:
    return bool(
        F2_ABOUT_BLANK_RE.match(line)
        or F2_PAGE_BREAK_RE.match(line)
        or F2_PAGE_NUMBER_RE.match(line)
        or F2_TIMESTAMP_RE.match(line)
        or F2_EQUALS_SEPARATOR_RE.match(line)
        or F2_DASH_SEPARATOR_RE.match(line)
    )


def f2_clean_lines(raw_text: str):
    kept_lines = []
    inside_table = False
    table_count = 0

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\n")

        if not inside_table:
            if FORMAT2_START_RE.search(line):
                inside_table = True
                table_count += 1
            continue

        if F2_END_MARKER_RE.match(line):
            inside_table = False
            continue

        if f2_is_page_break_junk(line):
            continue

        if not line.strip():
            continue

        kept_lines.append(line)

    return kept_lines, table_count


def f2_collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def f2_parse_line(line: str):
    dates = list(F2_DATE_RE.finditer(line[:45]))
    if len(dates) < 2:
        return None

    date_val = dates[0].group()
    value_date = dates[1].group()

    remainder = line[dates[-1].end():]

    r_match = F2_R_FLAG_RE.match(remainder)
    r_flag_end = r_match.end() if r_match else 0

    amounts = list(F2_AMOUNT_RE.finditer(remainder))

    if not amounts:
        description = f2_collapse_spaces(remainder[r_flag_end:])
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
        if absolute_pos < F2_COLUMN_SPLIT:
            debit = amt_value
        else:
            credit = amt_value
        description_text = remainder[r_flag_end:amt_match.start()]
    else:
        description_text = remainder[r_flag_end:amounts[0].start()]

    description = f2_collapse_spaces(description_text)

    return {
        "DATE": date_val,
        "VALUE DATE": value_date,
        "DESCRIPTION": description,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": balance,
    }


def f2_build_rows(lines):
    rows = []
    for raw_line in lines:
        line = raw_line.rstrip("\n") if raw_line.endswith("\n") else raw_line

        if not line.strip():
            continue

        row = f2_parse_line(line)

        if row is None:
            if rows:
                extra = f2_collapse_spaces(line)
                if extra:
                    rows[-1]["DESCRIPTION"] = f2_collapse_spaces(
                        f"{rows[-1]['DESCRIPTION']} {extra}"
                    )
            continue

        rows.append(row)

    return rows


# =======================================================================
# Pipeline entry point
# =======================================================================

def run_pipeline(pdf_path: str, output_csv: str, keep_intermediate: bool = False,
                  forced_format=None):
    print(f"[1/3] Extracting text from: {pdf_path}")
    raw_text = extract_raw_text(pdf_path)

    if keep_intermediate:
        raw_txt_path = str(Path(output_csv).with_name(Path(pdf_path).stem + "_raw.txt"))
        with open(raw_txt_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        print(f"      Raw extracted text saved to: {raw_txt_path}")

    fmt = forced_format or detect_format(raw_text)

    if fmt is None:
        print("Error: could not detect statement format (neither format's "
              "column-header line was found). Use --format 1 or --format 2 "
              "to force it, or check the PDF's extracted text.")
        sys.exit(1)

    print(f"      Detected format: {fmt}")

    print("[2/3] Finding transaction tables and cleaning text")
    if fmt == 1:
        kept_lines, table_count = f1_clean_lines(raw_text)
    else:
        kept_lines, table_count = f2_clean_lines(raw_text)

    print(f"      Tables found: {table_count} | Lines kept: {len(kept_lines)}")

    if keep_intermediate:
        cleaned_txt_path = str(Path(output_csv).with_name(Path(pdf_path).stem + "_cleaned.txt"))
        with open(cleaned_txt_path, "w", encoding="utf-8") as f:
            for line in kept_lines:
                f.write(line + "\n")
        print(f"      Cleaned text saved to: {cleaned_txt_path}")

    print("[3/3] Converting to structured rows")
    if fmt == 1:
        rows = f1_build_rows(kept_lines)
        columns = F1_COLUMNS
    else:
        rows = f2_build_rows(kept_lines)
        columns = F2_COLUMNS

    print(f"      Transaction rows parsed: {len(rows)}")

    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Done. CSV written to: {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Unified PDF -> CSV parser for BSP bank statements (both formats)."
    )
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument(
        "output_csv",
        nargs="?",
        default=None,
        help="Path to the output CSV file (defaults to <pdf_name>.csv)",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Also save the raw extracted text and cleaned text as .txt files",
    )
    parser.add_argument(
        "--format",
        type=int,
        choices=[1, 2],
        default=None,
        help="Force a specific statement format instead of auto-detecting",
    )

    args = parser.parse_args()

    if not Path(args.pdf_path).exists():
        print(f"Error: file not found: {args.pdf_path}")
        sys.exit(1)

    output_csv = args.output_csv or str(Path(args.pdf_path).with_suffix(".csv"))

    run_pipeline(
        args.pdf_path,
        output_csv,
        keep_intermediate=args.keep_intermediate,
        forced_format=args.format,
    )


if __name__ == "__main__":
    main()