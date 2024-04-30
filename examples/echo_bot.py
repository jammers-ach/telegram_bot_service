#!/usr/bin/env python3
'''
EchoBot: A telegram bot that echos what you say
'''
import argparse
import logging
import asyncio

from tg_bot.bot import TelegramBot

logger = logging.getLogger(__name__)


class EchoBot(TelegramBot):
    '''Simple telegram bot that echos what you've just said,

    after it thinks for a bit.

    It has two commands:

        /help to display help text
        /change <new text> to change the thinking text'''
    name = "EchoBot"

    thinking_text = "Let me just process.."
    wait_time = 3 #seconds

    async def handle_update(self, update):
        await update.message.reply_text(self.thinking_text)
        await self.typing(update)
        await asyncio.sleep(self.wait_time)
        await update.message.reply_text(f"You said: {update.message.text}")


    @TelegramBot.command
    async def help(self, update):

        helptext='''Simple telegram bot that echos what you've just said,

    after it thinks for a bit.

    It has two commands:

        /help to display help text
        /change <new text> to change the thinking text'''
        await update.message.reply_text(helptext)

    @TelegramBot.command
    async def change(self, update):
        self.thinking_text = update.message.text.replace("/change ","")
        await update.message.reply_text(f"Ok I will now set the thinking text to: {self.thinking_text}")





def run():
    parser = argparse.ArgumentParser(description="Echo bot, a pytho bot which echos back all of the text you send")
    parser.add_argument('--send', metavar='MESSAGE', help='Send a message')

    args = parser.parse_args()

    if args.send:
        bot = EchoBot()
        asyncio.run(bot.single_send_msg(args.send))
    else:
        bot = EchoBot()
        bot.start()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)


    run()
