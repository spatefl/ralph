# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import ralph.lib.mixins.fields
import ralph.lib.transitions.fields


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0043_disaster_relief_categories"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0012_auto_20250408_1522"),
        ("fleet", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FleetAsset",
            fields=[
                (
                    "asset_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="assets.asset",
                    ),
                ),
                (
                    "license_plate",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=32,
                        null=True,
                        unique=True,
                        verbose_name="license plate",
                    ),
                ),
                (
                    "vin",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=32,
                        null=True,
                        unique=True,
                        verbose_name="vehicle identification number (VIN)",
                    ),
                ),
                (
                    "vehicle_type",
                    models.CharField(
                        choices=[
                            ("car", "Car"),
                            ("truck", "Truck"),
                            ("van", "Van"),
                            ("suv", "SUV"),
                            ("heavy", "Heavy equipment"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=32,
                        verbose_name="vehicle type",
                    ),
                ),
                (
                    "fuel_type",
                    models.CharField(
                        choices=[
                            ("gasoline", "Gasoline"),
                            ("diesel", "Diesel"),
                            ("hybrid", "Hybrid"),
                            ("electric", "Electric"),
                            ("other", "Other"),
                        ],
                        default="gasoline",
                        max_length=16,
                        verbose_name="fuel type",
                    ),
                ),
                (
                    "odometer_km",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="odometer (km)",
                    ),
                ),
                (
                    "hours_used",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="hours used",
                    ),
                ),
                (
                    "assigned_location",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="assigned location",
                    ),
                ),
                (
                    "status",
                    ralph.lib.transitions.fields.TransitionField(
                        choices=[
                            (1, "new"),
                            (2, "in service"),
                            (3, "maintenance"),
                            (4, "reserved"),
                            (5, "out of service"),
                            (6, "decommissioned"),
                        ],
                        default=1,
                    ),
                ),
                (
                    "last_service_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="last service date",
                    ),
                ),
                (
                    "next_service_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="next service date",
                    ),
                ),
                (
                    "next_service_odometer",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="next service odometer (km)",
                    ),
                ),
                (
                    "last_status_change",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="last status change",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fleet_assets_as_owner",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="asset owner",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="accounts.region",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fleet_assets_as_driver",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned driver",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fleet asset",
                "verbose_name_plural": "Fleet assets",
            },
            bases=("assets.asset", models.Model),
        ),
    ]

