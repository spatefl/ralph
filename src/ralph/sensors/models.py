from decimal import Decimal
from datetime import date, timedelta

from collections import defaultdict

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ralph.accounts.models import Regionalizable
from ralph.assets.models.assets import (
    Asset,
    MaintenanceRecord,
    MaintenanceRecordStatus,
    MaintenanceRecordType,
)
from ralph.lib.dj_choices import Choices
from ralph.lib.lifecycle import LifecycleStatusMixin
from ralph.lib.mixins.fields import NullableCharField
from ralph.lib.mixins.models import AdminAbsoluteUrlMixin, TimeStampMixin
from ralph.lib.transitions.decorators import transition_action
from ralph.lib.transitions.fields import TransitionField


def _history_entry(kwargs, instance):
    history_kwargs = kwargs.get("history_kwargs")
    if history_kwargs is None:
        history_kwargs = kwargs["history_kwargs"] = defaultdict(dict)
    history_kwargs.setdefault(instance.pk, {})
    return history_kwargs[instance.pk]


class SensorAssetStatus(Choices):
    _ = Choices.Choice

    new = _("new")
    active = _("active")
    under_maintenance = _("under maintenance")
    faulty = _("faulty")
    retired = _("retired")


class SensorCategory(Choices):
    _ = Choices.Choice

    environmental = _("Environmental monitoring")
    security = _("Security & surveillance")
    infrastructure = _("Infrastructure & utilities")
    logistics = _("Logistics & asset tracking")
    wearable = _("Wearable / personnel support")
    other = _("Other sensors")


