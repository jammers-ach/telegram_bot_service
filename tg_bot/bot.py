import argparse
import os
import logging
import asyncio

from telegram import ForceReply, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

class TelegramBot:

    # Set to true if only authorized chats can talk
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


    @property
    def config_dir(self):
        return os.path.expanduser(f"~/.config/tgbot-{self.name.lower()}")


    def load_config(self):
        '''loads the bots config from ~/.config/tgbot-{botname}/config

        the config file is a simple text file with key=value'''
        config_file = os.path.join(self.config_dir, "config")

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
        await self._send_message(self.chat_ids[0], f"{self.name} is starting up")

    async def _send_message(self, chat_id, message):
        '''Sends :message: to :chat_id:'''
        assert chat_id in self.chat_ids, "unauthorised chat id"
        async def job(context):
            await context.bot.send_message(chat_id=chat_id, text=message)
        self.application.job_queue.run_once(job, 0)


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


    async def single_send_msg(self, message, chat_ids=None):
        '''starts the bot, sends a sync message to the first contact in the list
        or a list of contacts

        then stops the bot'''
        if not chat_ids:
            chat_ids = [self.chat_ids[0]]

        async def send_msg():
            for chat_id in chat_ids:
                await self._send_message(chat_id, message)

        await self._single_do(send_msg)



    async def _single_do(self, function):
        '''starts the bot, then calls a function, then stops the bot'''
        self._bot_init() #HACK - reinitilise the bot's queues since we're not doing it in it's own handler
        await self.application.initialize()
        await self.application.start()
        await function()
        await self.application.stop()
        await self.application.shutdown()


    async def typing(self, update):
        '''sets the status to `typing`'''
        chat_id = update.message.chat_id
        await self.application.bot.send_chat_action(chat_id, ChatAction.TYPING)


