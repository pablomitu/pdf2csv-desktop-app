"""
clean_2.py

A variant of clean.py for a DIFFERENT statement format. Scans a .txt
file line by line, finds transaction tables inside it, and writes out
ONLY the lines that belong to those tables. The output is still a .txt
file — a later script will parse it into the final 6-column CSV:

    DATE           -> Date     (DD-MMM-YYYY)
    VALUE DATE     -> Date     (DD-MMM-YYYY)
    DESCRIPTION    -> Text
    DEBIT          -> Text     (kept as NVARCHAR, not Decimal, because
                                 values can carry a trailing "-", e.g.
                                 "0.06-" — see note below)
    CREDIT         -> Text     (same reason as DEBIT)
    BALANCE        -> Text     (same reason as DEBIT)

How table boundaries are detected
----------------------------------
START of a table: a header line like
    "   DATE             VALUE DATE          DESCRIPTION              DEBIT             CREDIT         BALANCE          "
Everything AFTER this line (but not the line itself) is treated as
transaction-table content, until...

END of a table: a line that starts with "Totals", e.g.
    "   Totals                                                         163,760.66      202,867.18     39,106.52         "
This line (and the line itself) is also excluded.

Page-break noise, NOT a table ender
------------------------------------
"about:blank" is NOT the end of the table — it's a recurring artifact
that shows up at every page break, along with a handful of other junk
lines (page markers, bare page-number fractions, print timestamps).
This noise is scattered in the MIDDLE of the table, interrupting real
transaction data, e.g.:

    29-JUN-2023   29-JUN-2023   MERCHANT PURCHASE-PNG   300.00        16.72
                                 Auto Cheap Ltd Wabag
    about:blank
    1/64
    --- Page 2 ---
    8/19/26, 11:23 AM
    about:blank
                                 PG-999VPOS231800Y96
    29-JUN-2023   29-JUN-2023   Merchant Purchase       0.25          16.47

All of these junk lines are stripped WITHOUT ending the table, so the
transaction data on either side of a page break stays connected (the
continuation line "PG-999VPOS231800Y96" above still gets treated as
part of the previous row's Description).

Blank / whitespace-only lines are also dropped everywhere, since they
never carry transaction data.

Usage:
    python clean_2.py input.txt [output.txt]
"""

import re
import sys
from pathlib import Path

# Matches the column-header line that starts a transaction table.
START_MARKER_RE = re.compile(
    r"DATE\s+VALUE\s+DATE\s+DESCRIPTION\s+DEBIT\s+CREDIT\s+BALANCE",
    re.IGNORECASE,
)

# Matches the line that truly ends a transaction table, e.g. "   Totals ..."
END_MARKER_RE = re.compile(r"^\s*Totals\b", re.IGNORECASE)

# --- Page-break junk patterns: skipped wherever they appear, without
# --- ending the table. ---

# "about:blank"
ABOUT_BLANK_RE = re.compile(r"^\s*about:blank\s*$", re.IGNORECASE)

# "--- Page 2 ---" style page markers (e.g. from PDF text extraction)
PAGE_BREAK_RE = re.compile(r"^\s*-+\s*Page\s+\d+\s*-+\s*$", re.IGNORECASE)

# Bare page-number fractions, e.g. "1/64"
PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")

# Print-header timestamps, e.g. "8/19/26, 11:23 AM"
TIMESTAMP_RE = re.compile(
    r"^\s*\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(AM|PM)\s*$",
    re.IGNORECASE,
)

# Pure divider lines made of "=" characters, e.g.
# "===================================================================================================================="
SEPARATOR_LINE_RE = re.compile(r"^[\s=]+$")

# Pure divider lines made of "-" characters (and whitespace), e.g. the
# dashed rule under the column header:
# "------------     ------------------    -------------           ----------        -----------    ------------       "
DASH_SEPARATOR_RE = re.compile(r"^[\s\-]+$")


def is_page_break_junk(line: str) -> bool:
    """True if this line is one of the known page-break/divider artifacts."""
    return bool(
        ABOUT_BLANK_RE.match(line)
        or PAGE_BREAK_RE.match(line)
        or PAGE_NUMBER_RE.match(line)
        or TIMESTAMP_RE.match(line)
        or SEPARATOR_LINE_RE.match(line)
        or DASH_SEPARATOR_RE.match(line)
    )


def extract_transaction_lines(lines):
    """
    Walk through the lines with a simple two-state machine:
    OUTSIDE a table (skip everything) / INSIDE a table (keep lines
    until the "Totals" end marker, skipping page-break junk along the
    way without ending the table).

    Returns (kept_lines, table_count).
    """
    kept_lines = []
    inside_table = False
    table_count = 0

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if not inside_table:
            if START_MARKER_RE.search(line):
                inside_table = True
                table_count += 1
            # Whether or not this was a start marker, this line itself
            # is never kept — either it's the header line, or it's
            # unrelated text outside any table.
            continue

        # inside_table is True from here on
        if END_MARKER_RE.match(line):
            inside_table = False
            continue  # the "Totals" line itself is excluded too

        if is_page_break_junk(line):
            continue  # skip, but stay inside the table

        if not line.strip():
            continue  # skip blank lines too

        kept_lines.append(line)

    return kept_lines, table_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python clean_2.py input.txt [output.txt]")
        sys.exit(1)

    input_path = sys.argv[1]

    if not Path(input_path).exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        p = Path(input_path)
        output_path = str(p.with_name(f"{p.stem}_cleaned{p.suffix}"))

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Read {len(lines)} line(s) from: {input_path}")

    kept_lines, table_count = extract_transaction_lines(lines)

    print(f"Number of transaction tables found: {table_count}")
    print(f"Number of transaction-data lines kept: {len(kept_lines)}")

    with open(output_path, "w", encoding="utf-8") as f:
        for line in kept_lines:
            f.write(line + "\n")

    print(f"Cleaned output written to: {output_path}")


if __name__ == "__main__":
    main()