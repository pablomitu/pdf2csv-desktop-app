import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

from parser.parser_logic import convert_pdfs_and_write


class PDF2CSVApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF to CSV/Excel Converter")
        self.root.geometry("600x400")
        self.root.configure(bg="#f0f0f0")

        self.pdf_paths = []

        # --- Title ---
        self.title_label = tk.Label(
            root, text="PDF → CSV/Excel Converter",
            font=("Segoe UI", 18), bg="#f0f0f0"
        )
        self.title_label.pack(pady=20)

        # --- Drag & Drop Frame ---
        self.drop_frame = tk.Frame(
            root, width=500, height=120,
            bg="#ffffff", highlightbackground="#888",
            highlightthickness=2
        )
        self.drop_frame.pack(pady=10)
        self.drop_frame.pack_propagate(False)

        self.drop_label = tk.Label(
            self.drop_frame,
            text="Drag & Drop PDF files here",
            font=("Segoe UI", 12),
            bg="#ffffff"
        )
        self.drop_label.pack(expand=True)

        # Enable drag & drop
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

        # --- Select Files Button ---
        self.browse_btn = tk.Button(
            root, text="Select PDF Files",
            command=self.select_files,
            font=("Segoe UI", 11),
            width=20
        )
        self.browse_btn.pack(pady=10)

        # --- Convert Button ---
        self.convert_btn = tk.Button(
            root, text="Convert to CSV/Excel",
            command=self.convert_files,
            font=("Segoe UI", 12),
            bg="#4CAF50", fg="white",
            width=20
        )
        self.convert_btn.pack(pady=10)

        # --- Status Label ---
        self.status_label = tk.Label(
            root, text="", font=("Segoe UI", 10),
            bg="#f0f0f0", fg="black"
        )
        self.status_label.pack(pady=15)

    # -----------------------------
    # Drag & Drop event
    # -----------------------------
    def on_drop(self, event):
        files = self.root.splitlist(event.data)
        pdfs = [f for f in files if f.lower().endswith(".pdf")]

        if not pdfs:
            messagebox.showwarning("Invalid Files", "Please drop only PDF files.")
            return

        self.pdf_paths.extend(pdfs)
        self.update_status()

    # -----------------------------
    # Manual file selection
    # -----------------------------
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF Files", "*.pdf")]
        )

        if files:
            self.pdf_paths.extend(files)
            self.update_status()

    # -----------------------------
    # Update label showing selected file count
    # -----------------------------
    def update_status(self):
        if not self.pdf_paths:
            self.status_label.config(text="No files selected.")
        else:
            self.status_label.config(text=f"{len(self.pdf_paths)} PDF file(s) selected.")

    # -----------------------------
    # Convert button logic
    # -----------------------------
    def convert_files(self):
        if not self.pdf_paths:
            messagebox.showwarning("No Files", "Please select or drop at least one PDF.")
            return

        # Ask where to save
        out_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[
                ("Excel Workbook", "*.xlsx"),
                ("CSV File", "*.csv"),
                ("All Files", "*.*")
            ],
            title="Save Output File"
        )

        if not out_path:
            return

        self.status_label.config(text="Processing... Please wait.")
        self.root.update_idletasks()

        success, message = convert_pdfs_and_write(self.pdf_paths, out_path)

        if success:
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)

        self.status_label.config(text="Done.")

        # Reset for next run
        self.pdf_paths = []


# -----------------------------
# App launcher (PyInstaller-friendly)
# -----------------------------
if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = PDF2CSVApp(root)
    root.mainloop()
