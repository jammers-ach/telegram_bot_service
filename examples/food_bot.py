#!/usr/bin/env python3
'''
FoodBot: A bot for logging what you've eaten

Send what you ate to the bot, it stores the time of that and at the end of the day
gives you a list of what you ate.

Like this:

> biscuit
< logged 10:14 biscuit
> /log 08:30 cheeky marshmallow
< logged 08:30 cheeky marshmallow
> /day
< Today you ate:
< 08:30 - cheeky marshmaoow
< 10:14 - biscuit
< 12:00 - some lunch


1) create a config file ~/.config/tbot-foodbot/config
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

from tg_bot.bot  import TelegramBot

logger = logging.getLogger(__name__)


class FoodBot(TelegramBot):
    '''Telegram Bot which stores time series data from conversations'''
    name = "FoodBot"


    def __init__(self):
        super().__init__()
        self.db_file = os.path.join(self.config_dir, "database")
        self.shortcut_db = os.path.join(self.config_dir, "shortcuts")

        if os.path.exists(self.db_file):
            with open(self.db_file) as f:
                self.db = json.load(f)
        else:
            self.db = {}

        if os.path.exists(self.shortcut_db):
            with open(self.shortcut_db) as f:
                self.shortcuts = json.load(f)
        else:
            self.shortcuts = {}
        self.states = {}

    def _save_shortcut(self, chatid, key, item):
        if chatid not in self.shortcuts:
            self.shortcuts[chatid] = {}
        key = key.lower()
        self.shortcuts[chatid][key] = item
        with open(self.shortcut_db, "w") as f:
            json.dump(self.shortcuts, f, indent=2)

    def _get_shortcut(self, chatid, key):
        if chatid not in self.shortcuts:
            return key
        return self.shortcuts[chatid].get(key.lower(), key)

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
            self.db[chat_id][key] = []

        self.db[chat_id][key].append(record)
        self.states[chat_id] = 0

        self._save_db()

    @TelegramBot.command
    async def help(self, update):

        helptext='''Bot to log what food you eat:
