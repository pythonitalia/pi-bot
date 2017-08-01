#!/usr/bin/env python3

import unittest
import mlbot

import datetime as dt
import dateparser as dp
import locale

class TestPage(unittest.TestCase):
    '''This class tests that the pipermail webpage is still as we expect it.'''
    def test_get_date(self):
        # Set locale used for dates
        locale.setlocale(locale.LC_TIME, 'it_IT')

        base = 'http://lists.python.it/pipermail/pycon/'
        url_dates = [
            ('2017-May/002516.html', 'Lun 29 Mag 2017 12:20:58 CEST'), # This was "Maggio" on the website
            ('2017-July/002569.html', 'Lun 31 Lug 2017 11:28:30 CEST'),
            ('2015-March/000863.html', 'Mar 17 Mar 2015 14:59:58 CET'),
            ('2014-October/000017.html', 'Mer 15 Ott 2014 16:57:03 CEST'),
            ('2017-July/002552.html', 'Gio 20 Lug 2017 10:57:40 CEST'),
            ('2015-March/000912.html', 'Ven 20 Mar 2015 17:40:22 CET'),
            ('2015-March/000765.html', 'Dom 1 Mar 2015 12:22:43 CET'),
            ('2015-March/000838.html', 'Mer 4 Mar 2015 14:02:16 CET'),
        ]

        for u, d in url_dates:
            pd = dp.parse(d, date_formats=['%a %d %b %Y %H:%M:%S %Z'], settings={'RETURN_AS_TIMEZONE_AWARE': True})
            dd = mlbot.get_date(base + u)
            self.assertEqual(pd, dd)

    def test_for_month(self):
        threads = [
            ('2017-06-12 10:46:44', '[Pycon] PyCon Italia 9?', '002524.html'),
            ('2017-06-14 06:12:16', '[Pycon] Necessito di ricevuta!', '002537.html'),
            ('2017-06-15 11:17:16', '[Pycon] Feedback di PyCon 8!', '002546.html'),
        ]

        for gt, ft in zip(mlbot.threads_for_month('2017', 'June'), threads):
            self.assertEqual(gt[1:], ft[1:])
            # Convert time and check that
            gd = dt.datetime.strftime(gt[0], '%Y-%m-%d %H:%M:%S')
            self.assertEqual(ft[0], gd)

    def test_bot_months_iter(self):
        bot = mlbot.MailingListBot()
        n = 36
        for i, ym in enumerate(bot.months_after(dp.parse('{} months ago'.format(n)))):
            pdate = dp.parse(' '.join(ym))
            cdate = dp.parse('{} months ago'.format(n - i))
            self.assertEqual(pdate.year, cdate.year)
            self.assertEqual(pdate.month, cdate.month)

if __name__ == '__main__':
    unittest.main()
