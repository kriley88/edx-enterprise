# -*- coding: utf-8 -*-
"""
Django admin integration for configuring automated data reporting for Enterprise Customers.
"""
from __future__ import absolute_import, unicode_literals

from django.contrib import admin
from enterprise_reporting.models import EnterpriseCustomerReportingConfiguration


@admin.register(EnterpriseCustomerReportingConfiguration)
class EnterpriseCustomerReportingConfigurationAdmin(admin.ModelAdmin):
    """
    Django admin model for EnterpriseCustomerReportingConfiguration.
    """

    list_display = (
        "enterprise_customer",
        "active",
        "email",
        "frequency",
        "day_of_month",
        "day_of_week",
        "hour_of_day",
    )

    readonly_fields = (
        "password",
    )

    list_filter = ("active",)
    search_fields = ("enterprise_customer",)

    class Meta(object):
        model = EnterpriseCustomerReportingConfiguration
