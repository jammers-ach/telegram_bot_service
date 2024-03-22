#!/usr/bin/env python3
import argparse
import os
import logging
import asyncio

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        if not hasattr(self, 'name'):
            raise NotImplementedError("Bot must have a name")

        self.config = {}
        self.load_config()

        for x in ["bot_token", "chat_ids"]:
            if x not in self.config:
                raise Exception(f"Missing {x} from config")

        self.chat_ids = self.config["chat_ids"].split(",")
        self.bot_token = self.config["bot_token"]
        self._bot_init()


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

        # add handler for all the commands

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
        self.send_message(self.chat_ids[0], f"{self.name} is starting up")

    def send_message(self, chat_id, message):
        '''Sends :message: to :chat_id:'''
        assert chat_id in self.chat_ids, "unauthorised chat id"
        self.application.create_task(self.application.bot.send_message(chat_id=chat_id, text=message))


    async def _msghandle(self, update, context):
        logger.info("Got message: %s", update.message.text)
        await self.handle_update(update)

    async def handle_update(self, update):
        '''handles an update (i.e. a new message) coming into the bot

        '''
        raise NotImplementedError("Bot implement handle_update")

class EchoBot(TelegramBot):
    name = "EchoBot"

    async def handle_update(self, update):
        await update.message.reply_text(f"Let me just process..")
        await asyncio.sleep(1)
        await update.message.reply_text(f"You said: {update.message.text}")


def run():
    bot = EchoBot()

    bot.start()



if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)


    run()
