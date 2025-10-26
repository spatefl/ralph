from decimal import Decimal
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.lib.lifecycle import LifecycleStatusMixin
from ralph.lib.mixins.models import AdminAbsoluteUrlMixin, TimeStampMixin


class SensorQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=SensorStatus.INSTALLED_ACTIVE)

    def due_for_calibration(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return self.filter(
            Q(next_calibration_due__isnull=False, next_calibration_due__lte=reference_date)
        )


class SensorStatus(models.TextChoices):
    INSTALLED_ACTIVE = "installed_active", _("Installed / Active")
    MAINTENANCE = "maintenance_calibrating", _("Maintenance / Calibrating")
    FAULTY = "faulty", _("Faulty")
    RETIRED = "retired", _("Retired")


class Sensor(LifecycleStatusMixin, AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    name = models.CharField(
        max_length=128,
        verbose_name=_("Name"),
    )
    sensor_type = models.CharField(
        max_length=64,
        verbose_name=_("Type"),
    )
    model_name = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Model"),
    )
    serial_number = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_("Serial number"),
    )
    status = models.CharField(
        max_length=32,
        choices=SensorStatus.choices,
        default=SensorStatus.INSTALLED_ACTIVE,
        verbose_name=_("Status"),
    )
    installation_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Installation date"),
    )
    location_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location description"),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
    )
    last_calibrated = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Last calibrated"),
    )
    next_calibration_due = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next calibration due"),
    )
    calibration_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Calibration interval (days)"),
    )
    acquisition_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Acquisition date"),
    )
    acquisition_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Acquisition cost"),
    )
    total_maintenance_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total maintenance cost"),
    )
    total_operational_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total operational cost"),
    )
    last_online_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last online at"),
    )
    total_uptime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name=_("Total uptime (hours)"),
    )
    total_downtime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name=_("Total downtime (hours)"),
    )
    warranty_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Warranty expiration"),
    )
    service_contract_expiration = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Service contract expiration"),
    )
    cost_center = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Cost center"),
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensors",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned user"),
    )
    retired_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Retired at"),
    )

    STATUS_TRANSITIONS = {
        SensorStatus.INSTALLED_ACTIVE: {
            SensorStatus.MAINTENANCE,
            SensorStatus.FAULTY,
            SensorStatus.RETIRED,
        },
        SensorStatus.MAINTENANCE: {
            SensorStatus.INSTALLED_ACTIVE,
            SensorStatus.FAULTY,
            SensorStatus.RETIRED,
        },
        SensorStatus.FAULTY: {SensorStatus.MAINTENANCE, SensorStatus.RETIRED},
        SensorStatus.RETIRED: set(),
    }

    objects = SensorQuerySet.as_manager()

    class Meta:
        verbose_name = _("Sensor")
        verbose_name_plural = _("Sensors")
        ordering = ("name",)

    def __str__(self):
        return "{} ({})".format(self.name, self.serial_number)

    def pre_status_change(self, old_status, new_status, user, note="", metadata=None):
        metadata = metadata or {}
        updates = []
        if new_status in {SensorStatus.FAULTY, SensorStatus.RETIRED}:
            if self.assigned_user_id:
                self.assigned_user = None
                updates.append("assigned_user")
        if new_status == SensorStatus.RETIRED:
            self.retired_at = metadata.get("retired_at", date.today())
            updates.append("retired_at")
        if metadata.get("next_calibration_due"):
            self.next_calibration_due = metadata["next_calibration_due"]
            updates.append("next_calibration_due")
        return updates

    def create_status_log(self, user, old_status, new_status, note="", metadata=None):
        SensorStatusLog.objects.create(
            sensor=self,
            previous_status=old_status,
            new_status=new_status,
            changed_by=user,
            note=note,
            metadata=metadata or {},
        )

    def assign_to(
        self,
        user=None,
        location="",
        latitude=None,
        longitude=None,
        assigned_by=None,
        note="",
    ):
        if self.status == SensorStatus.RETIRED:
            raise ValidationError(_("Cannot assign a retired sensor."))
        with transaction.atomic():
            SensorAssignment.close_open_assignments(self, assigned_by)
            SensorAssignment.objects.create(
                sensor=self,
                assignee=user,
                location=location or "",
                latitude=latitude,
                longitude=longitude,
                assigned_by=assigned_by,
                note=note,
            )
            update_fields = []
            if user is not None or self.assigned_user_id:
                self.assigned_user = user
                update_fields.append("assigned_user")
            if location is not None:
                self.location_description = location or ""
                update_fields.append("location_description")
            if latitude is not None:
                self.latitude = latitude
                update_fields.append("latitude")
            if longitude is not None:
                self.longitude = longitude
                update_fields.append("longitude")
            if update_fields:
                update_fields.append("modified")
                self.save(update_fields=update_fields)

    def unassign(self, unassigned_by=None, note=""):
        if (
            not self.assigned_user
            and not self.location_description
            and self.latitude is None
            and self.longitude is None
        ):
            return False
        with transaction.atomic():
            SensorAssignment.close_open_assignments(self, unassigned_by, note=note)
            self.assigned_user = None
            self.location_description = ""
            self.latitude = None
            self.longitude = None
            self.save(
                update_fields=[
                    "assigned_user",
                    "location_description",
                    "latitude",
                    "longitude",
                    "modified",
                ]
            )
        return True

    def is_calibration_overdue(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        return bool(
            self.next_calibration_due
            and self.next_calibration_due <= reference_date
        )

    @property
    def total_cost_of_ownership(self):
        cost = Decimal(self.acquisition_cost or 0)
        return cost + Decimal(self.total_maintenance_cost) + Decimal(
            self.total_operational_cost
        )


class SensorStatusLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    sensor = models.ForeignKey(
        Sensor,
        related_name="status_logs",
        on_delete=models.CASCADE,
    )
    previous_status = models.CharField(
        max_length=32,
        choices=SensorStatus.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=32,
        choices=SensorStatus.choices,
        verbose_name=_("New status"),
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Changed by"),
    )
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Sensor status log entry")
        verbose_name_plural = _("Sensor status log entries")
        ordering = ("-created",)

    def __str__(self):
        return "{}: {} → {}".format(self.sensor, self.previous_status, self.new_status)


class SensorMaintenanceResult(models.TextChoices):
    PASSED = "passed", _("Passed")
    FAILED = "failed", _("Failed")
    NOT_APPLICABLE = "not_applicable", _("Not applicable")


class SensorMaintenanceLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    sensor = models.ForeignKey(
        Sensor,
        related_name="maintenance_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Maintenance date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    result = models.CharField(
        max_length=32,
        choices=SensorMaintenanceResult.choices,
        default=SensorMaintenanceResult.PASSED,
        verbose_name=_("Result"),
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cost"),
    )
    technician = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Technician"),
    )
    reference = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Reference / ticket"),
    )
    next_calibration_due = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Next calibration due"),
    )

    class Meta:
        verbose_name = _("Sensor maintenance log")
        verbose_name_plural = _("Sensor maintenance logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.sensor, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sensor = self.sensor
        updates = set()
        if self.result != SensorMaintenanceResult.FAILED:
            sensor.last_calibrated = self.date
            updates.add("last_calibrated")
        if self.next_calibration_due:
            sensor.next_calibration_due = self.next_calibration_due
            updates.add("next_calibration_due")
        elif sensor.calibration_interval_days:
            sensor.next_calibration_due = self.date + timedelta(
                days=sensor.calibration_interval_days
            )
            updates.add("next_calibration_due")
        if updates:
            updates.add("modified")
            sensor.save(update_fields=list(updates))

        aggregates = sensor.maintenance_logs.aggregate(total_cost=Sum("cost"))
        total_cost = aggregates.get("total_cost") or Decimal("0.00")
        if sensor.total_maintenance_cost != total_cost:
            sensor.total_maintenance_cost = total_cost
            sensor.save(update_fields=["total_maintenance_cost", "modified"])


class SensorAssignment(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    sensor = models.ForeignKey(
        Sensor,
        related_name="assignments",
        on_delete=models.CASCADE,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensor_assignments",
        on_delete=models.SET_NULL,
        verbose_name=_("Assignee"),
    )
    location = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Location"),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensor_assignments_created",
        on_delete=models.SET_NULL,
        verbose_name=_("Assigned by"),
    )
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensor_assignments_closed",
        on_delete=models.SET_NULL,
        verbose_name=_("Unassigned by"),
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Sensor assignment")
        verbose_name_plural = _("Sensor assignments")
        ordering = ("-assigned_at",)

    def __str__(self):
        target = self.assignee or self.location or "-"
        return "{} → {}".format(self.sensor, target)

    @classmethod
    def close_open_assignments(cls, sensor, user=None, note=""):
        assignments = (
            cls.objects.select_for_update()
            .filter(sensor=sensor, unassigned_at__isnull=True)
        )
        now = timezone.now()
        for assignment in assignments:
            assignment.unassigned_at = now
            assignment.unassigned_by = user
            if note:
                assignment.note = (
                    assignment.note + "\n" if assignment.note else ""
                ) + note
            assignment.save(
                update_fields=["unassigned_at", "unassigned_by", "note", "modified"]
            )


class SensorUptimeLog(AdminAbsoluteUrlMixin, TimeStampMixin, models.Model):
    sensor = models.ForeignKey(
        Sensor,
        related_name="uptime_logs",
        on_delete=models.CASCADE,
    )
    date = models.DateField(default=timezone.now, verbose_name=_("Log date"))
    hours_online = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=0,
        verbose_name=_("Hours online"),
    )
    hours_offline = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=0,
        verbose_name=_("Hours offline"),
    )
    operational_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Operational cost"),
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Recorded by"),
    )

    class Meta:
        verbose_name = _("Sensor uptime log")
        verbose_name_plural = _("Sensor uptime logs")
        ordering = ("-date", "-created")

    def __str__(self):
        return "{} – {}".format(self.sensor, self.date)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sensor = self.sensor
        aggregates = sensor.uptime_logs.aggregate(
            total_online=Sum("hours_online"),
            total_offline=Sum("hours_offline"),
            total_cost=Sum("operational_cost"),
        )
        sensor.total_uptime_hours = aggregates.get("total_online") or 0
        sensor.total_downtime_hours = aggregates.get("total_offline") or 0
        total_cost = aggregates.get("total_cost") or Decimal("0.00")
        sensor.total_operational_cost = total_cost
        updates = {
            "total_uptime_hours",
            "total_downtime_hours",
            "total_operational_cost",
            "modified",
        }
        if self.hours_online and self.hours_online > 0:
            sensor.last_online_at = timezone.now()
            updates.add("last_online_at")
        sensor.save(update_fields=list(updates))
