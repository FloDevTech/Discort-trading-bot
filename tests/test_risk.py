from decimal import Decimal
from unittest import TestCase

from trading_bot.core.risk import PlanValidationError, build_trading_plan_from_strings


class TradingPlanTests(TestCase):
    def test_builds_three_phase_plan(self) -> None:
        plan = build_trading_plan_from_strings(
            phases_count=3,
            total_risk="5",
            target_r="3",
            entries="0.52,0.53,0.54",
            stop_margins="0.05,0.05,0.05",
            risk_percentages="25,35,40",
        )

        self.assertEqual(plan.total_risk, Decimal("5"))
        self.assertEqual(plan.commission, Decimal("0"))
        self.assertEqual([phase.risk_amount for phase in plan.phases], [Decimal("1.25"), Decimal("1.75"), Decimal("2.00")])
        self.assertEqual([phase.shares for phase in plan.phases], [25, 35, 40])
        self.assertEqual([phase.stop_price for phase in plan.phases], [Decimal("0.4700"), Decimal("0.4800"), Decimal("0.4900")])
        self.assertEqual([phase.breakeven_price for phase in plan.phases], [Decimal("0.5200"), Decimal("0.5258"), Decimal("0.5315")])
        self.assertEqual([phase.take_profit_price for phase in plan.phases], [Decimal("0.6700"), Decimal("0.6800"), Decimal("0.6900")])
        self.assertEqual(plan.total_shares, 100)
        self.assertEqual(plan.weighted_average_entry, Decimal("0.5315"))

    def test_commission_is_added_to_each_phase_breakeven(self) -> None:
        plan = build_trading_plan_from_strings(
            phases_count=3,
            total_risk="5",
            target_r="3",
            commission="0.005",
            entries="0.52,0.53,0.54",
            stop_margins="0.05,0.05,0.05",
            risk_percentages="25,35,40",
        )

        self.assertEqual(plan.commission, Decimal("0.005"))
        self.assertEqual(
            [phase.breakeven_price for phase in plan.phases],
            [Decimal("0.5250"), Decimal("0.5308"), Decimal("0.5365")],
        )

    def test_commission_cannot_be_negative(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "comision"):
            build_trading_plan_from_strings(
                phases_count=1,
                total_risk="5",
                target_r="3",
                commission="-0.01",
                entries="0.52",
                stop_margins="0.05",
                risk_percentages="100",
            )

    def test_percentages_must_sum_to_100(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "sumar 100"):
            build_trading_plan_from_strings(
                phases_count=3,
                total_risk="5",
                target_r="3",
                entries="0.52,0.53,0.54",
                stop_margins="0.05,0.05,0.05",
                risk_percentages="25,35,30",
            )

    def test_values_must_match_phase_count(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "entradas"):
            build_trading_plan_from_strings(
                phases_count=3,
                total_risk="5",
                target_r="3",
                entries="0.52,0.53",
                stop_margins="0.05,0.05,0.05",
                risk_percentages="25,35,40",
            )
