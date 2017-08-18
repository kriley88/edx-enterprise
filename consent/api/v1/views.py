# -*- coding: utf-8 -*-
"""
A generic API for edX Enterprise's Consent application.
"""

from __future__ import absolute_import, unicode_literals

from consent.api import permissions
from consent.errors import ConsentAPIRequestError
from consent.models import DataSharingConsent, ProxyDataSharingConsent
from edx_rest_framework_extensions.authentication import BearerAuthentication, JwtAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView

from enterprise.api.throttles import ServiceUserThrottle
from enterprise.api_client.discovery import CourseCatalogApiClient
from enterprise.models import EnterpriseCustomer


class DataSharingConsentView(APIView):
    """
        **Use Cases**

            Presents a generic data sharing consent API to applications
            that have Enterprise customers who require data sharing
            consent from users.

        **Behavior**

            Implements GET, POST, and DELETE which each have roughly
            the following behavior (see their individual handlers for
            more documentation):

            GET /consent/api/v1/data_sharing_consent?username=bob&enterprise_customer_uuid=ENTERPRISE-UUID&course_id=ID
            >>> {
            >>>     "username": "bob",
            >>>     "course_id": "course-v1:edX+DemoX+Demo_Course",
            >>>     "enterprise_customer_uuid": "enterprise-uuid-goes-right-here",
            >>>     "exists": False,
            >>>     "consent_provided": False,
            >>>     "consent_required": True,
            >>> }

            If the ``exists`` key is false, then the body will be returned
            with a 404 Not Found error code; otherwise, 200 OK. If either
            of ``enterprise_customer_uuid`` or ``username`` is not provided, an
            appropriate 400-series error will be returned.

            POST or DELETE /consent/api/v1/data_sharing_consent
            >>> {
            >>>     "username": "bob",
            >>>     "course_id": "course-v1:edX+DemoX+Demo_Course",
            >>>     "enterprise_customer_uuid": "enterprise-uuid-goes-right-here"
            >>> }

            The API accepts JSON objects with these key-value pairs for
            POST or DELETE.

        **Notes**

            ``course_id`` specifies a course key (course-v1:edX+DemoX),
            and not a course run key (course-v1:edX+DemoX+Demo_Course).

    """

    permission_classes = (permissions.IsStaffOrUserInRequest,)
    authentication_classes = (JwtAuthentication, BearerAuthentication, SessionAuthentication,)
    throttle_classes = (ServiceUserThrottle,)

    REQUIRED_PARAM_USERNAME = 'username'
    REQUIRED_PARAM_COURSE_ID = 'course_id'
    REQUIRED_PARAM_PROGRAM_ID = 'program_id'
    REQUIRED_PARAM_ENTERPRISE_CUSTOMER = 'enterprise_customer_uuid'  # pylint: disable=invalid-name

    CONSENT_EXISTS = 'exists'
    CONSENT_GRANTED = 'consent_provided'
    CONSENT_REQUIRED = 'consent_required'

    MISSING_REQUIRED_PARAMS_MSG = (
        "Some query parameter(s) missing: "
        "username '{username}', "
        "course_id '{course_id}', "
        "enterprise customer uuid '{enterprise_customer_uuid}'."
    )

    QUERY_PARAM_METHODS = {'GET', 'DELETE'}

    def get_consent_record(self, request):
        """
        Get the consent record relevant to the request at hand.
        """
        username, course_id, program_id, enterprise_customer_uuid = self.get_required_query_params(request)
        try:
            if course_id:
                return DataSharingConsent.objects.proxied_get(
                    username=username,
                    course_id=course_id,
                    enterprise_customer__uuid=enterprise_customer_uuid
                )
            discovery_client = CourseCatalogApiClient(request.user)
            course_ids = discovery_client.get_program_course_keys(program_id)
            return ProxyDataSharingConsent.from_children(
                program_id,
                *(DataSharingConsent.objects.proxied_get(
                    username=username,
                    course_id=individual_course_id,
                    enterprise_customer__uuid=enterprise_customer_uuid
                ) for individual_course_id in course_ids)
            )
        except EnterpriseCustomer.DoesNotExist:
            return None

    def get_required_query_params(self, request):
        """
        Gets ``username``, ``course_id``, and ``enterprise_customer_uuid``,
        which are the relevant query parameters for this API endpoint.

        :param request: The request to this endpoint.
        :return: The ``username``, ``course_id``, and ``enterprise_customer_uuid`` from the request.
        """
        if request.method in self.QUERY_PARAM_METHODS:
            username = request.query_params.get(
                self.REQUIRED_PARAM_USERNAME,
                request.data.get(self.REQUIRED_PARAM_USERNAME, '')
            )
            course_id = request.query_params.get(
                self.REQUIRED_PARAM_COURSE_ID,
                request.data.get(self.REQUIRED_PARAM_COURSE_ID, '')
            )
            program_id = request.query_params.get(
                self.REQUIRED_PARAM_PROGRAM_ID,
                request.data.get(self.REQUIRED_PARAM_PROGRAM_ID, '')
            )
            enterprise_customer_uuid = request.query_params.get(
                self.REQUIRED_PARAM_ENTERPRISE_CUSTOMER,
                request.data.get(self.REQUIRED_PARAM_ENTERPRISE_CUSTOMER)
            )
        else:
            username = request.data.get(
                self.REQUIRED_PARAM_USERNAME,
                request.query_params.get(self.REQUIRED_PARAM_USERNAME, '')
            )
            course_id = request.data.get(
                self.REQUIRED_PARAM_COURSE_ID,
                request.query_params.get(self.REQUIRED_PARAM_COURSE_ID, '')
            )
            program_id = request.data.get(
                self.REQUIRED_PARAM_PROGRAM_ID,
                request.query_params.get(self.REQUIRED_PARAM_PROGRAM_ID, '')
            )
            enterprise_customer_uuid = request.data.get(
                self.REQUIRED_PARAM_ENTERPRISE_CUSTOMER,
                request.query_params.get(self.REQUIRED_PARAM_ENTERPRISE_CUSTOMER)
            )
        if not (username and (course_id or program_id) and enterprise_customer_uuid):
            raise ConsentAPIRequestError(
                self.MISSING_REQUIRED_PARAMS_MSG.format(
                    username=username,
                    course_id=course_id,
                    enterprise_customer_uuid=enterprise_customer_uuid
                )
            )
        return username, course_id, program_id, enterprise_customer_uuid

    def get_no_record_response(self, request):
        """
        Get an HTTPResponse that can be used when there's no related EnterpriseCustomer.
        """
        username, course_id, program_id, enterprise_customer_uuid = self.get_required_query_params(request)
        data = {
            self.REQUIRED_PARAM_USERNAME: username,
            self.REQUIRED_PARAM_ENTERPRISE_CUSTOMER: enterprise_customer_uuid,
            self.CONSENT_EXISTS: False,
            self.CONSENT_GRANTED: False,
            self.CONSENT_REQUIRED: False,
        }
        if course_id:
            data[self.REQUIRED_PARAM_COURSE_ID] = course_id

        if program_id:
            data[self.REQUIRED_PARAM_PROGRAM_ID] = program_id

        return Response(data, status=HTTP_200_OK)

    def get(self, request):
        """
        GET /consent/api/v1/data_sharing_consent?username=bob&course_id=id&enterprise_customer_uuid=uuid
        *username*
            The edX username from whom to get consent.
        *course_id*
            The course for which consent is granted.
        *enterprise_customer_uuid*
            The UUID of the enterprise customer that requires consent.
        """
        try:
            consent_record = self.get_consent_record(request)
            if consent_record is None:
                return self.get_no_record_response(request)
        except ConsentAPIRequestError as invalid_request:
            return Response({'error': str(invalid_request)}, status=HTTP_400_BAD_REQUEST)

        return Response(consent_record.serialize(request), status=HTTP_200_OK)

    def post(self, request):
        """
        POST /consent/api/v1/data_sharing_consent

        Requires a JSON object of the following format:
        >>> {
        >>>     "username": "bob",
        >>>     "course_id": "course-v1:edX+DemoX+Demo_Course",
        >>>     "enterprise_customer_uuid": "enterprise-uuid-goes-right-here"
        >>> }

        Keys:
        *username*
            The edX username from whom to get consent.
        *course_id*
            The course for which consent is granted.
        *enterprise_customer_uuid*
            The UUID of the enterprise customer that requires consent.
        """
        try:
            consent_record = self.get_consent_record(request)
            if consent_record is None:
                return self.get_no_record_response(request)
            if consent_record.consent_required(request.user):
                # If and only if the given EnterpriseCustomer requires data sharing consent
                # for the given course, then, since we've received a POST request, set the
                # consent state for the EC/user/course combo.
                consent_record.granted = True

                # Models don't have return values when saving, but ProxyDataSharingConsent
                # objects do - they should return either a model instance, or another instance
                # of ProxyDataSharingConsent if representing a multi-course consent record.
                consent_record = consent_record.save() or consent_record

        except ConsentAPIRequestError as invalid_request:
            return Response({'error': str(invalid_request)}, status=HTTP_400_BAD_REQUEST)

        return Response(consent_record.serialize(request))

    def delete(self, request):
        """
        DELETE /consent/api/v1/data_sharing_consent

        Requires a JSON object of the following format:
        >>> {
        >>>     "username": "bob",
        >>>     "course_id": "course-v1:edX+DemoX+Demo_Course",
        >>>     "enterprise_customer_uuid": "enterprise-uuid-goes-right-here"
        >>> }

        Keys:
        *username*
            The edX username from whom to get consent.
        *course_id*
            The course for which consent is granted.
        *enterprise_customer_uuid*
            The UUID of the enterprise customer that requires consent.
        """
        try:
            consent_record = self.get_consent_record(request)
            if consent_record is None:
                return self.get_no_record_response(request)

            # We're fine with proactively refusing consent, even when there's no actual
            # requirement for consent yet.
            consent_record.granted = False

            # Models don't have return values when saving, but ProxyDataSharingConsent
            # objects do - they should return either a model instance, or another instance
            # of ProxyDataSharingConsent if representing a multi-course consent record.
            consent_record = consent_record.save() or consent_record

        except ConsentAPIRequestError as invalid_request:
            return Response({'error': str(invalid_request)}, status=HTTP_400_BAD_REQUEST)

        return Response(consent_record.serialize(request))
