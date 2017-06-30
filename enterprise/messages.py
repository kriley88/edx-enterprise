# -*- coding: utf-8 -*-
"""
Utility functions for interfacing with the Django messages framework.
"""
from __future__ import absolute_import, unicode_literals

from django.contrib import messages
from django.utils.translation import ugettext as _

try:
    from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
except ImportError:
    configuration_helpers = None


def add_consent_declined_message(request, enterprise_customer, course_details):
    messages.warning(
        request,
        _(
            '{strong_start}We could not enroll you in {em_start}{course_name}{em_end}.{strong_end} '
            '<span>If you have questions or concerns about sharing your data, please contact your learning '
            'manager at {enterprise_customer_name}, or contact {external_link_start} edX support'
            '{external_link_end}.{span_end}'
        ).format(
            course_name=course_details.get('name'),
            em_start='<em>',
            em_end='</em>',
            enterprise_customer_name=enterprise_customer.name,
            external_link_start='<a href="{support_link}" target="_blank"><i class="fa fa-external-link" '
                                'aria-hidden="true">'.format(
                                    support_link=configuration_helpers.get_value('ENTERPRISE_SUPPORT_URL')
                                ),
            external_link_end='</i></a>',
            span_start='<span>',
            span_end='</span>',
            strong_start='<strong>',
            strong_end='</strong>',
        )
    )
