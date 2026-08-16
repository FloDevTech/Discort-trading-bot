from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP


MONEY_QUANT = Decimal("0.01")
PRICE_QUANT = Decimal("0.0001")


class PlanValidationError(ValueError):
    """Raised when a trading plan input is invalid."""


@dataclass(frozen=True)
class TradingPhase:
    number: int
    entry: Decimal
    commission: Decimal
    stop_margin: Decimal
    risk_percent: Decimal
    risk_amount: Decimal
    shares: int
    stop_price: Decimal
    breakeven_price: Decimal
    take_profit_price: Decimal


@dataclass(frozen=True)
class TradingPlan:
    total_risk: Decimal
    target_r: Decimal
    commission: Decimal
    phases: tuple[TradingPhase, ...]

    @property
    def total_shares(self) -> int:
        return sum(phase.shares for phase in self.phases)

    @property
    def allocated_risk(self) -> Decimal:
        return sum((phase.risk_amount for phase in self.phases), Decimal("0"))

    @property
    def weighted_average_entry(self) -> Decimal:
        if self.total_shares == 0:
            return Decimal("0")
        total_cost = sum((phase.entry * phase.shares for phase in self.phases), Decimal("0"))
        return (total_cost / Decimal(self.total_shares)).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def parse_decimal_list(raw: str, field_name: str) -> list[Decimal]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise PlanValidationError(f"{field_name} no puede estar vacio.")

    parsed: list[Decimal] = []
    for value in values:
        try:
            parsed.append(Decimal(value))
        except InvalidOperation as exc:
            raise PlanValidationError(f"{field_name} contiene un numero invalido: {value}") from exc
    return parsed


def build_trading_plan(
    *,
    phases_count: int,
    total_risk: Decimal,
    target_r: Decimal,
    commission: Decimal = Decimal("0"),
    entries: list[Decimal],
    stop_margins: list[Decimal],
    risk_percentages: list[Decimal],
) -> TradingPlan:
    if phases_count <= 0:
        raise PlanValidationError("fases debe ser mayor que 0.")
    if total_risk <= 0:
        raise PlanValidationError("riesgo_total debe ser mayor que 0.")
    if target_r <= 0:
        raise PlanValidationError("r_objetivo debe ser mayor que 0.")
    if commission < 0:
        raise PlanValidationError("comision debe ser mayor o igual que 0.")

    _ensure_length("entradas", entries, phases_count)
    _ensure_length("margenes", stop_margins, phases_count)
    _ensure_length("porcentajes", risk_percentages, phases_count)

    total_percentage = sum(risk_percentages, Decimal("0"))
    if total_percentage != Decimal("100"):
        raise PlanValidationError("porcentajes debe sumar 100.")

    calculated_phases: list[TradingPhase] = []
    cumulative_cost = Decimal("0")
    cumulative_shares = 0
    for index, (entry, stop_margin, risk_percent) in enumerate(
        zip(entries, stop_margins, risk_percentages, strict=True),
        start=1,
    ):
        if entry <= 0:
            raise PlanValidationError(f"entrada de fase {index} debe ser mayor que 0.")
        if stop_margin <= 0:
            raise PlanValidationError(f"margen al stop de fase {index} debe ser mayor que 0.")
        if risk_percent <= 0:
            raise PlanValidationError(f"porcentaje de fase {index} debe ser mayor que 0.")

        risk_amount = (total_risk * risk_percent / Decimal("100")).quantize(
            MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )
        shares = int((risk_amount / stop_margin).to_integral_value(rounding=ROUND_FLOOR))
        stop_price = (entry - stop_margin).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)
        take_profit_price = (entry + (stop_margin * target_r)).quantize(
            PRICE_QUANT,
            rounding=ROUND_HALF_UP,
        )
        cumulative_cost += (entry + commission) * shares
        cumulative_shares += shares
        breakeven_price = (cumulative_cost / Decimal(cumulative_shares)).quantize(
            PRICE_QUANT,
            rounding=ROUND_HALF_UP,
        )

        calculated_phases.append(
            TradingPhase(
                number=index,
                entry=entry,
                commission=commission,
                stop_margin=stop_margin,
                risk_percent=risk_percent,
                risk_amount=risk_amount,
                shares=shares,
                stop_price=stop_price,
                breakeven_price=breakeven_price,
                take_profit_price=take_profit_price,
            )
        )

    return TradingPlan(
        total_risk=total_risk,
        target_r=target_r,
        commission=commission,
        phases=tuple(calculated_phases),
    )


def build_trading_plan_from_strings(
    *,
    phases_count: int,
    total_risk: str,
    target_r: str,
    commission: str = "0",
    entries: str,
    stop_margins: str,
    risk_percentages: str,
) -> TradingPlan:
    try:
        parsed_total_risk = Decimal(total_risk)
    except InvalidOperation as exc:
        raise PlanValidationError("riesgo_total contiene un numero invalido.") from exc
    try:
        parsed_target_r = Decimal(target_r)
    except InvalidOperation as exc:
        raise PlanValidationError("r_objetivo contiene un numero invalido.") from exc
    try:
        parsed_commission = Decimal(commission)
    except InvalidOperation as exc:
        raise PlanValidationError("comision contiene un numero invalido.") from exc

    return build_trading_plan(
        phases_count=phases_count,
        total_risk=parsed_total_risk,
        target_r=parsed_target_r,
        commission=parsed_commission,
        entries=parse_decimal_list(entries, "entradas"),
        stop_margins=parse_decimal_list(stop_margins, "margenes"),
        risk_percentages=parse_decimal_list(risk_percentages, "porcentajes"),
    )


def _ensure_length(field_name: str, values: list[Decimal], expected: int) -> None:
    if len(values) != expected:
        raise PlanValidationError(
            f"{field_name} debe tener {expected} valores, pero recibio {len(values)}."
        )
