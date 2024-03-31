#!/usr/bin/env python3
import argparse
import os
import logging
import asyncio

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

class TelegramBot:

    only_authorized = True
    command_registry = []

    @classmethod
    def command(cls, foo):
        '''decorator to indicate this a command'''
        cls.command_registry.append(foo)
        return foo

    def __init__(self):
        if not hasattr(self, 'name'):
            raise NotImplementedError("Bot must have a name")

        self.config = {}
        self.load_config()

        for x in ["bot_token", "chat_ids"]:
            if x not in self.config:
                raise Exception(f"Missing {x} from config")

        self.chat_ids = [int(i.strip()) for i in self.config["chat_ids"].split(",")]
        self.bot_token = self.config["bot_token"]
        self._bot_init()

        self.commands = []


    def load_config(self):
        '''loads the bots config from ~/.config/tgbot-{botname}/config

        the config file is a simple text file with key=value'''
        config_dir = os.path.expanduser(f"~/.config/tgbot-{self.name.lower()}")
        config_file = os.path.join(config_dir, "config")

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        logger.info("load config file %s", config_file)
        with open(config_file, "r") as file:
            for line in file:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    self.config[key.strip()] = value.strip()


    def _bot_init(self):
        logger.info("building the telegram bot")
        # initilise the application
        self.application = Application.builder().token(self.bot_token).build()
        global command

        # each command in the command registry can't directly be passed
        # because it doesn't have a reference to self. So we wrap it in
        # a funciton that does
        def call(foo):
            async def msg(update, context):
                # for some reason we're not propogating the message context
                # for now
                await foo(self, update)

            return msg

        for command in self.command_registry:
            logger.info("Found command %s", command.__name__)
            self.application.add_handler(CommandHandler(command.__name__, call(command)))

        # add handler for non command messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._msghandle))

    def start(self):
        logger.info("starting bot")
        self.application.post_init = self.__post_startup
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


    async def __post_startup(self, _):
        await self.post_startup()

    async def post_startup(self):
        '''called when this bot has just started up'''
        self._send_message(self.chat_ids[0], f"{self.name} is starting up")

    def _send_message(self, chat_id, message):
        '''Sends :message: to :chat_id:'''
        assert chat_id in self.chat_ids, "unauthorised chat id"
        self.application.create_task(self.application.bot.send_message(chat_id=chat_id, text=message))


    async def _msghandle(self, update, context):
        self._authorized_check(update)
        logger.info("Got message: %s", update.message.text)
        await self.handle_update(update)

    async def handle_update(self, update):
        '''handles an update (i.e. a new message) coming into the bot

        '''
        raise NotImplementedError("Bot implement handle_update")


    def _authorized_check(self, update):
        if self.only_authorized:
            if update.message.chat_id not in self.chat_ids:
                raise PermissionError(f"{update.message.chat_id} not in authorised chat list")
        else:
            return False


    async def single_send_msg(self, message, chat_id=None):
        '''starts the bot, sends a sync message to the first contact in the list

        then stops the bot'''
        if not chat_id:
            chat_id = self.chat_ids[0]

        def send_msg():
            self._send_message(self.chat_ids[0], message)

        await self._single_do(send_msg)



    async def _single_do(self, function):
        '''starts the bot, then calls a function, then stops the bot'''
        await self.application.initialize()
        await self.application.start()
        function()
        await self.application.stop()
        await self.application.shutdown()





class EchoBot(TelegramBot):
    '''Simple telegram bot that echos what you've just said,

    after it thinks for a bit.

    It has two commands:

        /help to display help text
        /change <new text> to change the thinking text'''
    name = "EchoBot"

    thinking_text = "Let me just process.."

    async def handle_update(self, update):
        await update.message.reply_text(self.thinking_text)
        await asyncio.sleep(1)
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
