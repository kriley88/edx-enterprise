# -*- coding: utf-8 -*-
"""
Mixins for edX Enterprise's Consent application.
"""

from __future__ import absolute_import, unicode_literals

from django.utils.encoding import python_2_unicode_compatible


@python_2_unicode_compatible
class ConsentModelMixin(object):
    """
    A mixin for Data Sharing Consent classes that require common, reusable functionality.
    """

    def __str__(self):
        """
        Return a human-readable string representation.
        """
        return "<{class_name} for user {username} of Enterprise {enterprise_name}>".format(
            class_name=self.__class__.__name__,
            username=self.username,
            enterprise_name=self.enterprise_customer.name,
        )

    def __repr__(self):
        """
        Return a uniquely identifying string representation.
        """
        return self.__str__()

    def consent_required(self, request_user):
        """
        Return a boolean value indicating whether a consent action must be taken.
        """
        children = getattr(self, '_child_consents', [])
        if children:
            return any((child.consent_required(request_user) for child in children))

        if self.granted:
            return False

        return bool(
            (self.enterprise_customer.enforces_data_sharing_consent('at_enrollment')) and
            (self.enterprise_customer.catalog_contains_course(request_user, self.course_id))
        )

    def serialize(self, request):
        """
        Return a dictionary, appropriate for the request, that provides the core details of the consent record.
        """
        details = {
            'username': self.username,
            'enterprise_customer_uuid': self.enterprise_customer.uuid,
            'exists': self.exists,
            'consent_provided': self.granted,
            'consent_required': self.consent_required(request.user),
        }
        if self.course_id:
            details['course_id'] = self.course_id
        if getattr(self, 'program_id', None):
            details['program_id'] = self.program_id
        return details
