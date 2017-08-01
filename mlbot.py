#!/usr/bin/env python3

# Telegram bot API
import telegram
from telegram.ext import Job
from telegram.ext import Updater
from telegram.ext import CommandHandler

# Calendar for month names
import calendar
# Scraping mailing list archives
from bs4 import BeautifulSoup
from urllib import request
from urllib.error import HTTPError

# Set italian locale
import locale

# Date parsing
import maya
import datetime as dt
import dateparser as dp

# Some logging
import logging

def now():
    return maya.now().datetime()

def human_date(d):
    '''Returns a formatted string for date'''
    return dt.datetime.strftime(d, '%c')

def get_date(mail_url):
    '''Given URL of a mail, parse its date'''

    page = request.urlopen(mail_url).read()
    soup = BeautifulSoup(page, 'lxml')
    post_date = soup.body.i.string
    # Try parsing expected formats
    date = dp.parse(post_date, date_formats=['%a %d %b %Y %H:%M:%S %Z', '%a %d %B %Y %H:%M:%S %Z'], settings={'RETURN_AS_TIMEZONE_AWARE': True})
    # If fail, try automatic parser
    if date is None:
        date = dp.parse(post_date, settings={'RETURN_AS_TIMEZONE_AWARE': True})
    return date

def get_month_url(year, month):
    '''Return the URL of the page containing month threads'''

    return 'http://lists.python.it/pipermail/pycon/{}-{}/'.format(year, month)

def threads_for_month(year, month):
    '''Generates threads in the specified month'''

    try:
        base_url = get_month_url(year, month)
        thread_url = base_url + 'thread.html'
        logging.info('Reading page %s', thread_url)
        page = request.urlopen(thread_url).read()
    except HTTPError:
        # Page not found, return
        return

    # pipermail omits closing tags: html.parser fails to parse correctly
    soup = BeautifulSoup(page, 'lxml')
    # Extract the first level of the hierarchy
    topics = soup.body.find_all('ul', recursive=False)[1].find_all('li', recursive=False)
    # Build threads
    for t in topics:
        msg = t.a.string.strip()
        url = t.a.get('href')
        date = get_date(base_url + url)
        yield (date, msg, url)

def build_thread_row(date, message, url):
    '''Returns a string for a thread'''

    # Ensure line is not too long (limit for telegram messages is 4096)
    max_len = 4000 - len(url)
    message = message.strip()
    label = '{} {}'.format(message[:max_len], human_date(date))
    return ' - <a href="{}">{}</a>'.format(url, label)

def paginate_message(rows):
    '''Max length for a message is 4096: this will produce shorter chunks'''
    acc = ''
    for row in rows:
        if len(acc + row) + 1 > 4000:
            yield acc
            acc = row + '\n'
        else:
            acc += row + '\n'
    yield acc

class MailingListBot:
    def __init__(self):
        # Save month names in english locale
        locale.setlocale(locale.LC_TIME, 'en_US')
        self.month_names = list(calendar.month_name)
        self.short_month_names = list(calendar.month_abbr)
        # We will use italian dates most of the times
        locale.setlocale(locale.LC_TIME, 'it_IT')
        # Time of last check
        self.last_check = now()
        # Do we have a recurrent check?
        self.started = False

    def months_after(self, date):
        '''Iterates (year,month) tuples after the specified date, till today'''

        today = now()
        start = 12 * date.year + date.month - 1
        end = 12 * today.year + today.month
        for mm in range(start, end):
            y, m = divmod(mm, 12)
            yield (str(y), self.month_names[m+1])

    def set_last_check(self, bot, update):
        '''Changes date of last check. Useful when testing the bot or setting it up.'''

        if not self.started:
            bot.send_message(chat_id=update.message.chat_id, text='Bot was not started. Use /start first')
            return

        text = update.message.text
        logging.info('Setting last check with %s', text)

        try:
            skip = text.index(' ') + 1
            day = maya.when(text[skip:]).datetime()
            logging.info('Parsed date: %s', day)
            self.last_check = day
            bot.send_message(chat_id=update.message.chat_id, text='Setting last check: ' + human_date(day))
        except ValueError:
            bot.send_message(chat_id=update.message.chat_id, text='Sorry, I did not understand. Please, send dates in unambiguous format (e.g. yyyy-mm-dd)')

    def check_new_threads(self, bot, job):
        '''This function is called periodically to check if new threads are present since last check.'''

        logging.info('Checking for new threads since {}'.format(human_date(self.last_check)))
        # Threads found
        new_threads = []
        # Iterate over all threads after the last check date
        for year, month in self.months_after(self.last_check):
            base_url = get_month_url(year, month)
            for td, tm, tu in threads_for_month(year, month):
                if td <= self.last_check:
                    continue # Already checked
                logging.info('Found a thread in month {}-{}'.format(year, month, tm))
                new_threads.append(build_thread_row(td, tm, base_url+tu))

        # Set last check
        self.last_check = now()

        # Write only if necessary
        if new_threads:
            out = '<b>New threads since {}</b>\n'.format(human_date(self.last_check))
            for msg in paginate_message([out] + new_threads):
                bot.send_message(
                    chat_id=job.context,
                    parse_mode=telegram.ParseMode.HTML,
                    text=msg,
                    #text=out,
                )

    def threads(self, bot, update, args):
        '''Prints threads in a specified year-month'''

        # Parse arguments as date
        try:
            date = maya.when(' '.join(args)).datetime()
            # If we couldn't parse, use now
            if date is None:
                date = now()
            # Get arguments in suitable format
            args = (str(date.year), self.month_names[date.month])
            # Output string we are building

            rows = []
            base_url = get_month_url(*args)
            for td, tm, tu in threads_for_month(*args):
                rows.append(build_thread_row(td, tm, base_url+tu))

            out = '<b>Threads {} {}</b>\n'.format(*args)
            for msg in paginate_message([out] + rows):
                bot.send_message(
                    chat_id=update.message.chat_id,
                    parse_mode=telegram.ParseMode.HTML,
                    text=msg,
                )
        except ValueError:
            bot.send_message(chat_id=update.message.chat_id, text='Sorry, I did not understand. Please, send dates in unambiguous format (e.g. yyyy-mm-dd)')

    def start(self, bot, update, job_queue):
        '''Starts the bot, setting up repeated check and printing welcome message'''

        self.last_check = now()
        bot.send_message(chat_id=update.message.chat_id,
            text="*Welcome!*\nGet threads with /th 2016 July\nSet Last Check date with /slc 1 maggio 2017\n\nBot will check for new threads every 2 minutes",
            parse_mode=telegram.ParseMode.MARKDOWN)
        job_queue.run_repeating(self.check_new_threads, 10.0, context=update.message.chat_id)
        self.started = True

    def run_bot(self):
        # Setup bot
        with open('./bot.key') as keyfile:
            updater = Updater(token=keyfile.read().strip())

        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler('start', self.start, pass_job_queue=True))
        dispatcher.add_handler(CommandHandler('threads', self.threads, pass_args=True))
        dispatcher.add_handler(CommandHandler('th', self.threads, pass_args=True))
        dispatcher.add_handler(CommandHandler('setlastcheck', self.set_last_check))
        dispatcher.add_handler(CommandHandler('slc', self.set_last_check))

        updater.start_polling()

if __name__ == '__main__':
    # Some logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Create bot and run polling main loop
    mlb = MailingListBot()
    mlb.run_bot()
