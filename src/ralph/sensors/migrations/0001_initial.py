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
            name="Sensor",
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
                ("name", models.CharField(max_length=128, verbose_name="Name")),
                (
                    "sensor_type",
                    models.CharField(max_length=64, verbose_name="Type"),
                ),
                (
                    "model_name",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Model",
                    ),
                ),
                (
                    "serial_number",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        verbose_name="Serial number",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("installed_active", "Installed / Active"),
                            ("maintenance_calibrating", "Maintenance / Calibrating"),
                            ("faulty", "Faulty"),
                            ("retired", "Retired"),
                        ],
                        default="installed_active",
                        max_length=32,
                        verbose_name="Status",
                    ),
                ),
                (
                    "installation_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Installation date",
                    ),
                ),
                (
                    "location_description",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Location description",
                    ),
                ),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="Latitude",
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="Longitude",
                    ),
                ),
                (
                    "last_calibrated",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Last calibrated",
                    ),
                ),
                (
                    "next_calibration_due",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next calibration due",
                    ),
                ),
                (
                    "calibration_interval_days",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Calibration interval (days)",
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
                    "last_online_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Last online at",
                    ),
                ),
                (
                    "total_uptime_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total uptime (hours)",
                    ),
                ),
                (
                    "total_downtime_hours",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=10,
                        verbose_name="Total downtime (hours)",
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
                    "retired_at",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Retired at",
                    ),
                ),
                (
                    "assigned_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensors",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assigned user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor",
                "verbose_name_plural": "Sensors",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="SensorMaintenanceLog",
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
                    "result",
                    models.CharField(
                        choices=[
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("not_applicable", "Not applicable"),
                        ],
                        default="passed",
                        max_length=32,
                        verbose_name="Result",
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
                    "technician",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Technician",
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
                    "next_calibration_due",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Next calibration due",
                    ),
                ),
                (
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maintenance_logs",
                        to="sensors.sensor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor maintenance log",
                "verbose_name_plural": "Sensor maintenance logs",
                "ordering": ("-date", "-created"),
            },
        ),
        migrations.CreateModel(
            name="SensorAssignment",
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
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                    ),
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
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensor_assignments_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assigned by",
                    ),
                ),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensor_assignments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Assignee",
                    ),
                ),
                (
                    "unassigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensor_assignments_closed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Unassigned by",
                    ),
                ),
                (
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments",
                        to="sensors.sensor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor assignment",
                "verbose_name_plural": "Sensor assignments",
                "ordering": ("-assigned_at",),
            },
        ),
        migrations.CreateModel(
            name="SensorUptimeLog",
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
                        verbose_name="Log date",
                    ),
                ),
                (
                    "hours_online",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=6,
                        verbose_name="Hours online",
                    ),
                ),
                (
                    "hours_offline",
                    models.DecimalField(
                        decimal_places=1,
                        default=0,
                        max_digits=6,
                        verbose_name="Hours offline",
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
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="uptime_logs",
                        to="sensors.sensor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor uptime log",
                "verbose_name_plural": "Sensor uptime logs",
                "ordering": ("-date", "-created"),
            },
        ),
        migrations.CreateModel(
            name="SensorStatusLog",
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
                            ("installed_active", "Installed / Active"),
                            ("maintenance_calibrating", "Maintenance / Calibrating"),
                            ("faulty", "Faulty"),
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
                            ("installed_active", "Installed / Active"),
                            ("maintenance_calibrating", "Maintenance / Calibrating"),
                            ("faulty", "Faulty"),
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
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="sensors.sensor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sensor status log entry",
                "verbose_name_plural": "Sensor status log entries",
                "ordering": ("-created",),
            },
        ),
    ]
