#!/usr/bin/env python3
'''
EchoBot: A telegram bot that echos what you say
'''
import argparse
import logging
import asyncio
import os

from tg_bot.bot import TelegramBot

logger = logging.getLogger(__name__)


class EchoBot(TelegramBot):
    '''Simple telegram bot that echos what you've just said'''
    name = "EchoBot"
    description = """Simple telegram bot that echos what you've just said
after it thinks for a bit"""

    thinking_text = "Let me just process.."
    wait_time = 3 #seconds

    async def handle_update(self, update):
        await update.message.reply_text(self.thinking_text)
        await self.typing(update)
        await asyncio.sleep(self.wait_time)
        await self._send_message(f"You said: {update.message.text}")


    @TelegramBot.command(args="<NEW STRING>")
    async def change(self, update):
        """change the input string"""
        self.thinking_text = update.message.text.replace("/change ","")
        await self._send_message(f"Ok I will now set the thinking text to: {self.thinking_text}")

    @TelegramBot.command
    async def self_test(self, update):
        """Runs through the bots selftest"""
        await self._send_message("Sending text")
        await self._send_markdown("Sending `Markdown`")

        file_path = os.path.join(self.config_dir, "example.png")
        if os.path.exists(file_path):
            await self._send_image(file_path)
        else:
            await self._send_markdown(f"no image in `{file_path}`")


    async def send_message(self, message):
        """Sends the message"""
        await self._send_markdown(message)


def run():
    parser = argparse.ArgumentParser(description="Echo bot, a pytho bot which echos back all of the text you send")
    parser.add_argument('--send', metavar='MESSAGE', help='Send a message')

    args = parser.parse_args()

    if args.send:
        bot = EchoBot()
        async def do_send():
            await bot.send_message(f"Send from commandline {args.send}")
            await bot.batch_send()

        asyncio.run(do_send())
    else:
        bot = EchoBot()
        bot.start()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    run()
