from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trading_bot.core.scanner_config import ScannerConfig, ScannerConfigStore
from trading_bot.core.stock_scanner import ScannerFilters


class ScannerConfigTests(TestCase):
    def test_saves_and_loads_scanner_config(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "scanner.json"
            store = ScannerConfigStore(path)
            config = ScannerConfig(
                filters=ScannerFilters(
                    max_price=3,
                    min_volume=1_000_000,
                    symbols=("DFSC", "MDXH"),
                ),
                interval_minutes=7,
            )

            store.save(config)
            loaded = store.load()

            self.assertEqual(loaded.interval_minutes, 7)
            self.assertEqual(loaded.filters.max_price, 3)
            self.assertEqual(loaded.filters.min_volume, 1_000_000)
            self.assertEqual(loaded.filters.symbols, ("DFSC", "MDXH"))

    def test_rejects_invalid_filter_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_price"):
            ScannerFilters(min_price=3, max_price=2).validated()
