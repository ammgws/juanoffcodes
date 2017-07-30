#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Imports from Python Standard Library
import base64
import datetime as dt
import email
import json
import logging
import os.path
import re
from time import sleep
# Third party imports
import click
import requests
# Custom imports
from google_auth import GoogleAuth
from hangoutsclient import HangoutsClient


def get_soccer_dates(config_path):
    """
    Generator that returns datetime object for each soccer match date found in local file.
    soccer.txt should have match dates in YYYYMMDD format with each on a new line.
    """
    with open(os.path.join(config_path, 'soccer.txt'), 'r') as f:
        soccer_dates = f.readlines()
    for date_str in soccer_dates:
        yield dt.datetime.strptime(date_str.strip(), '%Y%m%d').date()


def get_last_date(config_path):
    """
    Get the date of last attended event from the last time this script was run.
    """
    try:
        with open(os.path.join(config_path, 'last_date.txt'), 'r') as f:
            last_date = f.readline()
    except IOError as e:
        # TODO: better return value
        return None
    return dt.datetime.strptime(last_date.strip(), '%Y%m%d').date()


def parse_loglevel(ctx, param, log_level_str):
    log_levels = {'debug': logging.DEBUG,
                  'info': logging.INFO,
                  'warning': logging.WARNING,
                  'error': logging.ERROR,
                  }
    return log_levels[log_level_str]


@click.command()
@click.option('--config_path', '-c', default=os.path.expanduser('~/.config/futsal_shamer'), type=click.Path(exists=True),
              help='path to directory containing config file.')
@click.option('--cut_off', '-c', default=7, help='Number of days to allow between attended events before shaming.')
@click.option('--log_level', '-l', callback=parse_loglevel, expose_value=True,
              default='debug', type=click.Choice(['debug', 'info', 'warning', 'error']), help='Set log level.')
def main(config_path, cut_off, log_level):
    """
    Check Gmail for futsal confirmation emails, and send 'shame' message on Hangouts if haven't been in the past week.

    OAuth for devices doesn't support Hangouts or Gmail scopes, so have to send auth link through the terminal.
    https://developers.google.com/identity/protocols/OAuth2ForDevices
    """
    configure_logging(config_path, log_level)

    config_file = os.path.join(config_path, 'futsal.ini')
    logging.debug('Using config file: %s', config_file)

    # Setup Google OAUTH instance for acccessing Gmail
    oauth2_scope = ('https://www.googleapis.com/auth/gmail.readonly '
                    'https://www.googleapis.com/auth/userinfo.email')
    oauth = GoogleAuth(config_file, oauth2_scope, service='Gmail')
    oauth.authenticate()

    # Retrieves all messages received in the past x days:
    logging.debug('Getting emails for: %s', oauth.get_email())
    current_date = dt.datetime.today()
    after = (current_date - dt.timedelta(days=cut_off)).strftime('%Y/%m/%d')
    request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages?q="after:{0}"'.format(after)
    authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
    resp = requests.get(request_url, headers=authorization_header)
    data = resp.json()

    # Extract futsal event dates from email message body to check date of last event.
    event_dates = list(get_soccer_dates(config_path))  # initialise with soccer match dates, since won't have futsal those days
    had_event_this_week = 0
    if 'messages' in data:
        for message in data['messages']:
            request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages/{0}?format=raw'.format(message['id'])
            authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
            resp = requests.get(request_url, headers=authorization_header)  # get raw email data

            if resp.status_code == 200:
                data = json.loads(resp.text)  # requests' json() method seems to have issues handling this response
                email_datetime = dt.datetime.fromtimestamp(int(data['internalDate'])/1000)  # get epoch time in seconds
                decoded_raw_text = base64.urlsafe_b64decode(data['raw'])
                parsed_raw_text = email.message_from_bytes(decoded_raw_text)

                for part in parsed_raw_text.walk():
                    decoded_message = part.get_payload(decode=True)
                    if decoded_message:
                        # strip html tags, using http://stackoverflow.com/a/4869782
                        cleaned_message = re.sub('<[^<]+?>', '', decoded_message.decode('utf-8'))
                        # get futsal event date part of string
                        date_prefixes = ['第１希望：', '日程：']
                        for prefix in date_prefixes:
                            try:
                                futsal_date_str = cleaned_message.split(prefix, 1)[1][:5]
                                # futsal confirmation email doesn't include the year, so assume the year from the email timestamp
                                futsal_date = dt.datetime.strptime(futsal_date_str, "%m/%d").replace(year=email_datetime.year).date()
                                event_dates.append(futsal_date)
                            except IndexError:
                                pass

                # TODO: clean up code below, handle case of multiple dates from the same week
                for date in event_dates:
                    if date < (current_date - dt.timedelta(days=cut_off)).date():
                        had_event_this_week = -1
    else:
        # did not find any mails, so must not have booked futsal
        logging.info('No mails found from the past week')
        had_event_this_week = -1

    last_event = get_last_date(config_path)
    if last_event >= (current_date - dt.timedelta(days=cut_off)).date():
                        had_event_this_week = 0

    if had_event_this_week == -1:
        message = 'Someone has been naughty. Last attended futsal or soccer was on {0}.'.format(
            last_event.strftime('%Y/%m/%d'))

        # Setup Hangouts bot instance, connect and send message.
        hangouts = HangoutsClient(config_file)
        if hangouts.connect():
            hangouts.process(block=False)
            sleep(5)  # need time for Hangouts roster to update
            hangouts.send_to_all(message)
            hangouts.disconnect(wait=True)
            logging.info("Finished sending message")
        else:
            logging.error('Unable to connect to Hangouts.')
    else:
        logging.info('Went to event in the past week - no need to send shaming message!')

    if max(event_dates) > last_event:
        last_event = max(event_dates)
    with open(os.path.join(config_path, 'last_date.txt'), 'w') as f:
        f.write(last_event.strftime('%Y%m%d'))


def configure_logging(config_path, log_level):
    # Configure root logger.
    logger = logging.getLogger()
    logger.setLevel(level=log_level)

    log_folder = os.path.join(config_path, 'logs')
    if not os.path.exists(log_folder):
        os.makedirs(log_folder, exist_ok=True)

    log_filename = 'futsal_{0}.log'.format(dt.datetime.now().strftime('%Y%m%d_%Hh%Mm%Ss'))
    log_filepath = os.path.join(log_folder, log_filename)
    log_handler = logging.FileHandler(log_filepath)

    log_format = logging.Formatter(
        fmt='%(asctime)s.%(msecs).03d %(name)-12s %(levelname)-8s %(message)s (%(filename)s:%(lineno)d)',
        datefmt='%Y-%m-%d %H:%M:%S')
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)
    # Lower requests module's log level so that OAUTH2 details aren't logged
    logging.getLogger('requests').setLevel(logging.WARNING)
    # Quieten SleekXMPP output
    # logging.getLogger('sleekxmpp.xmlstream.xmlstream').setLevel(logging.INFO)


if __name__ == '__main__':
    main()
