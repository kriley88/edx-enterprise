"""
Serializers for enterprise api version 1.
"""
from __future__ import absolute_import, unicode_literals

from rest_framework import serializers

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.utils.translation import ugettext_lazy as _

from enterprise import models
from enterprise.api.v1.mixins import EnterpriseCourseContextSerializerMixin


class ImmutableStateSerializer(serializers.Serializer):
    """
    Base serializer for any serializer that inhibits state changing requests.
    """

    def create(self, validated_data):
        """
        Do not perform any operations for state changing requests.
        """
        pass

    def update(self, instance, validated_data):
        """
        Do not perform any operations for state changing requests.
        """
        pass


class ResponsePaginationSerializer(ImmutableStateSerializer):
    """
    Serializer for responses that require pagination.
    """

    count = serializers.IntegerField(read_only=True, help_text=_('Total count of items.'))
    next = serializers.CharField(read_only=True, help_text=_('URL to fetch next page of items.'))
    previous = serializers.CharField(read_only=True, help_text=_('URL to fetch previous page of items.'))
    results = serializers.ListField(read_only=True, help_text=_('List of items.'))


class SiteSerializer(serializers.ModelSerializer):
    """
    Serializer for Site model.
    """

    class Meta:
        model = Site
        fields = (
            'domain', 'name',
        )


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model.
    """

    class Meta:
        model = User
        fields = (
            'id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'is_active', 'date_joined'
        )


class EnterpriseCustomerBrandingConfigurationSerializer(serializers.ModelSerializer):
    """
    Serializer for EnterpriseCustomerBrandingConfiguration model.
    """

    class Meta:
        model = models.EnterpriseCustomerBrandingConfiguration
        fields = (
            'enterprise_customer', 'logo'
        )


class EnterpriseCustomerEntitlementSerializer(serializers.ModelSerializer):
    """
    Serializer for EnterpriseCustomerEntitlement model.
    """

    class Meta:
        model = models.EnterpriseCustomerEntitlement
        fields = (
            'enterprise_customer', 'entitlement_id'
        )


class EnterpriseCustomerSerializer(serializers.ModelSerializer):
    """
    Serializer for EnterpriseCustomer model.
    """

    class Meta:
        model = models.EnterpriseCustomer
        fields = (
            'uuid', 'name', 'catalog', 'active', 'site', 'enable_data_sharing_consent', 'enforce_data_sharing_consent',
            'enterprise_customer_users', 'branding_configuration', 'enterprise_customer_entitlements',
            'enable_audit_enrollment'
        )

    site = SiteSerializer()
    branding_configuration = EnterpriseCustomerBrandingConfigurationSerializer()
    enterprise_customer_entitlements = EnterpriseCustomerEntitlementSerializer(  # pylint: disable=invalid-name
        many=True,
    )


class EnterpriseCourseEnrollmentReadOnlySerializer(serializers.ModelSerializer):
    """
    Serializer for EnterpriseCourseEnrollment model.
    """

    class Meta:
        model = models.EnterpriseCourseEnrollment
        fields = (
            'enterprise_customer_user', 'consent_granted', 'course_id'
        )


class EnterpriseCourseEnrollmentWriteSerializer(serializers.ModelSerializer):
    """
    Serializer for writing to the EnterpriseCourseEnrollment model.
    """

    class Meta:
        model = models.EnterpriseCourseEnrollment
        fields = (
            'username', 'course_id', 'consent_granted'
        )

    username = serializers.CharField(max_length=30)
    enterprise_customer_user = None

    def validate_username(self, value):
        """
        Verify that the username has a matching user, and that the user has an associated EnterpriseCustomerUser.
        """
        try:
            user = User.objects.get(username=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")

        try:
            enterprise_customer_user = models.EnterpriseCustomerUser.objects.get(user_id=user.pk)
        except models.EnterpriseCustomerUser.DoesNotExist:
            raise serializers.ValidationError("User has no EnterpriseCustomerUser")

        self.enterprise_customer_user = enterprise_customer_user
        return value

    def save(self):  # pylint: disable=arguments-differ
        """
        Save the model with the found EnterpriseCustomerUser.
        """
        course_id = self.validated_data['course_id']
        consent_granted = self.validated_data['consent_granted']

        models.EnterpriseCourseEnrollment.objects.get_or_create(
            enterprise_customer_user=self.enterprise_customer_user,
            course_id=course_id,
            consent_granted=consent_granted,
        )


class EnterpriseCustomerCatalogSerializer(serializers.ModelSerializer):
    """
    Serializer for the ``EnterpriseCustomerCatalog`` model.
    """

    class Meta:
        model = models.EnterpriseCustomerCatalog
        fields = (
            'uuid', 'enterprise_customer', 'query',
        )


class UserDataSharingConsentAuditSerializer(serializers.ModelSerializer):
    """
    Serializer for UserDataSharingConsentAudit model.
    """

    class Meta:
        model = models.UserDataSharingConsentAudit
        fields = (
            'user', 'state', 'enabled'
        )


class EnterpriseCustomerUserReadOnlySerializer(serializers.ModelSerializer):
    """
    Serializer for EnterpriseCustomerUser model.
    """

    class Meta:
        model = models.EnterpriseCustomerUser
        fields = (
            'id', 'enterprise_customer', 'user_id', 'user', 'data_sharing_consent'
        )

    user = UserSerializer()
    enterprise_customer = EnterpriseCustomerSerializer()
    data_sharing_consent = UserDataSharingConsentAuditSerializer(many=True)


class EnterpriseCustomerUserWriteSerializer(serializers.ModelSerializer):
    """
    Serializer for writing to the EnterpriseCustomerUser model.
    """

    class Meta:
        model = models.EnterpriseCustomerUser
        fields = (
            'enterprise_customer', 'username'
        )

    username = serializers.CharField(max_length=30)
    user = None

    def validate_username(self, value):
        """
        Verify that the username has a matching user.
        """
        try:
            self.user = User.objects.get(username=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")

        return value

    def save(self):  # pylint: disable=arguments-differ
        """
        Save the EnterpriseCustomerUser.
        """
        enterprise_customer = self.validated_data['enterprise_customer']

        ecu = models.EnterpriseCustomerUser(
            user_id=self.user.pk,
            enterprise_customer=enterprise_customer,
        )
        ecu.save()


class EnterpriseCustomerUserEntitlementSerializer(ImmutableStateSerializer):
    """
    Serializer for the entitlements of EnterpriseCustomerUser.

    This Serializer is for read only endpoint of enterprise learner's entitlements
    It will ignore any state changing requests like POST, PUT and PATCH.
    """

    entitlements = serializers.ListField(
        child=serializers.DictField()
    )

    user = UserSerializer(read_only=True)
    enterprise_customer = EnterpriseCustomerSerializer(read_only=True)
    data_sharing_consent = UserDataSharingConsentAuditSerializer(many=True, read_only=True)


class EnterpriseCustomerCatalogReadOnlySerializer(ResponsePaginationSerializer):
    """
    Paginated serializer for Enterprise Catalog API responses.
    """
    pass


class EnterpriseProgramApiReadOnlySerializer(ImmutableStateSerializer, EnterpriseCourseContextSerializerMixin):
    """
    Serializer for detailed Programs responses.
    """

    uuid = serializers.UUIDField(
        read_only=True,
        help_text=_('UUID of the Enterprise Program.'),
    )
    title = serializers.CharField(
        max_length=255,
        help_text=_('The user-facing display title for this Program.'),
    )
    subtitle = serializers.CharField(
        max_length=255,
        help_text=_('A brief, descriptive subtitle for the Program.'),
    )
    type = serializers.CharField(
        max_length=32,
    )
    status = serializers.CharField(
        max_length=24,
        help_text=_('The lifecycle status of this Program.'),
    )
    marketing_slug = serializers.SlugField(
        max_length=255,
        help_text=_("Slug used to generate links to the Enterprise's marketing site."),
    )
    marketing_url = serializers.URLField(
        help_text=_("URL to the Enterprise's marketing site."),
    )
    banner_image = serializers.DictField(
        help_text=_("The Enterprise's banner image for this Program."),
    )
    courses = serializers.ListField(
        help_text=_('List of courses in the Program.'),
    )
    authoring_organizations = serializers.ListField(
        help_text=_('The organizations involved in authoring the courses in the Program.'),
    )
    card_image_url = serializers.URLField(
        help_text=_('Image used for discovery cards'),
    )
    is_program_eligible_for_one_click_purchase = serializers.BooleanField(  # pylint: disable=invalid-name
        help_text=_('Allow courses in this program to be purchased in a single transaction'),
    )
    overview = serializers.CharField(
        help_text=_('Overview of the Program.'),
    )
    min_hours_effort_per_week = serializers.IntegerField()
    max_hours_effort_per_week = serializers.IntegerField()
    video = serializers.DictField()
    expected_learning_items = serializers.ListField()
    faq = serializers.ListField()
    credit_backing_organizations = serializers.ListField()
    corporate_endorsements = serializers.ListField()
    job_outlook_items = serializers.ListField()
    individual_endorsements = serializers.ListField()
    languages = serializers.ListField()
    transcript_languages = serializers.ListField()
    subjects = serializers.ListField()
    price_ranges = serializers.ListField()
    staff = serializers.ListField()
    credit_redemption_overview = serializers.CharField(
        help_text=_('The description of credit redemption for courses in program'),
    )
    applicable_seat_types = serializers.ListField()


class CourseCatalogApiResponseReadOnlySerializer(ImmutableStateSerializer):
    """
    Serializer for enterprise customer catalog.
    """

    # pylint: disable=invalid-name
    id = serializers.IntegerField(read_only=True, help_text=_('Enterprise course catalog primary key.'))
    name = serializers.CharField(help_text=_('Catalog name'))
    query = serializers.CharField(help_text=_('Query to retrieve catalog contents'))
    courses_count = serializers.IntegerField(read_only=True, help_text=_('Number of courses contained in this catalog'))
    viewers = serializers.ListField(
        allow_null=True, allow_empty=True, required=False,
        help_text=_('Usernames of users with explicit access to view this catalog'),
        style={'base_template': 'input.html'},
        child=serializers.CharField(),
    )


class EnterpriseCatalogCoursesReadOnlySerializer(ResponsePaginationSerializer, EnterpriseCourseContextSerializerMixin):
    """
    Serializer for enterprise customer catalog courses.
    """
    pass
