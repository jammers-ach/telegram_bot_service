#!/usr/bin/env python3
'''
MeasurementBot: A bot that stores and graphs self reported measurements

Send a simple number to the bot, it will ask what the measurement is for.

It then stores that locally, and you can query for all the measurements.

Like this:

> 72
< 72.0, what should I store it under?
> weight
< Stored 2024-01-01 18:35: 72.0 in `weight`
> /graph weight
[Graph of your weight]
> /keys
< weight
< height
< whatever
> /list height
> 2024-01-01 18:34: 101
> 2024-01-02 18:34: 102
> 2024-01-03 18:34: 103



1) create a config file ~/.config/tbot-measurementbot/config
```
bot_token=<BOT TOKEN>
chat_ids=<CHAT_IDS>
```

'''

import argparse
import os
import logging
import asyncio
import datetime
import json
import tempfile

import matplotlib.dates as md
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont
from matplotlib.ticker import AutoMinorLocator, AutoLocator

from tg_bot.bot  import TelegramBot

logger = logging.getLogger(__name__)


def plot_measurements(dates, values, title, ylab='Value'):
    # Convert the list of dates from seconds since epoch to datetime objects
    dates = [datetime.datetime.fromtimestamp(ts) for ts in dates]

    # Create the plot
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, values, marker='o', linestyle='-')

    ax.set_xlabel('Date')
    ax.set_ylabel(ylab)
    ax.set_title(title)
    ax.grid(True)
    fig.tight_layout()

    # Rotating the date labels for better readability
    fig.autofmt_xdate()

    return fig, ax

class MeasureBot(TelegramBot):
    '''Telegram Bot which stores time series data from conversations'''
    name = "MeasureBot"


    def __init__(self):
        super().__init__()
        self.db_file = os.path.join(self.config_dir, "database")

        if os.path.exists(self.db_file):
            with open(self.db_file) as f:
                self.db = json.load(f)
        else:
            self.db = {}
        self.states = {}

    def _save_db(self):
            with open(self.db_file, "w") as f:
                json.dump(self.db, f, indent=2)


    def _db_get(self, chat_id, key):
        chat_id = str(chat_id)
        if chat_id not in self.db:
            self.db[chat_id] = {}
        return self.db[chat_id][key]

    def _db_put(self, chat_id, key, record):
        chat_id = str(chat_id)
        if chat_id not in self.db:
            self.db[chat_id] = {}

        if key not in self.db[chat_id]:
            self.db[chat_id][key] = {"data":[], "type":"ts"}

        date, value = record

        self.db[chat_id][key]["data"].append((date, value))
        self.states[chat_id] = 0

        self._save_db()



    @TelegramBot.command
    async def keys(self, update):
        chat_id = str(update.message.chat_id)
        if chat_id not in self.db:
            await update.message.reply_text("No data yet")
            return
        else:
            keys = "\n".join(self.db[chat_id].keys())
            await update.message.reply_text(keys)


    @TelegramBot.command
    async def list(self, update):

        try:
            key = update.message.text.split(" ", 1)[1].strip().lower()
        except IndexError:
            await update.message.reply_text("please specify a key")
            return

        chat_id = str(update.message.chat_id)

        try:
            data = self._db_get(chat_id, key)["data"]
            text = [f"{key}: {value}" for key,value in data]
            await update.message.reply_text("\n".join(text))
        except KeyError:
            await update.message.reply_text(f"{key} not found in database")

    @TelegramBot.command
    async def graph(self, update):
        try:
            key = update.message.text.split(" ", 1)[1].strip().lower()
        except IndexError:
            await update.message.reply_text("please specify a key")
            return

        chat_id = str(update.message.chat_id)

        try:
            data = self._db_get(chat_id, key)["data"]
            ts, val = zip(*data)
            fig, ax = plot_measurements(ts, val, key)

            with tempfile.NamedTemporaryFile() as fp:
                fig.savefig(fp, format="png")
                fp.seek(0)
                await update.message.reply_photo(fp)


        except KeyError:
            await update.message.reply_text(f"{key} not found in database")


    async def handle_update(self, update):
        chat_id = str(update.message.chat_id)

        state = self.states.get(chat_id, 0)
        text = update.message.text

        if state == 0:
            try:
                value = float(text)
                await update.message.reply_text(f"*{value}*, what should this be stored under?")
                self.states[chat_id] = 1
                self.last_value = value
                self.last_date = datetime.datetime.now()
            except:
                await update.message.reply_text(f"please enter a valid number.")
        elif state == 1:
            value = self.last_value
            date = self.last_date
            key = text.lower()
            try:
                self._db_put(chat_id, key, (date.timestamp(), value))
                await update.message.reply_text(f"Added: {key}: {date}, {value}")
            except Exception as e:
                await update.message.reply_text(f"Failed to add to database")
                raise e





def run():
    parser = argparse.ArgumentParser(description="MeasureBot: stores timeseries data from conversations and graphs them")
    args = parser.parse_args()

    bot = MeasureBot()
    bot.start()

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run()
