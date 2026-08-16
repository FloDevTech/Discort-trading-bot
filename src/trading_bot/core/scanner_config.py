from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_bot.core.stock_scanner import ScannerFilters


DEFAULT_CONFIG_PATH = "scanner_config.json"


@dataclass(frozen=True)
class ScannerConfig:
    filters: ScannerFilters
    interval_minutes: float = 5.0

    @classmethod
    def load(cls, path: Path) -> ScannerConfig:
        if not path.exists():
            return cls.from_env()

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        filters = ScannerFilters.from_mapping(data.get("filters", {}))
        interval_minutes = float(data.get("interval_minutes", _env_float("STOCK_SCANNER_INTERVAL_MINUTES", 5.0)))
        return cls(filters=filters, interval_minutes=_validate_interval(interval_minutes))

    @classmethod
    def from_env(cls) -> ScannerConfig:
        return cls(
            filters=ScannerFilters.from_env().validated(),
            interval_minutes=_validate_interval(_env_float("STOCK_SCANNER_INTERVAL_MINUTES", 5.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_minutes": self.interval_minutes,
            "filters": self.filters.to_dict(),
        }


class ScannerConfigStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("STOCK_SCANNER_CONFIG_PATH", DEFAULT_CONFIG_PATH))

    def load(self) -> ScannerConfig:
        return ScannerConfig.load(self.path)

    def save(self, config: ScannerConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(config.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")


def _validate_interval(value: float) -> float:
    if value < 1:
        raise ValueError("interval_minutes debe ser al menos 1.")
    if value > 120:
        raise ValueError("interval_minutes debe ser 120 o menos.")
    return value


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
