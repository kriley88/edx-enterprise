# -*- coding: utf-8 -*-
"""
Tests for the `consent.helpers` module.
"""
from __future__ import absolute_import, unicode_literals

import unittest

from consent.helpers import get_data_sharing_consent
from pytest import mark

from test_utils import TEST_UUID


@mark.django_db
class TestConsentHelpers(unittest.TestCase):
    """
    Test functions in the consent helpers module
    """

    def test_get_data_sharing_consent_no_enterprise(self):
        """
        Test that the returned consent record is None when no EnterpriseCustomer exists.
        """
        assert get_data_sharing_consent('bob', 'fake-course', TEST_UUID) is None
