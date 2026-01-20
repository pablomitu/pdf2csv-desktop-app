# parser/bsp_parser.py
"""
BSP PDF Parser for PDF-to-CSV converter app.

Handles BSP bank statements using Tabula + in-memory processing.
"""

import os
import re
import subprocess
import tempfile
from decimal import Decimal
from typing import Callable, List
import pandas as pd

class BSPParser:
    """Parser class for BSP PDFs (Other Revenue Accounts)."""

    DATE_PAIR_RE = re.compile(
        r'^\s*"?\s*'
        r'(?P<d1>[0-9O o]{1,2}-[A-Za-z]{3,9}-[0-9Oo]{2,4})'
        r'\s*'
        r'(?P<d2>[0-9O o]{1,2}-[A-Za-z]{3,9}-[0-9Oo]{2,4})'
        r'(?P<rest>.*)$'
    )
    DEC_RE = re.compile(r'-?\d{1,3}(?:,\d{3})*(?:\.\s?\d{1,2})|-?\d+\.\s?\d{1,2}')

    def __init__(self, tabula_jar_path: str):
        self.tabula_jar = tabula_jar_path

    def can_parse(self, pdf_text: str) -> bool:
        """
        Determine if this parser can handle the PDF.
        A simple heuristic: look for BSP-related keywords
        """
        return "BSP" in pdf_text.upper() or "BANK OF SOUTH PACIFIC" in pdf_text.upper()

    def parse_pdf(
        self,
        pdf_path: str,
        progress_callback: Callable[[str], None] = None
    ) -> pd.DataFrame:
        """
        Parse BSP PDF into a structured DataFrame.

        Args:
            pdf_path: path to BSP PDF
            progress_callback: function(message: str) for logging

        Returns:
            pandas.DataFrame with columns ["DATE","VALUE DATE","DESCRIPTION","DEBIT","CREDIT","BALANCE"]
        """
        if progress_callback:
            progress_callback(f"Processing {os.path.basename(pdf_path)}")

        # STEP 1 – Optional OCR (skip if unavailable)
        pdf_to_use = self._run_ocr_if_available(pdf_path, progress_callback)

        # STEP 2 – Extract CSV via Tabula
        csv_text = self._extract_csv_via_tabula(pdf_to_use, progress_callback)

        # STEP 3 – Remove symbol-only rows
        csv_text = self._remove_symbol_only_rows(csv_text, progress_callback)

        # STEP 4 – Collapse to single column
        csv_text = self._collapse_to_single_column(csv_text, progress_callback)

        # STEP 5 – Trim between DATEVALUE and Totals
        csv_text = self._trim_block(csv_text, progress_callback)

        # STEP 6 – Parse structured records
        records = self._parse_records(csv_text, progress_callback)

        df = pd.DataFrame(records)
        
        # Clean up descriptions - remove extra quotes and whitespace
        if 'DESCRIPTION' in df.columns:
            df['DESCRIPTION'] = df['DESCRIPTION'].apply(self._clean_description)
        
        return df

    # ==================== Internal pipeline helpers ====================

    def _run_ocr_if_available(self, input_pdf: str, log: Callable = None) -> str:
        if log:
            log("STEP 1 – Optional OCR")
        try:
            subprocess.run(["ocrmypdf", "--version"], capture_output=True, 
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            ocrmypdf_available = True
        except FileNotFoundError:
            ocrmypdf_available = False

        if not ocrmypdf_available:
            if log:
                log("  OCR not found → using original PDF")
            return input_pdf

        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        if log:
            log(f"  Running OCR → {temp_pdf}")
        subprocess.run(["ocrmypdf", "--skip-text", "--output-type", "pdf", input_pdf, temp_pdf],
                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return temp_pdf if os.path.exists(temp_pdf) else input_pdf

    def _extract_csv_via_tabula(self, pdf_path: str, log: Callable = None) -> str:
        if log:
            log("STEP 2 – Extract CSV via Tabula")
        temp_csv = tempfile.NamedTemporaryFile(delete=False, suffix=".csv").name
        cmd = ["java", "-jar", self.tabula_jar, "-p", "all", "-f", "CSV", "-o", temp_csv, pdf_path]
        
        # Hide console window on Windows
        if os.name == 'nt':
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.run(cmd)
            
        if not os.path.exists(temp_csv):
            raise RuntimeError("Tabula failed to produce CSV")
        with open(temp_csv, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()

    def _remove_symbol_only_rows(self, csv_text: str, log: Callable = None) -> str:
        if log:
            log("STEP 3 – Remove symbol-only rows")
        lines = csv_text.splitlines()
        return "\n".join(l for l in lines if re.search(r"[A-Za-z0-9]", l))

    def _collapse_to_single_column(self, csv_text: str, log: Callable = None) -> str:
        if log:
            log("STEP 4 – Collapse to single column")
        out_lines = []
        for line in csv_text.splitlines():
            cols = line.split(",")
            out_lines.append("".join(cols))
        return "\n".join(out_lines)

    def _trim_block(self, csv_text: str, log: Callable = None) -> str:
        if log:
            log("STEP 5 – Trim block between DATEVALUE and Totals row")
        lines = csv_text.splitlines()
        header_re = re.compile(r'^"?(DATEVALUE)')
        totals_re = re.compile(r'^"?Totals"?(?:"|\d)', re.IGNORECASE)
        start = next((i for i, l in enumerate(lines) if header_re.match(l)), None)
        if start is None:
            raise ValueError("DATEVALUE header not found")
        end = next((i for i, l in enumerate(lines[start+1:], start=start+1) if totals_re.match(l)), None)
        if end is None:
            raise ValueError("Totals row not found")
        return "\n".join(lines[start+1:end])

    def _parse_records(self, trimmed_text: str, log: Callable = None) -> List[dict]:
        if log:
            log("STEP 6 – Parse structured records")
        lines = trimmed_text.splitlines()
        records = []
        current = None
        prev_balance = None

        for line in lines:
            if not line.strip():
                if current:
                    current["description_lines"].append("")
                continue
            m = self.DATE_PAIR_RE.match(line)
            if m:
                if current:
                    descr = " ".join(ln.strip() for ln in current["description_lines"] if ln.strip())
                    records.append({
                        "DATE": current["date"],
                        "VALUE DATE": current["value_date"],
                        "DESCRIPTION": descr,
                        "DEBIT": current.get("debit", ""),
                        "CREDIT": current.get("credit", ""),
                        "BALANCE": current.get("balance", "")
                    })
                    prev_balance = self._to_decimal(current.get("balance"))
                d1 = re.sub(r"[Oo]", "0", m.group("d1"))
                d2 = re.sub(r"[Oo]", "0", m.group("d2"))
                rest = m.group("rest").strip()
                decs = list(self.DEC_RE.finditer(rest))
                first_amount = self._normalize_num_str(decs[0].group(0)) if decs else None
                second_amount = self._normalize_num_str(decs[1].group(0)) if len(decs) > 1 else ""
                desc_raw = rest[:decs[0].start()] if decs else rest
                current = {"date": d1, "value_date": d2, "description_lines": [desc_raw], "balance": second_amount}
                fa = self._to_decimal(first_amount)
                sb = self._to_decimal(second_amount)
                # debit/credit assignment
                if fa is None:
                    current["debit"] = ""
                    current["credit"] = ""
                else:
                    if prev_balance is None:
                        current["debit"] = ""
                        current["credit"] = str(fa)
                    else:
                        if sb is None:
                            current["debit"] = ""
                            current["credit"] = str(fa)
                        elif sb > prev_balance:
                            current["debit"] = ""
                            current["credit"] = str(fa)
                        elif sb < prev_balance:
                            current["debit"] = str(fa)
                            current["credit"] = ""
                        else:
                            current["debit"] = ""
                            current["credit"] = str(fa)
                continue
            # continuation line
            if current:
                current["description_lines"].append(line.strip())
        # finalize last record
        if current:
            descr = " ".join(ln.strip() for ln in current["description_lines"] if ln.strip())
            records.append({
                "DATE": current["date"],
                "VALUE DATE": current["value_date"],
                "DESCRIPTION": descr,
                "DEBIT": current.get("debit", ""),
                "CREDIT": current.get("credit", ""),
                "BALANCE": current.get("balance", "")
            })
        return records

    def _normalize_num_str(self, s: str) -> str:
        return s.replace(",", "").replace('"', "").replace(" ", "").strip()

    def _to_decimal(self, s: str):
        if not s:
            return None
        try:
            return Decimal(self._normalize_num_str(s))
        except:
            filtered = re.sub(r"[^\d.-]", "", s)
            try:
                return Decimal(filtered)
            except:
                return None
    
    def _clean_description(self, text: str) -> str:
        """
        Clean up description text by removing extra quotes and normalizing whitespace.
        
        Args:
            text: raw description text
            
        Returns:
            cleaned description text
        """
        if not isinstance(text, str):
            return text
        
        # Remove all standalone quote marks (both single and double)
        # This removes quotes that are not part of actual quoted content
        cleaned = re.sub(r'"{2,}', '', text)  # Remove multiple consecutive quotes
        cleaned = re.sub(r'(?<!\w)"(?!\w)', '', cleaned)  # Remove isolated quotes
        cleaned = re.sub(r'(?<!\w)""(?!\w)', '', cleaned)  # Remove double quotes not attached to words
        
        # Normalize whitespace - replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Remove leading/trailing whitespace and quotes
        cleaned = cleaned.strip().strip('"').strip()
        
        return cleaned