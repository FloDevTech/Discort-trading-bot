from unittest import TestCase

from trading_bot.core.stock_scanner import (
    ScannerFilters,
    StockScanner,
    build_candidate,
    candidate_passes_filters,
)


class StaticSymbolSource:
    def fetch_symbols(self, filters: ScannerFilters) -> list[str]:
        return ["AAA", "BBB", "CCC"]


class StaticFinanceClient:
    def fetch_quote(self, symbol: str) -> dict:
        return {
            "AAA": {
                "shortName": "Alpha",
                "regularMarketPrice": 1.20,
                "regularMarketChangePercent": 12.5,
                "marketCap": 10_000_000,
                "regularMarketVolume": 12_000_000,
                "averageDailyVolume3Month": 2_000_000,
                "floatShares": 1_000_000,
            },
            "BBB": {
                "shortName": "Beta",
                "regularMarketPrice": 1.50,
                "regularMarketChangePercent": 8.2,
                "marketCap": 20_000_000,
                "regularMarketVolume": 800_000,
                "averageDailyVolume3Month": 2_000_000,
                "floatShares": 2_000_000,
            },
            "CCC": {
                "shortName": "Gamma",
                "regularMarketPrice": 3.00,
                "regularMarketChangePercent": 4.1,
                "marketCap": 25_000_000,
                "regularMarketVolume": 15_000_000,
                "averageDailyVolume3Month": 3_000_000,
                "floatShares": 1_500_000,
            },
        }[symbol]


class StockScannerTests(TestCase):
    def test_build_candidate_calculates_float_rotation(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 1.0,
                "regularMarketChangePercent": 25,
                "regularMarketVolume": 10_000_000,
                "averageDailyVolume3Month": 2_000_000,
                "floatShares": 1_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.float_rotation, 10)
        self.assertEqual(candidate.volume_relative, 5)
        self.assertEqual(candidate.change_percent, 25)

    def test_filters_reject_high_price(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 2.50,
                "regularMarketVolume": 10_000_000,
                "floatShares": 1_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertFalse(candidate_passes_filters(candidate, ScannerFilters(max_price=2.0)))

    def test_filters_reject_missing_float_when_rotation_filter_is_active(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 1.0,
                "regularMarketVolume": 10_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertIsNone(candidate.float_rotation)
        self.assertFalse(
            candidate_passes_filters(candidate, ScannerFilters(min_float_rotation=0.5))
        )

    def test_filters_allow_missing_float_when_rotation_filter_is_disabled(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 1.0,
                "regularMarketVolume": 10_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertTrue(
            candidate_passes_filters(candidate, ScannerFilters(min_float_rotation=0))
        )

    def test_filters_reject_low_change_percent(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 1.0,
                "regularMarketChangePercent": 12.5,
                "regularMarketVolume": 10_000_000,
                "floatShares": 1_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertFalse(
            candidate_passes_filters(candidate, ScannerFilters(min_change_percent=50))
        )

    def test_filters_reject_missing_change_when_change_filter_is_active(self) -> None:
        candidate = build_candidate(
            "TEST",
            {
                "regularMarketPrice": 1.0,
                "regularMarketVolume": 10_000_000,
                "floatShares": 1_000_000,
            },
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertFalse(
            candidate_passes_filters(candidate, ScannerFilters(min_change_percent=1))
        )

    def test_scan_ranks_candidates(self) -> None:
        scanner = StockScanner(
            symbol_source=StaticSymbolSource(),
            finance_client=StaticFinanceClient(),
            filters=ScannerFilters(limit=2, min_float_rotation=0.1),
        )

        scan = scanner.scan()

        self.assertEqual([candidate.symbol for candidate in scan.candidates], ["AAA", "BBB"])
