# -*- coding: utf-8 -*-
"""
Database models for Enterprise Reporting.
"""
from __future__ import absolute_import, unicode_literals

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from model_utils.models import TimeStampedModel

from enterprise.models import EnterpriseCustomer


@python_2_unicode_compatible
class EnterpriseCustomerReportingConfiguration(TimeStampedModel):
    """
    The Enterprise's configuration for sending automated data reports securely via email to the Enterprise Admin.
    """

    FREQUENCY_TYPE_DAILY = 'daily'
    FREQUENCY_TYPE_MONTHLY = 'monthly'
    FREQUENCY_TYPE_WEEKLY = 'weekly'

    FREQUENCY_CHOICES = (
        (FREQUENCY_TYPE_DAILY, FREQUENCY_TYPE_DAILY),
        (FREQUENCY_TYPE_MONTHLY, FREQUENCY_TYPE_MONTHLY),
        (FREQUENCY_TYPE_WEEKLY, FREQUENCY_TYPE_WEEKLY),
    )

    DELIVERY_METHOD_EMAIL = 'email'
    # We are adding this field preemptively as we plan to support FTP, but don't have the details yet.
    DELIVERY_METHOD_FTP = 'ftp'

    DELIVERY_METHOD_CHOICES = (
        (DELIVERY_METHOD_EMAIL, DELIVERY_METHOD_EMAIL),
        (DELIVERY_METHOD_FTP, DELIVERY_METHOD_FTP),
    )

    DAYS_OF_WEEK = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )

    enterprise_customer = models.OneToOneField(
        EnterpriseCustomer, blank=False, null=False, verbose_name=_("Enterprise Customer")
    )
    active = models.BooleanField(blank=False, null=False, verbose_name=_("Active"))
    delivery_method = models.CharField(
        max_length=20,
        choices=DELIVERY_METHOD_CHOICES,
        blank=False,
        default=DELIVERY_METHOD_EMAIL,
        verbose_name=_("Delivery Method"),
        help_text=_("The method in which the data should be sent.")
    )
    email = models.EmailField(blank=False, null=False, verbose_name=_("Email"))
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        blank=False,
        default=FREQUENCY_TYPE_MONTHLY,
        verbose_name=_("Frequency"),
        help_text=_("The frequency interval (daily, weekly, or monthly) that the report should be sent."),
    )
    day_of_month = models.SmallIntegerField(
        blank=True,
        null=True,
        verbose_name=_("Day of Month"),
        help_text=_("The day of the month to send the report. "
                    "This field is required and only valid when the frequency is monthly."),
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    day_of_week = models.SmallIntegerField(
        blank=True,
        null=True,
        choices=DAYS_OF_WEEK,
        verbose_name=_("Day of Week"),
        help_text=_("The day of the week to send the report. "
                    "This field is required and only valid when the frequency is weekly."),
    )
    hour_of_day = models.SmallIntegerField(
        blank=False,
        null=False,
        verbose_name=_("Hour of Day"),
        help_text=_("The hour of the day to send the report, in Eastern Standard Time (EST). "
                    "This is required for all frequency settings."),
        validators=[MinValueValidator(0), MaxValueValidator(23)]
    )
    password = models.CharField(
        max_length=20,
        blank=False,
        null=False,
        editable=False,
        verbose_name=_("Password"),
    )

    class Meta:
        app_label = 'enterprise_reporting'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<EnterpriseCustomerReportingConfiguration for Enterprise {enterprise_name}>".format(
            enterprise_name=self.enterprise_customer.name
        )

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()

    def save(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """
        Override of model save method to dynamically generate the password field and perform additional validation.
        """
        self.password = get_random_string(length=20)
        self.full_clean()
        super(EnterpriseCustomerReportingConfiguration, self).save(*args, **kwargs)

    def clean(self):
        """
        Override of clean method to perform additional validation on frequency and day_of_month/day_of week.
        """
        if self.frequency == self.FREQUENCY_TYPE_DAILY:
            self.day_of_month = None
            self.day_of_week = None
        elif self.frequency == self.FREQUENCY_TYPE_WEEKLY:
            if self.day_of_week is None or self.day_of_week == '':
                raise ValidationError({'day_of_week': _('Day of week must be set if the frequency is weekly.')})
            self.day_of_month = None
        elif self.frequency == self.FREQUENCY_TYPE_MONTHLY:
            if not self.day_of_month:
                raise ValidationError({'day_of_month': _('Day of month must be set if the frequency is monthly.')})
            self.day_of_week = None
        else:
            raise ValidationError(_('Frequency must be set to either daily, weekly, or monthly.'))
