from __future__ import annotations

from decimal import Decimal

from trading_bot.core.risk import TradingPlan
from trading_bot.core.scanner_config import ScannerConfig
from trading_bot.core.stock_scanner import StockCandidate, StockScan


def format_money(value: Decimal) -> str:
    normalized = value.normalize()
    return f"${normalized:f}"


def format_plan_for_discord(plan: TradingPlan) -> str:
    lines = [
        "📊 **PLAN AVANZADO DE TRADING**",
        "",
        f"🎯 Riesgo total: **{format_money(plan.total_risk)}**",
        f"🧱 Fases: **{len(plan.phases)}**",
        f"🎚️ Objetivo: **{plan.target_r:f}R**",
        f"💸 Comision por accion: **{format_money(plan.commission)}**",
        f"⚖️ Entrada media: **{format_money(plan.weighted_average_entry)}**",
        f"📦 Acciones totales: **{plan.total_shares}**",
        "",
    ]

    for phase in plan.phases:
        lines.extend(
            [
                f"📌 **Fase {phase.number}** ({phase.risk_percent:f}% riesgo)",
                f"• Entrada: **{format_money(phase.entry)}**",
                f"• Comision/accion: **{format_money(phase.commission)}**",
                f"• Margen al stop: **{format_money(phase.stop_margin)}**",
                f"• Stop price: **{format_money(phase.stop_price)}**",
                f"• Break-even etapa: **{format_money(phase.breakeven_price)}**",
                f"• TP {plan.target_r:f}R: **{format_money(phase.take_profit_price)}**",
                f"• Riesgo fase: **{format_money(phase.risk_amount)}**",
                f"• 🧮 Acciones: **{phase.shares}**",
                "",
            ]
        )

    return "\n".join(lines).strip()


def format_scanner_config_for_discord(config: ScannerConfig) -> str:
    filters = config.filters
    symbols = ", ".join(filters.symbols) if filters.symbols else "Finviz screener publico"
    return "\n".join(
        [
            "**Configuracion actual del scanner**",
            f"Intervalo: **{config.interval_minutes:g} min**",
            f"Precio: **${filters.min_price:g} - ${filters.max_price:g}**",
            f"Market cap: **${filters.min_market_cap:,} - ${filters.max_market_cap:,}**",
            f"Volumen minimo: **{filters.min_volume:,}**",
            f"Movimiento minimo: **{filters.min_change_percent:g}%**",
            f"Float rotation minima: **{filters.min_float_rotation:g}x**",
            f"Resultados: **{filters.limit}**",
            f"Tickers a revisar: **{filters.max_symbols_to_enrich}**",
            f"Universo: **{symbols}**",
        ]
    )


def format_stock_scan_for_discord(scan: StockScan) -> str:
    if not scan.candidates:
        return (
            "**Scanner micro-cap**\n"
            "No encontre acciones que pasen los filtros actuales.\n"
            f"Filtros: precio <= ${scan.filters.max_price:g}, volumen >= {scan.filters.min_volume:,}, "
            f"rotacion float >= {scan.filters.min_float_rotation:g}x."
        )

    return "\n".join(
        [
            f"**Scanner micro-cap | {len(scan.candidates)} acciones**",
            (
                f"Filtros: precio ${scan.filters.min_price:g}-${scan.filters.max_price:g}, "
                f"vol >= {_compact_number(scan.filters.min_volume)}, "
                f"% >= {scan.filters.min_change_percent:g}, "
                f"rot >= {scan.filters.min_float_rotation:g}x"
            ),
            "",
            "```text",
            _format_stock_scan_table(scan.candidates),
            "```",
            "No es recomendacion financiera; es una lista de vigilancia para investigacion.",
        ]
    ).strip()


def split_discord_message(content: str, limit: int = 1900) -> list[str]:
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in content.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > limit:
            chunks.append("\n".join(current).strip())
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length

    if current:
        chunks.append("\n".join(current).strip())
    return chunks


def _format_stock_scan_table(candidates: tuple[StockCandidate, ...]) -> str:
    headers = ("Symbol", "Price", "%", "Volume", "Float", "Rot")
    rows = [
        (
            candidate.symbol,
            _format_price(candidate.price),
            _format_optional_percent(candidate.change_percent),
            _compact_number(candidate.volume),
            _format_optional_shares(candidate.float_shares),
            _format_optional_ratio(candidate.float_rotation),
        )
        for candidate in candidates
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def border(left: str, separator: str, right: str) -> str:
        return left + separator.join("─" * (width + 2) for width in widths) + right

    def row(values: tuple[str, ...]) -> str:
        return "│ " + " │ ".join(
            value.rjust(widths[index]) for index, value in enumerate(values)
        ) + " │"

    lines = [
        border("┌", "┬", "┐"),
        row(headers),
        border("├", "┼", "┤"),
    ]
    lines.extend(row(values) for values in rows)
    lines.append(border("└", "┴", "┘"))
    return "\n".join(lines)


def _format_price(value: float) -> str:
    if value >= 10:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _format_optional_money(value: int | None) -> str:
    if value is None:
        return "N/D"
    return f"${_compact_number(value)}"


def _format_optional_shares(value: int | None) -> str:
    if value is None:
        return "N/D"
    return _compact_number(value)


def _format_optional_ratio(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f}x"


def _compact_number(value: int) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return str(value)


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."