class SensorAsset(Regionalizable, Asset):
    _allow_in_dashboard = True

    sensor_type = models.CharField(
        max_length=64,
        verbose_name=_("sensor type"),
    )
    model_name = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("model"),
    )
    category = models.CharField(
        max_length=32,
        choices=SensorCategory(),
        default=SensorCategory.other.id,
        verbose_name=_("category"),
    )
    serial_number = NullableCharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("serial number"),
    )
    external_identifier = NullableCharField(
        max_length=128,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("external identifier"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensor_assets_as_owner",
        on_delete=models.CASCADE,
        verbose_name=_("asset owner"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sensor_assets_as_user",
        on_delete=models.CASCADE,
        verbose_name=_("assigned user"),
    )
    location_description = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("location description"),
    )
    installation_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("installation date"),
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("longitude"),
    )
    battery_level_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery level (%)"),
    )
    battery_level_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("battery threshold (%)"),
    )
    last_calibrated = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last calibrated"),
    )
    next_calibration_due = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("next calibration due"),
    )
    calibration_interval_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("calibration interval (days)"),
    )
    last_online_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("last online at"),
    )
    status = TransitionField(
        default=SensorAssetStatus.new.id,
        choices=SensorAssetStatus(),
    )
    last_status_change = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("last status change"),
    )
    total_uptime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name=_("total uptime (hours)"),
    )
    total_downtime_hours = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name=_("total downtime (hours)"),
    )
    external_feed_reference = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("external feed reference"),
    )

    class Meta:
        verbose_name = _("Sensor asset")
        verbose_name_plural = _("Sensor assets")

    def __str__(self):
        identifier = (
            self.external_identifier or self.serial_number or self.hostname or "-"
        )
        return "{} ({})".format(identifier, self.sensor_type)

    def battery_threshold(self):
        return (
            self.battery_level_threshold_percent
            if self.battery_level_threshold_percent is not None
            else Decimal("20.00")
        )

    def battery_alert_payload(self):
        if self.battery_level_percent is None:
            return None
        threshold = self.battery_threshold()
        if self.battery_level_percent <= threshold:
            return {
                "metric": "battery_level_percent",
                "value": float(self.battery_level_percent),
                "threshold": float(threshold),
            }
        return None

    def calibration_alerts(self, reference_date=None):
        reference_date = reference_date or timezone.now().date()
        today = timezone.now().date()
        alerts = []
        if (
            self.next_calibration_due
            and self.next_calibration_due <= reference_date
            and self.status != SensorAssetStatus.retired.id
        ):
            days_until = (self.next_calibration_due - today).days
            alerts.append(
                {
                    "metric": "next_calibration_due",
                    "value": self.next_calibration_due.isoformat(),
                    "threshold": reference_date.isoformat(),
                    "days_until_due": days_until,
                }
            )
        return alerts

    @classmethod
    @transition_action(
        verbose_name=_("Activate sensor"),
        form_fields={
            "user": {
                "field": forms.CharField(
                    label=_("Assigned user"),
                    required=False,
                ),
                "autocomplete_field": "user",
            },
            "location_description": {
                "field": forms.CharField(
                    label=_("Location description"),
                    required=False,
                )
            },
            "latitude": {
                "field": forms.DecimalField(
                    label=_("Latitude"),
                    required=False,
                    max_digits=9,
                    decimal_places=6,
                )
            },
            "longitude": {
                "field": forms.DecimalField(
                    label=_("Longitude"),
                    required=False,
                    max_digits=9,
                    decimal_places=6,
                )
            },
            "installation_date": {
                "field": forms.DateField(
                    label=_("Installation date"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
        },
    )
    def activate_sensor_asset(cls, instances, **kwargs):
        user = None
        user_id = kwargs.get("user")
        if user_id:
            user = get_user_model().objects.get(pk=int(user_id))
        location = kwargs.get("location_description")
        latitude = kwargs.get("latitude")
        longitude = kwargs.get("longitude")
        install_date = kwargs.get("installation_date")
        requester = kwargs.get("requester")
        performed_by = kwargs.get("performed_by")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if user is not None:
                instance.user = user
                history[_("User")] = str(user)
            if location is not None:
                instance.location_description = location or ""
                if location:
                    history[_("Location")] = location
            if latitude is not None:
                instance.latitude = latitude
                history[_("Latitude")] = float(latitude)
            if longitude is not None:
                instance.longitude = longitude
                history[_("Longitude")] = float(longitude)
            if install_date:
                instance.installation_date = install_date
                history[_("Installed on")] = install_date
            instance.status = SensorAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            MaintenanceRecord.close_open_records(
                instance,
                resolution=_("Sensor activated"),
                performed_by=performed_by or requester,
            )

    @classmethod
    @transition_action(
        verbose_name=_("Begin maintenance"),
        form_fields={
            "expected_completion": {
                "field": forms.DateField(
                    label=_("Expected completion date"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "maintenance_note": {
                "field": forms.CharField(
                    label=_("Maintenance note"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
        },
    )
    def start_sensor_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        expected = kwargs.get("expected_completion")
        note = kwargs.get("maintenance_note")
        performed_by = kwargs.get("performed_by")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if expected:
                history[_("Expected completion")] = expected
                instance.next_calibration_due = expected
            if note:
                history[_("Note")] = note
            instance.status = SensorAssetStatus.under_maintenance.id
            instance.last_status_change = timezone.now().date()
            record = MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.maintenance.id,
                status=MaintenanceRecordStatus.in_progress.id,
                description=note or "",
                expected_completion=expected,
                out_of_service=True,
                reported_by=requester,
                performed_by=performed_by,
            )
            history[_("Maintenance record")] = str(record.pk)

    @classmethod
    @transition_action(
        verbose_name=_("Complete maintenance"),
        form_fields={
            "calibrated_on": {
                "field": forms.DateField(
                    label=_("Calibrated on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "next_calibration_due": {
                "field": forms.DateField(
                    label=_("Next calibration due"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "battery_level_percent": {
                "field": forms.DecimalField(
                    label=_("Battery level (%)"),
                    required=False,
                    max_digits=5,
                    decimal_places=2,
                    min_value=0,
                    max_value=100,
                )
            },
            "maintenance_summary": {
                "field": forms.CharField(
                    label=_("Maintenance summary"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
            "performed_by": {
                "field": forms.CharField(
                    label=_("Performed by"),
                    required=False,
                )
            },
        },
    )
    def complete_sensor_maintenance(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        calibrated_on = kwargs.get("calibrated_on") or timezone.now().date()
        next_due = kwargs.get("next_calibration_due")
        battery_level = kwargs.get("battery_level_percent")
        summary = kwargs.get("maintenance_summary")
        performed_by = kwargs.get("performed_by")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Calibrated on")] = calibrated_on
            instance.last_calibrated = calibrated_on
            if next_due:
                instance.next_calibration_due = next_due
                history[_("Next calibration due")] = next_due
            if battery_level is not None:
                instance.battery_level_percent = battery_level
                history[_("Battery level (%)")] = float(battery_level)
            if summary:
                history[_("Summary")] = summary
            instance.status = SensorAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            extra = {
                "calibrated_on": calibrated_on.isoformat(),
                "next_calibration_due": next_due.isoformat() if next_due else None,
                "battery_level_percent": float(battery_level)
                if battery_level is not None
                else None,
            }
            MaintenanceRecord.close_latest(
                instance,
                record_type=MaintenanceRecordType.maintenance.id,
                resolution=summary,
                extra_data=extra,
                performed_by=performed_by or requester,
            )

    @classmethod
    @transition_action(
        verbose_name=_("Mark faulty"),
        form_fields={
            "fault_note": {
                "field": forms.CharField(
                    label=_("Fault description"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
        },
    )
    def mark_sensor_faulty(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        note = kwargs.get("fault_note")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if note:
                history[_("Fault note")] = note
            instance.status = SensorAssetStatus.faulty.id
            instance.last_status_change = timezone.now().date()
            record = MaintenanceRecord.start_record(
                base_object=instance,
                record_type=MaintenanceRecordType.repair.id,
                status=MaintenanceRecordStatus.open.id,
                description=note or "",
                out_of_service=True,
                reported_by=requester,
            )
            history[_("Maintenance record")] = str(record.pk)

    @classmethod
    @transition_action(
        verbose_name=_("Restore sensor"),
        form_fields={
            "note": {
                "field": forms.CharField(
                    label=_("Restoration note"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            }
        },
    )
    def restore_sensor_asset(cls, instances, **kwargs):
        requester = kwargs.get("requester")
        note = kwargs.get("note")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            if note:
                history[_("Note")] = note
            instance.status = SensorAssetStatus.active.id
            instance.last_status_change = timezone.now().date()
            MaintenanceRecord.close_open_records(
                instance,
                record_type=MaintenanceRecordType.repair.id,
                resolution=note or _("Sensor restored"),
                performed_by=requester,
            )

    @classmethod
    @transition_action(
        verbose_name=_("Retire sensor"),
        form_fields={
            "retired_on": {
                "field": forms.DateField(
                    label=_("Retired on"),
                    required=False,
                    widget=forms.TextInput(attrs={"class": "datepicker"}),
                )
            },
            "retirement_reason": {
                "field": forms.CharField(
                    label=_("Retirement reason"),
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            },
        },
    )
    def retire_sensor_asset(cls, instances, **kwargs):
        retired_on = kwargs.get("retired_on") or timezone.now().date()
        reason = kwargs.get("retirement_reason")
        requester = kwargs.get("requester")
        for instance in instances:
            history = _history_entry(kwargs, instance)
            history[_("Retired on")] = retired_on
            if reason:
                history[_("Reason")] = reason
            instance.status = SensorAssetStatus.retired.id
            instance.last_status_change = retired_on
            instance.user = None
            instance.owner = None
            instance.location_description = ""
            instance.latitude = None
            instance.longitude = None
            MaintenanceRecord.close_open_records(
                instance,
                resolution=reason or _("Sensor retired"),
                performed_by=requester,
            )


class SensorAssetCategoryManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return self.model.filtered_queryset(queryset)

    @classmethod
    def filtered_queryset(cls, queryset):
        category = cls.sensor_category_filter
        if not category:
            return queryset
        return queryset.filter(category=category)


class SensorAssetCategoryProxyMixin:
    sensor_category_filter = None
    objects = SensorAssetCategoryManager()


class EnvironmentalSensorAsset(SensorAssetCategoryProxyMixin, SensorAsset):
    sensor_category_filter = SensorCategory.environmental.id

    class Meta:
        proxy = True
        verbose_name = _("Environmental sensor")
        verbose_name_plural = _("Environmental sensors")


class SecuritySensorAsset(SensorAssetCategoryProxyMixin, SensorAsset):
    sensor_category_filter = SensorCategory.security.id

    class Meta:
        proxy = True
        verbose_name = _("Security sensor")
        verbose_name_plural = _("Security sensors")


class InfrastructureSensorAsset(SensorAssetCategoryProxyMixin, SensorAsset):
    sensor_category_filter = SensorCategory.infrastructure.id

    class Meta:
        proxy = True
        verbose_name = _("Infrastructure sensor")
        verbose_name_plural = _("Infrastructure sensors")


class LogisticsSensorAsset(SensorAssetCategoryProxyMixin, SensorAsset):
    sensor_category_filter = SensorCategory.logistics.id

    class Meta:
        proxy = True
        verbose_name = _("Logistics & tracking sensor")
        verbose_name_plural = _("Logistics & tracking sensors")


class WearableSensorAsset(SensorAssetCategoryProxyMixin, SensorAsset):
    sensor_category_filter = SensorCategory.wearable.id

    class Meta:
        proxy = True
        verbose_name = _("Wearable support sensor")
        verbose_name_plural = _("Wearable support sensors")


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
