# -*- coding: utf-8 -*-
"""
Sends an Enterprise Customer's data file to a configured destination.
"""

from __future__ import absolute_import, unicode_literals

from logging import getLogger

from enterprise_reporting.models import EnterpriseCustomerReportingConfiguration
from enterprise_reporting.reporter import EnterpriseReportSender

from django.core.management.base import BaseCommand, CommandError

# Import djcelery, or stub it if not available.
try:
    from djcelery.celery import task as celery_task
except ImportError:
    def celery_task(func):
        """Use a no-op decorator if djcelery is not available."""
        def no_delay(*args, **kwargs):
            """
            Provides the celery.task.delay function, which can be used to spawn an asynchronous celery task.
            Here, it just calls the function.
            """
            func(*args, **kwargs)
        func.delay = no_delay
        return func


LOGGER = getLogger(__name__)


class Command(BaseCommand):
    """
    Send csv reports to EnterpriseCustomers that are configured to receive data based on a schedule.
    """

    def add_arguments(self, parser):
        """
        Add required arguments to the parser.
        """
        parser.add_argument(
            '--enterprise_customer',
            dest='enterprise_customer',
            metavar='ENTERPRISE_CATALOG_API_USERNAME',
            default=None,
            help='EnterpriseCustomer UUID.'
        )
        super(Command, self).add_arguments(parser)

    def handle(self, *args, **options):
        """
        Send csv reports to the EnterpriseCustomer(s) configured to receive data.
        """
        enterprise_customer = options['enterprise_customer']

        if enterprise_customer:
            filter_params = {'enterprise_customer__uuid': enterprise_customer, 'active': True}
        else:
            filter_params = {'active': True}

        reporting_configs = EnterpriseCustomerReportingConfiguration.objects.filter(**filter_params)
        if enterprise_customer and not reporting_configs.exists():
            raise CommandError('The enterprise {} does not have a reporting configuration.'.format(enterprise_customer))

        for reporting_config in reporting_configs:
            if enterprise_customer or reporting_config.is_current_time_in_schedule():
                send_data_task.delay(reporting_config)


@celery_task
def send_data_task(reporting_config):
    """
    Task to send data report to each enterprise.

    Args:
        reporting_config
    """
    enterprise_customer_name = reporting_config.enterprise_customer.name
    LOGGER.info('Kicking off job to send report for {}'.format(
        enterprise_customer_name
    ))

    try:
        reporter = EnterpriseReportSender(reporting_config)
        reporter.send_enterprise_report()
    except Exception:  # pylint: disable=broad-except
        exception_message = 'Data report failed to send for {enterprise_customer}'.format(
            enterprise_customer=enterprise_customer_name,
        )
        LOGGER.exception(exception_message)

    LOGGER.info('Finished job to send report for {}'.format(
        enterprise_customer_name
    ))
