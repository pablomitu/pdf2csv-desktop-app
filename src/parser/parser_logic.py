import pdfplumber
import pandas as pd
import re
from datetime import datetime
import os

money_pattern = r"\b\d{1,3}(?:,\d{3})*\.\d{2}\b"

def find_monetary_values(text):
    return re.findall(money_pattern, text)

def format_date(date_str):
    for fmt in ("%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return date_str

def process_pdf(pdf_path):
    data = []
    headers_identified = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = text.split("\n")
            line_count = len(lines)

            for line in lines:
                line = line.strip()

                if (
                    "BANK OF PAPUA NEW GUINEA" in line
                    or "Bank Statement for Account" in line
                    or "END OF REPORT" in line
                    or re.search(r"Page\s*\d+\s*of\s*\d+", line, re.IGNORECASE)
                ):
                    continue

                if not headers_identified and all(
                    kw in line
                    for kw in ["DATE", "TRANSACTION DETAILS", "DEBIT", "CREDIT", "BALANCE"]
                ):
                    headers_identified = True
                    continue

                if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", line):
                    if data:
                        data[-1][1] += " " + line
                    continue

                m = re.match(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(.*)$", line)
                if m:
                    date_str, rest = m.groups()
                    date_val = format_date(date_str.strip())
                    rest = rest.strip()

                    if "OPENING BALANCE" in rest:
                        mon = find_monetary_values(rest)
                        bal = mon[-1] if mon else "0.00"
                        data.append([
                            date_val, "OPENING BALANCE",
                            "0.00", "0.00", bal,
                            line_count, page_idx
                        ])
                        continue

                    money_matches = list(re.finditer(money_pattern, rest))

                    if not money_matches:
                        if data:
                            data[-1][1] += " " + line
                        continue

                    if len(money_matches) >= 3:
                        d = money_matches[-3].group()
                        c = money_matches[-2].group()
                        b = money_matches[-1].group()
                        spans = [(m.start(), m.end()) for m in money_matches[-3:]]
                        detail = ""
                        last = 0
                        for s, e in spans:
                            detail += rest[last:s]
                            last = e
                        detail += rest[last:]
                    elif len(money_matches) == 2:
                        d = "0.00"
                        c = money_matches[0].group()
                        b = money_matches[1].group()
                        detail = rest.split(c, 1)[0].strip()
                    else:
                        d = "0.00"
                        c = "0.00"
                        b = money_matches[0].group()
                        detail = rest.split(b, 1)[0].strip()

                    data.append([
                        date_val, detail.strip(),
                        d, c, b,
                        line_count, page_idx
                    ])
                    continue

                if re.match(r"^[\d,\.]+\s*$", line):
                    mon_vals = find_monetary_values(line)
                    if data and mon_vals:
                        last = data[-1]
                        if last[2] == "0.00" and last[3] == "0.00" and len(mon_vals) == 2:
                            last[3], last[4] = mon_vals
                        elif len(mon_vals) == 3:
                            last[2], last[3], last[4] = mon_vals
                        else:
                            last[1] += " " + line
                    elif data:
                        data[-1][1] += " " + line
                    continue

                if data:
                    data[-1][1] += " " + line

    return pd.DataFrame(
        data,
        columns=[
            "Date", "Transaction Details",
            "Debit", "Credit", "Balance",
            "Line Count", "Page Number"
        ]
    )

def clean_transaction_details(text):
    header_keywords = ["DATE","TRANSACTION","DETAILS","DEBIT","CREDIT","BALANCE"]
    words = text.split()
    idxs = []
    pos = 0
    for kw in header_keywords:
        for i in range(pos, len(words)):
            if words[i].upper() == kw:
                idxs.append(i)
                pos = i+1
                break
    if len(idxs) != len(header_keywords):
        return text.strip()
    f, l = idxs[0], idxs[-1]
    return " ".join(words[:f] + words[l+1:]).strip()

def clean_monetary_values(df):
    pat = r"\b\d{1,3}(?:,\d{1,3})*\.\d{2}\b"
    for i, row in df.iterrows():
        bvals = re.findall(pat, row["Balance"])
        if len(bvals) == 2:
            df.at[i, "Credit"] = bvals[0]
            df.at[i, "Balance"] = bvals[1]
            if bvals[0] == "0.00" and row["Credit"] not in ("0.00",""):
                df.at[i, "Debit"] = row["Credit"]
                df.at[i, "Credit"] = "0.00"
    return df

def convert_pdfs_and_write(pdf_paths, out_path):
    all_dfs = []
    for path in pdf_paths:
        df = process_pdf(path)
        df = clean_monetary_values(df)
        df["Transaction Details"] = df["Transaction Details"].apply(clean_transaction_details)
        all_dfs.append(df)

    if not all_dfs:
        return False, "No PDF data extracted."

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.drop(columns=["Line Count", "Page Number"])

    ext = os.path.splitext(out_path)[1].lower()
    if ext in (".xlsx", ".xls"):
        with pd.ExcelWriter(out_path) as writer:
            combined.to_excel(writer, sheet_name="AllData", index=False)
    else:
        combined.to_csv(out_path, index=False)

    return True, f"Saved to {out_path}"
