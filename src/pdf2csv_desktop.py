"""
GUI application for converting PDF files to CSV or Excel formats
with drag-and-drop, file selection, and live processing log.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

from parser.parser_logic import convert_pdfs_and_write

WINDOW_WIDTH = 700
WINDOW_HEIGHT = 600
DROP_WIDTH = 600
DROP_HEIGHT = 120


class PDF2CSVApp:
    """GUI application for converting PDF files to CSV or Excel."""

    def __init__(self, root):
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
        """Create all GUI widgets."""
        self._create_title()
        self._create_drop_frame()
        self._create_buttons()
        self._create_file_listbox()
        self._create_status_label()
        self._create_log_widget()

    def _create_title(self):
        """Create the title label."""
        title = tk.Label(
            self.root,
            text="PDF → CSV/Excel Converter",
            font=("Segoe UI", 18),
            bg="#f0f0f0",
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
            highlightthickness=2,
        )
        self.drop_frame.pack(pady=10)
        self.drop_frame.pack_propagate(False)

        drop_label = tk.Label(
            self.drop_frame,
            text="Drag & Drop PDF files here",
            font=("Segoe UI", 12),
            bg="#ffffff",
        )
        drop_label.pack(expand=True)

    def _create_buttons(self):
        """Create the file select, convert, and clear buttons."""
        btn_frame = tk.Frame(self.root, bg="#f0f0f0")
        btn_frame.pack(pady=10)

        browse_btn = tk.Button(
            btn_frame,
            text="Select PDF Files",
            command=self.select_files,
            font=("Segoe UI", 11),
            width=20,
        )
        browse_btn.grid(row=0, column=0, padx=5)

        convert_btn = tk.Button(
            btn_frame,
            text="Convert to CSV/Excel",
            command=self.convert_files,
            font=("Segoe UI", 12),
            bg="#4CAF50",
            fg="white",
            width=20,
        )
        convert_btn.grid(row=0, column=1, padx=5)

        clear_btn = tk.Button(
            btn_frame,
            text="Clear List",
            command=self.clear_list,
            font=("Segoe UI", 11),
            bg="#f44336",
            fg="white",
            width=20,
        )
        clear_btn.grid(row=0, column=2, padx=5)

    def _create_file_listbox(self):
        """Create a listbox to show selected PDFs."""
        self.file_listbox = tk.Listbox(
            self.root, width=80, height=8, selectmode=tk.SINGLE
        )
        self.file_listbox.pack(pady=10)

    def _create_status_label(self):
        """Create a status label showing number of files selected."""
        self.status_label = tk.Label(
            self.root,
            text="No files selected.",
            font=("Segoe UI", 10),
            bg="#f0f0f0",
            fg="black",
        )
        self.status_label.pack(pady=5)

    def _create_log_widget(self):
        """Create a text widget to display live processing messages."""
        self.log_frame = tk.Frame(self.root, bg="#f0f0f0")
        self.log_text = tk.Text(
            self.log_frame, width=80, height=15, state=tk.DISABLED, wrap=tk.WORD
        )
        self.log_text.pack(pady=5)
        self.log_frame.pack(pady=10)

    def log_message(self, message: str):
        """Append a message to the log text box safely from any thread."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Drag & Drop Setup
    # ------------------------------------------------------------------

    def _enable_drag_and_drop(self):
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

    def on_drop(self, event):
        """Handle PDF files dropped into the drop frame."""
        files = self.root.splitlist(event.data)
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
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
            title="Select PDF Files", filetypes=[("PDF Files", "*.pdf")]
        )
        if files:
            self.pdf_paths.extend(files)
            self.update_status()

    def update_status(self):
        """Update file list and status label."""
        self.file_listbox.delete(0, tk.END)
        for pdf in self.pdf_paths:
            self.file_listbox.insert(tk.END, pdf)

        self.status_label.config(
            text=f"{len(self.pdf_paths)} PDF file(s) selected."
            if self.pdf_paths
            else "No files selected."
        )

    def clear_list(self):
        """Clear the list of selected PDFs."""
        self.pdf_paths = []
        self.update_status()
        self.log_message("File list cleared.")

    # ------------------------------------------------------------------
    # Conversion & Live Log
    # ------------------------------------------------------------------

    def convert_files(self):
        """Convert selected PDFs to CSV/Excel with live logging."""
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

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

        def process_pdfs():
            success, message = convert_pdfs_and_write(
                self.pdf_paths, save_path, log_callback=self.log_message
            )
            if success:
                self.log_message(f"Completed! Saved to {save_path}")
                messagebox.showinfo(
                    "Success", f"PDFs processed successfully!\nSaved to {save_path}"
                )
            else:
                self.log_message(f"Error: {message}")
                messagebox.showerror("Error", message)

            self.pdf_paths = []
            self.update_status()

        threading.Thread(target=process_pdfs, daemon=True).start()


# ----------------------------------------------------------------------
# App Launcher
# ----------------------------------------------------------------------

def main():
    """Launch the PDF to CSV/Excel converter application."""
    root = TkinterDnD.Tk()
    app = PDF2CSVApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
