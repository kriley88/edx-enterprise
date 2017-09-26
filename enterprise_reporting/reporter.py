# -*- coding: utf-8 -*-
"""
Classes that handle sending reports for EnterpriseCustomers.
"""
from __future__ import absolute_import, unicode_literals

import csv
import datetime
import logging
import os
from smtplib import SMTPException

from enterprise_reporting.client import VerticaClient
from enterprise_reporting.utils import compress_and_encrypt, send_email_with_attachment

LOGGER = logging.getLogger(__name__)


class EnterpriseReportSender(object):
    """
    Class that handles the process of sending a data report to an Enterprise Customer.
    """

    VERTICA_QUERY = ("SELECT {fields} FROM business_intelligence.enterprise_enrollment"
                     " WHERE enterprise_id = '{enterprise_id}'")
    VERTICA_QUERY_FIELDS = (
        'enterprise_user_id',
        'enrollment_created_timestamp',
        'consent_granted',
        'course_id',
    )
    REPORT_FILE_NAME_FORMAT = "{enterprise_id}_{date}.{extension}"
    REPORT_EMAIL_SUBJECT = 'edX Learner Report'
    REPORT_EMAIL_BODY = ''
    REPORT_EMAIL_FROM_EMAIL = 'enterprise-integrations@edx.org'

    def __init__(self, reporting_config):
        """
        Initialize with an EnterpriseCustomerReportingConfiguration.
        """
        self.reporting_config = reporting_config
        self.vertica_client = VerticaClient()
        self.report_sent = False

    def send_enterprise_report(self):
        """
        Query the data warehouse (vertica) and export data to a csv file.

        This file will get encrypted and emailed to the Enterprise Customer.
        """
        enterprise_customer_name = self.reporting_config.enterprise_customer.name

        if self.report_sent:
            LOGGER.warn('This EnterpriseReportSender instance has already attempted to run a report for {}'.format(
                enterprise_customer_name
            ))
            return

        LOGGER.info('Starting process to send email report to {}'.format(enterprise_customer_name))

        # initialize base csv file and file writer
        data_report_file_name, data_report_file_writer = self._create_data_report_csv_writer()

        # query vertica and write each row to the file
        LOGGER.debug('Querying Vertica for data for {}'.format(enterprise_customer_name))
        data_report_file_writer.writerows(self._query_vertica())

        # create a password encrypted zip file
        LOGGER.debug('Encrypting data report for {}'.format(enterprise_customer_name))
        data_report_zip_name = compress_and_encrypt(data_report_file_name, self.reporting_config.password)

        # email the file to the email address in the configuration
        LOGGER.debug('Sending encrypted data to {}'.format(enterprise_customer_name))
        try:
            send_email_with_attachment(
                self.REPORT_EMAIL_SUBJECT,
                self.REPORT_EMAIL_BODY,
                self.REPORT_EMAIL_FROM_EMAIL,
                self.reporting_config.email,
                data_report_zip_name
            )
        except SMTPException:
            LOGGER.exception('Failed to send email for {}'.format(enterprise_customer_name))

        self._cleanup([data_report_file_name, data_report_zip_name])

    def _create_data_report_csv_writer(self):
        """
        Create a csv file and file writer with the field headers for the data report.
        """
        data_report_file_name = self.REPORT_FILE_NAME_FORMAT.format(
            enterprise_id=self.reporting_config.enterprise_customer.uuid,
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            extension='csv',
        )
        data_report_file = open(data_report_file_name, 'w')  # pylint: disable=open-builtin
        data_report_file_writer = csv.writer(data_report_file)
        data_report_file_writer.writerow(self.VERTICA_QUERY_FIELDS)
        return data_report_file_name, data_report_file_writer

    def _query_vertica(self):
        """
        Use a connection to Vertica to execute the report query.
        """
        query = self.VERTICA_QUERY.format(
            fields=','.join(self.VERTICA_QUERY_FIELDS),
            enterprise_id=self.reporting_config.enterprise_customer.uuid
        )
        return self.vertica_client.stream_results(query)

    def _cleanup(self, filenames):
        """
        Perform various cleanup operations after we've attempted (successfully or not) to send a report.
        """
        self.vertica_client.close_connection()

        for filename in filenames:
            os.remove(filename)

        self.report_sent = True
