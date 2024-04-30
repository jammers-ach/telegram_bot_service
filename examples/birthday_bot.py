#!/usr/bin/env python3
'''
BirthdayBot: A telegram bot that reads birthdays from a google sheet.

It include command line options to tell you if there are any birthdays in
the next few days. These can be added to your crontab on your server.


To set it up.
1) Create a google spreadsheet, with two 3 columns:
    DOB    Name      Present idea (optional)

2) Setup a service account
   https://docs.gspread.org/en/latest/oauth2.html#service-account


3) create a config file ~/.config/tbot-birthdaybot/config
```
bot_token=<BOT TOKEN>
chat_ids=<CHAT_IDS>
sheet_url=<SHEET_URL_FOR_SERVICE_ACCOUNT>
```

4) Setup some cronjobs
# remind at 8am of who has a birthday today
0 8 * * * /path/to/bot/birthday_bot.py -todays
# remind on sunday evening who has birthdays in the next 2 weeks
20 0 * * 0 /path/to/bot/birthday_bot.py -birthdays 2
# remind on sunday who I need to get a present for in the next 4 weeks
20 0 * * 0 /path/to/bot/birthday_bot.py -presents 4

5) setup the bot service (optional)
   The cronjobs will do the checking.
   The bot service is only there if you want to query for users

'''
import argparse
import os
import logging
import asyncio
import gspread
import datetime

from tg_bot.bot  import TelegramBot

logger = logging.getLogger(__name__)

def day_delta(d1, d2):
    """
    calculates the number of days between d1 and and d2
    taking into account a 365 day year.
    """
    # Calculate the day of the year for both dates
    day_of_year_d1 = d1.timetuple().tm_yday
    day_of_year_d2 = d2.timetuple().tm_yday

    days_until_same_day = day_of_year_d2 - day_of_year_d1

    if days_until_same_day < 0:
        return days_until_same_day + 365
    return days_until_same_day


class BirthdayBot(TelegramBot):
    '''Telegram bot which reads in birthdays from a google sheet'''
    name = "BirthdayBot"
    norm_msg="{day}.{month} {dow} - {name}"
    present_msg="{day}.{month} {dow} - {name}, {present} maybe?"

    def __init__(self):
        super().__init__()
        self.gc = gspread.service_account()
        self._refresh_sheet()


    def _refresh_sheet(self):
        self.sheets = self.gc.open_by_url(self.config['sheet_url'])


    def _load_birthdays(self):
        today = datetime.datetime.now()
        list_of_dicts = self.sheets.sheet1.get_all_records()

        # add to each entry the date that their birthday would fall on in this year
        for entry in list_of_dicts:
            parsed_dob = datetime.datetime.strptime(entry["DOB"], "%d.%m.%Y")
            entry["date"] = parsed_dob.replace(year=today.year)

        list_of_dicts.sort(key=lambda x: x["date"])
        return list_of_dicts


    def _filter_birthdays(self, filter_func):
        '''provide a list of birthdays filtering by the filter

            `filter_func` is given a date and returns true or false
        '''
        birthdays = self._load_birthdays()
        return filter(filter_func, birthdays)


    @TelegramBot.command
    async def all(self, update):
        self.typing(update)
        birthdays = self._filter_birthdays(lambda x: True)

        msg = "\n".join([f'{b["DOB"]}, {b["Who"]}' for b in birthdays])
        await update.message.reply_text(msg)


    @TelegramBot.command
    async def help(self, update):
        msg = '''
        /all to see a list of all the birthdays
        /days <days> to see whos birthday it is in the next X days
        '''
        await update.message.reply_text(msg)


    @TelegramBot.command
    async def days(self, update):
        try:
            text = update.message.text.split(" ", 1)[1].strip()

            if not text.isnumeric():
                await update.message.reply_text("please specify a number of days")
                return

            days = int(text)
        except (IndexError, ValueError) as e:
                await update.message.reply_text("please specify a number of days")
                return

        msg = self.make_birthday_msg(days)

        if msg == "":
            await update.message.reply_text(f"No birthdays in the next {days} days")
        else:
            await update.message.reply_text(f"Here is a list of birthdays in the next {days} days")
            await update.message.reply_text(msg)



    def make_birthday_msg(self, days, extra_filter=None):
        '''makes a message with the inumber of days remaining'''
        today = datetime.datetime.now()
        birthdays = self._filter_birthdays(lambda x: day_delta(today, x["date"]) < days)

        if extra_filter:
            birthdays = filter(extra_filter, birthdays)

        message = []
        for birthday in birthdays:
            key = {
                'month': birthday['date'].month,
                'day': birthday['date'].day,
                'dow': birthday['date'].strftime("%a"),
                'name': birthday['Who'],
                'present': birthday['Present']
            }

            if key['present'] == '':
                msg = self.norm_msg.format(**key)
            else:
                msg = self.present_msg.format(**key)

            message.append(msg)

        return '\n'.join(message)

    async def todays(self):
        msg = self.make_birthday_msg(0)
        if msg:
            await self.single_send_msg(msg)
        else:
            print("no birthdays today")

    async def birthdays(self, days):
        msg = self.make_birthday_msg(days)
        if msg:
            await self.single_send_msg(msg)
        else:
            print(f"no birthdays in the next {days}")

    async def presents(self, days):
        msg = self.make_birthday_msg(days, lambda x: x["Present"] != "")
        if msg:
            await self.single_send_msg(msg)
        else:
            print(f"no birthdays in the next {days}")

def run():
    parser = argparse.ArgumentParser(description="Birthday bot: A telegram bot that reads birthdays from a google sheet and notifies you if they are needed")

    parser.add_argument('-todays', action='store_true', help='List who has birthdays today')
    parser.add_argument('-birthdays', type=int, metavar='weeks', help='List all people with birthdays in the next <weeks> number of weeks')
    parser.add_argument('-presents', type=int, metavar='weeks', help='List all people and their presents in the next <weeks> number of weeks')


    args = parser.parse_args()

    bot = BirthdayBot()
    if args.todays:
        asyncio.run(bot.todays())
    elif args.birthdays:
        asyncio.run(bot.birthdays(args.birthdays))
    elif args.presents:
        asyncio.run(bot.presents(args.presents))
    else:
        bot.start()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run()
