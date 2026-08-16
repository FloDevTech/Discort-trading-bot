from unittest import TestCase

from trading_bot.core.risk import build_trading_plan_from_strings
from trading_bot.formatters import format_plan_for_discord, split_discord_message


class DiscordMessageSplitterTests(TestCase):
    def test_splits_long_messages_under_limit(self) -> None:
        content = "\n".join(f"line {index} " + ("x" * 100) for index in range(30))

        chunks = split_discord_message(content, limit=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))


class TradingPlanFormatterTests(TestCase):
    def test_includes_average_take_profit_in_summary(self) -> None:
        plan = build_trading_plan_from_strings(
            phases_count=3,
            total_risk="5",
            target_r="3",
            entries="0.52,0.53,0.54",
            stop_margins="0.05,0.05,0.05",
            risk_percentages="25,35,40",
        )

        message = format_plan_for_discord(plan)

        self.assertIn("TP medio 3R: **$15.5315**", message)
