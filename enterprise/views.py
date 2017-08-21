"""
User-facing views for the Enterprise app.
"""
from __future__ import absolute_import, unicode_literals

from logging import getLogger

from consent.helpers import consent_required
from consent.models import DataSharingConsent
from dateutil.parser import parse
from edx_rest_api_client.exceptions import HttpClientError
from requests.exceptions import HTTPError, Timeout

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.utils.translation import get_language_from_request, ungettext
from django.views.generic import View

try:
    from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
except ImportError:
    configuration_helpers = None


# isort:imports-firstparty
from enterprise.api_client.discovery import CourseCatalogApiServiceClient
from enterprise.api_client.ecommerce import EcommerceApiClient
from enterprise.api_client.lms import CourseApiClient, EnrollmentApiClient
from enterprise.decorators import enterprise_login_required, force_fresh_session
from enterprise.messages import add_consent_declined_message
from enterprise.models import EnterpriseCourseEnrollment, EnterpriseCustomer, EnterpriseCustomerUser
from enterprise.utils import (
    NotConnectedToOpenEdX,
    filter_audit_course_modes,
    get_enterprise_customer_for_user,
    get_enterprise_customer_or_404,
    get_enterprise_customer_user,
)
from six.moves.urllib.parse import urlencode, urljoin  # pylint: disable=import-error


LOGGER = getLogger(__name__)
LMS_DASHBOARD_URL = urljoin(settings.LMS_ROOT_URL, '/dashboard')
LMS_START_PREMIUM_COURSE_FLOW_URL = urljoin(settings.LMS_ROOT_URL, '/verify_student/start-flow/{course_id}/')
LMS_COURSEWARE_URL = urljoin(settings.LMS_ROOT_URL, '/courses/{course_id}/courseware')
LMS_COURSE_URL = urljoin(settings.LMS_ROOT_URL, '/courses/{course_id}/courseware')


def verify_edx_resources():
    """
    Ensure that all necessary resources to render the view are present.
    """
    required_methods = {
        'configuration_helpers': configuration_helpers,
    }

    for method in required_methods:
        if required_methods[method] is None:
            raise NotConnectedToOpenEdX(
                _("The following method from the Open edX platform is necessary for this view but isn't available.")
                + "\nUnavailable: {method}".format(method=method)
            )


