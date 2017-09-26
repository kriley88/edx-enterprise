# -*- coding: utf-8 -*-
"""
Tests for the `edx-enterprise` api module.
"""
from __future__ import absolute_import, unicode_literals

from operator import itemgetter

import ddt
import mock
from pytest import mark
from rest_framework.reverse import reverse

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.utils import timezone

from enterprise.models import EnterpriseCustomer, EnterpriseCustomerIdentityProvider
from six.moves.urllib.parse import urlencode, urljoin  # pylint: disable=import-error
from test_utils import (
    FAKE_UUIDS,
    TEST_COURSE,
    TEST_PASSWORD,
    TEST_USERNAME,
    APITest,
    factories,
    fake_catalog_api,
    fake_enterprise_api,
)

CATALOGS_LIST_ENDPOINT = reverse('catalogs-list')
CATALOGS_DETAIL_ENDPOINT = reverse('catalogs-detail', (1, ))
CATALOGS_COURSES_ENDPOINT = reverse('catalogs-courses', (1, ))
ENTERPRISE_CATALOGS_LIST_ENDPOINT = reverse('enterprise-catalogs-list')
ENTERPRISE_CATALOGS_DETAIL_ENDPOINT = reverse(
    'enterprise-catalogs-detail',
    kwargs={'pk': FAKE_UUIDS[1]}
)
ENTERPRISE_CATALOGS_CONTAINS_CONTENT_ENDPOINT = reverse(
    'enterprise-catalogs-contains-content',
    kwargs={'pk': FAKE_UUIDS[1]}
)
ENTERPRISE_CATALOGS_COURSE_RUN_ENDPOINT = reverse(
    # pylint: disable=anomalous-backslash-in-string
    'enterprise-catalogs-course-runs/(?P<course-id>[^/+]+(/|\+)[^/+]+(/|\+)[^/?]+)',
    kwargs={'pk': FAKE_UUIDS[1], 'course_id': TEST_COURSE}
)
ENTERPRISE_CATALOGS_PROGRAM_ENDPOINT = reverse(
    'enterprise-catalogs-programs/(?P<program-uuid>[^/]+)',
    kwargs={'pk': FAKE_UUIDS[1], 'program_uuid': FAKE_UUIDS[3]}
)
ENTERPRISE_COURSE_ENROLLMENT_LIST_ENDPOINT = reverse('enterprise-course-enrollment-list')
ENTERPRISE_CUSTOMER_COURSES_ENDPOINT = reverse('enterprise-customer-courses', (FAKE_UUIDS[0],))
ENTERPRISE_CUSTOMER_ENTITLEMENT_LIST_ENDPOINT = reverse('enterprise-customer-entitlement-list')
ENTERPRISE_CUSTOMER_LIST_ENDPOINT = reverse('enterprise-customer-list')
ENTERPRISE_CUSTOMER_CONTAINS_CONTENT_ENDPOINT = reverse(
    'enterprise-customer-contains-content',
    kwargs={'pk': FAKE_UUIDS[0]}
)
ENTERPRISE_LEARNER_ENTITLEMENTS_ENDPOINT = reverse('enterprise-learner-entitlements', (1,))
ENTERPRISE_LEARNER_LIST_ENDPOINT = reverse('enterprise-learner-list')


