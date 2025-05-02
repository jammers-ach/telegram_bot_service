import argparse
import os
import logging
import asyncio
import functools

from telegram import ForceReply, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

class TelegramBot:

    # Set to true if only authorized chats can talk
    only_authorized = True
    command_registry = []
    command_usage = []

    @classmethod
    def command(cls, f_py=None, args=""):
        """Marks a method as having a command, so it can be called with /foo

        docstring gets added to the bots /help string, args in the decorator
        can be used to determine the helpstring:

        for example:
        @TelegramBot.command(args="<BAR>")
        async def foo(self, update):
            '''foos the bar'''
            bar = update.message.text
            await update.message.reply_text(f"Ok, I'm fooing your {bar}")

        """
        print(f"command registered {f_py}: {args}")
        assert callable(f_py) or f_py is None
        def _decorator(func):
            cls.command_registry.append(func)
            cls.command_usage.append(f"`{func.__name__} {args}` {func.__doc__}")
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return _decorator(f_py) if callable(f_py) else _decorator


    def __init__(self):
        if not hasattr(self, 'name'):
            raise NotImplementedError("Bot must have a name")

        if not hasattr(self, 'description'):
            raise NotImplementedError("Bot must have a description")

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
                self._lastupdate = update # memoize the last update
                await foo(self, update)

            return msg
        for command in self.command_registry:
            logger.info("Found command %s", command.__name__)
            self.application.add_handler(CommandHandler(command.__name__, call(command)))

        # add an alias for the start command as calling the help string
        # /start is automatically sent when you add a bot on telegram
        async def start(update, context):
            await self.help(update)
        self.application.add_handler(CommandHandler("start", start))

        # add handler for non command messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._msghandle))
        self.application.add_handler(MessageHandler(filters.VOICE, self._voicehandle))

    def start(self):
        logger.info("starting bot")
        self.application.post_init = self.__post_startup
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


    async def help(self, update):
        """Prints out the helptext"""

        helptext = f"{self.name}\n\n"
        helptext += self.description
        helptext += "\n\n"

        helptext += "\n".join(self.command_usage)
        await update.message.reply_markdown(helptext)



    async def __post_startup(self, _):
        await self.post_startup()

    async def post_startup(self):
        '''called when this bot has just started up'''
        await self._send_message(self.chat_ids[0], f"{self.name} is starting up")

    async def _send_message(self, chat_id, message, markdown=False):
        '''Sends :message: to :chat_id:'''
        assert chat_id in self.chat_ids, "unauthorised chat id"
        async def job(context):
            if markdown:
                await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)
            else:
                await context.bot.send_message(chat_id=chat_id, text=message)

        self.application.job_queue.run_once(job, 0)


    async def _msghandle(self, update, context):
        self._authorized_check(update)
        logger.info("Got message: %s", update.message.text)
        await self.handle_update(update)

    async def _voicehandle(self, update, context):
        self._authorized_check(update)
        logger.info("Got voice: %s", update.message.text)
        try:
            await self.handle_voice(update)
        except NotImplementedError as e:
            await update.message.reply_text("This bot cannot process voice")

    async def handle_update(self, update):
        '''handles an update (i.e. a new message) coming into the bot

        '''
        raise NotImplementedError("Bot implement handle_update")

    async def handle_voice(self, update):
        '''handles an voice message coming into the bot

        the file can be downloaded like this
        new_file = await update.message.effective_attachment.get_file()
        await new_file.download_to_drive('/tmp/foo.ogg')
        '''
        raise NotImplementedError("Bot implement handle_voice")

    def _authorized_check(self, update):
        if self.only_authorized:
            if update.message.chat_id not in self.chat_ids:
                raise PermissionError(f"{update.message.chat_id} not in authorised chat list")


    async def single_send_msg(self, message, chat_ids=None, markdown=False):
        '''starts the bot, sends a sync message to the first contact in the list
        or a list of contacts

        then stops the bot'''
        if not chat_ids:
            chat_ids = [self.chat_ids[0]]

        async def send_msg():
            for chat_id in chat_ids:
                await self._send_message(chat_id, message, markdown=markdown)

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


# hack because we want the help method to be a command.
TelegramBot.help = TelegramBot.command(TelegramBot.help)
