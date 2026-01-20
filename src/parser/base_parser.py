# parser/base_parser.py

from abc import ABC, abstractmethod
from typing import Callable
import pandas as pd


class BaseParser(ABC):
    """Abstract base class for bank-specific PDF parsers."""

    @abstractmethod
    def can_parse(self, pdf_text: str) -> bool:
        """Return True if the parser can handle this PDF."""
        pass

    @abstractmethod
    def parse_pdf(self, pdf_path: str, progress_callback=None) -> pd.DataFrame:
        """Must return a DataFrame of parsed PDF contents."""
        pass
