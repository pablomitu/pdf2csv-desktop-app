import re
from decimal import Decimal
from typing import List, Optional, Callable

import pdfplumber
import pandas as pd


class BSPParser:
    """
    Cleaned, single-definition BSP (Bank of South Pacific) statement parser.

    Responsibilities:
    - Detect whether a PDF looks like a BSP statement
    - Extract transaction-area lines from the PDF
    - Group multi-line transactions
    - Parse dates, descriptions, and amounts
    - Fix split monetary values (e.g. 2,224,385. + 99)
    - Reconcile debit / credit using running balances
    """

    # --- regex patterns ---
    DATE_PATTERN = re.compile(r"^\d{2}-[A-Z]{3}-\d{4}$")
    MONEY_PATTERN = re.compile(r"-?\d{1,3}(?:,\d{3})*\.\d{2}")
    INCOMPLETE_MONEY_PATTERN = re.compile(r"-?\d{1,3}(?:,\d{3})*\.$")
    DECIMAL_PART_PATTERN = re.compile(r"^\d{2}$")
    INTEGER_MONEY_IN_DESC = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")

    # sentinel used to mark totals/footer lines in the preprocessed line list
    TOTALS_SENTINEL = "__BSP_TOTALS__"

    def can_parse(self, pdf_text: str) -> bool:
        """Quick heuristic to check if this looks like a BSP statement."""
        text = pdf_text.upper()
        return "BANK OF SOUTH PACIFIC" in text or "BSP" in text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def parse_pdf(
        self,
        pdf_path: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> pd.DataFrame:
        """
        Main entry point.
        Returns a DataFrame with columns:
        DATE, VALUE DATE, DESCRIPTION, DEBIT, CREDIT, BALANCE
        """
        all_lines: List[str] = []
        capture = False
        finished = False

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                if finished:
                    break
                if progress_callback:
                    progress_callback(f"Processing page {page_idx}/{len(pdf.pages)}")

                text = page.extract_text() or ""
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

                for line in lines:
                    header = line.upper()
                    # detect header once (document-scoped)
                    if (
                        not capture
                        and "DATE" in header
                        and "VALUE" in header
                        and "DESCRIPTION" in header
                    ):
                        capture = True
                        continue

                    if not capture:
                        continue

                    stripped = header.strip()

                    # conservative end-of-statement detection: only explicit labels
                    end_markers = (
                        "END OF STATEMENT",
                        "END OF PERIOD",
                        "CLOSING BALANCE",
                        "ENDING BALANCE",
                        "STATEMENT TOTAL",
                    )
                    if any(m in stripped for m in end_markers):
                        finished = True
                        break

                    # skip obvious column separator lines (dashes) and page numbers
                    if set(stripped) <= set("- "):
                        continue
                    if stripped.isdigit():
                        continue

                    # if this line is a totals/footer line, append a sentinel so the
                    # transaction parser can stop at that boundary. We still skip adding
                    # the actual totals text to the transaction lines.
                    if stripped.startswith("TOTAL") or stripped.startswith("TOTALS") or stripped.startswith("===="):
                        all_lines.append(self.TOTALS_SENTINEL)
                        continue

                    all_lines.append(line)

        # fix split monetary values BEFORE transaction grouping
        all_lines = self._fix_incomplete_amounts(all_lines)

        records = self._parse_transactions(all_lines)
        df = pd.DataFrame(records)

        if df.empty:
            return df

        df = self._fix_debit_credit_columns(df)
        df = self._extract_amounts_from_description(df)
        df["DESCRIPTION"] = df["DESCRIPTION"].apply(self._clean_description)

        # ensure columns exist
        for col in ["DEBIT", "CREDIT", "BALANCE", "DESCRIPTION", "DATE", "VALUE DATE"]:
            if col not in df.columns:
                df[col] = None

        return df[[
            "DATE",
            "VALUE DATE",
            "DESCRIPTION",
            "DEBIT",
            "CREDIT",
            "BALANCE",
        ]]

    # ------------------------------------------------------------------
    # Line & transaction parsing
    # ------------------------------------------------------------------
    def _parse_transactions(self, lines: List[str]) -> List[dict]:
        """
        Parse transactions from a list of preprocessed lines.
        We operate on a local copy of lines so we can safely mutate as needed
        (e.g. when a value date is on the next line).

        This version treats the TOTALS_SENTINEL as a hard boundary that stops the
        current transaction's description (and is skipped from output).
        """
        records = []
        work_lines = list(lines)  # local copy so modifications don't leak
        i = 0
        while i < len(work_lines):
            # skip sentinel lines at top-level
            if work_lines[i] == self.TOTALS_SENTINEL:
                i += 1
                continue

            parts = work_lines[i].split()

            # Detect start of transaction by FIRST date only (BSP debits often wrap)
            if parts and self.DATE_PATTERN.match(parts[0]):
                date = parts[0]

                # Resolve value date
                if len(parts) > 1 and self.DATE_PATTERN.match(parts[1]):
                    value_date = parts[1]
                    consumed_next_line_remainder = None
                else:
                    # value date is on the next line
                    if i + 1 >= len(work_lines):
                        i += 1
                        continue
                    next_parts = work_lines[i + 1].split()
                    if not next_parts or not self.DATE_PATTERN.match(next_parts[0]):
                        i += 1
                        continue
                    value_date = next_parts[0]
                    consumed_next_line_remainder = " ".join(next_parts[1:]) if len(next_parts) > 1 else ""
                    work_lines[i + 1] = consumed_next_line_remainder

                # gather transaction lines (first line + continuations)
                tx_lines = [work_lines[i]]
                i += 1
                while i < len(work_lines):
                    # stop when we see the start of a new dated transaction
                    nxt = work_lines[i].split()
                    if nxt and self.DATE_PATTERN.match(nxt[0]):
                        break

                    # stop if we hit the totals sentinel or a totals-like line
                    stripped_nxt = work_lines[i].strip().upper()
                    if (
                        work_lines[i] == self.TOTALS_SENTINEL
                        or stripped_nxt.startswith("TOTAL")
                        or stripped_nxt.startswith("TOTALS")
                        or stripped_nxt.startswith("====")
                    ):
                        # do not consume the totals sentinel here; break so outer loop
                        # can skip it safely
                        break

                    tx_lines.append(work_lines[i])
                    i += 1

                # parse single transaction (first-line-only amount extraction)
                record = self._parse_single_transaction(date, value_date, tx_lines)
                records.append(record)
            else:
                i += 1

        return records

    def _parse_single_transaction(
        self, date: str, value_date: str, lines: List[str]
    ) -> dict:
        # Only extract monetary amounts from the FIRST line of the transaction
        first_line = lines[0]
        amounts = self.MONEY_PATTERN.findall(first_line)

        # Build description from all lines, then remove only the amounts we extracted
        description = " ".join(lines)
        description = description.replace(date, "").replace(value_date, "")
        for amt in amounts:
            description = description.replace(amt, "", 1)

        record = {
            "DATE": date,
            "VALUE DATE": value_date,
            "DESCRIPTION": description.strip(),
            "DEBIT": None,
            "CREDIT": None,
            "BALANCE": None,
        }

        # BSP-safe assignment:
        # - Always set BALANCE to the last money token on the first line (if present)
        # - Keep the first amount as an internal hint for first-row inference
        if amounts:
            record["BALANCE"] = amounts[-1]
            if len(amounts) >= 2:
                record["_first_amount"] = amounts[0]  # internal/debug use only

        return record

    # ------------------------------------------------------------------
    # Fixes & reconciliation
    # ------------------------------------------------------------------
    def _fix_incomplete_amounts(self, lines: List[str]) -> List[str]:
        """
        Improved merging of incomplete monetary tokens that may span lines.

        - Looks for tokens that end with a trailing dot (e.g. '5,468,862.') anywhere in
          the token list for the line (not only the last token).
        - Searches subsequent lines for the first token that looks like a 2-digit
          decimal part (e.g. '39') and attaches it.
        - If no exact two-digit match is found, will accept a short numeric token.
        - Removes the attached token from its original place, preserving other tokens.
        """
        fixed: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            tokens = line.split()

            # find any token in the line that is an incomplete money (ends with '.')
            idx = None
            for t_idx, tok in enumerate(tokens):
                if self.INCOMPLETE_MONEY_PATTERN.match(tok):
                    idx = t_idx
                    break

            if idx is not None:
                incomplete = tokens[idx]
                combined = incomplete
                merged = False
                j = i + 1
                while j < len(lines):
                    next_tokens = lines[j].split()
                    if not next_tokens:
                        j += 1
                        continue

                    # prefer an exact 2-digit token (safe decimal suffix)
                    found_k = None
                    for k, tok in enumerate(next_tokens):
                        if self.DECIMAL_PART_PATTERN.match(tok):
                            found_k = k
                            break

                    if found_k is not None:
                        combined = combined + next_tokens[found_k]
                        next_tokens.pop(found_k)
                        lines[j] = " ".join(next_tokens) if next_tokens else ""
                        merged = True
                        break

                    # otherwise accept a short numeric token (e.g. '39' not at position 0)
                    for k, tok in enumerate(next_tokens):
                        if tok.isdigit() and 1 <= len(tok) <= 3:
                            found_k = k
                            break
                    if found_k is not None:
                        combined = combined + next_tokens[found_k]
                        next_tokens.pop(found_k)
                        lines[j] = " ".join(next_tokens) if next_tokens else ""
                        merged = True
                        break

                    j += 1

                if merged:
                    tokens[idx] = combined
                    fixed.append(" ".join(tokens))
                    # we consumed tokens from line j; include remainder of that line if any
                    if j < len(lines) and lines[j].strip():
                        fixed.append(lines[j])
                    # advance pointer past the merged token line
                    i = j + 1
                    continue

            # nothing to merge here
            fixed.append(line)
            i += 1

        # remove empty lines
        fixed = [ln for ln in fixed if ln is not None and ln.strip()]
        return fixed

    def _fix_debit_credit_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        def to_dec(v):
            if v in (None, ""):
                return None
            try:
                return Decimal(v.replace(",", ""))
            except Exception:
                return None

        df = df.copy()

        # helper decimals
        df["_bal"] = df["BALANCE"].apply(to_dec)
        df["_dr"] = df["DEBIT"].apply(to_dec)
        df["_cr"] = df["CREDIT"].apply(to_dec)

        # also convert any internal first-amount hint
        if "_first_amount" in df.columns:
            df["_first_dec"] = df["_first_amount"].apply(to_dec)
        else:
            df["_first_dec"] = None

        for i in range(len(df)):
            # skip rows without balances
            if df.loc[i, "_bal"] is None:
                continue

            curr = df.loc[i, "_bal"]

            # FIRST ROW special handling: use _first_dec hint if present
            if i == 0:
                first_amt = df.loc[i, "_first_dec"] if "_first_dec" in df.columns else None
                # only infer if debit/credit are missing and we have a first-amount hint
                if (df.loc[i, "_dr"] is None or df.loc[i, "_dr"] == 0) and (
                    df.loc[i, "_cr"] is None or df.loc[i, "_cr"] == 0
                ) and first_amt is not None:
                    # guess previous balance = current - first_amt
                    prev_guess = None
                    try:
                        prev_guess = curr - first_amt
                    except Exception:
                        prev_guess = None

                    # If prev_guess is non-negative, treat first_amt as CREDIT (balance increased).
                    # Otherwise treat as DEBIT.
                    if prev_guess is not None and prev_guess >= Decimal("0"):
                        df.loc[i, "CREDIT"] = f"{first_amt:,.2f}"
                    else:
                        df.loc[i, "DEBIT"] = f"{abs(first_amt):,.2f}"
                # cannot compute delta for first row otherwise
                continue

            # for subsequent rows compute delta using previous balance
            prev = df.loc[i - 1, "_bal"]
            if prev is None:
                continue

            delta = curr - prev

            # if one side present but sign disagrees, swap
            if df.loc[i, "_cr"] and not df.loc[i, "_dr"]:
                if delta < 0:
                    df.loc[i, "DEBIT"] = df.loc[i, "CREDIT"]
                    df.loc[i, "CREDIT"] = None

            elif df.loc[i, "_dr"] and not df.loc[i, "_cr"]:
                if delta > 0:
                    df.loc[i, "CREDIT"] = df.loc[i, "DEBIT"]
                    df.loc[i, "DEBIT"] = None

            # If neither DEBIT nor CREDIT present, infer from balance delta
            if (df.loc[i, "_dr"] is None or df.loc[i, "_dr"] == 0) and (
                df.loc[i, "_cr"] is None or df.loc[i, "_cr"] == 0
            ):
                if delta > 0:
                    # balance increased -> credit
                    amt = delta
                    df.loc[i, "CREDIT"] = f"{amt:,.2f}"
                elif delta < 0:
                    amt = abs(delta)
                    df.loc[i, "DEBIT"] = f"{amt:,.2f}"

        # clean up helper columns
        drop_cols = ["_bal", "_dr", "_cr", "_first_dec", "_first_amount"]
        for c in drop_cols:
            if c in df.columns:
                df = df.drop(columns=[c])

        return df

    def _extract_amounts_from_description(self, df: pd.DataFrame) -> pd.DataFrame:
        def to_dec(v):
            if v in (None, ""):
                return None
            try:
                return Decimal(v.replace(",", ""))
            except Exception:
                return None

        df = df.copy()
        df["_bal"] = df["BALANCE"].apply(to_dec)

        for i in range(1, len(df)):
            # skip if debit/credit already present
            if df.loc[i, "DEBIT"] or df.loc[i, "CREDIT"]:
                continue

            bal = df.loc[i, "_bal"]
            prev = df.loc[i - 1, "_bal"]
            if bal is None or prev is None:
                continue

            diff = bal - prev
            if diff == 0:
                continue

            amt = abs(diff)
            if diff < 0:
                df.loc[i, "DEBIT"] = f"{amt:,.2f}"
            else:
                df.loc[i, "CREDIT"] = f"{amt:,.2f}"

        return df.drop(columns=["_bal"])

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_description(text: str) -> str:
        return " ".join(text.replace('"', "").split())