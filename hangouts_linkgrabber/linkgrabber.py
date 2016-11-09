#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Imports from Python Standard Library
import base64
import datetime as dt
import json
import logging
import os.path
from configparser import ConfigParser
from html.parser import HTMLParser
from sys import path
# Third party imports
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


def main():
    """
    Check Gmail for Hangouts chat messages, and check for any links inside.

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
    before = int(current_date.replace(hour=17, minute=30).timestamp())
    after = int(current_date.replace(hour=8, minute=30).timestamp())
    request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages?q="in:chats after:{0} before:{1} from:{2}"'.format(
        after, before, chat_partner)
    authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
    resp = requests.get(request_url, headers=authorization_header)
    data = resp.json()

    # Extract links from chat logs
    links = []
    parser = LinkParser()
    if 'messages' in data:
        for message in data['messages']:
            request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages/{0}?'.format(message['id'])
            authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
            resp = requests.get(request_url, headers=authorization_header)  # get message data

            if resp.status_code == 200:
                data = json.loads(resp.text)  # requests' json() method seems to have issues handling this response
                # get message sender
                sender = data['payload']['headers'][0]['value']
                # get message text
                decoded_raw_text = base64.urlsafe_b64decode(data['payload']['body']['data']).decode('utf-8')

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


if __name__ == '__main__':
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

    main()
