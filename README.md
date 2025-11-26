# PDF to CSV/Excel Desktop App

A Windows desktop application that converts **bank statement PDFs** into clean **CSV or Excel files** using a drag-and-drop interface.

Built with:

- Python 3
- Tkinter (TkinterDnD2 for drag & drop)
- pdfplumber
- pandas
- PyInstaller

---

## 🚀 Features

- Drag & Drop PDF files directly into the app
- Select files manually via file dialog
- Extracts structured transaction data:
  - Date
  - Transaction details
  - Debit
  - Credit
  - Balance
- Cleans and normalizes formatting
- Exports to:
  - **CSV**
  - **Excel (.xlsx)**
- Clean, simple GUI
- Fully self-contained EXE (no Python required)

---

## 📂 Project Structure
pdf2csv-desktop-app/
│
├── src/
│ ├── pdf2csv_desktop.py # GUI application
│ ├── parser/
│ │ ├── parser_logic.py # PDF parsing and cleaning logic
│ │ └── init.py
│ └── output/ # optional temporary output
│
├── requirements.txt
├── README.md
└── .gitignore


---

## 🛠 Installation (Developer)

### 1. Clone the repository
```bash
git clone <your-private-repo-url>
cd pdf2csv-desktop-app
```
---

### 2. Create a virtual environment
```bash
python -m venv venv`
venv\Scripts\activate`
```
---

### 3. Install Dependencies
`pip install -r requirements.txt`

---

### 4. Run the application
`python src/pdf2csv_desktop.py`