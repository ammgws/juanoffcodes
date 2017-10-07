#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Standard Library
import base64
import datetime as dt
import email
import json
import logging
import os.path
import re
from configparser import ConfigParser
from pathlib import Path
from time import sleep
# Third party
import click
import requests
from google_auth import GoogleAuth
from hangoutsclient import HangoutsClient

APP_NAME = 'futsal_shamer'


def get_soccer_dates(config_path):
    """Generator that returns datetime object for each soccer match date found in local file.
    soccer.txt should have match dates in YYYYMMDD format with each on a new line.
    """
    with open(os.path.join(config_path, 'soccer.txt')) as f:
        soccer_dates = f.readlines()
    for date_str in soccer_dates:
        yield dt.datetime.strptime(date_str.strip(), '%Y%m%d').date()


def get_last_date(cache_path):
    """Get the date of last attended event from the last time this script was run.
    """
    try:
        with open(os.path.join(cache_path, 'last_date')) as f:
            last_date = f.read().strip()
    except IOError as e:
        # TODO: better return value
        return None
    return last_date


def write_last_date(cache_path, last_event_str):
    with open(os.path.join(cache_path, 'last_date'), 'w') as f:
        f.write(last_event_str)


def parse_loglevel(ctx, param, log_level_str):
    log_levels = {'debug': logging.DEBUG,
                  'info': logging.INFO,
                  'warning': logging.WARNING,
                  'error': logging.ERROR,
                  }
    return log_levels[log_level_str]


def validate_cutoff(ctx, param, cut_off):
    if cut_off < 0:
        raise click.BadParameter('Cut-off must be a positive integer.')
    else:
        return cut_off


def validate_date(ctx, param, date):
    try:
        dt.datetime.strptime(date, '%Y%m%d')
    except ValueError:
        raise click.BadParameter('Date should be in YYYYMMDD format')
    except TypeError:
        # TODO: Click seems to use callback even if option is not supplied when run.
        #       This means that this date validation will fail when last-date is not given as date will be None...
        return date
    return date


def create_dir(ctx, param, directory):
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    return directory