class GrantDataSharingPermissions(View):
    """
    Provide a form and form handler for data sharing consent.

    View handles the case in which we get to the "verify consent" step, but consent
    hasn't yet been provided - this view contains a GET view that provides a form for
    consent to be provided, and a POST view that consumes said form.
    """

    page_title = _('Data sharing consent required')
    consent_message_header = _('Consent to share your data')
    requested_permissions_header = _('{enterprise_customer_name} would like to know about:')
    agreement_text = _(
        'I agree to allow {platform_name} to share data about my enrollment, completion and performance '
        'in all {platform_name} courses and programs where my enrollment is sponsored by {enterprise_customer_name}.'
    )
    continue_text = _('Yes, continue')
    abort_text = _('No, take me back.')
    policy_dropdown_header = _('Data Sharing Policy')
    sharable_items_header = _(
        'Enrollment, completion, and performance data that may be shared with {enterprise_customer_name} '
        '(or its designee) for these courses and programs are limited to the following:'
    )
    sharable_items = [
        _('My email address for my {platform_name} account'),
        _('My {platform_name} ID'),
        _('My {platform_name} username'),
        _('What courses and/or programs I\'ve enrolled in or unenrolled from'),
        _(
            'Whether I completed specific parts of each course or program (for example, whether '
            'I watched a given video or completed a given homework assignment)'
        ),
        _('My overall percentage completion of each course or program on a periodic basis'),
        _('My performance in each course or program'),
        _('My final grade in each course or program'),
        _('Whether I received a certificate in each course or program'),
    ]
    sharable_items_footer = _(
        'My permission applies only to data from courses or programs that are sponsored by {enterprise_customer_name}'
        ', and not to data from any {platform_name} courses or programs that I take on my own. I understand that '
        'once I grant my permission to allow data to be shared with {enterprise_customer_name}, '
        'I may not withdraw my permission but I may elect to unenroll from any courses that are '
        'sponsored by {enterprise_customer_name}.'
    )
    sharable_items_note_header = _('Please note')
    sharable_items_notes = [
        _('If you decline to consent, that fact may be shared with {enterprise_customer_name}.'),
    ]
    confirmation_modal_header = _('Are you aware...')
    modal_affirm_decline_msg = _('I decline')
    modal_abort_decline_msg = _('View the data sharing policy')
    policy_link_template = _('View the {start_link}data sharing policy{end_link}.').format(
        start_link='<a href="#consent-policy-dropdown-bar" class="policy-dropdown-link background-input" '
                   'id="policy-dropdown-link">',
        end_link='</a>',
    )
    policy_return_link_text = _('Return to Top')
    welcome_text = _('Welcome to {platform_name}.')
    enterprise_welcome_text = _(
        "{strong_start}{enterprise_customer_name}{strong_end} has partnered with "
        "{strong_start}{platform_name}{strong_end} to offer you high-quality learning "
        "opportunities from the world's best universities."
    )

    def get_default_context(self, enterprise_customer, platform_name):
        """
        Get the set of variables that will populate the template by default.
        """
        return {
            'page_title': self.page_title,
            'consent_message_header': self.consent_message_header,
            'requested_permissions_header': self.requested_permissions_header.format(
                enterprise_customer_name=enterprise_customer.name
            ),
            'agreement_text': self.agreement_text.format(
                enterprise_customer_name=enterprise_customer.name,
                platform_name=platform_name,
            ),
            'continue_text': self.continue_text,
            'abort_text': self.abort_text,
            'policy_dropdown_header': self.policy_dropdown_header,
            'sharable_items_header': self.sharable_items_header.format(
                enterprise_customer_name=enterprise_customer.name
            ),
            'sharable_items': [
                item.format(
                    enterprise_customer_name=enterprise_customer.name,
                    platform_name=platform_name
                ) for item in self.sharable_items
            ],
            'sharable_items_footer': self.sharable_items_footer.format(
                enterprise_customer_name=enterprise_customer.name,
                platform_name=platform_name,
            ),
            'sharable_items_note_header': self.sharable_items_note_header,
            'sharable_items_notes': [
                item.format(
                    enterprise_customer_name=enterprise_customer.name,
                    platform_name=platform_name
                ) for item in self.sharable_items_notes
            ],
            'confirmation_modal_header': self.confirmation_modal_header,
            'confirmation_modal_affirm_decline_text': self.modal_affirm_decline_msg,
            'confirmation_modal_abort_decline_text': self.modal_abort_decline_msg,
            'policy_link_template': self.policy_link_template,
            'policy_return_link_text': self.policy_return_link_text,
            'LMS_SEGMENT_KEY': settings.LMS_SEGMENT_KEY,
        }

    @method_decorator(login_required)
    def get_course_specific_consent(self, request, course_id):
        """
        Render a form with course-specific information about data sharing consent.

        This particular variant of the method is called when a `course_id` parameter
        is passed to the view. In this case, the form is rendered with information
        about the specific course that's being set up.

        A 404 will be raised if any of the following conditions are met:
            * Enrollment is not to be deferred and there's an EnterpriseCourseEnrollment
              associated with the current user, but the corresponding EnterpriseCustomer
              does not require course-level consent for this course.
            * Enrollment is to be deferred, but either no EnterpriseCustomer was
              supplied (via the enrollment_deferred GET parameter) or the supplied
              EnterpriseCustomer doesn't exist.
        """
        try:
            # Make sure course run exists.
            CourseApiClient().get_course_details(course_id)
        except HttpClientError:
            raise Http404

        next_url = request.GET.get('next')
        failure_url = request.GET.get('failure_url')

        enrollment_deferred = request.GET.get('enrollment_deferred')
        customer = None
        if enrollment_deferred is None:
            # For non-deferred enrollments, check if we need to collect
            # consent and retrieve the EnterpriseCustomer using the existing
            # EnterpriseCourseEnrollment.
            try:
                enrollment = EnterpriseCourseEnrollment.objects.get(
                    enterprise_customer_user__user_id=request.user.id,
                    course_id=course_id
                )
                customer = enrollment.enterprise_customer_user.enterprise_customer
                if not consent_required(
                        request.user,
                        enrollment.enterprise_customer_user.username,
                        course_id,
                        customer.uuid
                ):
                    raise Http404
            except EnterpriseCourseEnrollment.DoesNotExist:
                # Enrollment is not deferred, but we don't have
                # an EnterpriseCourseEnrollment yet, so we carry
                # and attempt to retrieve the EnterpriseCustomer
                # using the enterprise_id request param below.
                pass

        # Deferred enrollments will pass the EnterpriseCustomer UUID
        # as a request parameter. Use it to get the EnterpriseCustomer
        # if we were not able to retrieve it above.
        if not customer:
            enterprise_uuid = request.GET.get('enterprise_id')
            customer = get_object_or_404(EnterpriseCustomer, uuid=enterprise_uuid)

        platform_name = configuration_helpers.get_value("PLATFORM_NAME", settings.PLATFORM_NAME)
        context_data = self.get_default_context(customer, platform_name)
        # Translators: bold_start and bold_end are HTML tags for specifying
        # enterprise name in bold text.
        course_specific_context = {
            'consent_request_prompt': _(
                'To access this course, you must first consent to share your learning achievements '
                'with {bold_start}{enterprise_customer_name}{bold_end}.'
            ).format(
                enterprise_customer_name=customer.name,
                bold_start='<b>',
                bold_end='</b>',
            ),
            'requested_permissions_header': _(
                'Per the {start_link}Data Sharing Policy{end_link}, '
                '{bold_start}{enterprise_customer_name}{bold_end} would like to know about:'
            ).format(
                enterprise_customer_name=customer.name,
                bold_start='<b>',
                bold_end='</b>',
                start_link='<a href="#consent-policy-dropdown-bar" '
                           'class="policy-dropdown-link background-input failure-link" id="policy-dropdown-link">',
                end_link='</a>',

            ),
            'confirmation_alert_prompt': _(
                'In order to start this course and use your discount, {bold_start}you must{bold_end} consent '
                'to share your course data with {enterprise_customer_name}.'
            ).format(
                enterprise_customer_name=customer.name,
                bold_start='<b>',
                bold_end='</b>',
            ),
            'confirmation_alert_prompt_warning': '',
            'LANGUAGE_CODE': get_language_from_request(request),
            'platform_name': platform_name,
            'course_id': course_id,
            'redirect_url': next_url,
            'enterprise_customer_name': customer.name,
            'course_specific': True,
            'enrollment_deferred': enrollment_deferred is not None,
            'failure_url': failure_url,
            'requested_permissions': [
                _('your enrollment in this course'),
                _('your learning progress'),
                _('course completion'),
            ],
            'enterprise_customer': customer,
            'welcome_text': self.welcome_text.format(platform_name=platform_name),
            'enterprise_welcome_text': self.enterprise_welcome_text.format(
                enterprise_customer_name=customer.name,
                platform_name=platform_name,
                strong_start='<strong>',
                strong_end='</strong>',
            ),
            'policy_link_template': '',
        }
        context_data.update(course_specific_context)
        if customer.require_account_level_consent:
            context_data.update({
                'consent_request_prompt': _(
                    'To access this and other courses sponsored by {bold_start}{enterprise_customer_name}{bold_end}, '
                    'and to use the discounts available to you, you must first consent to share your '
                    'learning achievements with {bold_start}{enterprise_customer_name}{bold_end}.'
                ).format(
                    enterprise_customer_name=customer.name,
                    bold_start='<b>',
                    bold_end='</b>',
                ),
                'requested_permissions': [
                    _('your enrollment in all sponsored courses'),
                    _('your learning progress'),
                    _('course completion'),
                ],
            })

        return render(request, 'enterprise/grant_data_sharing_permissions.html', context=context_data)

    def get(self, request):
        """
        Render a form to collect user input about data sharing consent.
        """
        # Verify that all necessary resources are present
        verify_edx_resources()
        course = request.GET.get('course_id', '')

        return self.get_course_specific_consent(request, course)

    @method_decorator(login_required)
    def post_course_specific_consent(self, request, course_id, consent_provided):
        """
        Interpret the course-specific form above and save it to an EnterpriseCourseEnrollment object.
        """
        try:
            client = CourseApiClient()
            client.get_course_details(course_id)
        except HttpClientError:
            raise Http404

        enrollment_deferred = request.POST.get('enrollment_deferred')
        if enrollment_deferred is None:
            enterprise_customer = get_enterprise_customer_for_user(request.user)
            enterprise_customer_user, __ = EnterpriseCustomerUser.objects.get_or_create(
                enterprise_customer=enterprise_customer,
                user_id=request.user.id
            )
            EnterpriseCourseEnrollment.objects.update_or_create(
                enterprise_customer_user=enterprise_customer_user,
                course_id=course_id,
            )
            DataSharingConsent.objects.update_or_create(
                username=request.user.username,
                course_id=course_id,
                enterprise_customer=enterprise_customer,
                defaults={
                    'granted': consent_provided
                },
            )

        if not consent_provided:
            failure_url = request.POST.get('failure_url') or reverse('dashboard')
            return redirect(failure_url)

        return redirect(request.POST.get('redirect_url', reverse('dashboard')))

    def post(self, request):
        """
        Process the above form.
        """
        # Verify that all necessary resources are present
        verify_edx_resources()

        # If the checkbox is unchecked, no value will be sent
        consent_provided = request.POST.get('data_sharing_consent', False)
        specific_course = request.POST.get('course_id', '')

        return self.post_course_specific_consent(request, specific_course, consent_provided)


