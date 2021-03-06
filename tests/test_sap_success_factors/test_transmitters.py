# -*- coding: utf-8 -*-
"""
Module tests classes responsible for transmitting data to integrated channels.
"""
from __future__ import absolute_import, unicode_literals

import datetime
import json
import unittest

import mock
from integrated_channels.sap_success_factors.models import (
    CatalogTransmissionAudit,
    LearnerDataTransmissionAudit,
    SAPSuccessFactorsEnterpriseCustomerConfiguration,
    SAPSuccessFactorsGlobalConfiguration,
)
from integrated_channels.sap_success_factors.transmitters import courses, learner_data
from pytest import mark
from requests import RequestException

from test_utils.factories import EnterpriseCustomerFactory


class TestSuccessFactorsCourseTransmitter(unittest.TestCase):
    """
    Test SuccessFactorsCourseTransmitter.
    """

    @mark.django_db
    def setUp(self):
        super(TestSuccessFactorsCourseTransmitter, self).setUp()
        SAPSuccessFactorsGlobalConfiguration.objects.create(
            completion_status_api_path="",
            course_api_path="",
            oauth_api_path=""
        )

        enterprise_customer = EnterpriseCustomerFactory(
            name='Starfleet Academy',
        )

        self.enterprise_config = SAPSuccessFactorsEnterpriseCustomerConfiguration(
            enterprise_customer=enterprise_customer,
            key="client_id",
            sapsf_base_url="http://test.successfactors.com/",
            sapsf_company_id="company_id",
            sapsf_user_id="user_id",
            secret="client_secret"
        )

        self.payload = [{'course1': 'test1'}, {'course2': 'test2'}]

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.utils.reverse')
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_success(self, client_mock, track_selection_reverse_mock):
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value
        client_mock_instance.send_course_import.return_value = 200, '{"success":"true"}'
        track_selection_reverse_mock.return_value = '/course_modes/choose/course-v1:edX+DemoX+Demo_Course/'

        course_exporter_mock = mock.MagicMock(courses=self.payload)
        course_exporter_mock.get_serialized_data_blocks.return_value = [(json.dumps(self.payload), 2)]
        course_exporter_mock.resolve_removed_courses.return_value = {}

        transmitter = courses.SuccessFactorsCourseTransmitter(self.enterprise_config)
        assert transmitter.__class__.__bases__[0].__name__ == 'SuccessFactorsTransmitterBase'

        catalog_transmission_audit = transmitter.transmit(course_exporter_mock)

        client_mock_instance.send_course_import.assert_called_with(json.dumps(self.payload))
        course_exporter_mock.resolve_removed_courses.assert_called_with({})
        course_exporter_mock.get_serialized_data_blocks.assert_called()
        assert catalog_transmission_audit.enterprise_customer_uuid == self.enterprise_config.enterprise_customer.uuid
        assert catalog_transmission_audit.total_courses == len(self.payload)
        assert catalog_transmission_audit.status == '200'
        assert catalog_transmission_audit.error_message == ''

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.utils.reverse')
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_failure(self, client_mock, track_selection_reverse_mock):
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value
        client_mock_instance.send_course_import.side_effect = RequestException('error occurred')
        track_selection_reverse_mock.return_value = '/course_modes/choose/course-v1:edX+DemoX+Demo_Course/'

        course_exporter_mock = mock.MagicMock(courses=self.payload)
        course_exporter_mock.get_serialized_data_blocks.return_value = [(json.dumps(self.payload), 2)]
        course_exporter_mock.resolve_removed_courses.return_value = {}

        transmitter = courses.SuccessFactorsCourseTransmitter(self.enterprise_config)

        catalog_transmission_audit = transmitter.transmit(course_exporter_mock)

        client_mock_instance.send_course_import.assert_called_with(json.dumps(self.payload))
        course_exporter_mock.get_serialized_data_blocks.assert_called()
        course_exporter_mock.resolve_removed_courses.assert_called_with({})
        assert catalog_transmission_audit.enterprise_customer_uuid == self.enterprise_config.enterprise_customer.uuid
        assert catalog_transmission_audit.total_courses == len(self.payload)
        assert catalog_transmission_audit.status == '500'
        assert catalog_transmission_audit.error_message == 'error occurred'

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_with_previous_audit(self, client_mock):
        audit_summary = {
            'test_course': {
                'in_catalog': True,
                'status': 'ACTIVE',
            }
        }
        transmission_audit = CatalogTransmissionAudit(
            enterprise_customer_uuid=self.enterprise_config.enterprise_customer.uuid,
            total_courses=2,
            status='200',
            error_message='',
            audit_summary=json.dumps(audit_summary),
        )
        transmission_audit.save()

        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value
        client_mock_instance.send_course_import.return_value = 200, '{"success":"true"}'

        course_exporter_mock = mock.MagicMock(courses=self.payload)
        course_exporter_mock.get_serialized_data_blocks.return_value = [(json.dumps(self.payload), 2)]
        course_exporter_mock.resolve_removed_courses.return_value = {}

        transmitter = courses.SuccessFactorsCourseTransmitter(self.enterprise_config)
        assert transmitter.__class__.__bases__[0].__name__ == 'SuccessFactorsTransmitterBase'

        catalog_transmission_audit = transmitter.transmit(course_exporter_mock)

        client_mock_instance.send_course_import.assert_called_with(json.dumps(self.payload))
        course_exporter_mock.resolve_removed_courses.assert_called_with(audit_summary)
        course_exporter_mock.get_serialized_data_blocks.assert_called()
        assert catalog_transmission_audit.enterprise_customer_uuid == self.enterprise_config.enterprise_customer.uuid
        assert catalog_transmission_audit.total_courses == len(self.payload)
        assert catalog_transmission_audit.status == '200'
        assert catalog_transmission_audit.error_message == ''


