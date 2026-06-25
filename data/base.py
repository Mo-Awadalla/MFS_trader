"""Base downloader interface — all data sources implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class DownloadRequest:
    symbol: str
    start_date: str  # ISO date
    end_date: str | None = None
    frequency: str = "1min"


@dataclass
class DownloadResult:
    symbol: str
    source: str
    data: pd.DataFrame
    metadata: dict[str, Any]


class BaseDownloader(ABC):
    """Abstract base for all data downloaders (Alpaca, CCXT, etc.)."""

    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def download(self, request: DownloadRequest) -> DownloadResult: ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the downloader's API credentials are configured."""
        ...
