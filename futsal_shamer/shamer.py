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
from configparser import ConfigParser
from sys import path
# Third party imports
import requests
# Custom imports
from google_auth import GoogleAuth
from hangoutsclient import HangoutsClient

# Get absolute path of the dir script is run from
CWD = path[0]  # pylint: disable=C0103


def main():
    """
    Check Gmail for futsal confirmation emails, and send 'shame' message on Hangouts if haven't been in the past week.

    OAuth for devices doesn't support Hangouts or Gmail scopes, so have to send auth link through the terminal.
    https://developers.google.com/identity/protocols/OAuth2ForDevices
    """

    # Path to config file
    config_path = os.path.join(CWD, 'futsal.ini')

    # Read in config values
    config = ConfigParser()
    config.read(config_path)
    config_path = config_path
    logging.debug('Using config file: %s', config_path)

    # Setup Google OAUTH instance for acccessing Gmail
    oauth2_scope = ('https://www.googleapis.com/auth/gmail.readonly '
                    'https://www.googleapis.com/auth/userinfo.email')
    oauth = GoogleAuth(config_path, oauth2_scope, service='Gmail')
    oauth.google_authenticate()

    # Retrieves all messages received in the past 3 days:
    logging.debug('Getting emails for: %s', oauth.google_get_email())
    current_date = dt.datetime.today()
    before = current_date.strftime("%Y/%m/%d")
    after = (current_date - dt.timedelta(days=3)).strftime("%Y/%m/%d")
    request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages?q="after:{0} before:{1}"'.format(after, before)
    authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
    resp = requests.get(request_url, headers=authorization_header)
    data = resp.json()

    # Extract futsal event dates from email message body, to check date of last event.
    futsal_dates = {}
    for message in data['messages']:
        request_url = 'https://www.googleapis.com/gmail/v1/users/me/messages/{0}?format=raw'.format(message['id'])
        authorization_header = {"Authorization": "OAuth %s" % oauth.access_token}
        resp = requests.get(request_url, headers=authorization_header)  # get raw email data

        if resp.status_code == 200:
            data = json.loads(resp.text)  # requests' json() method seems to have issues handling this response
            decoded_raw_text = base64.urlsafe_b64decode(data['raw'])
            parsed_raw_text = email.message_from_bytes(decoded_raw_text)

            for part in parsed_raw_text.walk():
                decoded_message = part.get_payload(decode=True)
                if decoded_message:
                    # strip html tags, using http://stackoverflow.com/a/4869782
                    cleaned_message = re.sub('<[^<]+?>', '', decoded_message.decode('utf-8'))
                    # get futsal event date part of string
                    futsal_date_str = cleaned_message.split('日程：', 1)[1][:4]
                    futsal_dates[futsal_date_str] = 'booked'

    # TO DO: clean up code below, handle case of multiple dates from the same week, Save last attended date somewhere?
    had_futsal_this_week = 0
    futsal_date = 0
    for date in futsal_dates:
        # futsal confirmation email doesn't include the year, but we can assume any mails are from current year for now
        futsal_date = dt.datetime.strptime(date, "%m/%d").replace(year=current_date.year).date()
        if futsal_date < (current_date - dt.timedelta(days=5)).date():
            had_futsal_this_week = -1

    if had_futsal_this_week == -1:
        message = 'Someone has been a naughty boy. Has not been to futsal for a week. Last futsal was on {0}.'.format(
            futsal_date.strftime('%Y/%m/%d'))
        # Setup Hangouts bot instance, connect and send message.
        hangouts = HangoutsClient(config_path, message)
        if hangouts.connect(address=('talk.google.com', 5222),
                            reattempt=True, use_tls=True):
            hangouts.process(block=True)
            logging.info("Finished sending message")
        else:
            logging.error('Unable to connect to Hangouts.')


if __name__ == '__main__':
    # Configure root logger. Level 5 = verbose to catch mostly everything.
    logger = logging.getLogger()
    logger.setLevel(level=5)
    log_filename = 'futsal_{0}.log'.format(dt.datetime.now().strftime('%Y%m%d_%Hh%Mm%Ss'))
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
