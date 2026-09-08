"""
Extract text from a PDF file and write it to a .txt file.

Uses pdfminer.six to pull text page-by-page, and pandas to organize
the per-page results before writing everything out to a single .txt file.

Usage:
    python pdf_to_text.py input.pdf [output.txt]

If output.txt is omitted, it defaults to the same name as the input
file with a .txt extension.
"""

import sys
from pathlib import Path

import pandas as pd
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer


def extract_text_by_page(pdf_path: str) -> pd.DataFrame:
    """
    Extract text from each page of a PDF.

    Returns a DataFrame with columns: ['page', 'text']
    """
    records = []

    for page_num, page_layout in enumerate(extract_pages(pdf_path), start=1):
        page_text_parts = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                page_text_parts.append(element.get_text())

        page_text = "".join(page_text_parts).strip()
        records.append({"page": page_num, "text": page_text})

    return pd.DataFrame(records)


def save_text_to_file(df: pd.DataFrame, output_path: str) -> None:
    """
    Write the extracted text to a .txt file, with a simple
    page separator between each page's content.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            f.write(f"--- Page {row['page']} ---\n")
            f.write(row["text"])
            f.write("\n\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_text.py input.pdf [output.txt]")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        output_path = str(Path(pdf_path).with_suffix(".txt"))

    print(f"Extracting text from: {pdf_path}")
    df = extract_text_by_page(pdf_path)

    print(f"Extracted {len(df)} page(s). Writing to: {output_path}")
    save_text_to_file(df, output_path)

    print("Done.")


if __name__ == "__main__":
    main()