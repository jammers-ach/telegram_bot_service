from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)


class TelegramBot:
    """Convenience base class for small python-telegram-bot applications.

    Subclasses provide ``name`` and ``description`` and override the handler
    hooks they need. Configuration is read from
    ``~/.config/tgbot-{name}/config`` as simple ``key=value`` pairs.
    """

    only_authorized = True
    media_group_delay = 0.75

    def __init__(self) -> None:
        """Load configuration and build the Telegram application."""
        if not getattr(self, "name", None):
            raise NotImplementedError("Bot must have a name")
        if not getattr(self, "description", None):
            raise NotImplementedError("Bot must have a description")

        self.config: dict[str, str] = {}
        self.load_config()

        for key in ("bot_token", "chat_ids"):
            if key not in self.config:
                raise ValueError(f"Missing {key} from config")

        self.chat_ids = [
            int(value.strip())
            for value in self.config["chat_ids"].split(",")
            if value.strip()
        ]
        self.bot_token = self.config["bot_token"]

        self.application: Application | None = None
        self._standalone_started = False
        self._current_update: contextvars.ContextVar[Update | None] = (
            contextvars.ContextVar(f"{self.name}_current_update", default=None)
        )
        self._media_groups: dict[str, list[Update]] = {}
        self._media_group_tasks: dict[str, asyncio.Task[None]] = {}
        self._build_application()

    @classmethod
    def command(
        cls, func: Callable | None = None, args: str = ""
    ) -> Callable:
        """Mark an async method as a Telegram command.

        The method name becomes the command name, e.g. ``foo`` becomes
        ``/foo``. The first line of its docstring is included in ``/help``.
        """

        def decorator(command_func: Callable) -> Callable:
            if not asyncio.iscoroutinefunction(command_func):
                raise TypeError("Telegram command handlers must be async")

            command_func._telegram_command = True
            command_func._telegram_command_args = args
            return functools.wraps(command_func)(command_func)

        return decorator(func) if func is not None else decorator

    @property
    def config_dir(self) -> Path:
        """Return the per-bot configuration directory."""
        return Path(os.path.expanduser(f"~/.config/tgbot-{self.name.lower()}"))

    def load_config(self) -> None:
        """Load ``key=value`` settings from the bot configuration file."""
        config_file = self.config_dir / "config"
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        logger.info("Loading config file %s", config_file)
        with config_file.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                self.config[key.strip()] = value.strip()

    def _iter_commands(self):
        """Yield command methods defined by the concrete bot class hierarchy."""
        seen: set[str] = set()
        for owner in type(self).mro():
            for name, value in vars(owner).items():
                if name in seen or not callable(value):
                    continue
                if getattr(value, "_telegram_command", False):
                    seen.add(name)
                    yield value

    def _build_application(self) -> None:
        """Build the PTB application and register framework handlers."""
        self.application = Application.builder().token(self.bot_token).build()

        for command in self._iter_commands():
            logger.info("Registering command /%s", command.__name__)
            self.application.add_handler(
                CommandHandler(command.__name__, self._wrap_handler(command))
            )

        self.application.add_handler(
            CommandHandler("start", self._start_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._message_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.PHOTO, self._photo_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.VOICE, self._voice_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.Document.ALL, self._document_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.AUDIO, self._audio_handler)
        )
        self.application.add_handler(
            MessageHandler(filters.VIDEO, self._video_handler)
        )
        # Let python-telegram-bot route handler exceptions through one central
        # error handler. PTB supplies the failed Update and exception here.
        self.application.add_error_handler(self._error_handler)

    def _wrap_handler(self, callback: Callable) -> Callable:
        """Adapt a bot command to PTB's ``(update, context)`` callback API."""

        @functools.wraps(callback)
        async def wrapped(update: Update, context: Any) -> None:
            """Run the command with authorization and update context."""
            if not self._authorized_check(update):
                return
            token = self._current_update.set(update)
            try:
                await callback(self, update)
            finally:
                self._current_update.reset(token)

        return wrapped

    async def _start_handler(self, update: Update, context: Any) -> None:
        """Handle Telegram's automatic /start command by showing help."""
        await self.help(update, context)

    async def help(self, update: Update, context: Any = None) -> None:
        """Show the bot's help text."""
        lines = [self.name, "", self.description, ""]
        for command in self._iter_commands():
            args = getattr(command, "_telegram_command_args", "")
            usage = f"/{command.__name__}"
            if args:
                usage += f" {args}"
            description = (command.__doc__ or "").strip().splitlines()[0]
            lines.append(f"`{usage}` — {description}")
        await update.effective_message.reply_markdown("\n".join(lines))

    def start(self) -> None:
        """Run the bot with Telegram polling until the process is stopped."""
        logger.info("Starting bot")
        self.application.post_init = self._post_startup
        self.application.post_shutdown = self._post_shutdown
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _post_startup(self, application: Application) -> None:
        """Run the subclass startup hook after PTB initialization."""
        await self.post_startup()

    async def _post_shutdown(self, application: Application) -> None:
        """Run the subclass shutdown hook before PTB exits."""
        await self.post_shutdown()

    async def post_startup(self) -> None:
        """Hook called once after the polling application has started."""
        await self._send_message(f"{self.name} is starting up")

    async def post_shutdown(self) -> None:
        """Hook called once when the polling application is shutting down."""

    async def _message_handler(self, update: Update, context: Any) -> None:
        """Dispatch ordinary non-command text messages."""
        await self._dispatch(update, self.handle_update)

    async def _photo_handler(self, update: Update, context: Any) -> None:
        """Dispatch a photo, or aggregate photos in a Telegram media group."""
        if not self._authorized_check(update):
            return

        message = update.effective_message
        group_id = message.media_group_id if message else None
        if not group_id:
            await self._dispatch(update, self.handle_photo)
            return

        self._media_groups.setdefault(group_id, []).append(update)
        old_task = self._media_group_tasks.pop(group_id, None)
        if old_task:
            old_task.cancel()
        self._media_group_tasks[group_id] = self.application.create_task(
            self._finish_media_group(group_id),
            update=update,
            name=f"media-group-{group_id}",
        )

    async def _finish_media_group(self, group_id: str) -> None:
        """Wait briefly for a media group to finish arriving, then dispatch it."""
        try:
            await asyncio.sleep(self.media_group_delay)
            updates = self._media_groups.pop(group_id, [])
            self._media_group_tasks.pop(group_id, None)
            if updates:
                await self._dispatch(
                    updates[0], self.handle_media_group, updates
                )
        except asyncio.CancelledError:
            raise

    async def _voice_handler(self, update: Update, context: Any) -> None:
        """Dispatch a voice message to the voice hook."""
        await self._dispatch(update, self.handle_voice)

    async def _document_handler(self, update: Update, context: Any) -> None:
        """Dispatch a document/file to the document hook."""
        await self._dispatch(update, self.handle_document)

    async def _audio_handler(self, update: Update, context: Any) -> None:
        """Dispatch an audio message to the audio hook."""
        await self._dispatch(update, self.handle_audio)

    async def _video_handler(self, update: Update, context: Any) -> None:
        """Dispatch a video message to the video hook."""
        await self._dispatch(update, self.handle_video)

    async def _dispatch(
        self,
        update: Update,
        callback: Callable[..., Awaitable[Any]],
        *args: Any,
    ) -> None:
        """Run a handler with authorization and per-task update context."""
        if not self._authorized_check(update):
            return

        token = self._current_update.set(update)
        try:
            await callback(update, *args)
        except NotImplementedError:
            logger.info("No handler implemented for %s", callback.__name__)
        finally:
            self._current_update.reset(token)

    async def handle_update(self, update: Update) -> None:
        """Handle an ordinary non-command text message."""
        raise NotImplementedError

    async def handle_photo(self, update: Update) -> None:
        """Handle one photo that is not part of a media group."""
        raise NotImplementedError

    async def handle_media_group(
        self, update: Update, updates: list[Update]
    ) -> None:
        """Handle all messages belonging to one Telegram media group."""
        for group_update in updates:
            await self.handle_photo(group_update)

    async def handle_voice(self, update: Update) -> None:
        """Handle a voice message."""
        raise NotImplementedError

    async def handle_document(self, update: Update) -> None:
        """Handle a general Telegram document/file."""
        raise NotImplementedError

    async def handle_audio(self, update: Update) -> None:
        """Handle an audio message."""
        raise NotImplementedError

    async def handle_video(self, update: Update) -> None:
        """Handle a video message."""
        raise NotImplementedError

    def _authorized_check(self, update: Update) -> bool:
        """Return whether an update came from an allowed chat."""
        if not self.only_authorized:
            return True

        chat = update.effective_chat
        if chat is None or chat.id not in self.chat_ids:
            logger.warning(
                "Ignoring unauthorized update from chat %s",
                getattr(chat, "id", None),
            )
            return False
        return True

    async def _start_standalone(self) -> None:
        """Initialize the Telegram client for outbound standalone messages."""
        if self._standalone_started:
            return
        logger.info("Starting application in standalone mode")
        await self.application.initialize()
        self._standalone_started = True

    async def _stop_standalone(self) -> None:
        """Shut down a Telegram client initialized for standalone use."""
        if self._standalone_started:
            logger.info("Stopping application in standalone mode")
            await self.application.shutdown()
            self._standalone_started = False

    async def batch_send(self) -> None:
        """Finish standalone usage by shutting down the Telegram client."""
        await self._stop_standalone()

    async def typing(self, update: Update | None = None) -> None:
        """Show Telegram's typing indicator in the relevant chat."""
        update = update or self._current_update.get()
        if update is None or update.effective_chat is None:
            raise ValueError("typing() needs an update or active handler")
        await self.application.bot.send_chat_action(
            update.effective_chat.id, ChatAction.TYPING
        )

    async def _send(
        self,
        message: str,
        chat_id: int | None = None,
        parser: str | None = None,
    ) -> None:
        """Reply to the active update or send directly to configured chats."""
        update = self._current_update.get()
        if update and update.effective_message:
            await update.effective_message.reply_text(message, parse_mode=parser)
            return

        if self.application.running:
            chat_ids = [chat_id] if chat_id is not None else self.chat_ids
            for target_chat_id in chat_ids:
                await self.application.bot.send_message(
                    chat_id=target_chat_id,
                    text=message,
                    parse_mode=parser,
                )
            return

        await self._start_standalone()
        chat_ids = [chat_id] if chat_id is not None else self.chat_ids
        for target_chat_id in chat_ids:
            await self.application.bot.send_message(
                chat_id=target_chat_id,
                text=message,
                parse_mode=parser,
            )

    async def _send_message(
        self, message: str, chat_id: int | None = None
    ) -> None:
        """Send a plain text message."""
        await self._send(message, chat_id)

    async def _send_markdown(
        self, message: str, chat_id: int | None = None
    ) -> None:
        """Send a Markdown-formatted text message."""
        await self._send(message, chat_id, parser=ParseMode.MARKDOWN)

    async def _send_image(
        self,
        image: Any,
        chat_id: int | None = None,
        caption: str | None = None,
    ) -> None:
        """Send an image, replying to the active message when possible."""
        update = self._current_update.get()
        if update and update.effective_message:
            await update.effective_message.reply_photo(image, caption=caption)
            return

        if self.application.running:
            chat_ids = [chat_id] if chat_id is not None else self.chat_ids
            for target_chat_id in chat_ids:
                await self.application.bot.send_photo(
                    chat_id=target_chat_id,
                    photo=image,
                    caption=caption,
                )
            return

        await self._start_standalone()
        chat_ids = [chat_id] if chat_id is not None else self.chat_ids
        for target_chat_id in chat_ids:
            await self.application.bot.send_photo(
                chat_id=target_chat_id,
                photo=image,
                caption=caption,
            )

    async def _send_document(
        self,
        document: Any,
        chat_id: int | None = None,
        caption: str | None = None,
    ) -> None:
        """Send a file/document, replying to the active message when possible."""
        update = self._current_update.get()
        if update and update.effective_message:
            await update.effective_message.reply_document(
                document, caption=caption
            )
            return

        if self.application.running:
            chat_ids = [chat_id] if chat_id is not None else self.chat_ids
            for target_chat_id in chat_ids:
                await self.application.bot.send_document(
                    chat_id=target_chat_id,
                    document=document,
                    caption=caption,
                )
            return

        await self._start_standalone()
        chat_ids = [chat_id] if chat_id is not None else self.chat_ids
        for target_chat_id in chat_ids:
            await self.application.bot.send_document(
                chat_id=target_chat_id,
                document=document,
                caption=caption,
            )

    async def _download_photo(
        self,
        update: Update,
        destination: str | os.PathLike[str],
    ) -> Path:
        """Download the largest Telegram photo size to a local path."""
        message = update.effective_message
        if message is None or not message.photo:
            raise ValueError("Update does not contain a photo")

        photo = message.photo[-1]
        telegram_file = await photo.get_file()
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        await telegram_file.download_to_drive(path)
        return path

    async def _download_attachment(
        self,
        update: Update,
        destination: str | os.PathLike[str],
    ) -> Path:
        """Download the update's effective attachment to a local path."""
        attachment = update.effective_attachment
        if attachment is None:
            raise ValueError("Update does not contain a downloadable attachment")

        telegram_file = await attachment.get_file()
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        await telegram_file.download_to_drive(path)
        return path

    def schedule_repeating(
        self,
        callback: Callable[..., Awaitable[Any]],
        interval: float,
        *,
        first: float | None = None,
        name: str | None = None,
    ) -> Any:
        """Schedule an async callback repeatedly using PTB's JobQueue."""
        return self.application.job_queue.run_repeating(
            callback,
            interval=interval,
            first=first,
            name=name,
        )

    async def _error_handler(self, update: object, context: Any) -> None:
        """Log an exception and report it to the chat that caused it."""
        error = context.error
        logger.error("Unhandled Telegram bot error", exc_info=error)

        if not isinstance(update, Update):
            logger.error("The exception was not caused by a Telegram update")
            return

        message = update.effective_message
        if message is None:
            logger.error("The failed update has no message to reply to")
            return

        error_text = str(error) or error.__class__.__name__
        # Telegram messages are limited to 4096 characters. Keep the useful
        # exception text while leaving room for the error prefix.
        error_text = error_text[:4000]

        try:
            await message.reply_text(
                f"An error occurred:\n{error.__class__.__name__}: {error_text}"
            )
        except Exception:
            # Never allow a failure while reporting an error to hide the
            # original exception.
            logger.exception("Failed to send exception to Telegram chat")


# The help method is registered after the class is defined. This mirrors the
# original abstraction and avoids using @TelegramBot.command on the method.
TelegramBot.help = TelegramBot.command(TelegramBot.help)
