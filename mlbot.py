#!/usr/bin/env python3

# Telegram bot API
import telegram
from telegram.ext import Job
from telegram.ext import Updater
from telegram.ext import CommandHandler

# Calendar for month names
import calendar
# Copy month names before locale
month_names = list(calendar.month_name)
short_month_names = list(calendar.month_abbr)

# Scraping mailing list archives
from bs4 import BeautifulSoup
from urllib import request

# Set italian locale
import locale
locale.setlocale(locale.LC_TIME, 'it_IT')

# Date parsing
import maya

# Some logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# When was the page last checked?
last_check = maya.now()

def get_date(mail_url):
    '''Given URL of a mail, parse its date'''
    page = request.urlopen(mail_url).read()
    soup = BeautifulSoup(page, 'lxml')
    return soup.body.i.string

def get_month(s):
    '''Get full name of a month given abbreviation (or None).
    e.g.
        january -> January
        JAN -> January
        foo -> None
        None -> <name of current month>'''

    if s is None:
        return month_names[maya.now().month]
    s = s.capitalize()
    if s in month_names:
        return s
    try:
        i = short_month_names.index(s)
        return month_names[i]
    except ValueError:
        return None

def pipermail_combo(args):
    '''Returns a ('year', 'month') tuple to be used in pipermail URLs.'''

    cur_year = str(maya.now().year)
    if args is None or len(args) == 0:
        # If args is None or empy, returns current year and month
        return (cur_year, get_month(None))
    elif len(args) == 1:
        # If only one was provided, try to check if it's year or month
        # and fill missing value
        if args[0].isnumeric():
            return (args[0], get_month(None))
        else:
            return (cur_year, get_month(args[0]))
    if args[0].isnumeric():
        return (args[0], get_month(args[1]))
    return (cur_year, get_month(args[1]))

def get_month_url(year, month):
    '''Return the URL of the page containing month threads'''

    return 'http://lists.python.it/pipermail/pycon/{}-{}/'.format(year, month)

def threads_for_month(year, month):
    '''Generates threads in the specified month'''

    base_url = get_month_url(year, month)
    thread_url = base_url + 'thread.html'
    logging.info('Reading page %s', thread_url)
    page = request.urlopen(thread_url).read()
    # pipermail omits closing tags: html.parser fails to parse correctly
    soup = BeautifulSoup(page, 'lxml')
    # Extract the first level of the hierarchy
    topics = soup.body.find_all('ul', recursive=False)[1].find_all('li', recursive=False)
    # Build threads
    for t in topics:
        msg = t.a.string.strip()
        url = t.a.get('href')
        post_date = get_date(base_url + url)
        # XXX HORRIBLE patch below! XXX
        # dateparser has a bug with italian Tuesday abbreviation
        # it will not parse correctly Mar 7 Mar 2017 (Tue 7 Mar 2017)
        # so we skip the day of the week if "Mar" present
        # FIXME
        # Check status of https://github.com/scrapinghub/dateparser/issues/337
        # before fixing
        # FIXME
        if post_date[:3].lower() == 'mar':
            date = maya.when(post_date[4:])
        else:
            date = maya.when(post_date)
        yield (date, msg, url)

def set_last_check(bot, update):
    '''Changes date of last check. Useful when testing the bot or setting it up.'''

    global last_check

    text = update.message.text
    logging.info('Setting last check with %s', text)

    try:
        skip = text.index(' ') + 1
        day = maya.when(text[skip:])
        logging.info('Parsed date: %s', day)
        last_check = day
        bot.send_message(chat_id=update.message.chat_id, text='Setting last check: ' + day.rfc2822())
    except ValueError:
        bot.send_message(chat_id=update.message.chat_id, text='Send a date in unambiguous format (e.g. yyyy-mm-dd)')

def months_after(date):
    '''Iterates (year,month) tuples after the specified date, till today'''

    today = maya.now()
    start = 12 * date.year + date.month
    end = 12 * today.year + today.month + 1
    for mm in range(start, end):
        y, m = divmod(mm, 12)
        yield (str(date.year), month_names[m])

def build_thread_row(date, message, url):
    '''Returns a string for a thread'''

    label = '{} {}'.format(message, date.rfc2822())
    return ' - <a href="{}">{}</a>'.format(url, label)

def check_new_threads(bot, job):
    '''This function is called periodically to check if new threads are present since last check.'''

    global last_check
    logging.info('Checking for new threads since {}'.format(last_check.rfc2822()))
    # Threads found
    new_threads = []
    # Iterate over all threads after the last check date
    for year, month in months_after(last_check):
        base_url = get_month_url(year, month)
        for td, tm, tu in threads_for_month(year, month):
            if td <= last_check:
                continue # Already checked
            logging.info('Found a thread in month {}-{}'.format(year, month, tm))
            new_threads.append(build_thread_row(td, tm, base_url+tu))#row)

    # Set last check
    last_check = maya.now()

    # Write only if necessary
    if new_threads:
        out = '<b>New threads since {}</b>\n'.format(last_check.rfc2822())
        out += '\n'.join(new_threads)
        bot.send_message(
            chat_id=job.context,
            parse_mode=telegram.ParseMode.HTML,
            text=out,
        )

def threads(bot, update, args):
    '''Prints threads in a specified year-month'''

    # Parse arguments as date
    date = maya.when(' '.join(args))
    # If we couldn't parse, use now
    if date is None:
        date = maya.now()
    # Get arguments in suitable format
    args = (str(date.year), month_names[date.month])
    # Output string we are building
    out = '<b>Threads {} {}</b>\n'.format(*args)

    base_url = get_month_url(*args)
    for td, tm, tu in threads_for_month(*args):
        out += build_thread_row(td, tm, base_url+tu) + '\n'

    bot.send_message(
        chat_id=update.message.chat_id,
        parse_mode=telegram.ParseMode.HTML,
        text=out,
    )

def start(bot, update, job_queue):
    '''Starts the bot, setting up repeated check and printing welcome message'''

    global last_check
    last_check = maya.now()
    bot.send_message(chat_id=update.message.chat_id,
        text="*Welcome!*\nGet threads with /th 2016 July\nSet Last Check date with /slc 1 maggio 2017\n\nBot will check for new threads every 2 minutes",
        parse_mode=telegram.ParseMode.MARKDOWN)
    job_queue.run_repeating(check_new_threads, 120.0, context=update.message.chat_id)

# Setup bot
with open('./bot.key') as keyfile:
    updater = Updater(token=keyfile.read().strip())

dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler('start', start, pass_job_queue=True))
dispatcher.add_handler(CommandHandler('threads', threads, pass_args=True))
dispatcher.add_handler(CommandHandler('th', threads, pass_args=True))
dispatcher.add_handler(CommandHandler('setlastcheck', set_last_check))
dispatcher.add_handler(CommandHandler('slc', set_last_check))

updater.start_polling()
