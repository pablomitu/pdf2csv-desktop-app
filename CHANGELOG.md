# Changelog
All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog**, and this project adheres to **Semantic Versioning**.

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
