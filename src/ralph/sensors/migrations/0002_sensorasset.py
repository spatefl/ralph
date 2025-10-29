# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
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
        ("sensors", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SensorAsset",
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
                    "sensor_type",
                    models.CharField(
                        max_length=64,
                        verbose_name="sensor type",
                    ),
                ),
                (
                    "model_name",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="model",
                    ),
                ),
                (
                    "serial_number",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=64,
                        null=True,
                        unique=True,
                        verbose_name="serial number",
                    ),
                ),
                (
                    "external_identifier",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=128,
                        null=True,
                        unique=True,
                        verbose_name="external identifier",
                    ),
                ),
                (
                    "location_description",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="location description",
                    ),
                ),
                (
                    "installation_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="installation date",
                    ),
                ),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="latitude",
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="longitude",
                    ),
                ),
                (
                    "battery_level_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                        verbose_name="battery level (%)",
                    ),
                ),
                (
                    "last_calibrated",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="last calibrated",
                    ),
                ),
                (
                    "next_calibration_due",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="next calibration due",
                    ),
                ),
                (
                    "calibration_interval_days",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="calibration interval (days)",
                    ),
                ),
                (
                    "last_online_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="last online at",
                    ),
                ),
                (
                    "status",
                    ralph.lib.transitions.fields.TransitionField(
                        choices=[
                            (1, "new"),
                            (2, "installed"),
                            (3, "maintenance"),
                            (4, "faulty"),
                            (5, "retired"),
                        ],
                        default=1,
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
                    "total_uptime_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="total uptime (hours)",
                    ),
                ),
                (
                    "total_downtime_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="total downtime (hours)",
                    ),
                ),
                (
                    "external_feed_reference",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="external feed reference",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sensor_assets_as_owner",
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
                        related_name="sensor_assets_as_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor asset",
                "verbose_name_plural": "Sensor assets",
            },
            bases=("assets.asset", models.Model),
        ),
    ]

