# Changelog
All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog**, and this project adheres to **Semantic Versioning**.

---
## [1.3.1] - 2026-11-03
### Fixed
- BSP statements that don't print the bank name (e.g. logo-only headers) are now detected correctly instead of being skipped with a "could not detect parser" warning.
- Overdrawn balances in BSP Format 1 statements (shown with a trailing - in the PDF, e.g. 22,804,220.52-) now keep their negative sign. Previously they were exported as positive numbers, so running balances did not reconcile.
### Changed
- dispatcher.py - now also recognizes BSP statements by their table header, not just the bank name.
- The "could not detect parser" warning now includes the reason detection failed (unreadable PDF, no extractable text, or no known bank name/table header).

---
## [1.3.0] - 2026-09-09
### Added
- Unified BSP parser that handles both known Bank of South Pacific statement layouts and auto-detects which one a PDF uses:
  - Format 1: Posting Date / Effective Date / Cheque Sr. No. / Narrative / Debit / Credit / Balance
  - Format 2: DATE / VALUE DATE / DESCRIPTION / DEBIT / CREDIT / BALANCE
- BSP statements in the Format 1 layout, which previously failed or parsed badly, now convert correctly.

### Changed
- bsp_parser.py - rewritten as a single class covering both formats. Debit/Credit are now assigned by column position instead of by comparing consecutive balances.
- dispatcher.py - bank detection now checks the first three pages instead of only the first.
- BSP text extraction now uses pdfminer.six (already listed in requirements.txt).
- BSP Format 2 output has changed:
  - Dates stay in the statement's own format (DD-MMM-YYYY) instead of being converted to DD/MM/YYYY.
  - Debit, Credit and Balance are exported as text, and a trailing - (negative amount) is kept as printed.
  - The R flag that prefixes some descriptions is removed.

### Removed
- The balance-delta reconciliation logic previously used to work out debit vs. credit for BSP statements.
---
## [1.2.0] – 2026-01-23
### Added
- Improved **enhanced GUI** with:
  - Live **log output window** showing parsing steps
  - Sleek **progress bar**
  - New controls for **log output**
- **New Bank Statement Parsing Logic** - BSP Bank Statements can now be used with the tool

### Changed
- Major refactor of `pdf2csv_desktop.py`
- New python scripts for better module handling:
  - `base_parser.py` - abstract base class for bank-specific pdf parsers
  - `dispatcher.py` - dispatches PDF parsing to the correct parser based on content
  - `bsp_parser.py` - single-definition BSP PDF statement parser
  - `bpng_parser.py` - wraps the existing parser_logic functions into a class-based structure for modular integration with GUI and multi-bank architecture.

---
## [1.1.0] – 2025-12-05
### Added
- New **enhanced GUI** with:
  - Live **log output window** showing parsing steps
  - Embedded **progress bar** (no popup window)
  - Scrollable list of selected PDFs
  - **Clear file list** button
- Fully asynchronous PDF conversion using threads, preventing UI freeze.
- Real-time progress updates via new callback functions in `parser_logic.py`.

### Changed
- Major refactor of `parser_logic.py`:
  - Added callback-based reporting (`on_status`, `on_page`, `on_file_done`)
  - Split large operations into granular events for better user feedback
  - Improved date normalization, monetary parsing, and multi-line transaction handling
- GUI conversion workflow rewritten to be non-blocking and more user-friendly.

### Fixed
- Resolved issue where GUI became unresponsive during PDF processing.
- Fixed missing or inconsistent transaction descriptions during multi-line merges.
- Corrected misparsed debit/credit values for certain PDF formats.

---

## [1.0.0] – 2025-11-26
### Added
- Initial release of PDF2CSV Desktop App.
- Basic GUI for PDF selection and conversion.
- Core PDF parsing and CSV/Excel export engine.

---
