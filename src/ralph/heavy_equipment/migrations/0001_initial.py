# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import ralph.lib.mixins.fields
import ralph.lib.transitions.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("assets", "0043_disaster_relief_categories"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0012_auto_20250408_1522"),
    ]

    operations = [
        migrations.CreateModel(
            name="HeavyEquipmentAsset",
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
                    "equipment_identifier",
                    ralph.lib.mixins.fields.NullableCharField(
                        blank=True,
                        max_length=64,
                        null=True,
                        unique=True,
                        verbose_name="equipment identifier",
                    ),
                ),
                (
                    "equipment_type",
                    models.CharField(
                        choices=[
                            ("generator", "Generator"),
                            ("trailer", "Trailer"),
                            ("excavator", "Excavator"),
                            ("pump", "Pump"),
                            ("tank", "Tank / Water system"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=32,
                        verbose_name="equipment type",
                    ),
                ),
                (
                    "manufacturer",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="manufacturer",
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
                    "assigned_location",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="assigned location",
                    ),
                ),
                (
                    "fuel_capacity_liters",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="fuel capacity (L)",
                    ),
                ),
                (
                    "fuel_level_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                        verbose_name="fuel level (%)",
                    ),
                ),
                (
                    "water_tank_capacity_liters",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="water tank capacity (L)",
                    ),
                ),
                (
                    "water_level_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                        verbose_name="water level (%)",
                    ),
                ),
                (
                    "battery_capacity_kwh",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="battery capacity (kWh)",
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
                    "hours_used",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="hours used",
                    ),
                ),
                (
                    "odometer_km",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="odometer (km)",
                    ),
                ),
                (
                    "maintenance_interval_hours",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="maintenance interval (hours)",
                    ),
                ),
                (
                    "maintenance_interval_days",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="maintenance interval (days)",
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
                    "next_service_hours",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="next service hours",
                    ),
                ),
                (
                    "status",
                    ralph.lib.transitions.fields.TransitionField(
                        choices=[
                            (1, "new"),
                            (2, "staging"),
                            (3, "active"),
                            (4, "maintenance"),
                            (5, "standby"),
                            (6, "decommissioned"),
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
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="heavy_equipment_assets_as_owner",
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
                        related_name="heavy_equipment_assets_as_operator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="assigned operator",
                    ),
                ),
            ],
            options={
                "verbose_name": "Heavy equipment asset",
                "verbose_name_plural": "Heavy equipment assets",
            },
            bases=("assets.asset", models.Model),
        ),
    ]

