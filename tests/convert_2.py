"""
convert_2.py

Parses the cleaned .txt file produced by clean_2.py into the final CSV
with these 6 columns:

    DATE          -> Date (DD-MMM-YYYY)
    VALUE DATE    -> Date (DD-MMM-YYYY)
    DESCRIPTION   -> Text
    DEBIT         -> Text (NVARCHAR — kept as raw text, not converted
                     to a number, so a trailing "-" is preserved)
    CREDIT        -> Text (same reason as DEBIT)
    BALANCE       -> Text (same reason as DEBIT)

How a line is interpreted
--------------------------
1. Every real transaction line starts with two dates in DD-MMM-YYYY
   format: DATE, then VALUE DATE.

2. Right after the dates, an "R" may appear on its own (surrounded by
   whitespace, not the start of a longer word like "Reversal"). This
   flag just signals that one of DEBIT/CREDIT/BALANCE on this row has
   a trailing "-" — it is stripped out and not stored in any column.

3. Amounts (numbers with a decimal point, optionally followed by a
   trailing "-", e.g. "0.25" or "0.06-") are found in the rest of the
   line:
     - The LAST amount is always the Balance.
     - If there's one amount before the Balance, it's classified as
       Debit or Credit based on its horizontal position in the line
       (Debit column starts earlier than Credit column).
       COLUMN_SPLIT below controls that boundary — calibrated from
       sample rows; adjust if a different file's columns land
       elsewhere.

4. A line with no date at all (just leftover text) is treated as a
   continuation of the PREVIOUS row's Description, since clean_2.py
   already stripped out everything that isn't either a transaction row
   or a description continuation line.

Usage:
    python convert_2.py cleaned_input.txt [output.csv]
"""

import re
import sys
from pathlib import Path

import pandas as pd

COLUMNS = ["DATE", "VALUE DATE", "DESCRIPTION", "DEBIT", "CREDIT", "BALANCE"]

DATE_RE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}")
AMOUNT_RE = re.compile(r"\d[\d,]*\.\d{2}-?")

# Matches a standalone "R" flag right after the dates — whitespace on
# both sides, so it won't match the start of a longer word like
# "Reversal".
R_FLAG_RE = re.compile(r"^\s*R\s+")

# Horizontal character position separating the Debit column from the
# Credit column in this statement's layout. Amounts starting before
# this position are Debit; at or after it (and before the Balance)
# are Credit. Calibrated from sample data — adjust if a different
# file's columns land elsewhere.
COLUMN_SPLIT = 75


def collapse_spaces(text: str) -> str:
    """Collapse runs of whitespace into single spaces for a clean field."""
    return re.sub(r"\s+", " ", text).strip()


def parse_line(line: str):
    """
    Parse a single line into a row dict, or return None if it has no
    date (meaning it's a description-continuation line, not a new row).
    """
    dates = list(DATE_RE.finditer(line[:45]))
    if len(dates) < 2:
        return None  # continuation line — needs both dates to be a real row

    date_val = dates[0].group()
    value_date = dates[1].group()

    remainder = line[dates[-1].end():]

    # Detect (but don't yet strip) an "R" flag right after the dates.
    r_match = R_FLAG_RE.match(remainder)
    r_flag_end = r_match.end() if r_match else 0

    amounts = list(AMOUNT_RE.finditer(remainder))

    if not amounts:
        description = collapse_spaces(remainder[r_flag_end:])
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
        # Classify using the amount's position in the WHOLE original
        # line, since the Debit/Credit columns sit at fixed absolute
        # positions regardless of whether an "R" flag was present.
        absolute_pos = dates[-1].end() + amt_match.start()
        if absolute_pos < COLUMN_SPLIT:
            debit = amt_value
        else:
            credit = amt_value
        description_text = remainder[r_flag_end:amt_match.start()]
    else:
        description_text = remainder[r_flag_end:amounts[0].start()]

    description = collapse_spaces(description_text)

    return {
        "DATE": date_val,
        "VALUE DATE": value_date,
        "DESCRIPTION": description,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": balance,
    }


def build_rows(lines):
    rows = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if not line.strip():
            continue

        row = parse_line(line)

        if row is None:
            if rows:
                extra = collapse_spaces(line)
                if extra:
                    rows[-1]["DESCRIPTION"] = collapse_spaces(
                        f"{rows[-1]['DESCRIPTION']} {extra}"
                    )
            continue

        rows.append(row)

    return rows


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_2.py cleaned_input.txt [output.csv]")
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
    rows = build_rows(lines)
    print(f"Parsed {len(rows)} transaction row(s).")

    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"CSV written to: {output_path}")


if __name__ == "__main__":
    main()