class HandleConsentEnrollment(View):
    """
    Handle enterprise course enrollment at providing data sharing consent.

    View handles the case for enterprise course enrollment after successful
    consent.
    """

    @method_decorator(enterprise_login_required)
    def get(self, request, enterprise_uuid, course_id):
        """
        Handle the enrollment of enterprise learner in the provided course.

        Based on `enterprise_uuid` in URL, the view will decide which
        enterprise customer's course enrollment record should be created.

        Depending on the value of query parameter `course_mode` then learner
        will be either redirected to LMS dashboard for audit modes or
        redirected to ecommerce basket flow for payment of premium modes.
        """
        # Verify that all necessary resources are present
        verify_edx_resources()
        enrollment_course_mode = request.GET.get('course_mode')

        # Redirect the learner to LMS dashboard in case no course mode is
        # provided as query parameter `course_mode`
        if not enrollment_course_mode:
            return redirect(LMS_DASHBOARD_URL)

        try:
            enrollment_client = EnrollmentApiClient()
            course_modes = enrollment_client.get_course_modes(course_id)
        except HttpClientError:
            LOGGER.error('Failed to determine available course modes for course ID: %s', course_id)
            raise Http404

        # Verify that the request user belongs to the enterprise against the
        # provided `enterprise_uuid`.
        enterprise_customer = get_enterprise_customer_or_404(enterprise_uuid)
        enterprise_customer_user = get_enterprise_customer_user(request.user.id, enterprise_customer.uuid)
        if not enterprise_customer_user:
            raise Http404

        selected_course_mode = None
        for course_mode in course_modes:
            if course_mode['slug'] == enrollment_course_mode:
                selected_course_mode = course_mode
                break

        if not selected_course_mode:
            return redirect(LMS_DASHBOARD_URL)

        # Create the Enterprise backend database records for this course
        # enrollment
        EnterpriseCourseEnrollment.objects.update_or_create(
            enterprise_customer_user=enterprise_customer_user,
            course_id=course_id,
        )
        DataSharingConsent.objects.update_or_create(
            username=enterprise_customer_user.username,
            course_id=course_id,
            enterprise_customer=enterprise_customer_user.enterprise_customer,
            defaults={
                'granted': True
            },
        )

        audit_modes = getattr(settings, 'ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES', ['audit', 'honor'])
        if selected_course_mode['slug'] in audit_modes:
            # In case of Audit course modes enroll the learner directly through
            # enrollment API client and redirect the learner to dashboard.
            try:
                ecommerce_api_client = EcommerceApiClient(request.user)
                # Post to E-Commerce for audit enrollment.
                ecommerce_api_client.post_audit_order_to_ecommerce(request, selected_course_mode['sku'])
            except (HTTPError, Timeout, HttpClientError):
                return redirect('enterprise_course_enrollment_page', enterprise_uuid, course_id)

            return redirect(LMS_COURSEWARE_URL.format(course_id=course_id))

        # redirect the enterprise learner to the ecommerce flow in LMS
        # Note: LMS start flow automatically detects the paid mode
        return redirect(LMS_START_PREMIUM_COURSE_FLOW_URL.format(course_id=course_id))


