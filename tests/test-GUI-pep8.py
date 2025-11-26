"""
GUI application for converting PDF files to CSV or Excel formats using
drag-and-drop and file selection dialogs.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

from parser.parser_logic import convert_pdfs_and_write


WINDOW_WIDTH = 600
WINDOW_HEIGHT = 400
DROP_WIDTH = 500
DROP_HEIGHT = 120


class PDF2CSVApp:
    """GUI application for converting PDF files to CSV or Excel."""

    def __init__(self, root):
        """Initialize the GUI application."""
        self.root = root
        self.pdf_paths = []

        self._setup_window()
        self._create_widgets()
        self._enable_drag_and_drop()

    # ------------------------------------------------------------------
    # Window Setup
    # ------------------------------------------------------------------
    def _setup_window(self):
        """Configure the main application window."""
        self.root.title("PDF to CSV/Excel Converter")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg="#f0f0f0")

    # ------------------------------------------------------------------
    # GUI Widget Creation
    # ------------------------------------------------------------------
    def _create_widgets(self):
        """Create and place all GUI widgets."""
        self._create_title()
        self._create_drop_frame()
        self._create_buttons()
        self._create_status_label()

    def _create_title(self):
        """Create the title label."""
        title = tk.Label(
            self.root,
            text="PDF → CSV/Excel Converter",
            font=("Segoe UI", 18),
            bg="#f0f0f0"
        )
        title.pack(pady=20)

    def _create_drop_frame(self):
        """Create the drag-and-drop input frame."""
        self.drop_frame = tk.Frame(
            self.root,
            width=DROP_WIDTH,
            height=DROP_HEIGHT,
            bg="#ffffff",
            highlightbackground="#888",
            highlightthickness=2
        )
        self.drop_frame.pack(pady=10)
        self.drop_frame.pack_propagate(False)

        drop_label = tk.Label(
            self.drop_frame,
            text="Drag & Drop PDF files here",
            font=("Segoe UI", 12),
            bg="#ffffff"
        )
        drop_label.pack(expand=True)

    def _create_buttons(self):
        """Create the file select and convert buttons."""
        browse_btn = tk.Button(
            self.root,
            text="Select PDF Files",
            command=self.select_files,
            font=("Segoe UI", 11),
            width=20
        )
        browse_btn.pack(pady=10)

        convert_btn = tk.Button(
            self.root,
            text="Convert to CSV/Excel",
            command=self.convert_files,
            font=("Segoe UI", 12),
            bg="#4CAF50",
            fg="white",
            width=20
        )
        convert_btn.pack(pady=10)

    def _create_status_label(self):
        """Create the bottom status label."""
        self.status_label = tk.Label(
            self.root,
            text="",
            font=("Segoe UI", 10),
            bg="#f0f0f0",
            fg="black"
        )
        self.status_label.pack(pady=15)

    # ------------------------------------------------------------------
    # Drag & Drop Setup
    # ------------------------------------------------------------------
    def _enable_drag_and_drop(self):
        """Enable drag-and-drop behavior for the drop frame."""
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

    def on_drop(self, event):
        """Handle PDF files dropped into the drop frame."""
        files = self.root.splitlist(event.data)
        pdfs = [path for path in files if path.lower().endswith(".pdf")]

        if not pdfs:
            messagebox.showwarning("Invalid Files", "Please drop only PDF files.")
            return

        self.pdf_paths.extend(pdfs)
        self.update_status()

    # ------------------------------------------------------------------
    # File Selection & Status Update
    # ------------------------------------------------------------------
    def select_files(self):
        """Open a dialog for selecting PDF files manually."""
        files = filedialog.askopenfilenames(
            title="Select PDF Files",
            filetypes=[("PDF Files", "*.pdf")]
        )

        if files:
            self.pdf_paths.extend(files)
            self.update_status()

    def update_status(self):
        """Update the label showing how many files are selected."""
        if not self.pdf_paths:
            self.status_label.config(text="No files selected.")
        else:
            count = len(self.pdf_paths)
            self.status_label.config(text=f"{count} PDF file(s) selected.")

    # ------------------------------------------------------------------
    # Conversion Logic
    # ------------------------------------------------------------------
    def convert_files(self):
        """Convert selected PDFs to CSV or Excel and save the result."""
        if not self.pdf_paths:
            messagebox.showwarning("No Files", "Please select or drop at least one PDF.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[
                ("Excel Workbook", "*.xlsx"),
                ("CSV File", "*.csv"),
                ("All Files", "*.*"),
            ],
            title="Save Output File",
        )

        if not save_path:
            return

        self.status_label.config(text="Processing... Please wait.")
        self.root.update_idletasks()

        success, message = convert_pdfs_and_write(self.pdf_paths, save_path)

        if success:
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)

        self.status_label.config(text="Done.")
        self.pdf_paths = []


# ----------------------------------------------------------------------
# App Launcher (PyInstaller-Friendly)
# ----------------------------------------------------------------------
def main():
    """Launch the PDF to CSV/Excel converter application."""
    root = TkinterDnD.Tk()
    app = PDF2CSVApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
