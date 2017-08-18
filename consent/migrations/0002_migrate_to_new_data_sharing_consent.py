# -*- coding: utf-8 -*-
"""
Custom migration to transfer consent data from the ``enterprise`` application to the ``consent`` application's
``DataSharingConsent`` model.

This migration only does anything significant when running forward. If you would like to do a backwards-migration,
delete all new rows that were populated in the ``DataSharingConsent`` model's tables.
(If you have new data in the tables that weren't migrated, use timestamps as you see fit).

The reason there's no backwards-migration in code is because we can't reasonably determine which
data was transferred and which data is new at the time of the migration. In order to avoid deleting
new data, we simply leave it to someone with DB access to manage things based on the desired timestamp.
"""

from __future__ import unicode_literals

from consent.models import DataSharingConsent

from django.db import migrations

from enterprise.models import EnterpriseCourseEnrollment, UserDataSharingConsentAudit


def populate_data_sharing_consent(apps, schema_editor):
    """
    Populates the ``DataSharingConsent`` model with the ``enterprise`` application's consent data.

    Consent data from the ``enterprise`` application come from the ``EnterpriseCourseEnrollment`` and
    ``UserDataSharingConsentAudit`` models.

    We check the ``EnterpriseCourseEnrollment`` first, and only check ``UserDataSharingConsentAudit`` in case
    consent information isn't available in ``EnterpriseCourseEnrollment``.
    """
    for enrollment in EnterpriseCourseEnrollment.objects.all():
        data_sharing_consent = DataSharingConsent.objects.create(
            enterprise_customer=enrollment.enterprise_customer_user.enterprise_customer,
            course_id=enrollment.course_id
        )
        data_sharing_consent.granted = enrollment.consent_available
        data_sharing_consent.save()


class Migration(migrations.Migration):

    dependencies = [
        # Make sure enterprise models (source) are available.
        ('enterprise', '0023_audit_data_reporting_flag'),
        # Make sure consent models (target) are available.
        ('consent', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            populate_data_sharing_consent,
            reverse_code=lambda apps, schema_editor: None
        ),
    ]
