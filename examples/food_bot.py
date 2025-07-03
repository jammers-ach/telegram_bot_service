#!/usr/bin/env python3
'''
FoodBot: A bot for logging what you've eaten

Send what you ate to the bot, it stores the time of that and at the end of the day
gives you a list of what you ate.

Like this:

> biscuit
< logged 10:14 biscuit
> 0830 cheeky marshmallow
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
import re

from tg_bot.bot  import TelegramBot

logger = logging.getLogger(__name__)


class FoodBot(TelegramBot):
    '''bot to track what you eat'''
    name = "FoodBot"
    description = """bot to track what you eat, send it a message with something you ate and it will log that you ate it at that time
```
> biscuit
< logged 10:14 biscuit
> 0830 cheeky marshmallow
< logged 08:30 cheeky marshmallow
> /day
< Today you ate:
< 08:30 - cheeky marshmaoow
< 10:14 - biscuit
< 12:00 - some lunch
> /day wednesday
< on wednesday you ate:
....
> /shortcut c cookie :)
> 1500 c
< logged 15:00 cookie :)
```
"""


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
        item = self._sanatize(item)
        if chatid not in self.shortcuts:
            self.shortcuts[chatid] = {}
        key = key.lower()
        self.shortcuts[chatid][key] = item
        with open(self.shortcut_db, "w") as f:
            json.dump(self.shortcuts, f, indent=2)

    def _sanatize(self, item):
        return item.replace("*","x")


    def _parse_message(self, message, chatid):
        '''parses out a message and returns a time
        if there's no time it will use the current time
        it will look up the object in the shortcuts
        so for example:
             * "cookie" will return [<now>, "cookie"]
             * "1025 cookie" will return ["10:25", "cookie"]
             * "10 cookie" will return ["10:00", "cookie"]
             * "10 c" will return ["10:00", "cookie"] if there's a shortcut mapping c -> cookie
        '''
        parts = message.strip().split(maxsplit=1)
        time_str = None
        object_str = None

        # Regex to detect time pattern (e.g., "1025", "10")
        time_pattern = re.compile(r'^(\d{1,2})(\d{2})?$')

        if parts:
            match = time_pattern.match(parts[0])
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                time_str = f"{hour:02d}:{minute:02d}"
                if len(parts) > 1:
                    object_str = parts[1]
            else:
                object_str = message

            if object_str:
                object_str = self._get_shortcut(chatid, object_str)

        if not time_str:
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M")

        return [time_str, object_str or '']

    def _get_shortcut(self, chatid, key):
        '''looks up the shortcut for a chatid, returns key if there wasn't any'''
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


    @TelegramBot.command(args="<code> <full text>")
    async def shortcut(self, update):
        '''Creates a new shortcut from a code, or displays all the shortcuts'''
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

    @TelegramBot.command(args="<food>")
    async def yesterday(self, update):
        """Prints out what you ate yesterday, or logs food you ate yesterday"""
        yesterday = datetime.datetime.today() - datetime.timedelta(days=1)
        text = update.message.text
        if text == '/yesterday':
            await self.post_day(update, yesterday)
        else:
            item = text.replace("/yesterday","")
            await self.log_date(update, item, yesterday)




    @TelegramBot.command(args="<day>")
    async def day(self, update):
        '''Print out what was eaten today or on a specific date (e.g. monday, tuesday wednesday)'''
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
    async def stats(self, update):
        '''top 10 popular food in the last 7 days, and new food in the last 7 days'''
        chat_id = update.message.chat_id
        await self._send_weekly_stats(chat_id, update)


    async def handle_update(self, update):
        item = update.message.text
        await self.log_date(update, item, datetime.datetime.now())


    async def log_date(self, update, item, date):
        '''Stores that a specific food was eaten at a specific date'''
        chat_id = str(update.message.chat_id)
        day = date.strftime("%Y-%m-%d")

        time, item = self._parse_message(item, chat_id)
        print(time, item)

        for i in item.split("\n"):
            i = self._sanatize(i)
            if not i:
                continue
            self._db_put(chat_id, day, (time, i))
            await update.message.reply_markdown(f"{day}: *{i}* at `{time}`")


    def generate_day(self, day):
        '''generates the list of things eaten in a day'''
        text = ""
        day.sort(key=lambda x: x[0])
        for time, item in day:
            item = self._sanatize(item)
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
            await self._send_markdown("In the last 7 days you ate:", chat_id=chat_id)
            await self._send_markdown(msg, chat_id=chat_id)
        else:
            await update.message.reply_markdown("In the last 7 days you ate:")
            await update.message.reply_markdown(msg)

        msg = self.generate_new_food(chat_id)
        if not update:
            await self._send_markdown("New foods for you in the last 7 days:", chat_id=chat_id)
            await self._send_markdown(msg, chat_id=chat_id)
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
                    await self._send_message("Today you ate:", chat_id=chat_id)
                    await self._send_markdown(self.generate_day(keys), chat_id=chat_id)
                else:
                    await self._send_message("Today you ate nothing!?!", chat_id=chat_id)
                    await self._send_message("maybe you should correct that?", chat_id=chat_id)
            except Exception as e:
                print(e)



def run():
    parser = argparse.ArgumentParser(description="Foodbot: Logs what you eat each day")
    parser.add_argument('-today', action='store_true', help='Prints out what was eaten today')
    parser.add_argument('-week', action='store_true', help='Prints out the weekly stats')
    args = parser.parse_args()

    bot = FoodBot()

    if args.today:
        async def do_send():
            await bot.today()
            await bot.batch_send()
        asyncio.run(do_send())
    elif args.week:
        async def do_send():
            await bot.weekly_stats()
            await bot.batch_send()
        asyncio.run(do_send())
    else:
        bot.start()


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run()