class CourseEnrollmentView(View):
    """
    Enterprise landing page view.

    This view will display the course mode selection with related enterprise
    information.
    """

    PACING_FORMAT = {
        'instructor_paced': _('Instructor-Paced'),
        'self_paced': _('Self-Paced')
    }
    STATIC_TEXT_FORMAT = {
        'page_title': _('Confirm your course'),
        'confirmation_text': _('Confirm your course'),
        'starts_at_text': _('Starts'),
        'view_course_details_text': _('View Course Details'),
        'select_mode_text': _('Please select one:'),
        'price_text': _('Price'),
        'free_price_text': _('FREE'),
        'verified_text': _(
            'Earn a verified certificate!'
        ),
        'audit_text': _(
            'Not eligible for a certificate; does not count toward a MicroMasters'
        ),
        'continue_link_text': _('Continue'),
        'level_text': _('Level'),
        'effort_text': _('Effort'),
        'close_modal_button_text': _('Close'),
        'expected_learning_items_text': _("What you'll learn"),
        'course_full_description_text': _('About This Course'),
        'staff_text': _('Course Staff'),
    }
    WELCOME_TEXT_FORMAT = _('Welcome to {platform_name}.')
    ENT_WELCOME_TEXT_FORMAT = _(
        "{strong_start}{enterprise_customer_name}{strong_end} has partnered with "
        "{strong_start}{platform_name}{strong_end} to offer you high-quality learning "
        "opportunities from the world's best universities."
    )

    def set_final_prices(self, modes, request):
        """
        Set the final discounted price on each premium mode.
        """
        result = []
        for mode in modes:
            if mode['premium']:
                mode['final_price'] = self.get_final_price(mode, request)
            result.append(mode)
        return result

    def get_final_price(self, mode, request):
        """
        Get course mode's SKU discounted price after applying any entitlement available for this user.
        """
        try:
            ecommerce_api_client = EcommerceApiClient(request.user)
            return ecommerce_api_client.get_course_final_price(mode)
        except HttpClientError:
            LOGGER.error(
                "Failed to get price details for course mode's SKU '{sku}' for username '{username}'".format(
                    sku=mode['sku'], username=request.user.username
                )
            )
            return mode['original_price']

    def get_base_details(self, enterprise_uuid, course_run_id):
        """
        Retrieve fundamental details used by both POST and GET versions of this view.

        Specifically, take an EnterpriseCustomer UUID and a course run ID, and transform those
        into an actual EnterpriseCustomer, a set of details about the course, and a list
        of the available course modes for that course run.
        """
        try:
            course, course_run = CourseCatalogApiServiceClient().get_course_and_course_run(course_run_id)
        except (HttpClientError, ImproperlyConfigured):
            logger.error('Failed to get metadata for course run: %s', course_run_id)
            raise Http404

        if course is None or course_run is None:
            logger.error('Unable to find metadata for course run: %s', course_run_id)
            raise Http404

        enterprise_customer = get_enterprise_customer_or_404(enterprise_uuid)

        try:
            enrollment_client = EnrollmentApiClient()
            modes = enrollment_client.get_course_modes(course_run_id)
        except HttpClientError:
            logger.error('Failed to determine available course modes for course run: %s', course_run_id)
            raise Http404

        course_modes = []

        audit_modes = getattr(
            settings,
            'ENTERPRISE_COURSE_ENROLLMENT_AUDIT_MODES',
            ['audit', 'honor']
        )

        for mode in modes:
            if mode['min_price']:
                price_text = '${}'.format(mode['min_price'])
            else:
                price_text = self.STATIC_TEXT_FORMAT['free_price_text']
            if mode['slug'] in audit_modes:
                description = self.STATIC_TEXT_FORMAT['audit_text']
            else:
                description = self.STATIC_TEXT_FORMAT['verified_text']
            course_modes.append({
                'mode': mode['slug'],
                'min_price': mode['min_price'],
                'sku': mode['sku'],
                'title': mode['name'],
                'original_price': price_text,
                'final_price': price_text,
                'description': description,
                'premium': mode['slug'] not in audit_modes
            })

        return enterprise_customer, course, course_run, course_modes

    def get_enterprise_course_enrollment_page(self, request, enterprise_customer, course, course_run, course_modes,
                                              enterprise_course_enrollment):
        """
        Render enterprise specific course track selection page.
        """
        platform_name = configuration_helpers.get_value('PLATFORM_NAME', settings.PLATFORM_NAME)
        course_start_date = ''
        if course_run['start']:
            course_start_date = parse(course_run['start']).strftime('%B %d, %Y')

        # Format the course effort string using the min/max effort
        # fields for the course run.
        course_effort = ''
        min_effort = course_run['min_effort'] or ''
        max_effort = course_run['max_effort'] or ''
        effort_hours = '{min}-{max}'.format(min=min_effort, max=max_effort).strip('-')
        if effort_hours:
            # If we are dealing with just one of min/max effort
            # cast the hours value to a string so that pluralization
            # is handled appropriately when formatting the full
            # course effort string below.
            if '-' not in effort_hours:
                effort_hours = int(effort_hours)
            course_effort = ungettext(
                '{hours} hour per week',
                '{hours} hours per week',
                effort_hours,
            ).format(hours=effort_hours)

        # Retrieve the enterprise-discounted price from ecommerce.
        course_modes = self.set_final_prices(course_modes, request)
        premium_modes = [mode for mode in course_modes if mode['premium']]

        # Parse organization name and logo.
        organization_name = ''
        organization_logo = ''
        if course['owners']:
            # The owners key contains the organizations associated with the course.
            # We pick the first one in the list here to meet UX requirements.
            organization = course['owners'][0]
            organization_name = organization['name']
            organization_logo = organization['logo_image_url']

        # Add a message to the message display queue if the learner
        # has gone through the data sharing consent flow and declined
        # to give data sharing consent.
        if enterprise_course_enrollment and not enterprise_course_enrollment.consent_granted:
            add_consent_declined_message(request, enterprise_customer, course_run)

        context_data = {
            'LANGUAGE_CODE': get_language_from_request(request),
            'platform_name': platform_name,
            'course_title': course_run['title'],
            'course_short_description': course_run['short_description'] or '',
            'course_pacing': self.PACING_FORMAT.get(course_run['pacing_type'], ''),
            'course_start_date': course_start_date,
            'course_image_uri': course_run['image']['src'],
            'enterprise_customer': enterprise_customer,
            'welcome_text': self.WELCOME_TEXT_FORMAT.format(platform_name=platform_name),
            'enterprise_welcome_text': self.ENT_WELCOME_TEXT_FORMAT.format(
                enterprise_customer_name=enterprise_customer.name,
                platform_name=platform_name,
                strong_start='<strong>',
                strong_end='</strong>',
            ),
            'course_modes': filter_audit_course_modes(enterprise_customer, course_modes),
            'course_effort': course_effort,
            'course_full_description': course_run['full_description'],
            'organization_logo': organization_logo,
            'organization_name': organization_name,
            'course_level_type': course_run.get('level_type', ''),
            'premium_modes': premium_modes,
            'expected_learning_items': course['expected_learning_items'],
            'staff': course_run['staff'],
        }
        context_data.update(self.STATIC_TEXT_FORMAT)
        return render(request, 'enterprise/enterprise_course_enrollment_page.html', context=context_data)

    @method_decorator(transaction.non_atomic_requests)
    def dispatch(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """
        Disable atomicity for the view.

        Since we have settings.ATOMIC_REQUESTS enabled, Django wraps all view functions in an atomic transaction, so
        they can be rolled back if anything fails.

        However, the we need to be able to save data in the middle of get/post(), so that it's available for calls to
        external APIs.  To allow this, we need to disable atomicity at the top dispatch level.
        """
        return super(CourseEnrollmentView, self).dispatch(*args, **kwargs)

    @method_decorator(enterprise_login_required)
    def post(self, request, enterprise_uuid, course_id):
        """
        Process a submitted track selection form for the enterprise.
        """
        enterprise_customer, course, course_run, course_modes = self.get_base_details(enterprise_uuid, course_id)

        # Create a link between the user and the enterprise customer if it
        # does not already exist.
        enterprise_customer_user, __ = EnterpriseCustomerUser.objects.get_or_create(
            enterprise_customer=enterprise_customer,
            user_id=request.user.id
        )

        data_sharing_consent = DataSharingConsent.objects.proxied_get(
            username=enterprise_customer_user.username,
            course_id=course_id,
            enterprise_customer=enterprise_customer
        )

        try:
            enterprise_course_enrollment = EnterpriseCourseEnrollment.objects.get(
                enterprise_customer_user__enterprise_customer=enterprise_customer,
                enterprise_customer_user__user_id=request.user.id,
                course_id=course_id
            )
        except EnterpriseCourseEnrollment.DoesNotExist:
            enterprise_course_enrollment = None

        selected_course_mode_name = request.POST.get('course_mode')
        selected_course_mode = None
        for course_mode in course_modes:
            if course_mode['mode'] == selected_course_mode_name:
                selected_course_mode = course_mode
                break

        if not selected_course_mode:
            return self.get_enterprise_course_enrollment_page(
                request,
                enterprise_customer,
                course,
                course_run,
                course_modes,
                enterprise_course_enrollment,
                data_sharing_consent
            )

        user_consent_needed = consent_required(
            request.user,
            enterprise_customer_user.username,
            course_id,
            enterprise_customer.uuid
        )
        if not selected_course_mode.get('premium') and not user_consent_needed:
            # For the audit course modes (audit, honor), where DSC is not
            # required, enroll the learner directly through enrollment API
            # client and redirect the learner to LMS courseware page.
            if not enterprise_course_enrollment:
                # Create the Enterprise backend database records for this course enrollment.
                EnterpriseCourseEnrollment.objects.create(
                    enterprise_customer_user=enterprise_customer_user,
                    course_id=course_id,
                )

            try:
                # Post to E-Commerce for audit enrollment.
                ecommerce_api_client = EcommerceApiClient(request.user)
                ecommerce_api_client.post_audit_order_to_ecommerce(request, selected_course_mode['sku'])
            except (HTTPError, Timeout, HttpClientError):
                return redirect('enterprise_course_enrollment_page', enterprise_uuid, course_id)

            return redirect(LMS_COURSEWARE_URL.format(course_id=course_id))

        if user_consent_needed:
            # For the audit course modes (audit, honor) or for the premium
            # course modes (Verified, Prof Ed) where DSC is required, redirect
            # the learner to course specific DSC with enterprise UUID from
            # there the learner will be directed to the ecommerce flow after
            # providing DSC.
            next_url = '{handle_consent_enrollment_url}?{query_string}'.format(
                handle_consent_enrollment_url=reverse(
                    'enterprise_handle_consent_enrollment', args=[enterprise_customer.uuid, course_id]
                ),
                query_string=urlencode({'course_mode': selected_course_mode_name})
            )
            failure_url = reverse('enterprise_course_enrollment_page', args=[enterprise_customer.uuid, course_id])
            return redirect(
                '{grant_data_sharing_url}?{params}'.format(
                    grant_data_sharing_url=reverse('grant_data_sharing_permissions'),
                    params=urlencode(
                        {
                            'next': next_url,
                            'failure_url': failure_url,
                            'enterprise_id': enterprise_customer.uuid,
                            'course_id': course_id,
                        }
                    )
                )
            )

        # For the premium course modes (Verified, Prof Ed) where DSC is
        # not required, redirect the enterprise learner to the ecommerce
        # flow in LMS.
        # Note: LMS start flow automatically detects the paid mode
        return redirect(LMS_START_PREMIUM_COURSE_FLOW_URL.format(course_id=course_id))

    @method_decorator(force_fresh_session)
    @method_decorator(enterprise_login_required)
    def get(self, request, enterprise_uuid, course_id):
        """
        Show course track selection page for the enterprise.

        Based on `enterprise_uuid` in URL, the view will decide which
        enterprise customer's course enrollment page is to use.

        Unauthenticated learners will be redirected to enterprise-linked SSO.

        A 404 will be raised if any of the following conditions are met:
            * No enterprise customer uuid kwarg `enterprise_uuid` in request.
            * No enterprise customer found against the enterprise customer
                uuid `enterprise_uuid` in the request kwargs.
            * No course is found in database against the provided `course_id`.
        """
        # Verify that all necessary resources are present
        verify_edx_resources()

        enterprise_customer, course, course_run, modes = self.get_base_details(enterprise_uuid, course_id)

        # Create a link between the user and the enterprise customer if it does not already exist.  Ensure that the link
        # is saved to the database prior to invoking get_final_price() on the displayed course modes, so that the
        # ecommerce service knows this user belongs to an enterprise customer.
        with transaction.atomic():
            enterprise_customer_user, __ = EnterpriseCustomerUser.objects.get_or_create(
                enterprise_customer=enterprise_customer,
                user_id=request.user.id
            )

        data_sharing_consent = DataSharingConsent.objects.proxied_get(
            username=enterprise_customer_user.username,
            course_id=course_id,
            enterprise_customer=enterprise_customer
        )

        enrollment_client = EnrollmentApiClient()
        enrolled_course = enrollment_client.get_course_enrollment(request.user.username, course_id)
        try:
            enterprise_course_enrollment = EnterpriseCourseEnrollment.objects.get(
                enterprise_customer_user__enterprise_customer=enterprise_customer,
                enterprise_customer_user__user_id=request.user.id,
                course_id=course_id
            )
        except EnterpriseCourseEnrollment.DoesNotExist:
            enterprise_course_enrollment = None

        if enrolled_course and enterprise_course_enrollment:
            # The user is already enrolled in the course through the Enterprise Customer, so redirect to the course
            # info page.
            return redirect(LMS_COURSE_URL.format(course_id=course_id))

        return self.get_enterprise_course_enrollment_page(request, enterprise_customer, course, course_run, modes,
                                                          enterprise_course_enrollment)
