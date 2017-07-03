#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Imports from Python Standard Library
import base64
import datetime as dt
import json
import logging
import os.path
from argparse import ArgumentParser
from configparser import ConfigParser
from html.parser import HTMLParser
from sys import path
# Third party imports
import click
import requests
# Custom imports
from google_auth import GoogleAuth
from hangoutsclient import HangoutsClient

# Get absolute path of the dir script is run from
CWD = path[0]  # pylint: disable=C0103


class LinkParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.link = []
        self.lasttag = None

    def handle_starttag(self, tag, attr):
        self.lasttag = tag.lower()

    def handle_data(self, data):
        if self.lasttag == "a" and data.strip():
            self.link = data

    def error(self, message):
        pass


def validate_time(ctx, param, time_str):
    try:
        time = dt.datetime.strptime(time_str, "%H%M")
    except ValueError:
        raise click.BadParameter('Time should be in HHMM format')
    return time


@click.command()
@click.option('--after', '-a', default='0830',
              callback=validate_time, expose_value=True,
              help='"after" time in hhmm format. Default 0830.')
@click.option('--before', '-b', default='1730',
              callback=validate_time, expose_value=True,
              help='"before" time in hhmm format. Default 1730.')
def main(before, after):
    """
    Catch up on links sent during the day from a specified Hangouts contact.
    Hangouts messages are parsed through Gmail API.

    OAuth for devices doesn't support Hangouts or Gmail scopes, so have to send auth link through the terminal.
    https://developers.google.com/identity/protocols/OAuth2ForDevices
    """

    # Path to config file
    config_path = os.path.join(CWD, 'linkgrabber.ini')
    logging.debug('Using config file: %s', config_path)

    # Read in config values
    config = ConfigParser()
    config.read(config_path)
    chat_partner = config.get('Settings', 'chat_partner')  # Name or email of the chat partner to search chat logs for

    # Setup Google OAUTH instance for accessing Gmail
    oauth2_scope = ('https://www.googleapis.com/auth/gmail.readonly '
                    'https://www.googleapis.com/auth/userinfo.email')
    oauth = GoogleAuth(config_path, oauth2_scope, service='Gmail')
    oauth.google_authenticate()

    # Get email address so we can filter out messages sent by user later on
    user = oauth.google_get_email()

    # Retrieves all Hangouts chat messages received during 8.30AM and 17.30PM on the current day
    logging.debug('Getting emails for: %s', user)
    current_date = dt.datetime.today()
    before_timestamp = int(current_date.replace(hour=before.hour, minute=before.minute).timestamp())
    after_timestamp = int(current_date.replace(hour=after.hour, minute=after.minute).timestamp())
    request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages?q="after:{0} before:{1} from:{2}"'.format(
        after_timestamp, before_timestamp, chat_partner)
    logging.debug('URL for chat log search: %s', request_url)
    authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
    resp = requests.get(request_url, headers=authorization_header)
    logging.debug('Authorisation result: %s', resp.status_code)
    data = resp.json()

    # Extract links from chat logs
    links = []
    parser = LinkParser()
    if 'messages' in data:
        for message in data['messages']:
            request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages/{0}?'.format(message['id'])
            authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
            resp = requests.get(request_url, headers=authorization_header)  # get message data
            logging.debug('Message query result: %s', resp.status_code)

            if resp.status_code == 200:
                data = json.loads(resp.text)  # requests' json() method seems to have issues handling this response
                sender = data['payload']['headers'][0]['value']
                # Since the gmail API doesn't appear to support the 'in:chats/is:chat' query anymore,
                # we end up pulling both emails and chat messages, but the data structures are different so
                # wrapping this in a try-except as a quick-and-dirty fix to ignore all email messages
                try:
                    decoded_raw_text = base64.urlsafe_b64decode(data['payload']['body']['data']).decode('utf-8')
                except KeyError:
                    break

                # ignore messages sent by us, we only want links that chat partner has sent
                if user not in sender and 'href' in decoded_raw_text:
                    parser.feed(decoded_raw_text)
                    link = parser.link
                    links.append(link)
    else:
        logging.info('No messages found')

    if links:
        message = 'Links from today:\n' + ' \n'.join(links)
        # Setup Hangouts bot instance, connect and send message.
        hangouts = HangoutsClient(config_path, message)
        if hangouts.connect(address=('talk.google.com', 5222),
                            reattempt=True, use_tls=True):
            hangouts.process(block=True)
            logging.info("Finished sending message")
        else:
            logging.error('Unable to connect to Hangouts.')
    else:
        logging.info('No new links!')


def configure_logging():
    # Configure root logger. Level 5 = verbose to catch mostly everything.
    logger = logging.getLogger()
    logger.setLevel(level=5)
    log_filename = 'linkgrabber_{0}.log'.format(dt.datetime.now().strftime('%Y%m%d_%Hh%Mm%Ss'))
    log_handler = logging.FileHandler(os.path.join(CWD, 'logs', log_filename))
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
    configure_logging()
    main()
