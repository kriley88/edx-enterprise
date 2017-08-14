
# -*- coding: utf-8 -*-
"""
Client for communicating with the Enterprise API.
"""
from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.core.cache import cache

from enterprise.api_client.lms import LmsApiClient
from enterprise.utils import get_cache_key, traverse_pagination


class EnterpriseApiClient(LmsApiClient):
    """
    Object builds an API client to make calls to the Enterprise API.
    """

    API_BASE_URL = settings.LMS_ROOT_URL + 'enterprise/api/v1/'

    def get_all_enterprise_courses(self, enterprise_customer):
        """
        Query the Enter API for the course details of the given course_id.

        Arguments:
            enterprise_customer (Enterprise Customer): Enterprise customer for fetching courses

        Returns:
            dict: A dictionary containing details about the course, in an enrollment context (allowed modes, etc.)
        """
        api_resource_name = 'enterprise-customer'
        cache_key = get_cache_key(
            resource=api_resource_name,
            enterprise_uuid=enterprise_customer.uuid,
        )
        response = cache.get(cache_key)
        if not response:
            endpoint = getattr(self, api_resource_name)
            response = endpoint(enterprise_customer.uuid).get()
            all_response_results = traverse_pagination(response, endpoint)
            response = {
                'count': len(all_response_results),
                'next': 'None',
                'previous': 'None',
                'results': all_response_results,
            }
            cache.set(cache_key, response, settings.ENTERPRISE_API_CACHE_TIMEOUT)

        return response
