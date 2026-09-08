"""
Parse a cleaned bank-statement .txt file (one transaction per line, in the
fixed-width layout exported from the source PDF) into a CSV with these
7 columns:

    Posting Date     -> Date  (DD/MM/YYYY)
    Effective Date   -> Date  (DD/MM/YYYY)
    Cheque Sr. No.   -> Integer
    Narrative        -> Text
    Debit            -> Decimal
    Credit           -> Decimal
    Balance          -> Decimal

How a line is interpreted
--------------------------
1. Every data line starts with a Posting Date (D/MM/YYYY or DD/MM/YYYY).
   Some lines have a second date right after it — that's the Effective
   Date. Both are normalized to DD/MM/YYYY on output.

2. Immediately after the date(s), if the very next token is a standalone
   number (digits only, no letters), it's treated as the Cheque Sr. No.
   Everything after that is the Narrative.

3. Amounts (numbers with a decimal point, e.g. "1,690.49" or ".25") are
   found anywhere in the rest of the line:
     - The LAST amount on the line is always the Balance.
     - If there's one amount before the Balance, it's classified as
       Debit or Credit based on its horizontal position in the line
       (this file's Debit column sits to the left of the Credit
       column). The threshold below (COLUMN_SPLIT) was calibrated
       against the sample rows you shared — if amounts start landing
       in the wrong column for a different file, adjust that value.

4. A line with no date and no amounts (just leftover text) is treated
   as a continuation of the PREVIOUS row's Narrative — this handles
   cases where a narrative wraps onto its own line, e.g.:
        23/02/2018   1 Pakira Rodney            500.00   7,173.13
                     Mb Trf From Pakira Rodney

5. Blank / whitespace-only lines are skipped.

Usage:
    python parse_statement_to_csv.py input.txt [output.csv]
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = [
    "Posting Date",
    "Effective Date",
    "Cheque Sr. No.",
    "Narrative",
    "Debit",
    "Credit",
    "Balance",
]

DATE_RE = re.compile(r"\d{1,2}/\d{2}/\d{4}")
AMOUNT_RE = re.compile(r"\d[\d,]*\.\d{2}|\.\d{2}")

# Horizontal character position that separates the Debit column from the
# Credit column in this file's layout. Amounts starting before this
# position are Debit; at or after it (and before the Balance) are Credit.
# Calibrated from sample data — adjust if your file's columns differ.
COLUMN_SPLIT = 95


def normalize_date(raw: str) -> str:
    """Convert D/MM/YYYY or DD/MM/YYYY to zero-padded DD/MM/YYYY."""
    dt = datetime.strptime(raw, "%d/%m/%Y")
    return dt.strftime("%d/%m/%Y")


def normalize_amount(raw: str) -> float:
    """Convert '1,690.49' or '.25' into a float."""
    return float(raw.replace(",", ""))


def parse_line(line: str):
    """
    Parse a single data line into a row dict, or return None if the
    line is blank or should be treated as a narrative continuation
    (caller handles continuation logic).
    """
    dates = list(DATE_RE.finditer(line[:45]))
    if not dates:
        return None  # blank line or continuation line

    posting_date = normalize_date(dates[0].group())
    effective_date = normalize_date(dates[1].group()) if len(dates) > 1 else ""

    remainder = line[dates[-1].end():]
    amounts = list(AMOUNT_RE.finditer(remainder))

    if not amounts:
        # No amounts at all — unusual, but keep whatever text there is
        narrative_text = remainder.strip()
        cheque_no, narrative = extract_cheque_no(narrative_text)
        return {
            "Posting Date": posting_date,
            "Effective Date": effective_date,
            "Cheque Sr. No.": cheque_no,
            "Narrative": narrative,
            "Debit": "",
            "Credit": "",
            "Balance": "",
        }

    balance = normalize_amount(amounts[-1].group())
    debit = ""
    credit = ""

    if len(amounts) >= 2:
        amt_match = amounts[-2]
        amt_value = normalize_amount(amt_match.group())
        # Classify using the amount's position in the WHOLE original line
        # (not just within `remainder`), since the Debit/Credit columns
        # sit at fixed absolute positions regardless of whether an
        # Effective Date pushed the remainder's starting point around.
        absolute_pos = dates[-1].end() + amt_match.start()
        if absolute_pos < COLUMN_SPLIT:
            debit = amt_value
        else:
            credit = amt_value
        narrative_text = remainder[:amt_match.start()].strip()
    else:
        # Only the balance was found; no debit/credit amount
        narrative_text = remainder[:amounts[0].start()].strip()

    cheque_no, narrative = extract_cheque_no(narrative_text)

    return {
        "Posting Date": posting_date,
        "Effective Date": effective_date,
        "Cheque Sr. No.": cheque_no,
        "Narrative": narrative,
        "Debit": debit,
        "Credit": credit,
        "Balance": balance,
    }


def extract_cheque_no(text: str):
    """
    If the text starts with a standalone number (digits only) followed
    by more text, treat that number as the Cheque Sr. No. and return
    the rest as the Narrative. Otherwise there's no cheque number.
    """
    tokens = text.split(None, 1)
    if tokens and tokens[0].isdigit():
        cheque_no = int(tokens[0])
        narrative = tokens[1].strip() if len(tokens) > 1 else ""
        return cheque_no, collapse_spaces(narrative)
    return "", collapse_spaces(text)


def collapse_spaces(text: str) -> str:
    """Collapse runs of whitespace into single spaces for a clean field."""
    return re.sub(r"\s+", " ", text).strip()


def parse_file(lines):
    rows = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if not line.strip():
            continue  # skip blank lines

        row = parse_line(line)

        if row is None:
            # No date found -> continuation of previous narrative
            if rows:
                extra = collapse_spaces(line)
                if extra:
                    rows[-1]["Narrative"] = collapse_spaces(
                        f"{rows[-1]['Narrative']} {extra}"
                    )
            continue

        rows.append(row)

    return rows


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_statement_to_csv.py input.txt [output.csv]")
        sys.exit(1)

    input_path = sys.argv[1]

    if not Path(input_path).exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = str(Path(input_path).with_suffix(".csv"))

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Read {len(lines)} line(s) from: {input_path}")
    rows = parse_file(lines)
    print(f"Parsed {len(rows)} transaction row(s).")

    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"CSV written to: {output_path}")


if __name__ == "__main__":
    main()