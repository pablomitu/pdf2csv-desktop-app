"""
GUI application for converting PDF files to CSV or Excel formats
with drag-and-drop, file selection, and live processing log.

Modern sleek design with improved UX.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

from parser.dispatcher import PDFParserDispatcher

# Window dimensions
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700

# Modern color palette
COLORS = {
    'primary': '#2563eb',      # Blue
    'primary_dark': '#1e40af',
    'success': '#10b981',      # Green
    'danger': '#ef4444',       # Red
    'warning': '#f59e0b',      # Orange
    'background': '#f8fafc',   # Light gray
    'surface': '#ffffff',      # White
    'border': '#e2e8f0',       # Light border
    'text': '#1e293b',         # Dark text
    'text_secondary': '#64748b', # Gray text
    'drop_zone': '#f1f5f9',    # Drop zone bg
    'drop_zone_hover': '#e0e7ff', # Drop zone hover
}

# Path to Tabula JAR file - works both in development and when bundled by PyInstaller
def get_tabula_jar_path():
    """Get the path to Tabula JAR, works in both dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, "lib", "tabula-1.0.5-jar-with-dependencies.jar")

TABULA_JAR_PATH = get_tabula_jar_path()


class PDF2CSVApp:
    """GUI application for converting PDF files to CSV or Excel."""

    def __init__(self, root):
        self.root = root
        self.pdf_paths = []
        self.is_processing = False
        
        # Initialize the dispatcher with Tabula JAR path
        self.dispatcher = PDFParserDispatcher(TABULA_JAR_PATH)

        self._setup_window()
        self._setup_styles()
        self._create_widgets()
        self._enable_drag_and_drop()

    # ------------------------------------------------------------------
    # Window Setup
    # ------------------------------------------------------------------

    def _setup_window(self):
        """Configure the main application window."""
        self.root.title("PDF to CSV/Excel Converter")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=COLORS['background'])
        
        # Center window on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (WINDOW_WIDTH // 2)
        y = (self.root.winfo_screenheight() // 2) - (WINDOW_HEIGHT // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _setup_styles(self):
        """Configure ttk styles for modern look."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure button styles
        style.configure('Primary.TButton',
                       background=COLORS['primary'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(20, 12))
        style.map('Primary.TButton',
                 background=[('active', COLORS['primary_dark'])])
        
        style.configure('Success.TButton',
                       background=COLORS['success'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(20, 12))
        style.map('Success.TButton',
                 background=[('active', '#059669')])
        
        style.configure('Danger.TButton',
                       background=COLORS['danger'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(20, 12))
        style.map('Danger.TButton',
                 background=[('active', '#dc2626')])

    # ------------------------------------------------------------------
    # GUI Widget Creation
    # ------------------------------------------------------------------

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main container with padding
        main_container = tk.Frame(self.root, bg=COLORS['background'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        self._create_header(main_container)
        self._create_drop_zone(main_container)
        self._create_action_buttons(main_container)
        self._create_file_list(main_container)
        self._create_log_section(main_container)

    def _create_header(self, parent):
        """Create the header section."""
        header_frame = tk.Frame(parent, bg=COLORS['background'])
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Title
        title = tk.Label(
            header_frame,
            text="PDF Statement Converter",
            font=("Segoe UI", 28, "bold"),
            bg=COLORS['background'],
            fg=COLORS['text']
        )
        title.pack()
        
        # Subtitle
        subtitle = tk.Label(
            header_frame,
            text="Convert BPNG & BSP bank statements to Excel or CSV",
            font=("Segoe UI", 11),
            bg=COLORS['background'],
            fg=COLORS['text_secondary']
        )
        subtitle.pack(pady=(5, 0))

    def _create_drop_zone(self, parent):
        """Create the drag-and-drop zone."""
        # Container for shadow effect
        drop_container = tk.Frame(parent, bg=COLORS['background'])
        drop_container.pack(fill=tk.X, pady=(0, 20))
        
        # Drop zone
        self.drop_frame = tk.Frame(
            drop_container,
            bg=COLORS['drop_zone'],
            highlightbackground=COLORS['border'],
            highlightthickness=2
        )
        self.drop_frame.pack(fill=tk.X, ipady=40)
        
        # Icon (using text)
        icon_label = tk.Label(
            self.drop_frame,
            text="📄",
            font=("Segoe UI", 48),
            bg=COLORS['drop_zone']
        )
        icon_label.pack(pady=(20, 10))
        
        # Drop text
        drop_label = tk.Label(
            self.drop_frame,
            text="Drag & Drop PDF files here",
            font=("Segoe UI", 14, "bold"),
            bg=COLORS['drop_zone'],
            fg=COLORS['text']
        )
        drop_label.pack()
        
        # Subtext
        drop_subtext = tk.Label(
            self.drop_frame,
            text="or use the button below to browse",
            font=("Segoe UI", 10),
            bg=COLORS['drop_zone'],
            fg=COLORS['text_secondary']
        )
        drop_subtext.pack(pady=(5, 20))

    def _create_action_buttons(self, parent):
        """Create action buttons."""
        btn_frame = tk.Frame(parent, bg=COLORS['background'])
        btn_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Center the buttons
        btn_container = tk.Frame(btn_frame, bg=COLORS['background'])
        btn_container.pack()
        
        # Browse button
        self.browse_btn = ttk.Button(
            btn_container,
            text="📁 Browse Files",
            command=self.select_files,
            style='Primary.TButton'
        )
        self.browse_btn.grid(row=0, column=0, padx=8)
        
        # Convert button
        self.convert_btn = ttk.Button(
            btn_container,
            text="✓ Convert to Excel/CSV",
            command=self.convert_files,
            style='Success.TButton'
        )
        self.convert_btn.grid(row=0, column=1, padx=8)
        
        # Clear button
        self.clear_btn = ttk.Button(
            btn_container,
            text="✕ Clear All",
            command=self.clear_list,
            style='Danger.TButton'
        )
        self.clear_btn.grid(row=0, column=2, padx=8)

    def _create_file_list(self, parent):
        """Create file list section."""
        list_frame = tk.Frame(parent, bg=COLORS['background'])
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Header
        list_header = tk.Frame(list_frame, bg=COLORS['background'])
        list_header.pack(fill=tk.X, pady=(0, 10))
        
        files_label = tk.Label(
            list_header,
            text="Selected Files",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS['background'],
            fg=COLORS['text']
        )
        files_label.pack(side=tk.LEFT)
        
        self.status_label = tk.Label(
            list_header,
            text="No files selected",
            font=("Segoe UI", 10),
            bg=COLORS['background'],
            fg=COLORS['text_secondary']
        )
        self.status_label.pack(side=tk.RIGHT)
        
        # Listbox with scrollbar
        list_container = tk.Frame(
            list_frame,
            bg=COLORS['surface'],
            highlightbackground=COLORS['border'],
            highlightthickness=1
        )
        list_container.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            font=("Segoe UI", 10),
            bg=COLORS['surface'],
            fg=COLORS['text'],
            borderwidth=0,
            highlightthickness=0,
            selectbackground=COLORS['primary'],
            selectforeground='white'
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.config(command=self.file_listbox.yview)

    def _create_log_section(self, parent):
        """Create log section."""
        log_frame = tk.Frame(parent, bg=COLORS['background'])
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        log_header = tk.Label(
            log_frame,
            text="Processing Log",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS['background'],
            fg=COLORS['text']
        )
        log_header.pack(anchor=tk.W, pady=(0, 10))
        
        # Log text with scrollbar
        log_container = tk.Frame(
            log_frame,
            bg=COLORS['surface'],
            highlightbackground=COLORS['border'],
            highlightthickness=1
        )
        log_container.pack(fill=tk.BOTH, expand=True)
        
        log_scrollbar = tk.Scrollbar(log_container)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_container,
            yscrollcommand=log_scrollbar.set,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=COLORS['surface'],
            fg=COLORS['text'],
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
            height=8
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        log_scrollbar.config(command=self.log_text.yview)

    def log_message(self, message: str):
        """Append a message to the log text box safely from any thread."""
        def update():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        
        # Ensure thread-safe GUI updates
        self.root.after(0, update)

    # ------------------------------------------------------------------
    # Drag & Drop Setup
    # ------------------------------------------------------------------

    def _enable_drag_and_drop(self):
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)
        self.drop_frame.dnd_bind("<<DragEnter>>", self.on_drag_enter)
        self.drop_frame.dnd_bind("<<DragLeave>>", self.on_drag_leave)

    def on_drag_enter(self, event):
        """Visual feedback when dragging over drop zone."""
        self.drop_frame.configure(bg=COLORS['drop_zone_hover'])
        for widget in self.drop_frame.winfo_children():
            widget.configure(bg=COLORS['drop_zone_hover'])

    def on_drag_leave(self, event):
        """Reset visual feedback when leaving drop zone."""
        self.drop_frame.configure(bg=COLORS['drop_zone'])
        for widget in self.drop_frame.winfo_children():
            widget.configure(bg=COLORS['drop_zone'])

    def on_drop(self, event):
        """Handle PDF files dropped into the drop zone."""
        self.on_drag_leave(event)  # Reset colors
        
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
        if self.is_processing:
            return
            
        files = filedialog.askopenfilenames(
            title="Select PDF Files",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if files:
            self.pdf_paths.extend(files)
            self.update_status()

    def update_status(self):
        """Update file list and status label."""
        self.file_listbox.delete(0, tk.END)
        for pdf in self.pdf_paths:
            filename = os.path.basename(pdf)
            self.file_listbox.insert(tk.END, filename)

        count = len(self.pdf_paths)
        if count == 0:
            self.status_label.config(text="No files selected", fg=COLORS['text_secondary'])
        elif count == 1:
            self.status_label.config(text="1 file ready", fg=COLORS['success'])
        else:
            self.status_label.config(text=f"{count} files ready", fg=COLORS['success'])

    def clear_list(self):
        """Clear the list of selected PDFs."""
        if self.is_processing:
            return
            
        self.pdf_paths = []
        self.update_status()
        self.log_message("✓ File list cleared")

    # ------------------------------------------------------------------
    # Conversion & Live Log
    # ------------------------------------------------------------------

    def convert_files(self):
        """Convert selected PDFs to CSV/Excel with live logging."""
        if self.is_processing:
            return
            
        if not self.pdf_paths:
            messagebox.showwarning("No Files", "Please select or drop at least one PDF file.")
            return

        # Auto-suggest output filename based on first PDF
        first_pdf = self.pdf_paths[0]
        pdf_dir = os.path.dirname(first_pdf)
        pdf_name = os.path.splitext(os.path.basename(first_pdf))[0]
        
        # If multiple files, use a generic name
        if len(self.pdf_paths) > 1:
            suggested_name = "combined_statements.xlsx"
        else:
            suggested_name = f"{pdf_name}.xlsx"
        
        suggested_path = os.path.join(pdf_dir, suggested_name)

        save_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialdir=pdf_dir,
            initialfile=suggested_name,
            filetypes=[
                ("Excel Workbook", "*.xlsx"),
                ("CSV File", "*.csv"),
                ("All Files", "*.*"),
            ],
            title="Save Output File",
        )
        if not save_path:
            return

        # Clear log
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
        # Disable buttons during processing
        self.is_processing = True
        self.browse_btn.config(state='disabled')
        self.convert_btn.config(state='disabled')
        self.clear_btn.config(state='disabled')

        def process_pdfs():
            try:
                self.log_message("━" * 60)
                self.log_message("Starting PDF processing...")
                self.log_message("━" * 60)
                
                # Use dispatcher to parse PDFs (auto-detects BPNG vs BSP)
                df = self.dispatcher.parse_pdfs(
                    self.pdf_paths, 
                    log_callback=self.log_message
                )
                
                if df.empty:
                    self.log_message("✗ ERROR: No data extracted from PDFs")
                    messagebox.showerror("Error", "No data could be extracted from the PDFs.")
                    return
                
                # Save to file
                self.log_message(f"💾 Saving to {os.path.basename(save_path)}...")
                
                ext = os.path.splitext(save_path)[1].lower()
                if ext in (".xlsx", ".xls"):
                    df.to_excel(save_path, index=False)
                else:
                    df.to_csv(save_path, index=False)
                
                self.log_message("━" * 60)
                self.log_message(f"✓ SUCCESS! Exported {len(df)} transactions")
                self.log_message(f"📁 Saved to: {save_path}")
                self.log_message("━" * 60)
                
                messagebox.showinfo(
                    "Success", 
                    f"PDFs processed successfully!\n\n"
                    f"Transactions: {len(df)}\n"
                    f"Saved to: {os.path.basename(save_path)}"
                )
                
            except FileNotFoundError as e:
                error_msg = f"Missing dependency: {str(e)}\n\nMake sure Tabula JAR and Java are installed."
                self.log_message(f"✗ ERROR: {error_msg}")
                messagebox.showerror("Dependency Error", error_msg)
                
            except Exception as e:
                error_msg = f"Processing failed: {str(e)}"
                self.log_message(f"✗ ERROR: {error_msg}")
                messagebox.showerror("Error", error_msg)
                
            finally:
                self.pdf_paths = []
                self.update_status()
                self.is_processing = False
                self.browse_btn.config(state='normal')
                self.convert_btn.config(state='normal')
                self.clear_btn.config(state='normal')

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