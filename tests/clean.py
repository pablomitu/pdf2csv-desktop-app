"""
clean.py

Scans a .txt file line by line, finds transaction tables inside it, and
writes out ONLY the lines that belong to those tables (skipping every
header, footer, and page-break artifact in between). The output is
still a .txt file — a later script will parse it into the final 7-column
CSV ("Posting Date", "Effective Date", "Cheque Sr. No.", "Narrative",
"Debit", "Credit", "Balance").

How table boundaries are detected
----------------------------------
START of a table: a header line like
    "     Date        Date      Sr. No.  Narrative       Debit   Credit   Balance "
Everything AFTER this line (but not the line itself) is treated as
transaction-table content, until...

END of a table: a footer line like
    "Account Transaction List                                      Page :    2 "
This line itself is also excluded. Everything between this line and the
next START marker is ignored (it's not transaction data — think page
headers, column headers repeating on the next page, etc.).

Lines inside a table are kept as-is, whether they:
    - look like an actual transaction row (start with a date), or
    - are plain continuation text (a narrative that wrapped onto its
      own line, e.g. "Mb Trf From Pakira Rodney")
Both cases matter for the later CSV-building script, so this stage
doesn't try to distinguish them — it just keeps everything inside the
table boundaries and drops everything outside them.

Blank / whitespace-only lines are dropped everywhere, since they never
carry transaction data.

Usage:
    python clean.py input.txt [output.txt]
"""

import re
import sys
from pathlib import Path

# Matches the column-header line that starts a transaction table.
# Tolerant of the exact amount of whitespace between words, since PDF
# text extraction doesn't always preserve spacing consistently.
START_MARKER_RE = re.compile(
    r"Date\s+Date\s+Sr\.?\s*No\.?\s+Narrative\s+Debit\s+Credit\s+Balance",
    re.IGNORECASE,
)

# Matches the footer line that ends a transaction table, e.g.
# "Account Transaction List ... Page : 2"
END_MARKER_RE = re.compile(
    r"Account\s+Transactions?\s+List.*Page\s*:\s*\d+",
    re.IGNORECASE,
)

# Matches page-break artifacts left over from PDF text extraction, e.g.
# "--- Page 2 ---". These are never valid transaction data and get
# stripped wherever they appear.
PAGE_BREAK_RE = re.compile(r"^\s*-+\s*Page\s+\d+\s*-+\s*$", re.IGNORECASE)


def extract_transaction_lines(lines):
    """
    Walk through the lines with a simple two-state machine:
    OUTSIDE a table (skip everything) / INSIDE a table (keep everything
    until the end marker).

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
        if END_MARKER_RE.search(line):
            inside_table = False
            continue  # the end-marker line itself is excluded too

        if PAGE_BREAK_RE.match(line):
            continue  # strip page-break artifacts like "--- Page 2 ---"

        if not line.strip():
            continue  # skip blank lines even inside a table

        kept_lines.append(line)

    return kept_lines, table_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python clean.py input.txt [output.txt]")
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