@ddt.ddt
@mark.django_db
class TestEnterpriseAPIViews(APITest):
    """
    Tests for enterprise api views.
    """
    # Get current datetime, so that all tests can use same datetime.
    now = timezone.now()

    def create_user(self, username=TEST_USERNAME, password=TEST_PASSWORD, **kwargs):
        """
        Create a test user and set its password.
        """
        self.user = factories.UserFactory(username=username, is_active=True, is_staff=True, **kwargs)
        self.user.set_password(password)  # pylint: disable=no-member
        self.user.save()  # pylint: disable=no-member

    def create_items(self, factory, items):
        """
        Create model instances using given factory
        """
        for item in items:
            factory.create(**item)

    @ddt.data(
        (
            True, EnterpriseCustomer.AT_ENROLLMENT, True,
            [1, 2, 3], {"entitlements": [
                {"entitlement_id": 1, "requires_consent": False},
                {"entitlement_id": 2, "requires_consent": False},
                {"entitlement_id": 3, "requires_consent": False},
            ]},
        ),
        (
            True, EnterpriseCustomer.AT_ENROLLMENT, False,
            [1, 2, 3], {"entitlements": [
                {"entitlement_id": 1, "requires_consent": True},
                {"entitlement_id": 2, "requires_consent": True},
                {"entitlement_id": 3, "requires_consent": True},
            ]},
        ),
        (
            False, EnterpriseCustomer.AT_ENROLLMENT, True,
            [1, 2, 3], {"entitlements": [
                {"entitlement_id": 1, "requires_consent": False},
                {"entitlement_id": 2, "requires_consent": False},
                {"entitlement_id": 3, "requires_consent": False},
            ]},
        ),
        (
            True, EnterpriseCustomer.AT_ENROLLMENT, None,
            [], {"entitlements": []},
        ),
        (
            True, EnterpriseCustomer.EXTERNALLY_MANAGED, True,
            [1, 2, 3],
            {"entitlements": [
                {"entitlement_id": 1, "requires_consent": False},
                {"entitlement_id": 2, "requires_consent": False},
                {"entitlement_id": 3, "requires_consent": False},
            ]},
        ),
    )
    @ddt.unpack
    def test_enterprise_learner_entitlements(
            self, enable_data_sharing_consent, enforce_data_sharing_consent,
            learner_consent_state, entitlements, expected_json
    ):
        """
        Test that entitlement details route on enterprise learner returns correct data.
        This test verifies that entitlements returned by entitlement details route on enterprise learner
        has the expected behavior as listed down.
            1. Empty entitlements list if enterprise customer requires data sharing consent
                (this includes enforcing data sharing consent at login and at enrollment) and enterprise learner
                 does not consent to share data.
            2. Full list of entitlements for all other cases.
        """
        user_id = self.user.id + 1
        enterprise_customer = factories.EnterpriseCustomerFactory(
            enable_data_sharing_consent=enable_data_sharing_consent,
            enforce_data_sharing_consent=enforce_data_sharing_consent,
        )
        user = factories.UserFactory(id=user_id)
        ecu = factories.EnterpriseCustomerUserFactory(
            user_id=user.id,
            enterprise_customer=enterprise_customer,
        )
        factories.DataSharingConsentFactory(
            username=user.username,
            enterprise_customer=enterprise_customer,
            granted=learner_consent_state,
        )
        for entitlement in entitlements:
            factories.EnterpriseCustomerEntitlementFactory(
                enterprise_customer=enterprise_customer,
                entitlement_id=entitlement,
            )
        url = reverse('enterprise-learner-entitlements', (ecu.id, ))
        response = self.client.get(settings.TEST_SERVER + url)
        response = self.load_json(response.content)
        assert sorted(response) == sorted(expected_json)

    @override_settings(ECOMMERCE_SERVICE_WORKER_USERNAME=TEST_USERNAME)
    @ddt.data(
        (
            # A valid request.
            True,
            [
                factories.EnterpriseCustomerUserFactory,
                [{
                    'id': 1, 'user_id': 0,
                    'enterprise_customer__uuid': FAKE_UUIDS[0],
                    'enterprise_customer__name': 'Test Enterprise Customer', 'enterprise_customer__catalog': 1,
                    'enterprise_customer__active': True, 'enterprise_customer__enable_data_sharing_consent': True,
                    'enterprise_customer__enforce_data_sharing_consent': 'at_enrollment',
                    'enterprise_customer__site__domain': 'example.com',
                    'enterprise_customer__site__name': 'example.com',
                }]
            ],
            {
                'username': TEST_USERNAME,
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            },
            201
        ),
        (
            # A bad request due to an invalid user.
            True,
            [
                factories.EnterpriseCustomerUserFactory,
                [{
                    'id': 1, 'user_id': 0,
                    'enterprise_customer__uuid': FAKE_UUIDS[0],
                    'enterprise_customer__name': 'Test Enterprise Customer', 'enterprise_customer__catalog': 1,
                    'enterprise_customer__active': True, 'enterprise_customer__enable_data_sharing_consent': True,
                    'enterprise_customer__enforce_data_sharing_consent': 'at_enrollment',
                    'enterprise_customer__site__domain': 'example.com',
                    'enterprise_customer__site__name': 'example.com',
                }]
            ],
            {
                'username': 'does_not_exist',
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            },
            400
        ),
        (
            # A rejected request due to missing model permissions.
            False,
            [
                factories.EnterpriseCustomerUserFactory,
                [{
                    'id': 1, 'user_id': 0,
                    'enterprise_customer__uuid': FAKE_UUIDS[0],
                    'enterprise_customer__name': 'Test Enterprise Customer', 'enterprise_customer__catalog': 1,
                    'enterprise_customer__active': True, 'enterprise_customer__enable_data_sharing_consent': True,
                    'enterprise_customer__enforce_data_sharing_consent': 'at_enrollment',
                    'enterprise_customer__site__domain': 'example.com',
                    'enterprise_customer__site__name': 'example.com',
                }]
            ],
            {
                'username': TEST_USERNAME,
                'consent_granted': True,
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            },
            403
        ),
        (
            # A bad request due to a non-existing EnterpriseCustomerUser.
            True,
            [
                factories.EnterpriseCustomerFactory,
                [{
                    'uuid': FAKE_UUIDS[0], 'name': 'Test Enterprise Customer',
                    'catalog': 1, 'active': True, 'enable_data_sharing_consent': True,
                    'enforce_data_sharing_consent': 'at_enrollment',
                    'site__domain': 'example.com', 'site__name': 'example.com',
                }]
            ],
            {
                'username': TEST_USERNAME,
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            },
            400
        )
    )
    @ddt.unpack
    def test_post_enterprise_course_enrollment(self, has_permissions, factory, request_data, status_code):
        """
        Make sure service users can post new EnterpriseCourseEnrollments.
        """
        factory_type, factory_data = factory
        if factory_type == factories.EnterpriseCustomerUserFactory:
            factory_data[0]['user_id'] = self.user.pk  # pylint: disable=no-member

        self.create_items(*factory)
        if has_permissions:
            permission = Permission.objects.get(name='Can add enterprise course enrollment')
            self.user.user_permissions.add(permission)

        response = self.client.post(
            settings.TEST_SERVER + ENTERPRISE_COURSE_ENROLLMENT_LIST_ENDPOINT,
            data=request_data
        )
        assert response.status_code == status_code
        response = self.load_json(response.content)

        if status_code == 201:
            self.assertDictEqual(request_data, response)

    def test_get_enterprise_customer_user_contains_consent_records(self):
        user = factories.UserFactory()
        enterprise_customer = factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        factories.EnterpriseCustomerUserFactory(
            user_id=user.id,
            enterprise_customer=enterprise_customer
        )
        factories.DataSharingConsentFactory(
            username=user.username,
            enterprise_customer=enterprise_customer,
            course_id=TEST_COURSE,
            granted=True
        )

        expected_json = [{
            'username': user.username,
            'enterprise_customer_uuid': FAKE_UUIDS[0],
            'exists': True,
            'course_id': TEST_COURSE,
            'consent_provided': True,
            'consent_required': False
        }]

        response = self.client.get(
            '{host}{path}?username={username}'.format(
                host=settings.TEST_SERVER,
                path=ENTERPRISE_LEARNER_LIST_ENDPOINT,
                username=user.username
            )
        )
        response = self.load_json(response.content)
        assert expected_json == response['results'][0]['data_sharing_consent_records']

    @override_settings(ECOMMERCE_SERVICE_WORKER_USERNAME=TEST_USERNAME)
    @ddt.data(
        (True, 201),
        (False, 403)
    )
    @ddt.unpack
    def test_post_enterprise_customer_user(self, has_permissions, status_code):
        """
        Make sure service users can post new EnterpriseCustomerUsers.
        """
        factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        data = {
            'enterprise_customer': FAKE_UUIDS[0],
            'username': TEST_USERNAME,
        }
        if has_permissions:
            permission = Permission.objects.get(name='Can add Enterprise Customer Learner')
            self.user.user_permissions.add(permission)

        response = self.client.post(settings.TEST_SERVER + ENTERPRISE_LEARNER_LIST_ENDPOINT, data=data)
        assert response.status_code == status_code
        response = self.load_json(response.content)

        if status_code == 201:
            self.assertDictEqual(data, response)

    def test_post_enterprise_customer_user_logged_out(self):
        """
        Make sure users can't post EnterpriseCustomerUsers when logged out.
        """
        self.client.logout()
        self.create_items(
            factories.EnterpriseCustomerFactory,
            [{
                'uuid': FAKE_UUIDS[0], 'name': 'Test Enterprise Customer',
                'catalog': 1, 'active': True, 'enable_data_sharing_consent': True,
                'enforce_data_sharing_consent': 'at_enrollment',
                'site__domain': 'example.com', 'site__name': 'example.com',
            }]
        )
        data = {
            'enterprise_customer': FAKE_UUIDS[0],
            'username': self.user.username
        }
        response = self.client.post(settings.TEST_SERVER + ENTERPRISE_LEARNER_LIST_ENDPOINT, data=data)
        assert response.status_code == 401

    @ddt.data(
        (
            FAKE_UUIDS[0],
            1,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            False,
            False,
            {},
            {'detail': 'Not found.'}
        ),
        (
            FAKE_UUIDS[0],
            None,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            False,
            True,
            {},
            {'detail': (
                "No catalog is associated with Enterprise Pied Piper from endpoint "
                "'/enterprise/api/v1/enterprise-customer/" + FAKE_UUIDS[0] + "/courses/'."
            )}
        ),
        (
            FAKE_UUIDS[0],
            None,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            True,
            False,
            {},
            {'detail': (
                "No catalog is associated with Enterprise Pied Piper from endpoint "
                "'/enterprise/api/v1/enterprise-customer/" + FAKE_UUIDS[0] + "/courses/'."
            )}
        ),
        (
            FAKE_UUIDS[0],
            1,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            False,
            True,
            {},
            {'detail': (
                "Unable to fetch API response for catalog courses for Enterprise Pied Piper from endpoint "
                "'/enterprise/api/v1/enterprise-customer/" + FAKE_UUIDS[0] + "/courses/'."
            )},
        ),
        (
            FAKE_UUIDS[0],
            1,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            True,
            False,
            {},
            {'detail': (
                "Unable to fetch API response for catalog courses for Enterprise Pied Piper from endpoint "
                "'/enterprise/api/v1/enterprise-customer/" + FAKE_UUIDS[0] + "/courses/'."
            )},
        ),
        (
            FAKE_UUIDS[0],
            1,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            True,
            False,
            fake_catalog_api.FAKE_CATALOG_COURSE_PAGINATED_RESPONSE,
            {
                'count': 3,
                'next': ('http://testserver/enterprise/api/v1/enterprise-customer/'
                         + FAKE_UUIDS[0] + '/courses/?page=3'),
                'previous': ('http://testserver/enterprise/api/v1/enterprise-customer/'
                             + FAKE_UUIDS[0] + '/courses/?page=1'),
                'results': [
                    {
                        'owners': [
                            {
                                'description': None,
                                'tags': [],
                                'name': '',
                                'homepage_url': None,
                                'key': 'edX',
                                'certificate_logo_image_url': None,
                                'marketing_url': None,
                                'logo_image_url': None,
                                'uuid': FAKE_UUIDS[1]
                            }
                        ],
                        'tpa_hint': None,
                        'catalog_id': 1,
                        'enterprise_id': FAKE_UUIDS[0],
                        'uuid': FAKE_UUIDS[2],
                        'title': 'edX Demonstration Course',
                        'prerequisites': [],
                        'image': None,
                        'expected_learning_items': [],
                        'sponsors': [],
                        'modified': '2017-03-03T07:34:19.322916Z',
                        'full_description': None,
                        'subjects': [],
                        'video': None,
                        'key': 'edX+DemoX',
                        'short_description': None,
                        'marketing_url': None,
                        'level_type': None,
                        'course_runs': []
                    }
                ]
            }
        ),
        (
            FAKE_UUIDS[0],
            1,
            ENTERPRISE_CUSTOMER_COURSES_ENDPOINT,
            False,
            True,
            fake_catalog_api.FAKE_CATALOG_COURSE_PAGINATED_RESPONSE,
            {
                'count': 3,
                'next': ('http://testserver/enterprise/api/v1/enterprise-customer/'
                         + FAKE_UUIDS[0] + '/courses/?page=3'),
                'previous': ('http://testserver/enterprise/api/v1/enterprise-customer/'
                             + FAKE_UUIDS[0] + '/courses/?page=1'),
                'results': [
                    {
                        'owners': [
                            {
                                'description': None,
                                'tags': [],
                                'name': '',
                                'homepage_url': None,
                                'key': 'edX',
                                'certificate_logo_image_url': None,
                                'marketing_url': None,
                                'logo_image_url': None,
                                'uuid': FAKE_UUIDS[1]
                            }
                        ],
                        'tpa_hint': None,
                        'catalog_id': 1,
                        'enterprise_id': FAKE_UUIDS[0],
                        'uuid': FAKE_UUIDS[2],
                        'title': 'edX Demonstration Course',
                        'prerequisites': [],
                        'image': None,
                        'expected_learning_items': [],
                        'sponsors': [],
                        'modified': '2017-03-03T07:34:19.322916Z',
                        'full_description': None,
                        'subjects': [],
                        'video': None,
                        'key': 'edX+DemoX',
                        'short_description': None,
                        'marketing_url': None,
                        'level_type': None,
                        'course_runs': []
                    }
                ]
            }
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.api.v1.views.CourseCatalogApiClient')
    def test_enterprise_customer_courses(
            self,
            enterprise_uuid,
            catalog,
            url,
            is_staff,
            is_linked_to_enterprise,
            mocked_catalog_courses,
            expected,
            mock_catalog_api_client
    ):
        """
        Make sure the enterprise courses view returns correct data.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(
            uuid=enterprise_uuid,
            catalog=catalog,
            name='Pied Piper',
        )

        self.user.is_staff = is_staff
        self.user.save()
        if is_linked_to_enterprise:
            factories.EnterpriseCustomerUserFactory(
                user_id=self.user.id,
                enterprise_customer=enterprise_customer,
            )

            EnterpriseCustomerIdentityProvider(
                enterprise_customer=enterprise_customer,
                provider_id='saml-testshib',
            )

        mock_catalog_api_client.return_value = mock.Mock(
            get_paginated_catalog_courses=mock.Mock(return_value=mocked_catalog_courses),
        )
        response = self.client.get(url)
        response = self.load_json(response.content)

        assert response == expected

    @ddt.data(
        (
            factories.EnterpriseCustomerFactory,
            ENTERPRISE_CUSTOMER_LIST_ENDPOINT,
            itemgetter('uuid'),
            [{
                'uuid': FAKE_UUIDS[0], 'name': 'Test Enterprise Customer',
                'catalog': 1, 'active': True, 'enable_data_sharing_consent': True,
                'enforce_data_sharing_consent': 'at_enrollment',
                'site__domain': 'example.com', 'site__name': 'example.com',
            }],
            [{
                'uuid': FAKE_UUIDS[0], 'name': 'Test Enterprise Customer',
                'catalog': 1, 'active': True, 'enable_data_sharing_consent': True,
                'enforce_data_sharing_consent': 'at_enrollment',
                'branding_configuration': None, 'enterprise_customer_entitlements': [],
                'enable_audit_enrollment': False,
                'site': {
                    'domain': 'example.com', 'name': 'example.com'
                },
            }],
        ),
        (
            factories.EnterpriseCustomerUserFactory,
            ENTERPRISE_LEARNER_LIST_ENDPOINT,
            itemgetter('user_id'),
            [{
                'id': 1, 'user_id': 0,
                'enterprise_customer__uuid': FAKE_UUIDS[0],
                'enterprise_customer__name': 'Test Enterprise Customer', 'enterprise_customer__catalog': 1,
                'enterprise_customer__active': True, 'enterprise_customer__enable_data_sharing_consent': True,
                'enterprise_customer__enforce_data_sharing_consent': 'at_enrollment',
                'enterprise_customer__site__domain': 'example.com',
                'enterprise_customer__site__name': 'example.com',

            }],
            [{
                'id': 1, 'user_id': 0, 'user': None, 'data_sharing_consent_records': [],
                'enterprise_customer': {
                    'uuid': FAKE_UUIDS[0], 'name': 'Test Enterprise Customer',
                    'catalog': 1, 'active': True, 'enable_data_sharing_consent': True,
                    'enforce_data_sharing_consent': 'at_enrollment',
                    'branding_configuration': None, 'enterprise_customer_entitlements': [],
                    'enable_audit_enrollment': False,
                    'site': {
                        'domain': 'example.com', 'name': 'example.com'
                    },
                }
            }],
        ),
        (
            factories.EnterpriseCustomerEntitlementFactory,
            ENTERPRISE_CUSTOMER_ENTITLEMENT_LIST_ENDPOINT,
            itemgetter('enterprise_customer'),
            [{
                'enterprise_customer__uuid': FAKE_UUIDS[0],
                'entitlement_id': 1
            }],
            [{
                'enterprise_customer': FAKE_UUIDS[0],
                'entitlement_id': 1
            }],
        ),
        (
            factories.EnterpriseCourseEnrollmentFactory,
            ENTERPRISE_COURSE_ENROLLMENT_LIST_ENDPOINT,
            itemgetter('enterprise_customer_user'),
            [{
                'enterprise_customer_user__id': 1,
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            }],
            [{
                'enterprise_customer_user': 1,
                'course_id': 'course-v1:edX+DemoX+DemoCourse',
            }],
        ),
    )
    @ddt.unpack
    def test_api_views(self, factory, url, sorting_key, model_items, expected_json):
        """
        Make sure API end point returns all of the expected fields.
        """
        self.create_items(factory, model_items)
        response = self.client.get(settings.TEST_SERVER + url)
        response = self.load_json(response.content)
        assert sorted(expected_json, key=sorting_key) == sorted(response['results'], key=sorting_key)

    @ddt.data(
        (False, False),
        (False, True),
        (True, False),
    )
    @ddt.unpack
    def test_enterprise_customer_catalogs_list(self, is_staff, is_linked_to_enterprise):
        """
        ``enterprise-catalogs``'s list endpoint should serialize the ``EnterpriseCustomerCatalog`` model.
        """
        catalog_uuid = FAKE_UUIDS[1]
        catalog_title = 'All Content'
        catalog_filter = {}
        enterprise_customer = factories.EnterpriseCustomerFactory(
            uuid=FAKE_UUIDS[0]
        )
        factories.EnterpriseCustomerCatalogFactory(
            uuid=catalog_uuid,
            title=catalog_title,
            enterprise_customer=enterprise_customer,
            content_filter=catalog_filter
        )
        self.user.is_staff = is_staff
        self.user.save()
        if is_linked_to_enterprise:
            factories.EnterpriseCustomerUserFactory(
                user_id=self.user.id,
                enterprise_customer=enterprise_customer,
            )
        if is_staff or is_linked_to_enterprise:
            expected_results = {
                'count': 1,
                'next': None,
                'previous': None,
                'results': [{
                    'uuid': catalog_uuid,
                    'title': catalog_title,
                    'enterprise_customer': enterprise_customer.uuid
                }]
            }
        else:
            expected_results = {
                'count': 0,
                'next': None,
                'previous': None,
                'results': []
            }

        response = self.client.get(ENTERPRISE_CATALOGS_LIST_ENDPOINT)
        response = self.load_json(response.content)

        assert response == expected_results

    @ddt.data(
        (
            False,
            False,
            {'detail': 'Not found.'},
        ),
        (
            False,
            True,
            fake_enterprise_api.build_fake_enterprise_catalog_detail(include_enterprise_context=True),
        ),
        (
            True,
            False,
            fake_enterprise_api.build_fake_enterprise_catalog_detail(include_enterprise_context=True),
        ),
        (
            True,
            True,
            fake_enterprise_api.build_fake_enterprise_catalog_detail(include_enterprise_context=True),
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_customer_catalogs_detail(
            self,
            is_staff,
            is_linked_to_enterprise,
            expected_result,
            mock_catalog_api_client,
    ):
        """
        Make sure the Enterprise Customer's Catalog view correctly returns details about specific catalogs based on
        the content filter.

        Search results should also take into account whether

        * requesting user is staff.
        * requesting user is linked to the EnterpriseCustomer which owns the requested catalog.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(
            uuid=FAKE_UUIDS[0]
        )
        factories.EnterpriseCustomerCatalogFactory(
            uuid=FAKE_UUIDS[1],
            enterprise_customer=enterprise_customer
        )
        if not is_staff:
            self.user.is_staff = False
            self.user.save()
        if is_linked_to_enterprise:
            factories.EnterpriseCustomerUserFactory(
                user_id=self.user.id,
                enterprise_customer=enterprise_customer
            )

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(
                return_value=fake_catalog_api.FAKE_SEARCH_ALL_RESULTS
            ),
        )
        response = self.client.get(ENTERPRISE_CATALOGS_DETAIL_ENDPOINT)
        response = self.load_json(response.content)

        assert response == expected_result

    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_customer_catalogs_detail_pagination(self, mock_catalog_api_client):
        """
        Verify the EnterpriseCustomerCatalog detail view returns the correct paging URLs.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(
            uuid=FAKE_UUIDS[0]
        )
        factories.EnterpriseCustomerCatalogFactory(
            uuid=FAKE_UUIDS[1],
            enterprise_customer=enterprise_customer
        )
        factories.EnterpriseCustomerUserFactory(
            user_id=self.user.id,
            enterprise_customer=enterprise_customer
        )

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(
                return_value=fake_catalog_api.FAKE_SEARCH_ALL_RESULTS_WITH_PAGINATION
            ),
        )
        response = self.client.get(ENTERPRISE_CATALOGS_DETAIL_ENDPOINT + '?page=2')
        response = self.load_json(response.content)

        expected_result = fake_enterprise_api.build_fake_enterprise_catalog_detail(
            previous_url=urljoin('http://testserver', ENTERPRISE_CATALOGS_DETAIL_ENDPOINT) + '?page=1',
            next_url=urljoin('http://testserver/', ENTERPRISE_CATALOGS_DETAIL_ENDPOINT) + '?page=3',
            include_enterprise_context=True
        )

        assert response == expected_result

    @ddt.data(
        (False, {}, {}, None),
        (False, {}, {'course_run_ids': ['fake1', 'fake2']}, None),
        (
            True,
            {
                'key': [
                    fake_catalog_api.FAKE_COURSE_RUN['key'],
                    fake_catalog_api.FAKE_COURSE_RUN2['key']
                ]
            },
            {
                'course_run_ids': [
                    fake_catalog_api.FAKE_COURSE_RUN['key'],
                    fake_catalog_api.FAKE_COURSE_RUN2['key']
                ]
            },
            None
        ),
        (
            True,
            {
                'uuid': [
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE1['uuid'],
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE2['uuid']
                ]
            },
            {
                'program_uuids': [
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE1['uuid'],
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE2['uuid']
                ]
            },
            None
        ),
        (
            True,
            {},
            {
                'course_run_ids': [
                    fake_catalog_api.FAKE_COURSE_RUN['key'],
                    fake_catalog_api.FAKE_COURSE_RUN2['key']
                ]
            },
            [fake_catalog_api.FAKE_COURSE_RUN, fake_catalog_api.FAKE_COURSE_RUN2]
        ),
        (
            True,
            {},
            {
                'program_uuids': [
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE1['uuid'],
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE2['uuid']
                ]
            },
            [fake_catalog_api.FAKE_PROGRAM_RESPONSE1, fake_catalog_api.FAKE_PROGRAM_RESPONSE2]
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_catalog_contains_content(self, contains_content, content_filter, query_params, search_results,
                                                 mock_catalog_api_client):
        """
        The ``programs`` detail endpoint should return correct results from course discovery,
        with enterprise context in courses.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        factories.EnterpriseCustomerCatalogFactory(
            uuid=FAKE_UUIDS[1],
            enterprise_customer=enterprise_customer,
            content_filter=content_filter
        )

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(return_value=search_results)
        )

        response = self.client.get(ENTERPRISE_CATALOGS_CONTAINS_CONTENT_ENDPOINT + '?' + urlencode(query_params, True))
        response_json = self.load_json(response.content)

        if query_params:
            assert response_json['contains_content'] == contains_content
        else:
            message = response_json[0]
            assert 'program_uuids' in message
            assert 'course_run_ids' in message
            assert response.status_code == 400

    @ddt.data(
        (False, False, False, {}, {'detail': 'Not found.'}),
        (False, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (False, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (
            False,
            True,
            True,
            fake_catalog_api.FAKE_COURSE_RUN,
            fake_catalog_api.FAKE_COURSE_RUN_WITH_ENTERPRISE_CONTEXT,
        ),
        (True, False, False, {}, {'detail': 'Not found.'}),
        (True, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (True, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (
            True,
            True,
            True,
            fake_catalog_api.FAKE_COURSE_RUN,
            fake_catalog_api.FAKE_COURSE_RUN_WITH_ENTERPRISE_CONTEXT,
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_catalog_course_run_detail(self, is_staff, is_linked_to_enterprise, is_course_run_in_catalog,
                                                  mocked_course_run, expected_result, mock_catalog_api_client):
        """
        The ``programs`` detail endpoint should return correct results from course discovery,
        with enterprise context in courses.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        factories.EnterpriseCustomerCatalogFactory(
            uuid=FAKE_UUIDS[1],
            enterprise_customer=enterprise_customer,
        )
        if is_staff:
            self.user.is_staff = True
            self.user.save()
        if is_linked_to_enterprise:
            factories.EnterpriseCustomerUserFactory(
                user_id=self.user.id,
                enterprise_customer=enterprise_customer
            )
        search_results = None
        if is_course_run_in_catalog:
            search_results = [fake_catalog_api.FAKE_COURSE_RUN]

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(return_value=search_results),
            get_course_run=mock.Mock(return_value=mocked_course_run),
        )
        response = self.client.get(ENTERPRISE_CATALOGS_COURSE_RUN_ENDPOINT)
        response = self.load_json(response.content)

        assert response == expected_result

    @ddt.data(
        (False, False, False, False, {}, {'detail': 'Not found.'}),
        (False, True, False, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (False, True, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (
            False,
            True,
            True,
            True,
            fake_catalog_api.FAKE_PROGRAM_RESPONSE1,
            fake_catalog_api.FAKE_PROGRAM_RESPONSE1_WITH_ENTERPRISE_CONTEXT,
        ),
        (True, False, False, False, {}, {'detail': 'Not found.'}),
        (True, True, False, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (True, True, True, False, {'detail': 'Not found.'}, {'detail': 'Not found.'}),
        (
            True,
            True,
            True,
            True,
            fake_catalog_api.FAKE_PROGRAM_RESPONSE1,
            fake_catalog_api.FAKE_PROGRAM_RESPONSE1_WITH_ENTERPRISE_CONTEXT,
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_catalog_program_detail(self, is_staff, is_linked_to_enterprise, has_existing_catalog,
                                               is_program_in_catalog, mocked_program, expected_result,
                                               mock_catalog_api_client):
        """
        The ``programs`` detail endpoint should return correct results from course discovery,
        with enterprise context in courses.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        factories.EnterpriseCustomerIdentityProviderFactory(
            enterprise_customer=enterprise_customer,
            provider_id='saml-testshib',
        )
        if is_staff:
            self.user.is_staff = True
            self.user.save()
        if is_linked_to_enterprise:
            factories.EnterpriseCustomerUserFactory(
                user_id=self.user.id,
                enterprise_customer=enterprise_customer
            )
        if has_existing_catalog:
            factories.EnterpriseCustomerCatalogFactory(
                uuid=FAKE_UUIDS[1],
                enterprise_customer=enterprise_customer,
            )
        search_results = None
        if is_program_in_catalog:
            search_results = [fake_catalog_api.FAKE_SEARCH_ALL_PROGRAM_RESULT]

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(return_value=search_results),
            get_program_by_uuid=mock.Mock(return_value=mocked_program),
        )
        response = self.client.get(ENTERPRISE_CATALOGS_PROGRAM_ENDPOINT)
        response = self.load_json(response.content)

        assert response == expected_result

    @ddt.data(
        (
            CATALOGS_LIST_ENDPOINT,
            {},
            {'detail': "Unable to fetch API response from endpoint '{}'.".format(CATALOGS_LIST_ENDPOINT)},
        ),
        (
            CATALOGS_LIST_ENDPOINT,
            {
                'count': 3,
                'next': 'http://testserver/enterprise/api/v1/catalogs/?page=3',
                'previous': 'http://testserver/enterprise/api/v1/catalogs/?page=1',
                'results':
                    [
                        {
                            'id': 2,
                            'name': 'Enterprise All Biology',
                            'query': 'title:*Biology*',
                            'courses_count': 3,
                            'viewers': []
                        },
                    ]
            },
            {
                'count': 3,
                'next': 'http://testserver/enterprise/api/v1/catalogs/?page=3',
                'previous': 'http://testserver/enterprise/api/v1/catalogs/?page=1',
                'results':
                    [
                        {
                            'id': 2,
                            'name': 'Enterprise All Biology',
                            'query': 'title:*Biology*',
                            'courses_count': 3,
                            'viewers': []
                        },
                    ]
            },
        )
    )
    @ddt.unpack
    def test_enterprise_catalogs_list(self, url, mocked_catalogs, expected_catalogs):
        """
        Make sure enterprise catalog view returns correct data.
        Arguments:
            mocked_catalogs (dict): A dict containing catalog information as returned by discovery API.
            expected_catalogs (dict): A dict elements containing expected catalog information.
        """
        with mock.patch('enterprise.api.v1.views.CourseCatalogApiClient') as mock_catalog_api_client:
            mock_catalog_api_client.return_value = mock.Mock(
                get_paginated_catalogs=mock.Mock(return_value=mocked_catalogs),
            )
            response = self.client.get(url)
            response = self.load_json(response.content)

            assert response == expected_catalogs

    @ddt.data(
        (
            CATALOGS_DETAIL_ENDPOINT,
            {},
            {'detail': "Unable to fetch API response for given catalog from endpoint '/catalog/1/'. "
                       "The resource you are looking for does not exist."},
        ),
        (
            CATALOGS_DETAIL_ENDPOINT,
            {
                'id': 1,
                'name': 'Enterprise Dummy Catalog',
                'query': '*',
                'courses_count': 22,
                'viewers': []
            },
            {
                'id': 1,
                'name': 'Enterprise Dummy Catalog',
                'query': '*',
                'courses_count': 22,
                'viewers': []
            },
        ),
    )
    @ddt.unpack
    def test_enterprise_catalog_details(self, url, mocked_catalog, expected):
        """
        Make sure enterprise catalog view returns correct data.
        Arguments:
            mocked_catalog (dict): This is used to mock catalog returned by catalog api.
            expected (list): This is the expected catalog from enterprise api.
        """
        with mock.patch('enterprise.api.v1.views.CourseCatalogApiClient') as mock_catalog_api_client:
            mock_catalog_api_client.return_value = mock.Mock(
                get_catalog=mock.Mock(return_value=mocked_catalog),
            )
            response = self.client.get(url)
            response = self.load_json(response.content)

            assert response == expected

    @ddt.data(
        (
            CATALOGS_COURSES_ENDPOINT,
            'saml-testshib',
            FAKE_UUIDS[0],
            {},
            {'detail': "Unable to fetch API response for catalog courses from endpoint "
                       "'/enterprise/api/v1/catalogs/1/courses/'. The resource you are looking for does not exist."},
        ),
        (
            CATALOGS_COURSES_ENDPOINT,
            'saml-testshib',
            FAKE_UUIDS[0],
            fake_catalog_api.FAKE_CATALOG_COURSE_PAGINATED_RESPONSE,
            {
                'count': 3,
                'next': 'http://testserver/enterprise/api/v1/catalogs/1/courses/?page=3',
                'previous': 'http://testserver/enterprise/api/v1/catalogs/1/courses/?page=1',
                'results': [
                    {
                        'owners': [
                            {
                                'description': None,
                                'tags': [],
                                'name': '',
                                'homepage_url': None,
                                'key': 'edX',
                                'certificate_logo_image_url': None,
                                'marketing_url': None,
                                'logo_image_url': None,
                                'uuid': FAKE_UUIDS[1]
                            }
                        ],
                        'tpa_hint': 'saml-testshib',
                        'catalog_id': '1',
                        'enterprise_id': FAKE_UUIDS[0],
                        'uuid': FAKE_UUIDS[2],
                        'title': 'edX Demonstration Course',
                        'prerequisites': [],
                        'image': None,
                        'expected_learning_items': [],
                        'sponsors': [],
                        'modified': '2017-03-03T07:34:19.322916Z',
                        'full_description': None,
                        'subjects': [],
                        'video': None,
                        'key': 'edX+DemoX',
                        'short_description': None,
                        'marketing_url': None,
                        'level_type': None,
                        'course_runs': []
                    }
                ]
            },
        ),
    )
    @ddt.unpack
    def test_enterprise_catalog_courses(self, url, provider_id, enterprise_customer, mocked_catalog_courses, expected):
        """
        Make sure enterprise catalog view returns correct data.
        Arguments:
            mocked_catalog_courses: This is used to mock catalog courses returned by catalog api.
            expected: This is the expected catalog courses from enterprise api.
        """
        # Populate database
        ecu = factories.EnterpriseCustomerUserFactory(
            user_id=self.user.id,
            enterprise_customer__uuid=enterprise_customer,
        )

        factories.EnterpriseCustomerIdentityProviderFactory(
            enterprise_customer=ecu.enterprise_customer,
            provider_id=provider_id,
        )

        with mock.patch('enterprise.api.v1.views.CourseCatalogApiClient') as mock_catalog_api_client:
            mock_catalog_api_client.return_value = mock.Mock(
                get_paginated_catalog_courses=mock.Mock(return_value=mocked_catalog_courses),
            )
            response = self.client.get(url)
            response = self.load_json(response.content)

            assert response == expected

    def test_enterprise_catalog_courses_unauthorized(self):
        """
        Make sure enterprise catalog view returns correct data.
        Arguments:
            mocked_catalog_courses: This is used to mock catalog courses returned by catalog api.
            expected: This is the expected catalog courses from enterprise api.
        """
        response = self.client.get(CATALOGS_COURSES_ENDPOINT)
        response_content = self.load_json(response.content)

        assert response.status_code == 403
        assert response_content['detail'] == 'User {username} is not associated with an EnterpriseCustomer.'.format(
            username=self.user.username
        )

    @ddt.data(
        (False, {}, None),
        (False, {'course_run_ids': ['fake1', 'fake2']}, None),
        (
            True,
            {
                'course_run_ids': [
                    fake_catalog_api.FAKE_COURSE_RUN['key'],
                    fake_catalog_api.FAKE_COURSE_RUN2['key']
                ]
            },
            [fake_catalog_api.FAKE_COURSE_RUN, fake_catalog_api.FAKE_COURSE_RUN2]
        ),
        (
            True,
            {
                'program_uuids': [
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE1['uuid'],
                    fake_catalog_api.FAKE_PROGRAM_RESPONSE2['uuid']
                ]
            },
            [fake_catalog_api.FAKE_PROGRAM_RESPONSE1, fake_catalog_api.FAKE_PROGRAM_RESPONSE2]
        ),
    )
    @ddt.unpack
    @mock.patch('enterprise.models.CourseCatalogApiServiceClient')
    def test_enterprise_customer_contains_content(self, contains_content, query_params, search_results,
                                                  mock_catalog_api_client):
        """
        The ``programs`` detail endpoint should return correct results from course discovery,
        with enterprise context in courses.
        """
        enterprise_customer = factories.EnterpriseCustomerFactory(uuid=FAKE_UUIDS[0])
        factories.EnterpriseCustomerCatalogFactory(
            uuid=FAKE_UUIDS[1],
            enterprise_customer=enterprise_customer
        )

        mock_catalog_api_client.return_value = mock.Mock(
            get_search_results=mock.Mock(return_value=search_results)
        )

        response = self.client.get(ENTERPRISE_CUSTOMER_CONTAINS_CONTENT_ENDPOINT + '?' + urlencode(query_params, True))
        response_json = self.load_json(response.content)

        if query_params:
            assert response_json['contains_content'] == contains_content
        else:
            message = response_json[0]
            assert 'program_uuids' in message
            assert 'course_run_ids' in message
            assert response.status_code == 400
