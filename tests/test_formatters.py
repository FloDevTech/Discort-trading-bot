from unittest import TestCase

from trading_bot.formatters import split_discord_message


class DiscordMessageSplitterTests(TestCase):
    def test_splits_long_messages_under_limit(self) -> None:
        content = "\n".join(f"line {index} " + ("x" * 100) for index in range(30))

        chunks = split_discord_message(content, limit=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))
