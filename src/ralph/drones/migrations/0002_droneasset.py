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
        ("drones", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DroneAsset",
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
                    "identifier",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=64,
                        null=True,
                        unique=True,
                        verbose_name="drone identifier",
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
                    "model_name",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="model",
                    ),
                ),
                (
                    "drone_type",
                    models.CharField(
                        choices=[
                            ("quadcopter", "Quadcopter"),
                            ("fixed_wing", "Fixed-wing"),
                            ("vtol", "VTOL"),
                            ("hexacopter", "Hexacopter"),
                            ("other", "Other"),
                        ],
                        default="quadcopter",
                        max_length=32,
                        verbose_name="type",
                    ),
                ),
                (
                    "firmware_version",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="firmware version",
                    ),
                ),
                (
                    "last_firmware_update",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="last firmware update",
                    ),
                ),
                (
                    "battery_capacity_mah",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="battery capacity (mAh)",
                    ),
                ),
                (
                    "battery_health_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                        verbose_name="battery health (%)",
                    ),
                ),
                (
                    "flight_time_limit_minutes",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="flight time limit (minutes)",
                    ),
                ),
                (
                    "total_flight_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=7,
                        verbose_name="total flight hours",
                    ),
                ),
                (
                    "flight_count",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="flight count",
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
                    "last_known_latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="last known latitude",
                    ),
                ),
                (
                    "last_known_longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="last known longitude",
                    ),
                ),
                (
                    "last_known_altitude_m",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=7,
                        null=True,
                        verbose_name="last known altitude (m)",
                    ),
                ),
                (
                    "status",
                    ralph.lib.transitions.fields.TransitionField(
                        choices=[
                            (1, "new"),
                            (2, "awaiting activation"),
                            (3, "operational"),
                            (4, "maintenance"),
                            (5, "grounded"),
                            (6, "retired"),
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
                    "next_maintenance_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="next maintenance date",
                    ),
                ),
                (
                    "next_maintenance_flight_hours",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=7,
                        null=True,
                        verbose_name="next maintenance flight hours",
                    ),
                ),
                (
                    "assigned_team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="drone_assets",
                        to="accounts.team",
                        verbose_name="assigned team",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="drone_assets_as_owner",
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
                        related_name="drone_assets_as_operator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned operator",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone asset",
                "verbose_name_plural": "Drone assets",
            },
            bases=("assets.asset", models.Model),
        ),
    ]

