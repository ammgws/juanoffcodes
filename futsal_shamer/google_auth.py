# Imports from Python Standard Library
import datetime as dt
import logging
from configparser import ConfigParser
from urllib.parse import urlencode

# Third party imports
import requests


class GoogleAuth(object):
    def __init__(self, config_path, scope, service='Hangouts'):
        # Set instance variables
        self.config_path = config_path
        self.oauth2_scope = scope
        self.service = service
        self.access_token = None
        self.token_expiry = None  # access token expiry time

        # Get OAUTH info from config file
        self.config = ConfigParser()
        self.config.read(self.config_path)
        self.client_id = self.config.get(self.service, 'client_id')
        self.client_secret = self.config.get(self.service, 'client_secret')
        self.refresh_token = self.config.get(self.service, 'refresh_token')

    def google_authenticate(self):
        """ Get access token. Note that Google access tokens expire in 3600 seconds."""
        # Authenticate with Google and get access token.
        if not self.refresh_token:
            # If no refresh token is found in config file, then need to start
            # new authorization flow and get access token that way.
            # Note: Google has limit of 25 refresh tokens per user account per
            # client. When limit reached, creating a new token automatically
            # invalidates the oldest token without warning.
            # (Limit does not apply to service accounts.)
            # https://developers.google.com/accounts/docs/OAuth2#expiration
            logging.debug('No refresh token in config file (val = %s of type %s). '
                          'Need to generate new token.',
                          self.refresh_token,
                          type(self.refresh_token))
            # Get authorisation code from user
            auth_code = self.google_authorisation_request()
            # Request access token using authorisation code
            self.google_token_request(auth_code)
            # Save refresh token for next login attempt or application startup
            self.config.set(self.service, 'refresh_token', self.refresh_token)
            with open(self.config_path, 'w') as config_file:
                self.config.write(config_file)
        elif (self.access_token is None) or (dt.datetime.now() > self.token_expiry):
            # Use existing refresh token to get new access token.
            logging.debug('Using refresh token to generate new access token.')
            # Request access token using existing refresh token
            self.google_token_request()
        else:
            # Access token is still valid, no need to generate new access token.
            logging.debug('Access token is still valid - no need to regenerate.')
            return

    def google_authorisation_request(self):
        """Start authorisation flow to get new access + refresh token."""

        # Start by getting authorization_code for Hangouts scope.
        # Email scope is used to get email address for Hangouts login.
        oauth2_login_url = 'https://accounts.google.com/o/oauth2/v2/auth?{}'.format(
            urlencode(dict(
                client_id=self.client_id,
                scope=self.oauth2_scope,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob',
                response_type='code',
                access_type='offline',
            ))
        )

        # Print auth URL and wait for user to grant access and
        # input authentication code into the console.
        print(oauth2_login_url)
        auth_code = input("Enter auth code from the above link: ")
        return auth_code

    def google_token_request(self, auth_code=None):
        """Make an access token request and get new token(s).
           If auth_code is passed then both access and refresh tokens will be
           requested, otherwise the existing refresh token is used to request
           an access token.

           Update the following class variables:
            access_token
            refresh_token
            token_expiry
           """
        # Build request parameters. Order doesn't seem to matter, hence using dict.
        token_request_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        if auth_code is None:
            # Use existing refresh token to get new access token.
            token_request_data['refresh_token'] = self.refresh_token
            token_request_data['grant_type'] = 'refresh_token'
        else:
            # Request new access and refresh token.
            token_request_data['code'] = auth_code
            token_request_data['grant_type'] = 'authorization_code'
            # 'urn:ietf:wg:oauth:2.0:oob' signals to the Google Authorization
            # Server that the authorization code should be returned in the
            # title bar of the browser, with the page text prompting the user
            # to copy the code and paste it in the application.
            token_request_data['redirect_uri'] = 'urn:ietf:wg:oauth:2.0:oob'
            token_request_data['access_type'] = 'offline'

        # Make token request to Google.
        oauth2_token_request_url = 'https://www.googleapis.com/oauth2/v4/token'
        resp = requests.post(oauth2_token_request_url, data=token_request_data)
        # If request is successful then Google returns values as a JSON array
        values = resp.json()
        self.access_token = values['access_token']
        if auth_code:  # Need to save value of new refresh token
            self.refresh_token = values['refresh_token']
        self.token_expiry = dt.datetime.now() + dt.timedelta(seconds=int(values['expires_in']))
        logging.info('Access token expires on %s', self.token_expiry.strftime("%Y/%m/%d %H:%M"))

    def google_get_email(self):
        """Get client's email address."""
        authorization_header = {"Authorization": "OAuth %s" % self.access_token}
        resp = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                            headers=authorization_header)
        # If request is successful then Google returns values as a JSON array
        values = resp.json()
        return values['email']
