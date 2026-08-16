from __future__ import annotations

import csv
import html
import json
import os
import re
import statistics
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from io import StringIO
from typing import Any


DEFAULT_SYMBOLS = (
    "DFSC",
    "MDXH",
    "ENSC",
    "BZAI",
    "MVST",
    "DARE",
    "VTGN",
    "KALA",
    "SURG",
    "IVP",
    "HOLO",
    "SNDL",
    "LUCY",
    "GNS",
    "BENF",
    "WTO",
    "CPOP",
    "ICU",
    "CNEY",
    "XCUR",
)


@dataclass(frozen=True)
class ScannerFilters:
    max_price: float = 2.0
    min_price: float = 0.05
    max_market_cap: int = 150_000_000
    min_market_cap: int = 1_000_000
    min_volume: int = 500_000
    min_float_rotation: float = 0.5
    min_change_percent: float = 0.0
    limit: int = 10
    max_symbols_to_enrich: int = 60
    symbols: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> ScannerFilters:
        return cls(
            max_price=_env_float("STOCK_SCANNER_MAX_PRICE", cls.max_price),
            min_price=_env_float("STOCK_SCANNER_MIN_PRICE", cls.min_price),
            max_market_cap=_env_int("STOCK_SCANNER_MAX_MARKET_CAP", cls.max_market_cap),
            min_market_cap=_env_int("STOCK_SCANNER_MIN_MARKET_CAP", cls.min_market_cap),
            min_volume=_env_int("STOCK_SCANNER_MIN_VOLUME", cls.min_volume),
            min_float_rotation=_env_float("STOCK_SCANNER_MIN_FLOAT_ROTATION", cls.min_float_rotation),
            min_change_percent=_env_float("STOCK_SCANNER_MIN_CHANGE_PERCENT", cls.min_change_percent),
            limit=_env_int("STOCK_SCANNER_LIMIT", cls.limit),
            max_symbols_to_enrich=_env_int("STOCK_SCANNER_MAX_SYMBOLS", cls.max_symbols_to_enrich),
            symbols=tuple(_symbols_from_env()),
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ScannerFilters:
        defaults = cls.from_env()
        symbols = data.get("symbols", defaults.symbols)
        if isinstance(symbols, str):
            symbols = _parse_symbols(symbols)
        return replace(
            defaults,
            max_price=float(data.get("max_price", defaults.max_price)),
            min_price=float(data.get("min_price", defaults.min_price)),
            max_market_cap=int(data.get("max_market_cap", defaults.max_market_cap)),
            min_market_cap=int(data.get("min_market_cap", defaults.min_market_cap)),
            min_volume=int(data.get("min_volume", defaults.min_volume)),
            min_float_rotation=float(data.get("min_float_rotation", defaults.min_float_rotation)),
            min_change_percent=float(data.get("min_change_percent", defaults.min_change_percent)),
            limit=int(data.get("limit", defaults.limit)),
            max_symbols_to_enrich=int(data.get("max_symbols_to_enrich", defaults.max_symbols_to_enrich)),
            symbols=tuple(str(symbol).upper() for symbol in symbols if str(symbol).strip()),
        ).validated()

    def updated(self, **changes: Any) -> ScannerFilters:
        return replace(self, **changes).validated()

    def validated(self) -> ScannerFilters:
        if self.min_price <= 0:
            raise ValueError("min_price debe ser mayor que 0.")
        if self.max_price <= 0:
            raise ValueError("max_price debe ser mayor que 0.")
        if self.min_price > self.max_price:
            raise ValueError("min_price no puede ser mayor que max_price.")
        if self.min_market_cap < 0 or self.max_market_cap < 0:
            raise ValueError("market cap no puede ser negativo.")
        if self.min_market_cap > self.max_market_cap:
            raise ValueError("min_market_cap no puede ser mayor que max_market_cap.")
        if self.min_volume < 0:
            raise ValueError("min_volume no puede ser negativo.")
        if self.min_float_rotation < 0:
            raise ValueError("min_float_rotation no puede ser negativo.")
        if self.min_change_percent < -100:
            raise ValueError("min_change_percent no puede ser menor que -100.")
        if self.limit < 1 or self.limit > 25:
            raise ValueError("limit debe estar entre 1 y 25.")
        if self.max_symbols_to_enrich < 1 or self.max_symbols_to_enrich > 300:
            raise ValueError("max_symbols_to_enrich debe estar entre 1 y 300.")
        return self

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["symbols"] = list(self.symbols)
        return data


@dataclass(frozen=True)
class StockCandidate:
    symbol: str
    name: str
    price: float
    change_percent: float | None
    market_cap: int | None
    float_shares: int | None
    volume: int
    average_volume: int | None
    float_rotation: float | None
    volume_relative: float | None
    market_sentiment: str
    catalyst: str
    score: float


@dataclass(frozen=True)
class StockScan:
    generated_at: datetime
    filters: ScannerFilters
    candidates: tuple[StockCandidate, ...]
    source_note: str


class FinvizSymbolSource:
    def __init__(self, timeout_seconds: int = 12) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_symbols(self, filters: ScannerFilters) -> list[str]:
        custom_symbols = list(filters.symbols) or _symbols_from_env()
        if custom_symbols:
            return custom_symbols[: filters.max_symbols_to_enrich]

        symbols = self._fetch_public_screener_symbols(filters)
        if symbols:
            return symbols[: filters.max_symbols_to_enrich]

        symbols = self._fetch_export_symbols(filters)
        if symbols:
            return symbols[: filters.max_symbols_to_enrich]

        return list(DEFAULT_SYMBOLS[: filters.max_symbols_to_enrich])

    def _fetch_public_screener_symbols(self, filters: ScannerFilters) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        page_start = 1

        while len(symbols) < filters.max_symbols_to_enrich:
            params = {
                "v": "111",
                "f": f"sh_price_u{filters.max_price},sh_avgvol_o500,sh_curvol_o500",
                "o": "-volume",
                "r": str(page_start),
            }
            url = f"https://finviz.com/screener.ashx?{urllib.parse.urlencode(params)}"
            try:
                response = _http_get_text(url, self.timeout_seconds)
            except OSError:
                break

            page_symbols = _parse_finviz_screener_symbols(response)
            if not page_symbols:
                break

            for symbol in page_symbols:
                if symbol not in seen:
                    seen.add(symbol)
                    symbols.append(symbol)
                if len(symbols) >= filters.max_symbols_to_enrich:
                    break

            page_start += 20

        return symbols

    def _fetch_export_symbols(self, filters: ScannerFilters) -> list[str]:
        params = {
            "v": "111",
            "f": f"sh_price_u{filters.max_price},sh_avgvol_o500,sh_curvol_o500",
            "o": "-volume",
        }
        url = f"https://finviz.com/export.ashx?{urllib.parse.urlencode(params)}"
        try:
            response = _http_get_text(url, self.timeout_seconds)
        except OSError:
            return list(DEFAULT_SYMBOLS[: filters.max_symbols_to_enrich])
        if "<html" in response[:500].lower() or "finviz elite" in response[:1000].lower():
            return list(DEFAULT_SYMBOLS[: filters.max_symbols_to_enrich])

        symbols: list[str] = []
        for row in csv.DictReader(StringIO(response)):
            symbol = (row.get("Ticker") or "").strip().upper()
            if symbol and symbol.isascii():
                symbols.append(symbol)
            if len(symbols) >= filters.max_symbols_to_enrich:
                break

        return symbols


class FinvizQuoteClient:
    def __init__(self, timeout_seconds: int = 12) -> None:
        self.timeout_seconds = timeout_seconds
        self.yahoo_fallback = YahooChartClient(timeout_seconds=timeout_seconds)

    def fetch_quote(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://finviz.com/quote.ashx?t={urllib.parse.quote(symbol)}&p=d"
        try:
            page = _http_get_text(url, self.timeout_seconds)
        except OSError:
            return self.yahoo_fallback.fetch_quote(symbol)

        quote = {
            "symbol": symbol,
            "shortName": _parse_finviz_title(page, symbol),
            "regularMarketPrice": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Price")),
            "regularMarketChangePercent": _parse_number_with_suffix(
                _parse_finviz_snapshot_value(page, "Change %")
                or _parse_finviz_snapshot_value(page, "Change")
            ),
            "marketCap": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Market Cap")),
            "regularMarketVolume": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Volume")),
            "averageDailyVolume3Month": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Avg Volume")),
            "floatShares": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Shs Float")),
            "sharesOutstanding": _parse_number_with_suffix(_parse_finviz_snapshot_value(page, "Shs Outstand")),
        }

        fallback_needed = quote["regularMarketPrice"] is None or quote["regularMarketVolume"] is None
        if fallback_needed:
            quote.update(self.yahoo_fallback.fetch_quote(symbol) or {})

        return quote if quote.get("regularMarketPrice") is not None and quote.get("regularMarketVolume") is not None else None


class YahooChartClient:
    def __init__(self, timeout_seconds: int = 12) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_quote(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1m"
        try:
            payload = _http_get_json(url, self.timeout_seconds)
        except OSError:
            return None

        results = payload.get("chart", {}).get("result") or []
        if not results:
            return None

        meta = results[0].get("meta", {})
        return {
            "symbol": symbol,
            "shortName": symbol,
            "regularMarketPrice": meta.get("regularMarketPrice") or meta.get("previousClose"),
            "regularMarketChangePercent": _calculate_yahoo_change_percent(meta),
            "regularMarketVolume": meta.get("regularMarketVolume"),
        }


class YahooFinanceClient:
    def __init__(self, timeout_seconds: int = 12) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_quote(self, symbol: str) -> dict[str, Any] | None:
        params = urllib.parse.urlencode({"symbols": symbol})
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?{params}"
        try:
            payload = _http_get_json(url, self.timeout_seconds)
        except OSError:
            return None

        results = payload.get("quoteResponse", {}).get("result", [])
        if not results:
            return None

        quote = dict(results[0])
        quote.update(self._fetch_quote_summary(symbol))
        return quote

    def _fetch_quote_summary(self, symbol: str) -> dict[str, Any]:
        modules = "defaultKeyStatistics,summaryDetail,financialData,recommendationTrend"
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(symbol)}?modules={modules}"
        try:
            payload = _http_get_json(url, self.timeout_seconds)
        except OSError:
            return {}

        results = payload.get("quoteSummary", {}).get("result") or []
        if not results:
            return {}

        flat: dict[str, Any] = {}
        for section in results[0].values():
            if isinstance(section, dict):
                flat.update(section)
        return flat


class StockScanner:
    def __init__(
        self,
        *,
        symbol_source: FinvizSymbolSource | None = None,
        finance_client: YahooFinanceClient | None = None,
        filters: ScannerFilters | None = None,
    ) -> None:
        self.symbol_source = symbol_source or FinvizSymbolSource()
        self.finance_client = finance_client or FinvizQuoteClient()
        self.filters = filters or ScannerFilters.from_env()

    def scan(self) -> StockScan:
        symbols = self.symbol_source.fetch_symbols(self.filters)
        candidates = []
        for symbol in symbols[: self.filters.max_symbols_to_enrich]:
            quote = self.finance_client.fetch_quote(symbol)
            candidate = build_candidate(symbol, quote or {})
            if candidate and candidate_passes_filters(candidate, self.filters):
                candidates.append(candidate)

        ranked = tuple(sorted(candidates, key=lambda item: item.score, reverse=True)[: self.filters.limit])
        return StockScan(
            generated_at=datetime.now(timezone.utc),
            filters=self.filters,
            candidates=ranked,
            source_note="Simbolos y datos: Finviz screener/quote. Fallback limitado: Yahoo chart.",
        )


def build_candidate(symbol: str, quote: dict[str, Any]) -> StockCandidate | None:
    price = _number(quote.get("regularMarketPrice") or quote.get("currentPrice"))
    volume = _int_number(quote.get("regularMarketVolume") or quote.get("volume"))
    if price is None or volume is None:
        return None

    market_cap = _int_number(quote.get("marketCap"))
    change_percent = _number(quote.get("regularMarketChangePercent"))
    float_shares = _int_number(quote.get("floatShares") or quote.get("sharesOutstanding"))
    average_volume = _int_number(quote.get("averageDailyVolume3Month") or quote.get("averageVolume"))
    float_rotation = volume / float_shares if float_shares and float_shares > 0 else None
    volume_relative = volume / average_volume if average_volume and average_volume > 0 else None
    sentiment = _sentiment_from_quote(quote, volume_relative)
    catalyst = _catalyst_from_quote(float_rotation, volume_relative)

    score_parts = [
        min(float_rotation or 0, 20) * 5,
        min(volume_relative or 0, 20) * 3,
        max(0, 2 - price) * 5,
    ]
    if market_cap:
        score_parts.append(max(0, 150_000_000 - market_cap) / 10_000_000)

    return StockCandidate(
        symbol=symbol.upper(),
        name=str(quote.get("shortName") or quote.get("longName") or symbol.upper()),
        price=price,
        change_percent=change_percent,
        market_cap=market_cap,
        float_shares=float_shares,
        volume=volume,
        average_volume=average_volume,
        float_rotation=float_rotation,
        volume_relative=volume_relative,
        market_sentiment=sentiment,
        catalyst=catalyst,
        score=sum(score_parts),
    )


def candidate_passes_filters(candidate: StockCandidate, filters: ScannerFilters) -> bool:
    if candidate.price < filters.min_price or candidate.price > filters.max_price:
        return False
    if candidate.volume < filters.min_volume:
        return False
    if candidate.market_cap is not None and candidate.market_cap < filters.min_market_cap:
        return False
    if candidate.market_cap is not None and candidate.market_cap > filters.max_market_cap:
        return False
    if filters.min_float_rotation > 0 and candidate.float_rotation is None:
        return False
    if candidate.float_rotation is not None and candidate.float_rotation < filters.min_float_rotation:
        return False
    if filters.min_change_percent != 0 and candidate.change_percent is None:
        return False
    if candidate.change_percent is not None and candidate.change_percent < filters.min_change_percent:
        return False
    return True


def _sentiment_from_quote(quote: dict[str, Any], volume_relative: float | None) -> str:
    recommendation = _number(quote.get("recommendationMean"))
    target_mean = _number(quote.get("targetMeanPrice"))
    price = _number(quote.get("regularMarketPrice") or quote.get("currentPrice"))
    signals: list[float] = []

    if recommendation:
        signals.append(3 - recommendation)
    if target_mean and price:
        signals.append((target_mean / price) - 1)
    if volume_relative:
        signals.append(min(volume_relative, 5) / 5)

    if not signals:
        return "sin datos suficientes"

    score = statistics.mean(signals)
    if score >= 0.75:
        return "alcista"
    if score >= 0.25:
        return "positivo"
    if score <= -0.25:
        return "debil"
    return "neutral"


def _catalyst_from_quote(float_rotation: float | None, volume_relative: float | None) -> str:
    if float_rotation and float_rotation >= 10:
        return "float rotando mas de 10x en la sesion"
    if float_rotation and float_rotation >= 3:
        return "alta rotacion del float"
    if volume_relative and volume_relative >= 5:
        return "volumen muy por encima del promedio"
    if volume_relative and volume_relative >= 2:
        return "volumen relativo elevado"
    return "setup de bajo precio con volumen activo"


def _http_get_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    return json.loads(_http_get_text(url, timeout_seconds))


def _http_get_text(url: str, timeout_seconds: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DiscordTradingTools/0.1",
            "Accept": "application/json,text/csv,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def _parse_finviz_snapshot_value(page: str, label: str) -> str | None:
    pattern = (
        r'<div class="snapshot-td-label">(?:<a[^>]*>)?'
        + re.escape(label)
        + r"(?:</a>)?</div></td><td[^>]*>"
        + r'<div class="snapshot-td-content"><b>(.*?)</b>'
    )
    match = re.search(pattern, page, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    value = re.sub(r"<[^>]+>", "", match.group(1))
    return html.unescape(value).strip()


def _parse_finviz_screener_symbols(page: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_symbol in re.findall(r'href="stock\?t=([A-Z.]{1,8})[&"]', page):
        symbol = raw_symbol.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def _parse_finviz_title(page: str, symbol: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if not match:
        return symbol.upper()

    title = html.unescape(match.group(1)).strip()
    prefix = f"{symbol.upper()} - "
    suffix = " Stock Price and Quote"
    if title.upper().startswith(prefix):
        title = title[len(prefix) :]
    if title.endswith(suffix):
        title = title[: -len(suffix)]
    return title.strip() or symbol.upper()


def _parse_number_with_suffix(raw: str | None) -> float | None:
    if not raw:
        return None

    cleaned = raw.strip().replace(",", "").replace("%", "")
    if cleaned in {"-", ""}:
        return None

    multiplier = 1.0
    suffix = cleaned[-1:].upper()
    if suffix == "K":
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif suffix == "M":
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif suffix == "B":
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]
    elif suffix == "T":
        multiplier = 1_000_000_000_000
        cleaned = cleaned[:-1]

    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _calculate_yahoo_change_percent(meta: dict[str, Any]) -> float | None:
    price = _number(meta.get("regularMarketPrice"))
    previous_close = _number(meta.get("previousClose"))
    if price is None or previous_close is None or previous_close == 0:
        return None
    return ((price - previous_close) / previous_close) * 100


def _symbols_from_env() -> list[str]:
    raw = os.getenv("STOCK_SCANNER_SYMBOLS", "")
    return _parse_symbols(raw)


def _parse_symbols(raw: str) -> list[str]:
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _number(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("raw")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_number(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number)
