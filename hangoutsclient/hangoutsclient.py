# Imports from Python Standard Library
import logging
import ssl
from configparser import ConfigParser
from time import sleep
# Third party imports
from google_auth import GoogleAuth
from sleekxmpp import ClientXMPP
from sleekxmpp.exceptions import IqError, IqTimeout
from sleekxmpp.xmlstream import cert


class HangoutsClient(ClientXMPP):
    """
    Client for connecting to Hangouts, sending a message to all users in the
    roster, and then disconnecting.
    """

    def __init__(self, config_path, message):
        # Initialise parameters
        self.message = message

        # Read in config values
        self.config = ConfigParser()
        self.config.read(config_path)
        self.config_path = config_path
        logging.debug('Using config file: %s', config_path)

        # Get Hangouts OAUTH info from config file
        self.client_id = self.config.get('Hangouts', 'client_id')
        self.client_secret = self.config.get('Hangouts', 'client_secret')
        self.refresh_token = self.config.get('Hangouts', 'refresh_token')

        # Generate access token
        scope = ('https://www.googleapis.com/auth/googletalk '
                 'https://www.googleapis.com/auth/userinfo.email')
        self.oauth = GoogleAuth(self.config_path, scope, service='Hangouts')
        self.oauth.google_authenticate()

        # Get email address for Hangouts login
        hangouts_login_email = self.oauth.google_get_email()
        logging.debug('Going to login using: %s', hangouts_login_email)

        # Setup new SleekXMPP client to connect to Hangouts.
        # Not passing in actual password since using OAUTH2 to login
        ClientXMPP.__init__(self,
                            jid=hangouts_login_email,
                            password=None,
                            sasl_mech='X-OAUTH2')
        self.auto_reconnect = True  # Restart stream in the event of an error
        #: Max time to delay between reconnection attempts (in seconds)
        self.reconnect_max_delay = 300

        # Register XMPP plugins (order does not matter.)
        # To do: remove unused plugins
        self.register_plugin('xep_0030')  # Service Discovery
        self.register_plugin('xep_0004')  # Data Forms
        self.register_plugin('xep_0199')  # XMPP Ping

        # The session_start event will be triggered when the XMPP client
        # establishes its connection with the server and the XML streams are
        # ready for use. We want to listen for this event so that we can
        # initialize our roster. Need threaded=True so that the session_start
        # handler doesn't block event processing while we wait for presence
        # stanzas to arrive.
        self.add_event_handler("session_start", self.start, threaded=True)

        # Triggered whenever a 'connected' XMPP event is stanza is received,
        # in particular when connection to XMPP server is established.
        # Fetches a new access token and updates the class' access_token value.
        self.add_event_handler('connected', self.reconnect_workaround)

        # When using a Google Apps custom domain, the certificate does not
        # contain the custom domain, just the Hangouts server name. So we will
        # need to process invalid certificates ourselves and check that it
        # really is from Google.
        self.add_event_handler("ssl_invalid_cert", self.invalid_cert)

    def reconnect_workaround(self, event):  # pylint: disable=W0613
        """ Workaround for SleekXMPP reconnect.
        If a reconnect is attempted after access token is expired, auth fails
        and the client is stopped. Get around this by updating the access
        token whenever the client establishes a connection to the server.
        """
        self.oauth.google_authenticate()
        self.credentials['access_token'] = self.oauth.access_token

    def invalid_cert(self, pem_cert):
        """ Verify that certificate originates from Google. """
        der_cert = ssl.PEM_cert_to_DER_cert(pem_cert)
        try:
            cert.verify('talk.google.com', der_cert)
            logging.debug("Found Hangouts certificate")
        except cert.CertificateError as err:
            logging.error(err)
            self.disconnect(send_close=False)

    def start(self, event):  # pylint: disable=W0613
        """
        Process the session_start event.

        Broadcast initial presence stanza, request the roster,
        and then send the message to the specified user(s).

        Args:
            event -- An empty dictionary. The session_start event does not
                     provide any additional data.
        """

        # Broadcast initial presence stanza
        self.send_presence()

        # Request the roster
        try:
            self.get_roster()
        except IqError as err:
            logging.error('There was an error getting the roster')
            logging.error(err.iq['error']['condition'])
            self.disconnect()
        except IqTimeout:
            logging.error('Server is taking too long to respond')
            self.disconnect(send_close=False)

        # Wait for presence stanzas to be received, otherwise roster will be empty
        sleep(5)

        # Send message to each user found in the roster
        num_users = 0
        for recipient in self.client_roster:
            if recipient != self.boundjid:
                num_users += 1
                logging.info('Sending to: %s (%s)', self.client_roster[recipient]['name'], recipient)
                self.send_message(mto=recipient, mbody=self.message, mtype='chat')

        logging.info('Sent message to %s users in roster', num_users)

        # Wait for all message stanzas to be sent before disconnecting
        self.disconnect(wait=True)
