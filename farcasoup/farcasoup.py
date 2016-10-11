#!/usr/bin/env python

import calendar
import datetime as dt
import fileinput
import re
import smtplib
import subprocess
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import urllib2
from bs4 import BeautifulSoup

username = "xxx@yyy.com"
password = "password"


def send_notice(match_date):
    msg = MIMEMultipart()
    msg['Subject'] = 'Download Notice for Match xxx'
    msg['From'] = username
    msg['To'] = 'yyy@zzz.com'

    text = MIMEText('Farca match date ' + str(match_date) + ' successfully sent to download list')
    msg.attach(text)

    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(username, password)
    s.sendmail(username, msg['To'], msg.as_string())
    print('Email notice sent!')
    s.quit()


def create_download_job(links):
    filename = 'myFile' + str(int(calendar.timegm(time.gmtime()))) + '.crawljob'

    f = open(filename, 'a')
    for link in links:
        f.write('\ntext=' + link + '\nautoStart=TRUE\n')
    f.close()

    return filename


def update_matchlist(match_date):
    for line in fileinput.input('matches.txt', inplace=1):
        try:
            if match_date == dt.datetime.strptime(line.strip().split(',')[0], '%d/%m/%Y').date():
                print(line.replace(',0', ',1'))
            else:
                print(line)
        except:
            pass

    to_dropbox('matches.txt', '/')


def get_matches():
    try:
        subprocess.check_call(['./dropbox_uploader.sh', 'download', 'matches.txt'])
    except:
        print('download fail')

    match_file = open('matches.txt', "r")
    match_list = []
    for row in match_file:
        match_list.append(row.strip().split(','))
    match_file.close()

    for match in match_list:
        try:
            if dt.datetime.strptime(match[0], '%d/%m/%Y').date() < dt.datetime.now().date():
                if match[1] == '0':
                    print(match[0])
                    return match[0]
        except:
            pass

    return False


def to_dropbox(filename, directory):
    try:
        subprocess.check_call(['./dropbox_uploader.sh', 'upload', filename, directory])
    except:
        print('upload fail')


def thread_scraper(url):
    """
    scrape thread for Sky Sports HD links on ul.to
    """

    ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:2.0.1) Gecko/20110506 Firefox/4.0.1'
    req = urllib2.Request(url)
    req.add_header('User-Agent', ua)

    try:
        html = (urllib2.urlopen(req)).read()
    except BaseException:
        print('Failed to read URL.')
        exit(1)

    soup = BeautifulSoup(html)
    search = soup.findAll('div', attrs={'class': 'postrow has_after_content'})
    index = 1

    links = False

    keyword_list = ['Sky Sports', 'English', '720p']

    for post in search:

        print('-----------------POST START---------------')

        if index == 1:
            # skip first post since it usually just has quotes of future posts and is annoying to parse
            pass
        elif index > 1:
            if all(keyword in post.renderContents() for keyword in keyword_list):
                print('===============found keywords===========')
                # found the post we're looking for

                # print post number
                # print 'Index:' + str(index)

                raw_links = post.findAll('a', href=True, text=re.compile(r'(http://ul.to/)'))
                links = [link.get('href') for link in raw_links]

                if links:
                    return links

        index += 1

    return links


def forum_scraper(url, matchdate):
    """ 
    scrape forum index to find match thread for given match date (if it exists)
    """

    ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:2.0.1) Gecko/20110506 Firefox/4.0.1'
    req = urllib2.Request(url)
    req.add_header('User-Agent', ua)

    try:
        html = (urllib2.urlopen(req)).read()
    except BaseException:
        print('Failed to read URL.')
        exit(1)

    soup = BeautifulSoup(html)
    search = soup.findAll('div', attrs={'class': 'inner'})
    index = 1
    keyword_list = ['La Liga', 'Copa', 'UEFA Champions', 'UCL']
    found_thread = False

    for base in search:
        title = base.find('h3', attrs={'class': 'threadtitle'}).a.string
        details = base.find('div', attrs={'class': 'author'}).span.a['title']

        if title:
            if title.startswith('FUTBOL'):
                if any(keyword in title for keyword in keyword_list) and 'Barcelona' in title:
                    match = re.search(r'(\d{2}/\d{2}/\d{4})', title)
                    if match:
                        date = dt.datetime.strptime(match.group(1), '%d/%m/%Y').date()
                        if date == match_date:
                            print(title.encode('latin-1'))
                            found_thread = 'http://forum.rojadirecta.es/' + base.find('h3', attrs={
                                'class': 'threadtitle'}).a.get('href').encode('latin-1')
                            break

                    match = re.search(r'(\d{2}/\d{2}/\d{2})', title)
                    if match:
                        date = dt.datetime.strptime(match.group(1), '%d/%m/%y').date()
                        if date == match_date:
                            found_thread = 'http://forum.rojadirecta.es/' + base.find('h3', attrs={
                                'class': 'threadtitle'}).a.get('href').encode('latin-1')
                            break

        index += 1

    return found_thread


def print_start_message():
    print('\n\t Parsing forum for farca')
    print('\n')


if __name__ == '__main__':
    print_start_message()

    match_date = get_matches()
    if match_date:
        match_date = dt.datetime.strptime(match_date, '%d/%m/%Y').date()

    found_thread = False
    if match_date:
        for n in range(1, 25):
            found_thread = forum_scraper(
                'http://forum.rojadirecta.es/forumdisplay.php?15-Partidos-en-descarga-(Full-matches)/page' + str(n),
                match_date)
            if found_thread:
                print(found_thread)
                break

    found_links = False
    if found_thread:
        found_links = thread_scraper(found_thread)

        if found_links:
            filename = create_download_job(found_links)
            to_dropbox(filename, '/fw')
            update_matchlist(match_date)
            send_notice(match_date)
        elif not found_links:
            print('found match thread but not links')

    elif not found_thread:
        print('no match thread found')
