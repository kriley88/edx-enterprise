# -*- coding: utf-8 -*-
"""
Utility functions for Enterprise Reporting.
"""
from __future__ import absolute_import, unicode_literals

import logging
import re

import pyminizip

from django.core.mail import EmailMessage

LOGGER = logging.getLogger(__name__)

COMPRESSION_LEVEL = 4


def compress_and_encrypt(filename, password):
    """
    Given a file and a password, create an encrypted zip file. Return the new filename.
    """
    zip_filename = re.sub(r'\.(\w+)$', 'zip', filename)
    if filename == zip_filename:
        LOGGER.warn('Unable to determine filename for compressing {}, '
                    'file must have a valid extension that is not .zip'.format(filename))
        return None

    pyminizip.compress(filename, zip_filename, password, COMPRESSION_LEVEL)
    return zip_filename


def send_email_with_attachment(subject, body, from_email, to_email, filename):
    """
    Send an email with a file attachment.
    """
    mail = EmailMessage(subject, body, from_email, to_email)
    mail.attach_file(filename)
    mail.send()
