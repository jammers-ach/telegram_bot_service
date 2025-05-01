#!/usr/bin/env python3
'''
ColorBot: A bot that will ask you for a color

It include command line options to tell you if there are any birthdays in
the next few days. These can be added to your crontab on your server.


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
import logging
import asyncio
import gspread
import datetime

from tg_bot.bot  import TelegramBot

logger = logging.getLogger(__name__)

# The week and day of a given date
week_and_day = lambda x: (x.isocalendar()[1], x.weekday()+1)


rgb = lambda r, g, b: (r/255, g/255, b/255)

colors = {
    "red": rgb(255,0,0),
    "blue": rgb(0,0,205),
    "green": rgb(34,139,34),
    "orange": rgb(255,140,0),
    "purple": rgb(186,85,211),
    "black": rgb(0,0,0)
}

class ColorDayBot(TelegramBot):
    '''Telegram bot which colors in your mood for the day'''
    name = "ColorDayBot"
    description = "Bot which colors in your mood for the day in a google sheet"

    def __init__(self):
        super().__init__()
        self.gc = gspread.service_account()
        self._refresh_sheet()

    def _refresh_sheet(self):
        self.sheet = self.gc.open_by_url(self.config['sheet_url'])
        self.emotions = self.sheet.get_worksheet(0)
        self.whys = self.sheet.get_worksheet(1)
        self.log = self.sheet.get_worksheet(2)


    async def make_update(self, update, text, date):
        if text.lower().startswith("why"):
            text = text[4::]
            await update.message.reply_text(f"You why: {text}")
            try:
                self.why_square(date, text)
                await update.message.reply_text(f"Updated {datetime.date.today()} with {text}")
            except Exception as e:
                await update.message.reply_text(f"failed: {e}")
        else:
            text = text.lower()
            if text not in colors:
                await update.message.reply_text(f"Invalid color {text}")
                color_list = "\n".join(colors.keys())
                await update.message.reply_text(f"Possible colors are: {color_list}")
                return

            try:
                self.color_square(date, text)
                await update.message.reply_text(f"Updated {datetime.date.today()} with {text}")
            except Exception as e:
                await update.message.reply_text(f"failed: {e}")

    async def handle_update(self, update):
        text = update.message.text
        self.make_update(update, text, datetime.date.today())


    def why_square(self, date, whys):
        row, col = week_and_day(date)
        cell = self.whys.cell(row, col).address
        self.whys.update(cell, whys)


    def color_square(self, date, color):
        row, col = week_and_day(date)
        cell = self.emotions.cell(row, col).address
        logger.info(f"for {date} got ({row}, {col}), cell {cell}")

        r,g,b = colors[color]

        self.emotions.format(cell, {
            "backgroundColor":{
                "red": r,
                "green": g,
                "blue": b
            }
        })
        self.emotions.update(cell, 'x')

    @TelegramBot.command(args="<NEW MSG>")
    async def yesterday(self, update):
        '''update yesterdays message (incase you forgot)'''
        text = update.message.text
        self.make_update(update, text, datetime.date.today() - datetime.timedelta(days=1))

    @TelegramBot.command
    async def help(self, update):
        msg = '''Color bot. I hope it works

        Tell the ColorBot what color you want for the day.

        Red = only bad
        Green = only good
        Orange = started bad but got good
        Purple = started good but got bad
        black = very very back
        '''
        await update.message.reply_text(msg)

    async def check(self):
        """Checks to see if someone has filled in the cell for today"""
        date = datetime.datetime.today()
        row, col = week_and_day(date)
        cell = self.emotions.cell(row, col).value
        logger.info(f"checking {row}, {col}")

        if cell != "x":
            logger.info("Not filled in")
            await self.single_send_msg("what color for today?", chat_ids=self.chat_ids)
        else:
            logger.info("filled in")


def run():
    parser = argparse.ArgumentParser(description="A bot asks you to color your mood for the day")
    parser.add_argument('-check', action='store_true', help='Check to see if someone filled in today')

    args = parser.parse_args()

    bot = ColorDayBot()

    if args.check:
        asyncio.run(bot.check())
    else:
        bot.start()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    run()