@click.command()
@click.option(
    '--config-path',
    type=click.Path(),
    default=os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), APP_NAME),
    callback=create_dir,
    help='Path to directory containing config file. Defaults to XDG config dir.',
)
@click.option(
    '--cache-path',
    type=click.Path(),
    default=os.path.join(os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache')), APP_NAME),
    callback=create_dir,
    help='Path to directory to store logs and such. Defaults to XDG cache dir.',
)
@click.option(
    '--cut-off',
    default=7,
    callback=validate_cutoff, expose_value=True,
    help='Number of days to allow between attended events before shaming.',
)
@click.option(
    '--last-date',
    type=click.STRING,
    callback=validate_date, expose_value=True,
    help='Date of last event.',
)
@click.option(
    '--log-level',
    type=click.Choice(['debug', 'info', 'warning', 'error']),
    callback=parse_loglevel, expose_value=True,
    default='debug',
    help='Set log level.',
)
def main(config_path, cache_path, cut_off, last_date, log_level):
    """Check Gmail for futsal confirmation emails and send 'shame' message on Hangouts if haven't been in the past week.

    NOTE:
    OAuth for devices doesn't support Hangouts or Gmail scopes, so have to send auth link through the terminal.
    https://developers.google.com/identity/protocols/OAuth2ForDevices
    """
    configure_logging(cache_path, log_level)

    # TODO: config from env vars

    config_file = os.path.join(config_path, 'futsal.ini')
    logging.debug('Using config file: %s.', config_file)
    config = ConfigParser()
    config.read(config_file)
    gmail_client_id = config.get('Gmail', 'client_id')
    gmail_client_secret = config.get('Gmail', 'client_secret')
    gmail_refresh_token = os.path.join(cache_path, 'gmail_refresh_token')
    if not os.path.isfile(gmail_refresh_token):
        Path(gmail_refresh_token).touch()
    hangouts_client_id = config.get('Hangouts', 'client_id')
    hangouts_client_secret = config.get('Hangouts', 'client_secret')
    hangouts_refresh_token = os.path.join(cache_path, 'hangouts_refresh_token')
    if not os.path.isfile(hangouts_refresh_token):
        Path(hangouts_refresh_token).touch()

    # Setup Google OAUTH instance for acccessing Gmail.
    gmail_scopes = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
    ]
    oauth = GoogleAuth(gmail_client_id, gmail_client_secret, gmail_scopes, gmail_refresh_token)
    oauth.authenticate()

    # Retrieves all messages received in the past x days:
    logging.debug('Getting emails for: %s.', oauth.get_email())
    current_date = dt.datetime.today()
    after = (current_date - dt.timedelta(days=cut_off)).strftime('%Y/%m/%d')
    url = f'https://www.googleapis.com/gmail/v1/users/me/messages?q="after:{after}"'
    authorization_header = {'Authorization': 'OAuth {oauth.access_token}'}
    resp = requests.get(url, headers=authorization_header)
    data = resp.json()

    # Extract futsal event dates from email message body to check date of last event.
    # Initialise with Sunday league match dates, since won't have futsal those days.
    event_dates = list(get_soccer_dates(config_path))
    had_event_this_week = 0
    if 'messages' in data:
        for message in data['messages']:
            url = f'https://www.googleapis.com/gmail/v1/users/me/messages/{message["id"]}?format=raw'
            authorization_header = {f'Authorization': 'OAuth {oauth.access_token}'}
            resp = requests.get(url, headers=authorization_header)  # Raw email data.

            if resp.status_code == 200:
                data = json.loads(resp.text)  # requests' json() method seems to have issues handling this response.
                email_dt = dt.datetime.fromtimestamp(int(data['internalDate'])/1000)  # Google gives epoch in μs.
                decoded_raw_text = base64.urlsafe_b64decode(data['raw'])
                parsed_raw_text = email.message_from_bytes(decoded_raw_text)

                for part in parsed_raw_text.walk():
                    decoded_message = part.get_payload(decode=True)
                    if decoded_message:
                        # Strip html tags (see http://stackoverflow.com/a/4869782).
                        cleaned_message = re.sub('<[^<]+?>', '', decoded_message.decode('utf-8'))
                        # Get futsal event date part of string.
                        date_prefixes = ['第１希望：', '日程：']
                        for prefix in date_prefixes:
                            try:
                                date_str = cleaned_message.split(prefix, 1)[1][:5]
                                # Confirmation email doesn't include the year, so assume the year from email timestamp.
                                futsal_date = dt.datetime.strptime(date_str, '%m/%d').replace(year=email_dt.year).date()
                                event_dates.append(futsal_date)
                            except IndexError:
                                pass

                # TODO: clean up code below, handle case of multiple dates from the same week
                for date in event_dates:
                    if date < (current_date - dt.timedelta(days=cut_off)).date():
                        had_event_this_week = -1
    else:
        logging.info('No mails found from the past week.')
        had_event_this_week = -1

    last_event_str = last_date or get_last_date(cache_path)
    last_event = dt.datetime.strptime(last_event_str, '%Y%m%d').date()
    if max(event_dates) > last_event:
        last_event = max(event_dates)

    write_last_date(cache_path, last_event.strftime('%Y%m%d'))

    if last_event >= (current_date - dt.timedelta(days=cut_off)).date():
        had_event_this_week = 0

    if had_event_this_week == -1:
        message = f'Someone has been naughty. Last attended futsal or soccer was on {last_event.strftime("%Y/%m/%d")}.'

        hangouts = HangoutsClient(hangouts_client_id, hangouts_client_secret, hangouts_refresh_token)
        if hangouts.connect():
            hangouts.process(block=False)
            sleep(5)  # Need time for Hangouts roster to update.
            hangouts.send_to_all(message)
            hangouts.disconnect(wait=True)
            logging.info('Finished sending message.')
        else:
            logging.error('Unable to connect to Hangouts.')
    else:
        logging.info('Went to event in the past week - no need to send shaming message!')


def configure_logging(log_dir, log_level):
    # Configure root logger.
    logger = logging.getLogger()
    logger.setLevel(level=log_level)

    log_folder = os.path.join(log_dir, 'logs')
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    log_filename = 'futsal_{0}.log'.format(dt.datetime.now().strftime('%Y%m%d_%Hh%Mm%Ss'))
    log_filepath = os.path.join(log_folder, log_filename)
    log_handler = logging.FileHandler(log_filepath)

    log_format = logging.Formatter(
        fmt='%(asctime)s.%(msecs).03d %(name)-12s %(levelname)-8s %(message)s (%(filename)s:%(lineno)d)',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)
    # Lower requests module's log level so that OAUTH2 details aren't logged.
    logging.getLogger('requests').setLevel(logging.WARNING)
    # Quieten SleekXMPP output.
    # logging.getLogger('sleekxmpp.xmlstream.xmlstream').setLevel(logging.INFO)


if __name__ == '__main__':
    main()
