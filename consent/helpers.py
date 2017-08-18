# -*- coding: utf-8 -*-
"""
Helper functions for the Consent application.
"""

from __future__ import absolute_import, unicode_literals

from consent.models import DataSharingConsent

from enterprise.models import EnterpriseCustomer
from enterprise.utils import get_enterprise_customer


def consent_provided(username, course_id, enterprise_customer_uuid):
    """
    Get whether consent is provided by the user to the Enterprise customer.

    :param username: The user that grants consent.
    :param course_id: The course for which consent is granted.
    :param enterprise_customer_uuid: The consent requester.
    :return: Whether consent is provided to the Enterprise customer by the user for a course.
    """
    consent = get_data_sharing_consent(username, course_id, enterprise_customer_uuid)
    return consent.granted if consent else False


def consent_required(request_user, username, course_id, enterprise_customer_uuid):
    """
    Get whether consent is required by the ``EnterpriseCustomer``.

    :param request_user: The user making the request related to consent.
    :param username: The user that grants consent.
    :param course_id: The course for which consent is granted.
    :param enterprise_customer_uuid: The consent requester.
    :return: Whether consent is required for a course by an Enterprise customer from a user.
    """
    if consent_provided(username, course_id, enterprise_customer_uuid):
        return False
    enterprise_customer = get_enterprise_customer(enterprise_customer_uuid)
    return bool(
        (enterprise_customer is not None) and
        (enterprise_customer.enforces_data_sharing_consent('at_enrollment')) and
        (enterprise_customer.catalog_contains_course(request_user, course_id))
    )


def get_data_sharing_consent(username, course_id, enterprise_customer_uuid):
    """
    Get the data sharing consent object associated with a certain user of a customer for a course.

    :param username: The user that grants consent.
    :param course_id: The course for which consent is granted.
    :param enterprise_customer_uuid: The consent requester.
    :return: The data sharing consent object, or None if the enterprise customer for the given UUID does not exist.
    """
    try:
        return DataSharingConsent.objects.proxied_get(
            username=username,
            course_id=course_id,
            enterprise_customer__uuid=enterprise_customer_uuid
        )
    except EnterpriseCustomer.DoesNotExist:
        return None
