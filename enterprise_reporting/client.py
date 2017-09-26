# -*- coding: utf-8 -*-
"""
Client for connecting to a Vertica database.
"""
from __future__ import absolute_import, unicode_literals

from logging import getLogger

import vertica_python

from django.conf import settings

LOGGER = getLogger(__name__)


class VerticaClient(object):
    """
    Client for connecting to Vertica.
    """

    def __init__(self):
        """
        Instantiate a new client using the Django settings to determine the vertica credentials.

        If there are none configured, throw an exception.
        """
        self.connection_info = {
            'host': settings.VERTICA_HOST,
            'port': settings.VERTICA_PORT,
            'user': settings.VERTICA_USERNAME,
            'password': settings.VERTICA_PASSWORD,
            'database': 'warehouse',
        }

        LOGGER.info('About to connect to Vertica with the following connection info: {}'.format(self.connection_info))

        self.connection = vertica_python.connect(**self.connection_info)

    def close_connection(self):
        """
        Close the connection to vertica.
        """
        self.connection.close()
        self.connection = None

    def stream_results(self, query):
        """
        Streams the results for a query using the current connection.
        """
        cursor = self.connection.cursor()
        cursor.execute(query)
        for row in cursor.iterate():
            yield row
