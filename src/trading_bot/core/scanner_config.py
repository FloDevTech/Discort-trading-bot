from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_bot.core.stock_scanner import ScannerFilters


DEFAULT_ENV_PATH = ".env"


@dataclass(frozen=True)
class ScannerConfig:
    filters: ScannerFilters
    interval_minutes: float = 5.0

    @classmethod
    def load(cls, path: Path = Path(DEFAULT_ENV_PATH)) -> ScannerConfig:
        load_env_file(path)
        return cls.from_env()

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
        self.path = Path(path or os.getenv("TRADING_BOT_ENV_PATH", DEFAULT_ENV_PATH))

    def load(self) -> ScannerConfig:
        return ScannerConfig.load(self.path)

    def save(self, config: ScannerConfig) -> None:
        update_env_file(self.path, _config_to_env(config))
        load_env_file(self.path, override=True)


def load_env_file(path: str | Path = DEFAULT_ENV_PATH, *, override: bool = False) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if override or key not in os.environ:
            os.environ[key] = _parse_env_value(value.strip())


def update_env_file(path: str | Path, updates: dict[str, str]) -> None:
    env_path = Path(path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining_updates = dict(updates)
    next_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key in remaining_updates:
            next_lines.append(f"{key}={_format_env_value(remaining_updates.pop(key))}")
        else:
            next_lines.append(line)

    if remaining_updates:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        for key, value in remaining_updates.items():
            next_lines.append(f"{key}={_format_env_value(value)}")

    env_path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def _config_to_env(config: ScannerConfig) -> dict[str, str]:
    filters = config.filters
    return {
        "STOCK_SCANNER_INTERVAL_MINUTES": _format_number(config.interval_minutes),
        "STOCK_SCANNER_MAX_PRICE": _format_number(filters.max_price),
        "STOCK_SCANNER_MIN_PRICE": _format_number(filters.min_price),
        "STOCK_SCANNER_MAX_MARKET_CAP": str(filters.max_market_cap),
        "STOCK_SCANNER_MIN_MARKET_CAP": str(filters.min_market_cap),
        "STOCK_SCANNER_MIN_VOLUME": str(filters.min_volume),
        "STOCK_SCANNER_MIN_CHANGE_PERCENT": _format_number(filters.min_change_percent),
        "STOCK_SCANNER_MIN_FLOAT_ROTATION": _format_number(filters.min_float_rotation),
        "STOCK_SCANNER_LIMIT": str(filters.limit),
        "STOCK_SCANNER_MAX_SYMBOLS": str(filters.max_symbols_to_enrich),
        "STOCK_SCANNER_SYMBOLS": ",".join(filters.symbols),
    }


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _format_env_value(value: str) -> str:
    if value == "" or any(char.isspace() for char in value) or "#" in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _format_number(value: float) -> str:
    return f"{value:g}"


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
