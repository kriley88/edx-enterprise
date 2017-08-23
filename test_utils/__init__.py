"""
Test utilities.
"""
# Since py.test discourages putting __init__.py into test directory (i.e. making tests a package)
# one cannot import from anywhere under tests folder. However, some utility classes/methods might be useful
# in multiple test modules. So this package the place to put them.

from __future__ import absolute_import, unicode_literals

import json
import uuid

import mock
import six
from pytest import mark
from rest_framework.test import APITestCase, APIClient
from six.moves.urllib.parse import parse_qs, urlsplit  # pylint: disable=import-error,ungrouped-imports

from test_utils import factories

FAKE_UUIDS = [str(uuid.uuid4()) for i in range(5)]  # pylint: disable=no-member
TEST_USERNAME = 'api_worker'
TEST_PASSWORD = 'QWERTY'
TEST_COURSE = 'course-v1:edX+DemoX+DemoCourse'
TEST_UUID = 'd2098bfb-2c78-44f1-9eb2-b94475356a3f'
TEST_USER_ID = 1


def get_magic_name(value):
    """
    Return value suitable for __name__ attribute.

    For python2, __name__ must be str, while for python3 it must be unicode (as there are no str at all).

    Arguments:
        value basestring: string to "convert"

    Returns:
        str or unicode
    """
    return str(value) if six.PY2 else value


def mock_view_function():
    """
    Return mock function for views that are decorated.
    """
    view_function = mock.Mock()
    view_function.__name__ = str('view_function') if six.PY2 else 'view_function'
    return view_function


def create_items(factory, items):
    """
    Create model instances using given factory.
    """
    for item in items:
        factory.create(**item)


def populate_enterprise_context(response, context):
    """
    Populate a fake response with any necessary Enterprise context for testing purposes.

    :param response: The response to populate with enterprise context.
    """
    for course in response['courses']:
        course.update(context)


@mark.django_db
class APITest(APITestCase):
    """
    Base class for API Tests.
    """

    def setUp(self):
        """
        Perform operations common to all tests.
        """
        super(APITest, self).setUp()
        self.create_user(username=TEST_USERNAME, password=TEST_PASSWORD)
        self.client = APIClient()
        self.client.login(username=TEST_USERNAME, password=TEST_PASSWORD)

    def tearDown(self):
        """
        Perform common tear down operations to all tests.
        """
        # Remove client authentication credentials
        self.client.logout()
        super(APITest, self).tearDown()

    def create_user(self, username=TEST_USERNAME, password=TEST_PASSWORD, **kwargs):
        """
        Create a test user and set its password.
        """
        self.user = factories.UserFactory(username=username, is_active=True, **kwargs)
        self.user.set_password(password)  # pylint: disable=no-member
        self.user.save()  # pylint: disable=no-member

    def load_json(self, content):
        """
        Parse content from django Response object.

        Arguments:
            content (bytes | str) : content type id bytes for PY3 and is string for PY2

        Returns:
            dict object containing parsed json from response.content

        """
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        return json.loads(content)

    def assert_url(self, first, second):
        """
        Compare first and second url.

        Arguments:
            first (str) : first url.
            second (str) : second url.

        Raises:
            Assertion error if both urls do not match.

        """
        # Convert query paramters to a dictionary, so that they can be compared correctly
        scheme, netloc, path, query_string, fragment = urlsplit(first)
        first = (scheme, netloc, path, parse_qs(query_string), fragment)

        # Convert query paramters to a dictionary, so that they can be compared correctly
        scheme, netloc, path, query_string, fragment = urlsplit(second)
        second = (scheme, netloc, path, parse_qs(query_string), fragment)

        assert first == second