/help to display help text
/day <date> display what you ate this day, or a specified day
/log <time> <food>: log some food you ate at a specific time, that you might have forgotten about
/day <datE> display what you ate on that date
/shortcut <key> <full text> adds a shortcut
/yesterday show what you ate yesterday
'''
        await update.message.reply_text(helptext)



    @TelegramBot.command
    async def shortcut(self, update):
        '''Creates a new shortcut, or displays all the shortcuts'''
        text = update.message.text
        chat_id = str(update.message.chat_id)
        if text == "/shortcut":
            t = ""
            if chat_id not in self.shortcuts:
                await update.message.reply_text("you have no shortcuts")
                return
            for key,value in self.shortcuts[chat_id].items():
                t += f"`{key}`: {value}\n"
            await update.message.reply_markdown(t)
        else:
            key = update.message.text.split(" ", 2)[1].strip().lower()
            value = update.message.text.split(" ", 2)[2].strip().lower()
            self._save_shortcut(chat_id, key, value)
            await update.message.reply_markdown(f"saved: `{key}`: {value}\n")

    def _from_humandate(self, text):
        '''Turns days of week into a certain date, or parases the date as YYYY-mm-dd'''
        text = text.lower()
        day_num = {'monday':0,'tuesday':1,'wednesday':2,'thursday':3,'friday':4,'saturday':5,'sunday':6}
        if text in day_num:
            today = datetime.datetime.today()
            days_ago = (today.weekday() - day_num[text]) % 7 or 7
            return (today - datetime.timedelta(days=days_ago)).date()
        else:
            date = datetime.datetime.strptime(text, "%Y-%m-%d")
            return date

    @TelegramBot.command
    async def yesterday(self, update):
        yesterday = datetime.datetime.today() - datetime.timedelta(days=1)
        await self.post_day(update, yesterday)



    @TelegramBot.command
    async def day(self, update):
        '''Print out what was eaten today or on a specific date'''
        text = update.message.text
        if text == '/day':
            await self.post_day(update, datetime.datetime.now())
        else:
            try:
                text = update.message.text.split(" ", 1)[1].strip().lower()
                date = self._from_humandate(text)
                await self.post_day(update, date)
            except Exception as e:
                await update.message.reply_text(str(e))

    async def post_day(self, update, date):
        day = date.strftime("%Y-%m-%d")
        chat_id = str(update.message.chat_id)
        if chat_id not in self.db:
            await update.message.reply_text("No data yet")
            return
        else:
            keys = self.db[chat_id].get(day,[])
            if not keys:
                await update.message.reply_markdown(f"You are nothing on {day}")
                return

            await update.message.reply_markdown(self.generate_day(keys))

    @TelegramBot.command
    async def log(self, update):
        try:
            time = update.message.text.split(" ", 2)[1].strip().lower()
            item = update.message.text.split(" ", 2)[2].strip().lower()
            dt = datetime.datetime.combine(datetime.datetime.today().date(), datetime.datetime.strptime(time, "%H:%M").time())
            await self.log_date(update, item, dt)
        except Exception as e:
            await update.message.reply_text(str(e))


    @TelegramBot.command
    async def stats(self, update):
        chat_id = update.message.chat_id
        await self._send_weekly_stats(chat_id, update)


    async def handle_update(self, update):
        item = update.message.text
        await self.log_date(update, item, datetime.datetime.now())


    async def log_date(self, update, item, date):
        chat_id = str(update.message.chat_id)
        day = date.strftime("%Y-%m-%d")
        time = date.strftime("%H:%M")

        item = self._get_shortcut(chat_id, item)
        self._db_put(chat_id, day, (time, item))
        await update.message.reply_markdown(f"{day}: *{item}* at `{time}`")


    def generate_day(self, day):
        '''generates the list of things eaten in a day'''
        text = ""
        day.sort(key=lambda x: x[0])
        for time, item in day:
            text += f"`{time}`: *{item}*\n"
        return text


    def _top_items(self, chat_id, top):
        '''returns the top N items from this week'''
        db = self.db[str(chat_id)]
        food_count_week = {}
        dates = [(datetime.datetime.today() - datetime.timedelta(days=i)).date().isoformat() for i in range(6, -1, -1)]
        for d in dates:
            keys = db.get(d, [])
            for _, key in keys:
                if key not in food_count_week:
                    food_count_week[key] = 0
                food_count_week[key] += 1
        sorted_items = sorted(food_count_week.items(), key=lambda item: -1*item[1])
        return sorted_items[0:top]


    def generate_top_list(self, chat_id, top=10):
        '''Generates a list of the top 5 foods you ate in the week
        '''
        top_items = self._top_items(chat_id, top=top)

        text = ""
        for item, count in top_items:
            text += f"`{count:>2}:` {item}\n"

        return text

    def generate_new_food(self, chat_id, days=7):
        '''prints out which foods were new for you in the last N days
        '''
        dates = [(datetime.datetime.today() - datetime.timedelta(days=i)).date().isoformat() for i in range(days-1, -1, -1)]
        db = self.db[str(chat_id)]
        other_foods, weeks_foods = [], []
        for key, items in db.items():
            (other_foods if key not in dates else weeks_foods).extend(food for _, food in items)
        new_foods = set(weeks_foods) - set(other_foods)
        return "\n".join(new_foods)


    async def weekly_stats(self):
        """Gives the weekly stats"""
        for chat_id in self.chat_ids:
            await self._send_weekly_stats(chat_id)

    async def _send_weekly_stats(self, chat_id, update=None):
        msg = self.generate_top_list(chat_id)
        if not update:
            await self.single_send_msg("In the last 7 days you ate:", chat_ids=[chat_id], markdown=True)
            await self.single_send_msg(msg, chat_ids=[chat_id], markdown=True)
        else:
            await update.message.reply_markdown("In the last 7 days you ate:")
            await update.message.reply_markdown(msg)

        msg = self.generate_new_food(chat_id)
        if not update:
            await self.single_send_msg("New foods for you in the last 7 days:", chat_ids=[chat_id], markdown=True)
            await self.single_send_msg(msg, chat_ids=[chat_id], markdown=True)
        else:
            await update.message.reply_markdown("New foods for you in the last 7 days:")
            await update.message.reply_markdown(msg)

    async def today(self):
        """prints out today's food"""
        date = datetime.datetime.today()
        day = date.strftime("%Y-%m-%d")
        for chat_id in self.chat_ids:
            try:
                keys = self.db[str(chat_id)].get(day,None)
                if keys:
                    await self.single_send_msg("Today you ate:", chat_ids=[chat_id,])
                    await self.single_send_msg(self.generate_day(keys), chat_ids=[chat_id,], markdown=True)
                else:
                    await self.single_send_msg("Today you ate nothing!?!", chat_ids=[chat_id,])
                    await self.single_send_msg("maybe you should correct that?", chat_ids=[chat_id,])
            except Exception as e:
                print(e)



def run():
    parser = argparse.ArgumentParser(description="Foodbot: Logs what you eat each day")
    parser.add_argument('-today', action='store_true', help='Prints out what was eaten today')
    parser.add_argument('-week', action='store_true', help='Prints out the weekly stats')
    args = parser.parse_args()

    bot = FoodBot()

    if args.today:
        asyncio.run(bot.today())
    elif args.week:
        asyncio.run(bot.weekly_stats())
    else:
        bot.start()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run()
