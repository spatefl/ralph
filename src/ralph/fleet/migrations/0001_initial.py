import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Vehicle",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "created",
                    models.DateTimeField(auto_now_add=True, verbose_name="date created"),
                ),
                (
                    "modified",
                    models.DateTimeField(auto_now=True, verbose_name="last modified"),
                ),
                (
                    "vin",
                    models.CharField(max_length=17, unique=True, verbose_name="VIN"),
                ),
                (
                    "license_plate",
                    models.CharField(
                        max_length=32,
                        unique=True,
                        verbose_name="License plate",
                    ),
                ),
                ("make", models.CharField(max_length=64, verbose_name="Make")),
                (
                    "model_name",
                    models.CharField(max_length=64, verbose_name="Model"),
                ),
                (
                    "year",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1900),
                            django.core.validators.MaxValueValidator(2100),
                        ],
                        verbose_name="Year",
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
                        verbose_name="Fuel type",
                    ),
                ),
                (
                    "seating_capacity",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Seating capacity",
                    ),
                ),
                (
                    "cargo_capacity_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        verbose_name="Cargo capacity (kg)",
                    ),
                ),
                (
                    "telematics_id",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Telematics ID",
                    ),
                ),
                (
                    "odometer_km",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Odometer (km)",
                    ),
                ),
                (
                    "average_fuel_consumption",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        verbose_name="Fuel consumption (L/100km)",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ordered", "Ordered / Purchased"),
                            ("in_service", "In Service"),
                            ("under_maintenance", "Under Maintenance"),
                            ("decommissioned", "Decommissioned"),
                        ],
                        default="ordered",
                        max_length=32,
                        verbose_name="Status",
                    ),
                ),
                (
                    "assigned_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fleet_vehicles",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assigned user",
                    ),
                ),
                (
                    "assigned_location",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Assigned location",
                    ),
                ),
                (
                    "acquisition_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Acquisition date",
                    ),
                ),
                (
                    "purchase_cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Purchase cost",
                    ),
                ),
                (
                    "depreciation_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        verbose_name="Depreciation rate (%)",
                    ),
                ),
                (
                    "total_maintenance_cost",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                        verbose_name="Total maintenance cost",
                    ),
                ),
                (
                    "total_operational_cost",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                        verbose_name="Total operational cost",
                    ),
                ),
                (
                    "warranty_expiration",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Warranty expiration",
                    ),
                ),
                (
                    "service_contract_expiration",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Service contract expiration",
                    ),
                ),
                (
                    "cost_center",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Cost center",
                    ),
                ),
                (
                    "maintenance_interval_days",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Service interval (days)",
                    ),
                ),
                (
                    "maintenance_interval_km",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Service interval (km)",
                    ),
                ),
                (
                    "next_service_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next service date",
                    ),
                ),
                (
                    "next_service_odometer",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Next service odometer (km)",
                    ),
                ),
                (
                    "decommissioned_at",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Decommissioned at",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vehicle",
                "verbose_name_plural": "Vehicles",
                "ordering": ("make", "model_name", "license_plate"),
            },
        ),
        migrations.CreateModel(
            name="VehicleMaintenanceLog",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date created"
                    ),
                ),
                (
                    "modified",
                    models.DateTimeField(auto_now=True, verbose_name="last modified"),
                ),
                (
                    "date",
                    models.DateField(
                        default=django.utils.timezone.now,
                        verbose_name="Maintenance date",
                    ),
                ),
                (
                    "description",
                    models.CharField(max_length=255, verbose_name="Description"),
                ),
                (
                    "mileage_km",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Odometer at service (km)",
                    ),
                ),
                (
                    "cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Cost",
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Reference / ticket",
                    ),
                ),
                (
                    "performed_by",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Performed by",
                    ),
                ),
                (
                    "next_service_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next service date",
                    ),
                ),
                (
                    "next_service_odometer",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Next service odometer (km)",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maintenance_logs",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vehicle maintenance log",
                "verbose_name_plural": "Vehicle maintenance logs",
                "ordering": ("-date", "-created"),
            },
        ),
        migrations.CreateModel(
            name="VehicleStatusLog",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date created"
                    ),
                ),
                (
                    "modified",
                    models.DateTimeField(auto_now=True, verbose_name="last modified"),
                ),
                (
                    "previous_status",
                    models.CharField(
                        choices=[
                            ("ordered", "Ordered / Purchased"),
                            ("in_service", "In Service"),
                            ("under_maintenance", "Under Maintenance"),
                            ("decommissioned", "Decommissioned"),
                        ],
                        max_length=32,
                        verbose_name="Previous status",
                    ),
                ),
                (
                    "new_status",
                    models.CharField(
                        choices=[
                            ("ordered", "Ordered / Purchased"),
                            ("in_service", "In Service"),
                            ("under_maintenance", "Under Maintenance"),
                            ("decommissioned", "Decommissioned"),
                        ],
                        max_length=32,
                        verbose_name="New status",
                    ),
                ),
                ("note", models.TextField(blank=True)),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Changed by",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vehicle status log entry",
                "verbose_name_plural": "Vehicle status log entries",
                "ordering": ("-created",),
            },
        ),
        migrations.CreateModel(
            name="VehicleAssignment",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date created"
                    ),
                ),
                (
                    "modified",
                    models.DateTimeField(auto_now=True, verbose_name="last modified"),
                ),
                (
                    "location",
                    models.CharField(blank=True, max_length=128, verbose_name="Location"),
                ),
                (
                    "assigned_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "unassigned_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("note", models.TextField(blank=True)),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vehicle_assignments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assignee",
                    ),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vehicle_assignments_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assigned by",
                    ),
                ),
                (
                    "unassigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vehicle_assignments_closed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Unassigned by",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vehicle assignment",
                "verbose_name_plural": "Vehicle assignments",
                "ordering": ("-assigned_at",),
            },
        ),
        migrations.CreateModel(
            name="VehicleUsageLog",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date created"
                    ),
                ),
                (
                    "modified",
                    models.DateTimeField(auto_now=True, verbose_name="last modified"),
                ),
                (
                    "date",
                    models.DateField(
                        default=django.utils.timezone.now,
                        verbose_name="Usage date",
                    ),
                ),
                (
                    "odometer_km",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Odometer reading (km)",
                    ),
                ),
                (
                    "distance_km",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        verbose_name="Distance (km)",
                    ),
                ),
                (
                    "fuel_volume_l",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        verbose_name="Fuel used (L)",
                    ),
                ),
                (
                    "fuel_cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Fuel cost",
                    ),
                ),
                ("note", models.TextField(blank=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Recorded by",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usage_logs",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vehicle usage log",
                "verbose_name_plural": "Vehicle usage logs",
                "ordering": ("-date", "-created"),
            },
        ),
    ]