class TestSuccessFactorsLearnerDataTransmitter(unittest.TestCase):
    """
    Test SuccessFactorsLearnerDataTransmitter.
    """

    @mark.django_db
    def setUp(self):
        super(TestSuccessFactorsLearnerDataTransmitter, self).setUp()
        SAPSuccessFactorsGlobalConfiguration.objects.create(
            completion_status_api_path="",
            course_api_path="",
            oauth_api_path=""
        )

        self.enterprise_config = SAPSuccessFactorsEnterpriseCustomerConfiguration(
            key="client_id",
            sapsf_base_url="http://test.successfactors.com/",
            sapsf_company_id="company_id",
            sapsf_user_id="user_id",
            secret="client_secret"
        )

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_already_sent(self, client_mock):
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value

        payload = LearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=5,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            completed_timestamp=1486755998,
            instructor_name='Professor Professorson',
            grade='Pass',
            error_message='',
        )
        payload.save()

        transmitter = learner_data.SuccessFactorsLearnerDataTransmitter(self.enterprise_config)
        response = transmitter.transmit(payload)
        assert response is None
        client_mock_instance.send_completion_status.assert_not_called()

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_updated_existing_event(self, client_mock):
        """
        The desired behavior for enrollments that have been updated in some way after they have been
        initially sent is for them to not get sent again. This could change in the future as we have
        more granular data available about progress/grades.
        """
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value

        previous_payload = LearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=5,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            completed_timestamp=1486755998,
            instructor_name='Professor Professorson',
            grade='Pass',
            error_message='',
        )
        previous_payload.save()

        payload = LearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=5,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            completed_timestamp=1486855998,
            instructor_name='Professor Professorson',
            grade='Passing even more',
            error_message='',
        )
        transmitter = learner_data.SuccessFactorsLearnerDataTransmitter(self.enterprise_config)
        response = transmitter.transmit(payload)
        assert response is None
        client_mock_instance.send_completion_status.assert_not_called()

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_success(self, client_mock):
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value
        client_mock_instance.send_completion_status.return_value = 200, '{"success":"true"}'

        payload = LearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=5,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            completed_timestamp=1486755998,
            instructor_name='Professor Professorson',
            grade='Pass',
        )
        transmitter = learner_data.SuccessFactorsLearnerDataTransmitter(self.enterprise_config)

        transmission_audit = transmitter.transmit(payload)
        client_mock_instance.send_completion_status.assert_called_with(
            payload.sapsf_user_id, payload.serialize()
        )
        assert transmission_audit.status == '200'
        assert transmission_audit.error_message == ''

    @mark.django_db
    @mock.patch('integrated_channels.sap_success_factors.transmitters.SAPSuccessFactorsAPIClient')
    def test_transmit_failure(self, client_mock):
        client_mock.get_oauth_access_token.return_value = "token", datetime.datetime.utcnow()
        client_mock_instance = client_mock.return_value
        client_mock_instance.send_completion_status.side_effect = RequestException('error occurred')

        payload = LearnerDataTransmissionAudit(
            enterprise_course_enrollment_id=5,
            sapsf_user_id='sap_user',
            course_id='course-v1:edX+DemoX+DemoCourse',
            course_completed=True,
            completed_timestamp=1486755998,
            instructor_name='Professor Professorson',
            grade='Pass',
        )
        transmitter = learner_data.SuccessFactorsLearnerDataTransmitter(self.enterprise_config)

        transmission_audit = transmitter.transmit(payload)
        client_mock_instance.send_completion_status.assert_called_with(
            payload.sapsf_user_id, payload.serialize()
        )
        assert transmission_audit.status == '500'
        assert transmission_audit.error_message == 'error occurred'
