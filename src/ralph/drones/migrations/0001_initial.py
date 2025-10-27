import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Drone",
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
                    "identifier",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        verbose_name="Identifier",
                    ),
                ),
                ("model_name", models.CharField(max_length=128, verbose_name="Model")),
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
                        verbose_name="Type",
                    ),
                ),
                (
                    "serial_number",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Serial number",
                    ),
                ),
                (
                    "firmware_version",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Firmware version",
                    ),
                ),
                (
                    "last_firmware_update",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Last firmware update",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("operational", "Operational"),
                            ("grounded", "Grounded"),
                            ("awaiting_certification", "Awaiting Certification"),
                            ("retired", "Retired"),
                        ],
                        default="awaiting_certification",
                        max_length=32,
                        verbose_name="Status",
                    ),
                ),
                (
                    "payload_capacity_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                        verbose_name="Payload capacity (kg)",
                    ),
                ),
                (
                    "payload_description",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Payload details",
                    ),
                ),
                (
                    "flight_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=7,
                        verbose_name="Flight hours",
                    ),
                ),
                (
                    "flight_count",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Flight count",
                    ),
                ),
                (
                    "battery_cycle_count",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Battery cycle count",
                    ),
                ),
                (
                    "last_service_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Last service date",
                    ),
                ),
                (
                    "maintenance_interval_days",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Maintenance interval (days)",
                    ),
                ),
                (
                    "maintenance_interval_flight_hours",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=7,
                        null=True,
                        verbose_name="Maintenance interval (flight hours)",
                    ),
                ),
                (
                    "next_maintenance_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next maintenance date",
                    ),
                ),
                (
                    "next_maintenance_flight_hours",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=7,
                        null=True,
                        verbose_name="Next maintenance flight hours",
                    ),
                ),
                (
                    "registration_number",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Registration number",
                    ),
                ),
                (
                    "pilot_license_required",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Required pilot license",
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
                    "current_mission",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Current mission",
                    ),
                ),
                (
                    "retired_at",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Retired at",
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
                    "acquisition_cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Acquisition cost",
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
                    "assigned_team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="drones",
                        to="accounts.team",
                        verbose_name="Assigned team",
                    ),
                ),
                (
                    "assigned_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="drones",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assigned user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone",
                "verbose_name_plural": "Drones",
                "ordering": ("identifier",),
            },
        ),
        migrations.CreateModel(
            name="DroneMaintenanceLog",
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
                    "flight_hours",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=7,
                        null=True,
                        verbose_name="Flight hours at service",
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
                    "firmware_version",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Firmware version",
                    ),
                ),
                (
                    "battery_cycles",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Battery cycles",
                    ),
                ),
                (
                    "next_maintenance_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next maintenance date",
                    ),
                ),
                (
                    "next_maintenance_flight_hours",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=7,
                        null=True,
                        verbose_name="Next maintenance flight hours",
                    ),
                ),
                (
                    "drone",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maintenance_logs",
                        to="drones.drone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone maintenance log",
                "verbose_name_plural": "Drone maintenance logs",
                "ordering": ("-date", "-created"),
            },
        ),
        migrations.CreateModel(
            name="DroneStatusLog",
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
                            ("operational", "Operational"),
                            ("grounded", "Grounded"),
                            ("awaiting_certification", "Awaiting Certification"),
                            ("retired", "Retired"),
                        ],
                        max_length=32,
                        verbose_name="Previous status",
                    ),
                ),
                (
                    "new_status",
                    models.CharField(
                        choices=[
                            ("operational", "Operational"),
                            ("grounded", "Grounded"),
                            ("awaiting_certification", "Awaiting Certification"),
                            ("retired", "Retired"),
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
                    "drone",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="drones.drone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone status log entry",
                "verbose_name_plural": "Drone status log entries",
                "ordering": ("-created",),
            },
        ),
        migrations.CreateModel(
            name="DroneAssignment",
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
                    "mission",
                    models.CharField(blank=True, max_length=128, verbose_name="Mission"),
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
                        related_name="drone_assignments",
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
                        related_name="drone_assignments_created",
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
                        related_name="drone_assignments_closed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Unassigned by",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="drone_assignments",
                        to="accounts.team",
                        verbose_name="Team",
                    ),
                ),
                (
                    "drone",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="drones.drone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone assignment",
                "verbose_name_plural": "Drone assignments",
                "ordering": ("-assigned_at",),
            },
        ),
        migrations.CreateModel(
            name="DroneFlightLog",
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
                        verbose_name="Flight date",
                    ),
                ),
                (
                    "duration_minutes",
                    models.PositiveIntegerField(verbose_name="Duration (minutes)"),
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
                    "mission",
                    models.CharField(blank=True, max_length=128, verbose_name="Mission"),
                ),
                (
                    "battery_cycles_used",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Battery cycles used",
                    ),
                ),
                (
                    "operational_cost",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Operational cost",
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
                    "drone",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flight_logs",
                        to="drones.drone",
                    ),
                ),
            ],
            options={
                "verbose_name": "Drone flight log",
                "verbose_name_plural": "Drone flight logs",
                "ordering": ("-date", "-created"),
            },
        ),
    ]
